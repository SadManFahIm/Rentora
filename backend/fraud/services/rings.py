"""Fraud ring detection (Phase 15 — D8).

A "ring" is a set of users whose listings look coordinated: they share a
phone number, or they acted from the same IP *and* list rooms in the same
area. Rings are a review aid for the Trust & Safety desk — never an automatic
block — surfaced as a ``fraud_ring`` signal on affected rooms and in the
admin rings endpoint.

Graph model
-----------
- Nodes: users who own at least one listing.
- Strong edge: same normalized phone (both users have a non-empty phone).
- Weak edge: both users appear in ``AuditLogEntry`` rows from the same IP and
  own at least one listing in the same area (a shared IP alone is too weak —
  NATs and office networks share IPs innocently).
- A ring is a connected component of >= 2 users under strong OR weak edges.

Every number is real platform data (``User.phone``, ``AuditLogEntry.ip_address``,
``Room.area``). Deterministic and self-hosted — no external risk scoring.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from django.utils import timezone


def _normalize_phone(phone: str) -> str:
    """Digits only, country code folded: '+880 1712…', '8801712…' and
    '01712…' all become the same 10-digit '1712…' form."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 13 and digits.startswith("880"):
        digits = digits[3:]
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits


def _users_with_phones() -> dict[int, str]:
    from django.contrib.auth import get_user_model

    User = get_user_model()
    rows = {}
    for user_id, phone in User.objects.exclude(phone="").values_list("id", "phone"):
        normalized = _normalize_phone(phone or "")
        if len(normalized) >= 6:  # too-short values are junk, not a signal
            rows[user_id] = normalized
    return rows


def _users_by_ip() -> dict[str, set[int]]:
    """Map IP -> user ids that performed sensitive actions from it."""
    from audit.models import AuditLogEntry

    by_ip: dict[str, set[int]] = defaultdict(set)
    for ip, actor_id in (
        AuditLogEntry.objects.exclude(ip_address=None)
        .exclude(actor=None)
        .values_list("ip_address", "actor_id")
    ):
        by_ip[ip].add(actor_id)
    return by_ip


def _users_with_listings() -> dict[int, set[str]]:
    """Map user id -> set of areas they list in (only users with listings)."""
    from rooms.models import Room

    by_user: dict[int, set[str]] = defaultdict(set)
    for owner_id, area in Room.objects.values_list("owner_id", "area"):
        by_user[owner_id].add(area)
    return by_user


def _build_edges() -> list[dict[str, Any]]:
    """All strong + weak edges between distinct users, with evidence."""
    edges: list[dict[str, Any]] = []

    phones = _users_with_phones()
    by_phone: dict[str, list[int]] = defaultdict(list)
    for user_id, phone in phones.items():
        by_phone[phone].append(user_id)
    for phone, members in by_phone.items():
        for i, a in enumerate(members):
            for b in members[i + 1 :]:
                edges.append(
                    {
                        "users": (a, b),
                        "strength": "strong",
                        "evidence": f"shared phone {phone}",
                    }
                )

    by_ip = _users_by_ip()
    listings = _users_with_listings()
    for ip, actors in by_ip.items():
        if len(actors) < 2:
            continue
        actors = sorted(actors)
        for i, a in enumerate(actors):
            for b in actors[i + 1 :]:
                shared_areas = set(listings.get(a, set())) & set(listings.get(b, set()))
                if not shared_areas:
                    continue
                if any(e["users"] == (a, b) or e["users"] == (b, a) for e in edges):
                    continue  # strong edge already covers this pair
                edges.append(
                    {
                        "users": (a, b),
                        "strength": "weak",
                        "evidence": f"same IP {ip} + listings in {', '.join(sorted(shared_areas))}",
                    }
                )

    return edges


def _components(edges: list[dict[str, Any]]) -> list[list[int]]:
    """Connected components of >= 2 users under the union of all edges."""
    graph: dict[int, set[int]] = defaultdict(set)
    for edge in edges:
        a, b = edge["users"]
        graph[a].add(b)
        graph[b].add(a)
    if not graph:
        return []

    seen: set[int] = set()
    components: list[list[int]] = []
    for start in sorted(graph):
        if start in seen:
            continue
        stack, component = [start], []
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            component.append(node)
            stack.extend(graph[node])
        if len(component) >= 2:
            components.append(sorted(component))
    return components


def _member_summary(user_id: int, edges: list[dict[str, Any]]) -> dict[str, Any]:
    from django.contrib.auth import get_user_model

    from rooms.models import Room

    User = get_user_model()
    try:
        user = User.objects.only(
            "id", "username", "email", "role", "nid_verified", "tenant_verified", "phone"
        ).get(pk=user_id)
    except User.DoesNotExist:
        return {"user_id": user_id, "missing": True}

    connected = {other for edge in edges for other in edge["users"] if user_id in edge["users"]}
    return {
        "user_id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "nid_verified": user.nid_verified,
        "tenant_verified": user.tenant_verified,
        "phone": user.phone,
        "connected_to": sorted(connected),
        "listings_count": Room.objects.filter(owner_id=user.id).count(),
    }


def _ring_score(component: list[int], edges: list[dict[str, Any]]) -> dict[str, Any]:
    """Ring-level collusion score (0-100) + per-member scores.

    A ring is suspicious to the degree it is *coordinated*: strong (phone)
    edges weigh more than weak (IP+area) edges, and bigger rings are more
    unusual. Score is for prioritising review, never proof of guilt.
    """
    member_set = set(component)
    ring_edges = [e for e in edges if e["users"][0] in member_set and e["users"][1] in member_set]
    strong = sum(1 for e in ring_edges if e["strength"] == "strong")
    weak = sum(1 for e in ring_edges if e["strength"] == "weak")
    n = len(component)

    score = 40 + min(30, 10 * max(0, n - 2)) + min(30, strong * 10)
    score = min(100, score)

    by_user: dict[int, int] = defaultdict(int)
    for edge in ring_edges:
        weight = 100 if edge["strength"] == "strong" else 50
        a, b = edge["users"]
        by_user[a] += weight
        by_user[b] += weight
    member_scores = {uid: min(100, by_user[uid]) for uid in component}

    return {
        "score": score,
        "strong_edges": strong,
        "weak_edges": weak,
        "member_scores": member_scores,
    }


def detect_rings() -> dict[str, Any]:
    """Compute every ring in the platform right now (pure read).

    Returns the full structure for the admin endpoint and the weekly task.
    Never persists anything — the task persists by re-scanning affected rooms
    through the normal detector pipeline.
    """
    edges = _build_edges()
    components = _components(edges)

    rings = []
    for idx, component in enumerate(components, start=1):
        pair_edges = [
            e for e in edges if e["users"][0] in set(component) and e["users"][1] in set(component)
        ]
        score = _ring_score(component, edges)
        members = [_member_summary(uid, pair_edges) for uid in component]
        from rooms.models import Room

        flagged_rooms = []
        for room in Room.objects.filter(
            owner_id__in=component, fraud_report__severity__in=["low", "medium", "high"]
        ):
            flagged_rooms.append(
                {
                    "room_id": room.pk,
                    "title": room.title,
                    "area": room.area,
                    "owner_id": room.owner_id,
                    "severity": room.fraud_report.severity,
                    "score": room.fraud_report.score,
                }
            )
        rings.append(
            {
                "ring_id": idx,
                "member_count": len(component),
                "score": score["score"],
                "strong_edges": score["strong_edges"],
                "weak_edges": score["weak_edges"],
                "member_scores": score["member_scores"],
                "members": members,
                "edges": [
                    {
                        "users": [e["users"][0], e["users"][1]],
                        "strength": e["strength"],
                        "evidence": e["evidence"],
                    }
                    for e in pair_edges
                ],
                "flagged_rooms": flagged_rooms,
            }
        )

    rings.sort(key=lambda r: r["score"], reverse=True)
    return {
        "rings": rings,
        "ring_count": len(rings),
        "user_count": sum(r["member_count"] for r in rings),
        "as_of": timezone.now().isoformat(),
        "note": (
            "Rings are linked by shared phone numbers or shared IPs + same-area "
            "listings. A ring flags accounts for priority review — it is not proof "
            "of fraud and never triggers an automatic block."
        ),
    }


def owner_ring_membership(owner) -> dict[str, Any] | None:
    """Focused check for one owner — used by the per-room detector.

    Returns the first ring membership found for this owner, or ``None`` when
    the owner is not part of any ring. Cheap (no global graph build), so it
    runs inside every ``run_scan`` without slowing the catalogue scan.
    """
    if owner is None or not getattr(owner, "pk", None):
        return None

    owner_phone = _normalize_phone(getattr(owner, "phone", "") or "")
    if len(owner_phone) >= 6:
        phones = _users_with_phones()
        peers = [uid for uid, phone in phones.items() if phone == owner_phone and uid != owner.pk]
        if peers:
            return {
                "member_count": len(peers) + 1,
                "strength": "strong",
                "evidence": f"shares phone {owner.phone} with {len(peers)} other account(s)",
                "peers": peers,
            }

    ip_peers: set[int] = set()
    for _ip, actors in _users_by_ip().items():
        if owner.pk in actors:
            ip_peers.update(a for a in actors if a != owner.pk)
    if ip_peers:
        from rooms.models import Room

        owner_areas = set(Room.objects.filter(owner_id=owner.pk).values_list("area", flat=True))
        for peer in sorted(ip_peers):
            peer_areas = set(Room.objects.filter(owner_id=peer).values_list("area", flat=True))
            if owner_areas & peer_areas:
                return {
                    "member_count": len(ip_peers) + 1,
                    "strength": "weak",
                    "evidence": f"shared IP with account #{peer} + same-area listings",
                    "peers": sorted(ip_peers),
                }
    return None
