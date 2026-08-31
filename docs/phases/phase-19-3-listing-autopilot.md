# Phase 19.3 — AI Listing Autopilot (landlord-side)

Phase 19.0 built the guarded Agent SDK; Phase 19.1 added explainable Property
Intelligence; Phase 19.2 shipped the first tenant-facing agent. This phase
ships the **landlord-side autopilot**: a weekly Celery analysis over every
eligible listing that mints typed, reviewable **proposals** (title,
description, amenities, photos, price, renewal) which the landlord approves or
rejects individually (or in one batch). Approving applies **exactly once** and
replay-safe; rejecting frees the slot for next week.

The autopilot is deterministic-by-design: scores come from the listing-quality
and property-intelligence engines, price from the price engine, eligibility
and validity from stored state. The LLM is used **only** to improve a title or
description's wording from grounded inputs. The AI **never** self-approves.

---

## 1. Design goals & non-goals

**Grounded, never invented** — a proposal's numbers, eligibility, price
direction and stale detection are all computed deterministically from stored
listing data and the reference engines. An LLM can reword a title or
description draft, but cannot introduce facts not present in the listing, and
never computes any score/price/validity value.

**Human in control** — every proposal starts `PENDING`. Only the owning
landlord can approve (apply) or reject it. Approval is exactly-once via the
SDK's locked `apply_proposal`; rejection is permanent for that week's slot.

**No duplicates, ever** — one `ListingAnalysis` per (room, week); no duplicate
*unresolved* proposal per (room, type); the weekly task is idempotent so
beat/double-fire runs are safe; apply itself is duplicate-apply-proof.

**No-spam notifications** — exactly one batched notification per landlord per
week that produced recommendations (never one per listing).

**Non-goals** — no chat surface (this is a background analyzer, not a
conversation), no tenant access, no self-approval, no LLM for scoring/price/
permissions, no new "second engine" (Phase 19.0 SDK + 18.x registries only).

---

## 2. Hard invariants

| Invariant | Mechanism |
|-----------|-----------|
| No duplicate proposals for the same unresolved recommendation | `_existing_unresolved(room, type)` suppress (PENDING/APPROVED blocks); resolved frees the slot |
| Ladder of exactly-once apply | SDK `apply_proposal` (locked `select_for_update`, TTL, status gate) |
| Landlord writes only to their own rooms | `_check_owner_owns_room` server-side; views scope by conversation owner |
| Never clobber a newer landlord edit | per-field `stale_checks` (checksums) re-verified in the executor against the DB row |
| Sibling proposals stay independently applicable | per-field (not whole-listing) grounding: applying `PRICE` does not invalidate `TITLE` from the same snapshot |
| AI never self-approves | autopilot creates rows directly with `status="pending"`; no approve path for non-owners |
| Per-field grounding survives process boundaries | `grounding_key` computed from a fresh DB read (`Room.objects.get(pk=room.pk)`), not the in-memory engine-mutated instance |
| One failing listing never aborts the run | per-room `transaction.atomic()` in the weekly task |

---

## 3. Architecture

```
Celery beat (Mon 06:30) ──► run_weekly_autopilot (tasks.py)
                                 │  per eligible Room, transaction.atomic
                                 ▼
                       analyze_and_propose (services.py)
                         ├─ analyze_room        (analysis.py)  ──► ListingAnalysis (room, week)
                         └─ _emit_proposal      (services.py)  ──► AgentProposal PENDING
                                 │                                   (Room via 19.0 SDK)
                                 ▼
   Dashboard Insights tab ──► AutopilotPanel (React) ──► /api/v1/autopilot/*
                                 │
                                 ▼
              autopilot_approve_and_apply / autopilot_reject (services.py)
                      → SDK apply_proposal (exactly-once, tools warm via registry)
```

### New app: `listing_autopilot`

| File | Responsibility |
|------|----------------|
| `models.py` | `ListingAnalysis` — unique `(room, week_key)` snapshot; quality/property/photo/stale scores, `grounding_key`, payload JSON, summary. |
| `constants.py` | `AutopilotSettings` (live settings reads), `PROPOSAL_TYPES`, content thresholds, identity keys (agent/feature/flag/prompt). |
| `analysis.py` | Deterministic `analyze_room(room)` — reuses `get_listing_quality`, `get_property_intelligence`/`public_payload`, `listing_price_recommendation`, `generate_listing_draft`, vision `analyze_listing`; `_STALE_FIELDS`, `field_grounding`, `grounding_key`. |
| `services.py` | `analyze_and_propose` (idempotent per room+week), `_emit_proposal`, `autopilot_approve_and_apply`, `autopilot_reject`, `landlord_proposals`, `landlord_analyses`, `proposal_payload`. |
| `apply_tools.py` | 1 READ_ONLY analyze tool + 6 STATE_CHANGING apply executors, registered in the Tool Registry; every executor re-verifies owner + per-field staleness. |
| `tasks.py` | `run_weekly_autopilot` — enabled/rollout gate, per-room transaction, failure isolation, one batched notification per landlord. |
| `notifications.py` | `landlord_digest` + `notify_weekly_summary` (single `ai_alert` notification per landlord per week). |
| `views.py` | overview / proposals / analyses / approve / reject / bulk-approve — `IsAuthenticated` + `AutopilotRateThrottle` (`listing_autopilot`, 120/h). |
| `serializers.py` | `RejectSerializer`, `BulkApproveSerializer`. |
| `management/commands/register_listing_autopilot.py` | Idempotent seed: flag `ai.listing_autopilot` (disabled), feature `rentora.listing_autopilot`, prompt `rentora.listing_autopilot` (v1), agent `ai.listing_autopilot` (disabled, staff audience). |
| `tests.py` | 24 tests covering analysis, idempotency, apply, staleness, ownership, schema, API, Celery, eval hook. |

Changes to existing apps:

* `agents/tools.py` — `register_builtin_tools()` now calls
  `register_listing_autopilot_tools()` (guarded).
* `config/settings/base.py` — `INSTALLED_APPS`, `LISTING_AUTOPILOT_*`
  settings, throttle rate, Celery beat entry `run-listing-autopilot`.
* `config/urls.py` — mounts `api/v1/autopilot/`.
* `config/test_tasks.py` — asserts the new beat entry + task import.

---

## 4. Proposals & lifecycle

One `AgentProposal` (Phase 19.0 model) per actionable recommendation. The
proposal's `action` records the tool name, arguments (including the per-field
`stale_checks` dict) and a `grounding_key` for snapshot audit.

| Type | Trigger (deterministic) | Executor |
|------|-------------------------|----------|
| `TITLE_UPDATE` | title absent / description-scored too thin | set grounded draft title |
| `DESCRIPTION_UPDATE` | description below content threshold | set fuller grounded draft |
| `AMENITY_UPDATE` | key amenities missing | add common verifiable amenities |
| `PHOTO_RECOMMENDATION` | photos below minimum / no primary | advisory action (+ suggested amenities) |
| `PRICE_UPDATE` | price engine direction raise/lower + dynamic figure | set suggested price |
| `LISTING_RENEWAL` | listing stale past threshold + soft interest | advisory touch (recency) |

```
PENDING ──► APPROVED ──► APPLIED         (landlord approves; apply exactly-once)
   │             └──► FAILED             (e.g. stale_grounding, room_missing)
   ├──► REJECTED                         (frees the slot)
   └──► EXPIRED                          (SDK expire_proposals beat)
```

Apply goes through `listing.autopilot.apply.<slug>` in the Tool Registry:
`register_builtin_tools()` keeps the registry warm even though the autopilot
never runs an agent conversation (its rows are created directly on schedule).

---

## 5. API

| Endpoint | Method | Body | Notes |
|----------|--------|------|-------|
| `/api/v1/autopilot/overview/` | GET | — | `enabled`, `pending_count`, `agent` |
| `/api/v1/autopilot/proposals/` | GET | `?status=` | caller's own proposals (default pending) |
| `/api/v1/autopilot/analyses/` | GET | — | weekly snapshots (scores) |
| `/api/v1/autopilot/proposals/<key>/approve/` | POST | — | approve+apply (owner only; 403/409 mapped) |
| `/api/v1/autopilot/proposals/<key>/reject/` | POST | `{reason}` | reject (owner only) |
| `/api/v1/autopilot/proposals/bulk-approve/` | POST | `{proposal_keys: []}` | applies valid pending ones, skips invalid (reports) |

Read-mostly; the two state-changing paths reuse the SDK's locked apply. All
endpoints are `IsAuthenticated` and throttled via `listing_autopilot`.

---

## 6. Rollout & observability

* **Feature flag** `ai.listing_autopilot` created **disabled**; the seeder
  registers feature/prompt/agent rows in the Phase 18 registries so telemetry
  and eval metadata hang off the standard attribution model.
* **Staged rollout** via `LISTING_AUTOPILOT_ROLLOUT_WEEK_KEYS` (an allow-list
  of ISO week keys; empty = all) and `LISTING_AUTOPILOT_ENABLED`.
* Every `AgentProposal` references a conversation + run + tool call, so the
  18.3 eval harness and the AI dashboard see autopilot activity like any other
  agent; `create_agent_eval_run` accepts autopilot runs (`test_sdk_eval_hook_accepts_autopilot_run`).
* Audit rows (`autopilot.proposal.created`, `.self_consented`, `.rejected`)
  through `audit.services.log_action`.

---

## 7. Frontend

`src/components/AutopilotPanel/AutopilotPanel.tsx` renders inside the Dashboard
**Insights** tab (landlord-only), backed by `useListingAutopilot`
(`src/hooks/useListingAutopilot.ts`) and `listingAutopilotService`
(`src/services/listingAutopilotService.ts`). It shows the weekly summary
(pending/applied/scored), status filters, reject-with-reason, single approve &
apply, batch approve-all, and a collapsible weekly-snapshots list.

---

## 8. Testing

* Backend — 24 tests in `listing_autopilot/tests.py`.
* Frontend — `listingAutopilotService.test.ts`.
* `config/test_tasks.py` — beat entry + task name guards.
* Live smoke test: weekly task ran over 32 rooms → 25 landlords notified once;
  approve of a live proposal → `applied`; stale/`room_missing` guards verified.