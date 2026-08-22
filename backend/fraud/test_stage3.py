"""Stage 3 — Scam-Network Graph tests.

Covers:
- GraphNode and GraphEdge model creation, constraints, str
- Graph service: rebuild_graph, update_incremental, detect_anomalies
- Graph service: graph_overview, node_neighbors
- Graph tasks: rebuild_fraud_graph, update_graph_incremental
- Graph API endpoints: overview, nodes, edges, anomalies
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from audit.models import AuditLogEntry
from fraud.models import GraphEdge, GraphNode

User = get_user_model()


def _make_user(username="testuser", role="tenant", **kwargs):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="test12345",
        role=role,
        **kwargs,
    )


def _make_room(owner, title="Room", area="Mirpur"):
    from rooms.models import Room

    return Room.objects.create(
        owner=owner,
        title=title,
        description="test",
        room_type="single",
        price=8000,
        area=area,
        address="test addr",
        lat=23.8,
        lng=90.4,
        size_sqft=200,
    )


# ---------------------------------------------------------------------------
# GraphNode model tests
# ---------------------------------------------------------------------------


class GraphNodeModelTests(TestCase):
    def test_create_user_node(self):
        node = GraphNode.objects.create(
            entity_type=GraphNode.EntityType.USER,
            entity_id="42",
            label="alice",
        )
        self.assertEqual(node.entity_type, "user")
        self.assertEqual(node.entity_id, "42")
        self.assertEqual(node.label, "alice")
        self.assertEqual(node.risk_score, 0)
        self.assertIsNone(node.community_id)
        self.assertEqual(node.metadata, {})

    def test_create_room_node(self):
        node = GraphNode.objects.create(
            entity_type=GraphNode.EntityType.ROOM,
            entity_id="99",
            label="Room 99",
        )
        self.assertEqual(node.entity_type, "room")

    def test_unique_constraint(self):
        from django.db import IntegrityError

        GraphNode.objects.create(entity_type="user", entity_id="1")
        with self.assertRaises(IntegrityError):
            GraphNode.objects.create(entity_type="user", entity_id="1")

    def test_str(self):
        node = GraphNode.objects.create(entity_type="user", entity_id="5", risk_score=75)
        self.assertIn("user:5", str(node))
        self.assertIn("75", str(node))


# ---------------------------------------------------------------------------
# GraphEdge model tests
# ---------------------------------------------------------------------------


class GraphEdgeModelTests(TestCase):
    def setUp(self):
        self.n1 = GraphNode.objects.create(entity_type="user", entity_id="1", label="alice")
        self.n2 = GraphNode.objects.create(entity_type="user", entity_id="2", label="bob")

    def test_create_edge(self):
        edge = GraphEdge.objects.create(
            source=self.n1,
            target=self.n2,
            edge_type="phone",
            strength="strong",
            weight=1.0,
            evidence={"phone_hash": "171***"},
        )
        self.assertEqual(edge.edge_type, "phone")
        self.assertEqual(edge.strength, "strong")
        self.assertEqual(edge.weight, 1.0)
        self.assertEqual(edge.evidence["phone_hash"], "171***")

    def test_unique_constraint(self):
        from django.db import IntegrityError

        GraphEdge.objects.create(source=self.n1, target=self.n2, edge_type="phone")
        with self.assertRaises(IntegrityError):
            GraphEdge.objects.create(source=self.n1, target=self.n2, edge_type="phone")

    def test_different_edge_types_allowed(self):
        GraphEdge.objects.create(source=self.n1, target=self.n2, edge_type="phone")
        GraphEdge.objects.create(source=self.n1, target=self.n2, edge_type="ip")
        self.assertEqual(GraphEdge.objects.count(), 2)

    def test_str(self):
        edge = GraphEdge.objects.create(
            source=self.n1, target=self.n2, edge_type="phone", weight=0.8
        )
        s = str(edge)
        self.assertIn("phone", s)
        self.assertIn("0.8", s)


# ---------------------------------------------------------------------------
# Graph service: rebuild_graph
# ---------------------------------------------------------------------------


class RebuildGraphTests(TestCase):
    def test_empty_graph(self):
        from fraud.services.graph import rebuild_graph

        result = rebuild_graph()
        self.assertEqual(result["nodes"], 0)
        self.assertEqual(result["edges"], 0)

    def test_creates_user_and_room_nodes(self):
        from fraud.services.graph import rebuild_graph

        owner = _make_user("owner1", role="landlord")
        _make_room(owner, "Room A", "Mirpur")
        result = rebuild_graph()
        self.assertGreaterEqual(result["nodes"], 2)

        user_node = GraphNode.objects.filter(entity_type="user", entity_id=str(owner.pk)).first()
        self.assertIsNotNone(user_node)
        self.assertEqual(user_node.label, "owner1")

        from rooms.models import Room

        room = Room.objects.filter(owner=owner).first()
        room_node = GraphNode.objects.filter(entity_type="room", entity_id=str(room.pk)).first()
        self.assertIsNotNone(room_node)

    def test_phone_sharing_creates_edge(self):
        from fraud.services.graph import rebuild_graph

        a = _make_user("user_a", role="landlord", phone="+8801712345678")
        b = _make_user("user_b", role="landlord", phone="+8801712345678")
        _make_room(a, "Room A", "Mirpur")
        _make_room(b, "Room B", "Mirpur")

        rebuild_graph()

        phone_edge = GraphEdge.objects.filter(edge_type="phone").first()
        self.assertIsNotNone(phone_edge)
        self.assertEqual(phone_edge.strength, "strong")
        self.assertEqual(phone_edge.weight, 1.0)

    def test_ip_sharing_creates_weak_edge(self):
        from fraud.services.graph import rebuild_graph

        a = _make_user("user_a2", role="landlord")
        b = _make_user("user_b2", role="landlord")
        _make_room(a, "Room A", "Mirpur")
        _make_room(b, "Room B", "Mirpur")

        AuditLogEntry.objects.create(actor=a, action="login", ip_address="10.0.0.1")
        AuditLogEntry.objects.create(actor=b, action="login", ip_address="10.0.0.1")

        result = rebuild_graph()
        self.assertGreater(result["new_edges"], 0)

        ip_edge = GraphEdge.objects.filter(edge_type="ip").first()
        self.assertIsNotNone(ip_edge)
        self.assertEqual(ip_edge.strength, "weak")
        self.assertEqual(ip_edge.weight, 0.6)

    def test_wipe_on_rebuild(self):
        from fraud.services.graph import rebuild_graph

        GraphNode.objects.create(entity_type="user", entity_id="999", label="stale")
        rebuild_graph()
        self.assertFalse(GraphNode.objects.filter(entity_id="999").exists())

    def test_behavioral_edge_for_owner_room(self):
        from fraud.services.graph import rebuild_graph

        owner = _make_user("owner2", role="landlord")
        _make_room(owner, "Room X", "Gulshan")
        rebuild_graph()

        beh = GraphEdge.objects.filter(edge_type="behavioral").first()
        self.assertIsNotNone(beh)
        self.assertEqual(beh.strength, "strong")

    def test_community_detection(self):
        from fraud.services.graph import rebuild_graph

        a = _make_user("comm_a", role="landlord", phone="+8801711111111")
        b = _make_user("comm_b", role="landlord", phone="+8801711111111")
        _make_room(a, "R1", "Mirpur")
        _make_room(b, "R2", "Mirpur")
        rebuild_graph()

        nodes = GraphNode.objects.filter(entity_type="user")
        communities = set(n.community_id for n in nodes if n.community_id is not None)
        self.assertEqual(len(communities), 1)

    def test_risk_score_propagation(self):
        from fraud.services.graph import rebuild_graph

        a = _make_user("risk_a", role="landlord", phone="+8801722222222")
        b = _make_user("risk_b", role="landlord", phone="+8801722222222")
        _make_room(a, "R1", "Mirpur")
        _make_room(b, "R2", "Mirpur")
        rebuild_graph()

        nodes = GraphNode.objects.filter(entity_type="user")
        for node in nodes:
            self.assertGreater(node.risk_score, 0)


# ---------------------------------------------------------------------------
# Graph service: update_incremental
# ---------------------------------------------------------------------------


class UpdateIncrementalTests(TestCase):
    def test_adds_new_room(self):
        from fraud.services.graph import rebuild_graph, update_incremental

        owner = _make_user("inc_owner", role="landlord")
        _make_room(owner, "R1", "Mirpur")
        rebuild_graph()

        count_before = GraphNode.objects.count()
        _make_room(owner, "R2", "Mirpur")
        update_incremental()

        self.assertGreater(GraphNode.objects.count(), count_before)


# ---------------------------------------------------------------------------
# Graph service: detect_anomalies
# ---------------------------------------------------------------------------


class DetectAnomaliesTests(TestCase):
    def test_no_anomalies_on_empty_graph(self):
        from fraud.services.graph import detect_anomalies

        self.assertEqual(detect_anomalies(), [])

    def test_detects_large_high_risk_community(self):
        from fraud.services.graph import (
            _compute_risk_scores,
            _detect_communities,
        )

        users = []
        for i in range(4):
            n = GraphNode.objects.create(
                entity_type="user",
                entity_id=str(i),
                label=f"user_{i}",
                risk_score=70,
                community_id=0,
            )
            users.append(n)

        for i in range(3):
            GraphEdge.objects.create(
                source=users[i],
                target=users[i + 1],
                edge_type="phone",
                strength="strong",
                weight=1.0,
            )

        _detect_communities()
        _compute_risk_scores({0: [str(u.pk) for u in users]})

        from fraud.services.graph import detect_anomalies

        anomalies = detect_anomalies()
        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0]["member_count"], 4)

    def test_ignores_small_community(self):
        n1 = GraphNode.objects.create(
            entity_type="user",
            entity_id="1",
            community_id=0,
            risk_score=80,
        )
        n2 = GraphNode.objects.create(
            entity_type="user",
            entity_id="2",
            community_id=0,
            risk_score=80,
        )
        GraphEdge.objects.create(
            source=n1,
            target=n2,
            edge_type="phone",
            strength="strong",
            weight=1.0,
        )

        from fraud.services.graph import detect_anomalies

        self.assertEqual(detect_anomalies(), [])


# ---------------------------------------------------------------------------
# Graph service: graph_overview
# ---------------------------------------------------------------------------


class GraphOverviewTests(TestCase):
    def test_empty_overview(self):
        from fraud.services.graph import graph_overview

        result = graph_overview()
        self.assertEqual(result["node_count"], 0)
        self.assertEqual(result["edge_count"], 0)
        self.assertEqual(result["community_count"], 0)
        self.assertEqual(result["high_risk_users"], 0)

    def test_populated_overview(self):
        from fraud.services.graph import graph_overview

        n1 = GraphNode.objects.create(entity_type="user", entity_id="1", risk_score=70)
        n2 = GraphNode.objects.create(entity_type="room", entity_id="2")
        GraphEdge.objects.create(source=n1, target=n2, edge_type="behavioral")

        result = graph_overview()
        self.assertEqual(result["node_count"], 2)
        self.assertEqual(result["edge_count"], 1)
        self.assertEqual(result["high_risk_users"], 1)


# ---------------------------------------------------------------------------
# Graph service: node_neighbors
# ---------------------------------------------------------------------------


class NodeNeighborsTests(TestCase):
    def test_nonexistent_node(self):
        from fraud.services.graph import node_neighbors

        result = node_neighbors(9999)
        self.assertIn("error", result)

    def test_returns_neighbors(self):
        from fraud.services.graph import node_neighbors

        n1 = GraphNode.objects.create(entity_type="user", entity_id="1", label="alice")
        n2 = GraphNode.objects.create(entity_type="user", entity_id="2", label="bob")
        GraphEdge.objects.create(
            source=n1,
            target=n2,
            edge_type="phone",
            strength="strong",
            weight=1.0,
        )

        result = node_neighbors(n1.pk)
        self.assertEqual(result["node"]["entity_id"], "1")
        self.assertEqual(len(result["neighbors"]), 1)
        self.assertEqual(result["neighbors"][0]["entity_id"], "2")
        self.assertEqual(len(result["edges"]), 1)


# ---------------------------------------------------------------------------
# Graph tasks
# ---------------------------------------------------------------------------


class GraphTaskTests(TestCase):
    def test_rebuild_fraud_graph(self):
        from fraud.tasks import rebuild_fraud_graph

        owner = _make_user("task_owner", role="landlord")
        _make_room(owner, "Task Room", "Mirpur")
        result = rebuild_fraud_graph()
        self.assertIn("nodes", result)
        self.assertIn("edges", result)
        self.assertGreater(result["nodes"], 0)

    def test_update_graph_incremental(self):
        from fraud.services.graph import rebuild_graph
        from fraud.tasks import update_graph_incremental

        owner = _make_user("inc_task_owner", role="landlord")
        _make_room(owner, "Inc R1", "Mirpur")
        rebuild_graph()

        _make_room(owner, "Inc R2", "Mirpur")
        result = update_graph_incremental()
        self.assertIn("new_nodes", result)

    def test_alert_graph_anomalies_no_alerts(self):
        from fraud.tasks import alert_graph_anomalies

        result = alert_graph_anomalies()
        self.assertEqual(result["alerted"], 0)


# ---------------------------------------------------------------------------
# Graph API endpoints
# ---------------------------------------------------------------------------


class GraphApiTests(TestCase):
    def setUp(self):
        self.admin = _make_user("admin1", role="admin", is_staff=True)
        self.tenant = _make_user("tenant1", role="tenant")
        self.client_obj = APIClient()

    def _admin(self):
        self.client_obj.force_authenticate(user=self.admin)

    def _tenant(self):
        self.client_obj.force_authenticate(user=self.tenant)

    def test_overview_admin(self):
        self._admin()
        res = self.client_obj.get("/api/v1/fraud/graph/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("node_count", res.data)

    def test_overview_forbidden(self):
        self._tenant()
        res = self.client_obj.get("/api/v1/fraud/graph/")
        self.assertEqual(res.status_code, 403)

    def test_nodes_list_admin(self):
        self._admin()
        GraphNode.objects.create(entity_type="user", entity_id="1", label="x")
        res = self.client_obj.get("/api/v1/fraud/graph/nodes/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data), 1)

    def test_nodes_list_filter(self):
        self._admin()
        GraphNode.objects.create(entity_type="user", entity_id="1", risk_score=80)
        GraphNode.objects.create(entity_type="room", entity_id="2", risk_score=10)
        res = self.client_obj.get(
            "/api/v1/fraud/graph/nodes/",
            {"entity_type": "user"},
        )
        self.assertEqual(len(res.data), 1)

    def test_edges_list_admin(self):
        self._admin()
        n1 = GraphNode.objects.create(entity_type="user", entity_id="1")
        n2 = GraphNode.objects.create(entity_type="user", entity_id="2")
        GraphEdge.objects.create(source=n1, target=n2, edge_type="phone")
        res = self.client_obj.get("/api/v1/fraud/graph/edges/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data), 1)

    def test_anomalies_admin(self):
        self._admin()
        res = self.client_obj.get("/api/v1/fraud/graph/anomalies/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data, [])

    def test_anomalies_forbidden(self):
        self._tenant()
        res = self.client_obj.get("/api/v1/fraud/graph/anomalies/")
        self.assertEqual(res.status_code, 403)

    def test_node_neighbors_admin(self):
        self._admin()
        n = GraphNode.objects.create(entity_type="user", entity_id="1")
        res = self.client_obj.get(f"/api/v1/fraud/graph/nodes/{n.pk}/neighbors/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["node"]["entity_id"], "1")

    def test_node_neighbors_404(self):
        self._admin()
        res = self.client_obj.get("/api/v1/fraud/graph/nodes/9999/neighbors/")
        self.assertEqual(res.status_code, 404)
