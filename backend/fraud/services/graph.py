"""Persistent fraud graph — rebuild, incremental update, community detection.

The fraud graph stores entities (users, rooms, devices, payments) as
``GraphNode`` instances and their relationships as ``GraphEdge`` instances.

1. Full rebuild (weekly): wipes the graph and rebuilds from scratch.
2. Incremental update (every 6 hours): adds new entities/edges only.
3. Community detection: connected-component BFS on the persistent graph.
4. Risk propagation: node score = max edge weight in community, scaled.

All functions are pure business logic — they read/write Django models
but have no HTTP or Celery dependencies.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from django.db import transaction
from django.utils import timezone

from audit.models import AuditLogEntry

logger = logging.getLogger(__name__)


def _normalize_phone(phone: str) -> str:
    """Digits-only, country-code folded."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 13 and digits.startswith("880"):
        digits = digits[3:]
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits


def _upsert_node(
    entity_type: str,
    entity_id: str,
    *,
    label: str = "",
    metadata: dict | None = None,
):
    """Get or create a GraphNode and update mutable fields."""
    from fraud.models import GraphNode

    node, created = GraphNode.objects.get_or_create(
        entity_type=entity_type,
        entity_id=str(entity_id),
        defaults={"label": label, "metadata": metadata or {}},
    )
    if not created:
        update_fields: list[str] = ["last_seen"]
        if label and node.label != label:
            node.label = label
            update_fields.append("label")
        if metadata:
            merged = {**node.metadata, **metadata}
            if merged != node.metadata:
                node.metadata = merged
                update_fields.append("metadata")
        node.save(update_fields=update_fields)
    return node


def _upsert_edge(
    source,
    target,
    edge_type: str,
    *,
    strength: str = "weak",
    weight: float = 0.5,
    evidence: dict | None = None,
):
    """Get or create a GraphEdge and update mutable fields."""
    from fraud.models import GraphEdge

    edge, created = GraphEdge.objects.get_or_create(
        source=source,
        target=target,
        edge_type=edge_type,
        defaults={
            "strength": strength,
            "weight": weight,
            "evidence": evidence or {},
        },
    )
    if not created:
        update_fields: list[str] = ["last_seen"]
        if strength and edge.strength != strength:
            edge.strength = strength
            update_fields.append("strength")
        if weight != edge.weight:
            edge.weight = weight
            update_fields.append("weight")
        if evidence:
            merged = {**edge.evidence, **evidence}
            if merged != edge.evidence:
                edge.evidence = merged
                update_fields.append("evidence")
        edge.save(update_fields=update_fields)
    return edge


def _detect_communities() -> dict[int, list[str]]:
    """Find connected components and assign community IDs.

    Returns {community_id: [node_pk, ...]} for communities with >= 2
    members. Isolated nodes get community_id=None.
    """
    from fraud.models import GraphEdge, GraphNode

    adjacency: dict[int, set[int]] = defaultdict(set)
    all_node_ids: set[int] = set()

    for src_id, tgt_id in GraphEdge.objects.values_list("source_id", "target_id"):
        adjacency[src_id].add(tgt_id)
        adjacency[tgt_id].add(src_id)
        all_node_ids.add(src_id)
        all_node_ids.add(tgt_id)

    if not all_node_ids:
        return {}

    seen: set[int] = set()
    communities: dict[int, list[str]] = {}
    community_idx = 0

    for start in sorted(all_node_ids):
        if start in seen:
            continue
        stack = [start]
        component: list[str] = []
        while stack:
            node_id = stack.pop()
            if node_id in seen:
                continue
            seen.add(node_id)
            component.append(str(node_id))
            stack.extend(adjacency.get(node_id, set()))
        if len(component) >= 2:
            communities[community_idx] = sorted(component)
            community_idx += 1

    node_id_to_community: dict[int, int] = {}
    for cid, members in communities.items():
        for nid_str in members:
            node_id_to_community[int(nid_str)] = cid

    bulk = []
    for node in GraphNode.objects.filter(pk__in=seen):
        new_cid = node_id_to_community.get(node.pk)
        if node.community_id != new_cid:
            node.community_id = new_cid
            bulk.append(node)

    if bulk:
        GraphNode.objects.bulk_update(bulk, ["community_id"], batch_size=500)

    return communities


def _compute_risk_scores(communities: dict[int, list[str]]) -> None:
    """Propagate risk: node risk = max edge weight, scaled by community size."""
    from fraud.models import GraphEdge, GraphNode

    max_weight: dict[int, float] = defaultdict(float)
    for src_id, tgt_id, weight in GraphEdge.objects.values_list("source_id", "target_id", "weight"):
        max_weight[src_id] = max(max_weight[src_id], weight)
        max_weight[tgt_id] = max(max_weight[tgt_id], weight)

    community_sizes: dict[int, int] = {}
    for cid, members in communities.items():
        community_sizes[cid] = len(members)

    bulk = []
    for node in GraphNode.objects.all():
        base = max_weight.get(node.pk, 0.0)
        cid = node.community_id
        size_factor = 1.0
        if cid is not None and cid in community_sizes:
            size_factor = min(2.0, 1.0 + 0.15 * (community_sizes[cid] - 2))
        new_score = min(100, int(base * 100 * size_factor))
        if node.risk_score != new_score:
            node.risk_score = new_score
            bulk.append(node)

    if bulk:
        GraphNode.objects.bulk_update(bulk, ["risk_score"], batch_size=500)


def rebuild_graph() -> dict[str, Any]:
    """Wipe and rebuild the entire fraud graph from platform data.

    Sources: phone sharing, audit-log IP sharing, user->room ownership.
    Returns a summary dict with counts for logging and the Celery task.
    """
    from fraud.models import GraphEdge, GraphNode
    from rooms.models import Room

    logger.info("graph.rebuild: starting full graph rebuild")

    with transaction.atomic():
        GraphEdge.objects.all().delete()
        GraphNode.objects.all().delete()

        owners: dict[int, str] = {}
        for owner_id, username in Room.objects.values_list(
            "owner_id", "owner__username"
        ).distinct():
            owners[owner_id] = username or f"user-{owner_id}"
        for uid, uname in owners.items():
            _upsert_node("user", str(uid), label=uname)

        rooms = list(Room.objects.select_related("owner").all())
        for room in rooms:
            _upsert_node("room", str(room.pk), label=room.title)

        for room in rooms:
            src = _upsert_node("user", str(room.owner_id))
            tgt = _upsert_node("room", str(room.pk))
            _upsert_edge(src, tgt, "behavioral", strength="strong", weight=1.0)

        from django.contrib.auth import get_user_model

        User = get_user_model()
        phone_map: dict[str, list[int]] = defaultdict(list)
        for user_id, phone in User.objects.exclude(phone="").values_list("id", "phone"):
            norm = _normalize_phone(phone or "")
            if len(norm) >= 6:
                phone_map[norm].append(user_id)

        edge_count = 0
        for phone, members in phone_map.items():
            if len(members) < 2:
                continue
            for i, a in enumerate(members):
                for b in members[i + 1 :]:
                    src = _upsert_node("user", str(a))
                    tgt = _upsert_node("user", str(b))
                    _upsert_edge(
                        src,
                        tgt,
                        "phone",
                        strength="strong",
                        weight=1.0,
                        evidence={"phone_hash": phone[:3] + "***"},
                    )
                    edge_count += 1

        by_ip: dict[str, set[int]] = defaultdict(set)
        for ip, actor_id in (
            AuditLogEntry.objects.exclude(ip_address=None)
            .exclude(actor=None)
            .values_list("ip_address", "actor_id")
        ):
            by_ip[ip].add(actor_id)

        owner_areas: dict[int, set[str]] = defaultdict(set)
        for owner_id, area in Room.objects.values_list("owner_id", "area"):
            owner_areas[owner_id].add(area or "")

        for ip, actors in by_ip.items():
            if len(actors) < 2:
                continue
            actors_list = sorted(actors)
            for i, a in enumerate(actors_list):
                for b in actors_list[i + 1 :]:
                    shared = owner_areas.get(a, set()) & owner_areas.get(b, set())
                    if not shared:
                        continue
                    src = _upsert_node("user", str(a))
                    tgt = _upsert_node("user", str(b))
                    _upsert_edge(
                        src,
                        tgt,
                        "ip",
                        strength="weak",
                        weight=0.6,
                        evidence={"ip": ip, "shared_areas": sorted(shared)},
                    )
                    edge_count += 1

        communities = _detect_communities()
        _compute_risk_scores(communities)

    result = {
        "nodes": GraphNode.objects.count(),
        "edges": GraphEdge.objects.count(),
        "communities": len(communities),
        "new_edges": edge_count,
    }
    logger.info("graph.rebuild: finished -- %s", result)
    return result


def update_incremental() -> dict[str, Any]:
    """Add new entities since last update. Much cheaper than full rebuild."""
    from django.contrib.auth import get_user_model

    from fraud.models import GraphEdge, GraphNode
    from rooms.models import Room

    logger.info("graph.incremental: starting incremental update")

    existing_user_ids = set(
        GraphNode.objects.filter(entity_type="user").values_list("entity_id", flat=True)
    )
    existing_room_ids = set(
        GraphNode.objects.filter(entity_type="room").values_list("entity_id", flat=True)
    )

    new_nodes = 0

    for room in Room.objects.all():
        if str(room.pk) not in existing_room_ids:
            _upsert_node("room", str(room.pk), label=room.title)
            _upsert_node("user", str(room.owner_id))
            src = _upsert_node("user", str(room.owner_id))
            tgt = GraphNode.objects.get(entity_type="room", entity_id=str(room.pk))
            _upsert_edge(src, tgt, "behavioral", strength="strong", weight=1.0)
            new_nodes += 1

    User = get_user_model()
    all_owner_ids = set(Room.objects.values_list("owner_id", flat=True).distinct())
    for uid in all_owner_ids:
        if str(uid) not in existing_user_ids:
            try:
                user = User.objects.get(pk=uid)
                _upsert_node("user", str(uid), label=user.username)
                new_nodes += 1
            except User.DoesNotExist:
                pass

    last_edge = GraphEdge.objects.order_by("-last_seen").first()
    since = last_edge.last_seen if last_edge else timezone.now() - timezone.timedelta(hours=12)
    new_ips: dict[str, set[int]] = defaultdict(set)
    for ip, actor_id in (
        AuditLogEntry.objects.filter(created_at__gte=since)
        .exclude(ip_address=None)
        .exclude(actor=None)
        .values_list("ip_address", "actor_id")
    ):
        new_ips[ip].add(actor_id)

    owner_areas: dict[int, set[str]] = defaultdict(set)
    for owner_id, area in Room.objects.values_list("owner_id", "area"):
        owner_areas[owner_id].add(area or "")

    new_edges = 0
    for ip, actors in new_ips.items():
        if len(actors) < 2:
            continue
        actors_list = sorted(actors)
        for i, a in enumerate(actors_list):
            for b in actors_list[i + 1 :]:
                shared = owner_areas.get(a, set()) & owner_areas.get(b, set())
                if not shared:
                    continue
                src = _upsert_node("user", str(a))
                tgt = _upsert_node("user", str(b))
                _upsert_edge(
                    src,
                    tgt,
                    "ip",
                    strength="weak",
                    weight=0.6,
                    evidence={"ip": ip, "shared_areas": sorted(shared)},
                )
                new_edges += 1

    communities = _detect_communities()
    _compute_risk_scores(communities)

    result = {
        "new_nodes": new_nodes,
        "new_edges": new_edges,
        "communities": len(communities),
    }
    logger.info("graph.incremental: finished -- %s", result)
    return result


def detect_anomalies() -> list[dict[str, Any]]:
    """Find communities that look like scam rings.

    Anomaly: community with >= 3 user nodes and at least one risk_score >= 60.
    For alerting only, never auto-blocks.
    """
    from fraud.models import GraphNode

    anomalies: list[dict[str, Any]] = []

    user_nodes = GraphNode.objects.filter(entity_type="user", community_id__isnull=False)
    by_community: dict[int, list] = defaultdict(list)
    for node in user_nodes:
        by_community[node.community_id].append(node)

    for cid, members in by_community.items():
        if len(members) < 3:
            continue
        high_risk = [n for n in members if n.risk_score >= 60]
        if not high_risk:
            continue
        anomalies.append(
            {
                "community_id": cid,
                "member_count": len(members),
                "high_risk_count": len(high_risk),
                "max_risk_score": max(n.risk_score for n in members),
                "member_ids": [n.entity_id for n in members],
                "member_labels": [n.label for n in members],
            }
        )

    anomalies.sort(key=lambda a: a["max_risk_score"], reverse=True)
    return anomalies


def graph_overview() -> dict[str, Any]:
    """Summary stats for the admin graph dashboard."""
    from fraud.models import GraphEdge, GraphNode

    node_count = GraphNode.objects.count()
    edge_count = GraphEdge.objects.count()
    user_count = GraphNode.objects.filter(entity_type="user").count()
    room_count = GraphNode.objects.filter(entity_type="room").count()
    community_count = (
        GraphNode.objects.filter(entity_type="user", community_id__isnull=False)
        .values("community_id")
        .distinct()
        .count()
    )
    high_risk_users = GraphNode.objects.filter(entity_type="user", risk_score__gte=60).count()

    return {
        "node_count": node_count,
        "edge_count": edge_count,
        "user_count": user_count,
        "room_count": room_count,
        "community_count": community_count,
        "high_risk_users": high_risk_users,
    }


def node_neighbors(node_id: int) -> dict[str, Any]:
    """Get all adjacent nodes and edges for a given graph node."""
    from fraud.models import GraphEdge, GraphNode

    try:
        node = GraphNode.objects.get(pk=node_id)
    except GraphNode.DoesNotExist:
        return {"error": "Node not found"}

    outgoing = GraphEdge.objects.filter(source=node).select_related("target")
    incoming = GraphEdge.objects.filter(target=node).select_related("source")

    neighbors = []
    edges = []
    seen_ids: set[int] = set()

    for edge in outgoing:
        neighbor = edge.target
        if neighbor.pk not in seen_ids:
            seen_ids.add(neighbor.pk)
            neighbors.append(
                {
                    "id": neighbor.pk,
                    "entity_type": neighbor.entity_type,
                    "entity_id": neighbor.entity_id,
                    "label": neighbor.label,
                    "risk_score": neighbor.risk_score,
                }
            )
        edges.append(
            {
                "id": edge.pk,
                "edge_type": edge.edge_type,
                "strength": edge.strength,
                "weight": edge.weight,
                "source_id": edge.source_id,
                "target_id": edge.target_id,
                "evidence": edge.evidence,
            }
        )

    for edge in incoming:
        neighbor = edge.source
        if neighbor.pk not in seen_ids:
            seen_ids.add(neighbor.pk)
            neighbors.append(
                {
                    "id": neighbor.pk,
                    "entity_type": neighbor.entity_type,
                    "entity_id": neighbor.entity_id,
                    "label": neighbor.label,
                    "risk_score": neighbor.risk_score,
                }
            )
        edges.append(
            {
                "id": edge.pk,
                "edge_type": edge.edge_type,
                "strength": edge.strength,
                "weight": edge.weight,
                "source_id": edge.source_id,
                "target_id": edge.target_id,
                "evidence": edge.evidence,
            }
        )

    return {
        "node": {
            "id": node.pk,
            "entity_type": node.entity_type,
            "entity_id": node.entity_id,
            "label": node.label,
            "risk_score": node.risk_score,
            "community_id": node.community_id,
        },
        "neighbors": neighbors,
        "edges": edges,
    }
