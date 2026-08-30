"""Seed demo data for the phase 15-19.2 screenshot run (idempotent).

* Phase 17: fraud-suspicion graph (GraphNode/GraphEdge) via the production
  upsert helpers, then community + risk scoring so the Django admin list is
  populated with a realistic scam-territory network.
* Phase 18.x: AI provider health rows for the dashboard's provider view.
* Phase 19.2: one grounded rental-agent conversation (search -> room cards ->
  bookmark consent) owned by the demo tenant, plus a pending consent proposal.

Safe to re-run: everything is a get-or-create / delete-then-recreate on rows
this script itself owns.
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta

from django.utils import timezone

from agents.models import (
    Agent,
    AgentConversation,
    AgentMessage,
    AgentProposal,
    AgentRun,
)
from ai_intelligence.models import ProviderHealth
from feature_flags.models import invalidate_cache
from rental_agent.services import room_card
from rental_agent.tools import BOOKMARK_TOOL, SEARCH_TOOL
from rooms.models import Room
from users.models import User

now = timezone.now()


def _card(room_id: int) -> dict:
    return room_card(Room.objects.get(pk=room_id))


def seed_rental_agent(tenant_email: str, room_ids: list[int], bookmark_room_id: int) -> None:
    agent = Agent.objects.get(key="ai.rental_agent")
    tenant = User.objects.get(email=tenant_email)

    AgentMessage.objects.filter(conversation__user=tenant, conversation__agent=agent).delete()
    AgentProposal.objects.filter(
        run__conversation__user=tenant, run__conversation__agent=agent
    ).delete()
    AgentRun.objects.filter(conversation__user=tenant, conversation__agent=agent).delete()
    AgentConversation.objects.filter(user=tenant, agent=agent).delete()

    cards = [_card(rid) for rid in room_ids]
    search_env = {
        "ok": True,
        "data": {
            "filters": {
                "query": "studio Mirpur",
                "areas": ["mirpur"],
                "budget_max": 22000,
                "room_type": "studio",
            },
            "rooms": cards,
            "total": len(cards),
        },
    }

    convo = AgentConversation.objects.create(agent=agent, user=tenant, title="AI Rental Agent")
    run = AgentRun.objects.create(
        run_key=uuid.uuid4(),
        conversation=convo,
        agent=agent,
        user=tenant,
        provider="mock_llm",
        model_name="gpt-4o-mini",
        prompt_key="rentora.rental_agent",
        prompt_version=1,
        status="completed",
        termination_reason="",
        turn_count=3,
        tool_call_count=2,
        started_at=now - timedelta(minutes=6),
        completed_at=now,
        duration_ms=340000,
        total_tokens=1420,
        output_tokens=900,
        estimated_cost_usd="0.0015",
    )

    def msg(role: str, content: str, sequence: int, metadata: dict | None = None) -> None:
        AgentMessage.objects.create(
            conversation=convo,
            run=run,
            role=role,
            content=content,
            sequence=sequence,
            timestamp=now - timedelta(minutes=(12 - sequence)),  # newest last
            metadata=metadata or {},
        )

    msg("user", "মিরপুরে ২২০০০ টাকার মধ্যে একটা স্টুডিও রুম দেখাও", 1)
    msg(
        "assistant",
        "",
        2,
        {
            "tool_call": {"id": "seed_tc_search", "name": SEARCH_TOOL, "arguments": {}},
            "tool_call_id": "seed_tc_search",
        },
    )
    msg("tool", json.dumps(search_env, ensure_ascii=False), 3, {"tool_call_id": "seed_tc_search"})
    msg(
        "assistant",
        "আপনার বাজেটে মিরপুরে দুটি স্টুডিও রুম পাওয়া গেছে — নিচের কার্ডে দেখুন। দুটোই ফার্নিশড ও ভেরিফাইড।",
        4,
    )
    msg(
        "assistant",
        "",
        5,
        {
            "tool_call": {
                "id": "seed_tc_bookmark",
                "name": BOOKMARK_TOOL,
                "arguments": {"room_id": bookmark_room_id},
            },
            "tool_call_id": "seed_tc_bookmark",
        },
    )
    msg(
        "tool",
        json.dumps(
            {"ok": True, "data": {"room_id": bookmark_room_id, "status": "proposed_for_consent"}},
            ensure_ascii=False,
        ),
        6,
        {"tool_call_id": "seed_tc_bookmark"},
    )
    msg(
        "assistant",
        "চাইলে “Premium Studio - Mirpur 10” রুমটা আপনার বুকমার্কে সেভ করে দিতে পারি — "
        "নিচের প্রস্তাবে Approve চাপলেই আপনার Saved listings-এ যোগ হয়ে যাবে।",
        7,
    )

    AgentProposal.objects.create(
        proposal_key=uuid.uuid4(),
        run=run,
        proposal_type=BOOKMARK_TOOL,
        title="Save room to bookmarks",
        summary=(
            "Save “Premium Studio - Mirpur 10 (Fully Furnished)” (৳22,000/mo, Mirpur) "
            "to your bookmarks. You can undo it anytime from your Saved listings."
        ),
        action={"tool": BOOKMARK_TOOL, "arguments": {"room_id": bookmark_room_id}},
        status="pending",
        approval_required="any_staff",
        expires_at=now + timedelta(hours=24),
    )

    invalidate_cache("ai.rental_agent")
    print(f"seeded rental agent conversation #{convo.pk} for {tenant.email}")


def seed_fraud_graph() -> None:
    from fraud.services.graph import _detect_communities, _upsert_edge, _upsert_node

    phone = "+8801712345678"
    host1 = _upsert_node("user", "9100000001", label="Host: Hasan", metadata={"role": "host"})
    host2 = _upsert_node("user", "9100000002", label="Host: Rakib", metadata={"role": "host"})
    tenant1 = _upsert_node(
        "user", "9100000003", label="Tenant: Nusrat", metadata={"role": "tenant"}
    )
    tenant2 = _upsert_node(
        "user", "9100000004", label="Tenant: Mahmud", metadata={"role": "tenant"}
    )
    host3 = _upsert_node("user", "9100000005", label="Host: Sharmin", metadata={"role": "host"})
    phone_node = _upsert_node("phone", phone, label="Shared phone", metadata={})

    _upsert_edge(
        host1,
        host2,
        "same_phone",
        strength="strong",
        weight=0.9,
        evidence={"phone": phone, "count": 2},
    )
    _upsert_edge(
        host1,
        tenant1,
        "same_area",
        strength="medium",
        weight=0.6,
        evidence={"area": "mirpur", "count": 2},
    )
    _upsert_edge(
        tenant1,
        tenant2,
        "same_device",
        strength="medium",
        weight=0.55,
        evidence={"device": "mock-a", "count": 2},
    )
    _upsert_edge(
        tenant2,
        host3,
        "same_area",
        strength="weak",
        weight=0.3,
        evidence={"area": "uttara", "count": 1},
    )
    _upsert_edge(
        host3,
        host1,
        "shared_iban",
        strength="strong",
        weight=0.8,
        evidence={"iban_suffix": "7890", "count": 2},
    )
    for node in (host1, host2, host3):
        _upsert_edge(
            node,
            phone_node,
            "uses_phone",
            strength="strong",
            weight=0.9,
            evidence={"phone": phone},
        )

    try:
        communities = _detect_communities()
        print(f"graph communities detected: {list(communities.items())[:4]}")
    except Exception as exc:
        print(f"community detection skipped: {exc}")
    print("fraud graph seeded")


def seed_ai_provider_health() -> None:
    rows = [
        {
            "provider": "openai",
            "feature_key": "rentora.rental_agent",
            "total_requests": 1420,
            "successful_requests": 1400,
            "failed_requests": 12,
            "timeout_requests": 8,
            "avg_latency_ms": 812,
            "p95_latency_ms": 1450,
            "p99_latency_ms": 2300,
            "total_cost_usd": "12.4820",
            "success_rate": 0.986,
            "is_healthy": True,
        },
        {
            "provider": "mock_llm",
            "feature_key": "rentora.rental_agent",
            "total_requests": 260,
            "successful_requests": 260,
            "failed_requests": 0,
            "timeout_requests": 0,
            "avg_latency_ms": 18,
            "p95_latency_ms": 42,
            "p99_latency_ms": 90,
            "total_cost_usd": "0.0000",
            "success_rate": 1.0,
            "is_healthy": True,
        },
        {
            "provider": "lingu",
            "feature_key": "rentora.transliteration",
            "total_requests": 520,
            "successful_requests": 493,
            "failed_requests": 27,
            "timeout_requests": 12,
            "avg_latency_ms": 240,
            "p95_latency_ms": 610,
            "p99_latency_ms": 1240,
            "total_cost_usd": "1.0520",
            "success_rate": 0.948,
            "is_healthy": False,
        },
    ]
    for row in rows:
        ProviderHealth.objects.update_or_create(
            provider=row["provider"],
            feature_key=row["feature_key"],
            defaults={
                **row,
                "window_start": now - timedelta(hours=24),
                "window_end": now,
            },
        )
    print(f"seeded {len(rows)} provider health rows")


if __name__ == "__main__":
    seed_rental_agent("tenant.pending@rentora.com", [90009, 15], 90009)
    seed_fraud_graph()
    seed_ai_provider_health()
    print("all demo seeds applied")
