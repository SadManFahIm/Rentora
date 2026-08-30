# Phase 19.2 — AI Rental Agent

Phase 19.0 built the guarded Agent SDK; Phase 19.1 added the explainable
Property Intelligence score and exposed it as a read-only agent tool. This
phase ships the first **tenant-facing agentic surface**: a conversational
**AI Rental Agent** that searches the live room catalogue, explains listings,
estimates commutes, compares prices and can request a bookmark — every answer
grounded in the platform's own data, with human review in front of any
state-changing action.

---

## 1. Design goals & non-goals

**Grounded, never invented** — the agent has no knowledge of its own. It can
only reason over what its tools return: a search result, a room card, a
commute estimate, a price comparison. Tool outputs are structured JSON that
(once sanitized by the SDK) survive into persistence and into the LLM context
verbatim; the UI renders cards read straight from that same stored payload.
If a value is unknown, the tool answers `available: false` — honestly, never
as a guess.

**Bengali-first** — prompts, schemas and API errors are written to work in
বাংলা, Banglish and English; the chat accepts any of the three.

**Dignified consent, not silent side effects** — bookmarking is the only
state-changing tool. In the SDK a tenant cannot approve their own proposal
(voting on your own action would be meaningless), so the phase applies
**token-holding self-consent**: the tenant's chat turn is itself the
authorization to act on their behalf. The UI deliberately renders *both*
stages — "awaiting approval" then "applied" — and clearly states that
approval is the manual step, so the human stays in control at all times.

**Verifiably single action** — sibling PENDING bookmark proposals for the
same owner are expired the moment one is approved, across *all* of that
user's agent conversations (not just the current thread). One tenant, one
booking intent, no duplicate Wishlist entries.

**Non-goals** — no payment handling, no booking creation, no landlord access,
no ungrounded knowledge, no persisted telemetry that isn't already the SDK's.

---

## 2. Architecture

```
React CopilotWidget ──► AiToolsPanel ──► RentalAgentPanel  (Phase 19.2 UI)
                                            │
                                            ▼
                  /api/v1/rental/chat/   POST ──► AgentSession (SDK)
                  /api/v1/rental/runs/<key>/   GET          │
                  /api/v1/rental/conversations/ GET/POST    │
                  /api/v1/rental/proposals/<key>/ approve│reject
                                            │
                 ┌──────────────────────────┴─────────────────────────┐
                 │  tools.py (6 tools)                                │
                 │   search        → grounded rooms + median/peak     │
                 │   room_details  → one room's card + badge          │
                 │   commute       → map-intel estimate (or honest no)│
                 │   price_compare → market segment + P10/P50/P90      │
                 │   area_overview → area median + trend               │
                 │   bookmark      → STATE_CHANGING proposal           │
                 └────────────────────────────────────────────────────┘
```

### New app: `rental_agent`

| File | Responsibility |
|------|----------------|
| `tools.py` | 6 tool definitions + executors; `bookmark` is `STATE_CHANGING`; `register_rental_agent_tools()` seeder (idempotent). |
| `services.py` | Ground-truth payloads: `room_card`, `room_insights`, `conversation_payload`, `_walk_messages` (attach stored cards to assistant frames), `self_consent_and_apply`, `_expire_sibling_bookmark_proposals`, suggestion chips. |
| `views.py` | `POST chat/`, `GET conversations/`, `GET conversations/<pk>/`, `GET runs/<key>/`, `POST proposals/<key>/approve|reject/` — `IsAuthenticated` + `TrustedUserRateThrottle` (`rental_agent`, 40/h). |
| `serializers.py` | `ChatRequestSerializer` (message 1–4000 chars, optional `conversation_id`), `ConsentRequestSerializer` (optional note ≤ 500). |
| `tests.py` | 42 tests: grounded-cards-only invariant, Bangla/budget free-text, consent ownership, sibling dedupe across two conversations, feature-flag gating, run lifecycle, rate limiting. |
| `management/commands/register_rental_agent.py` | Idempotent seed: feature flag `ai.rental_agent`, prompt `rentora.rental_agent` (v1), agent `ai.rental_agent`. |

### Agent configuration (seeded, flag disabled by default)

- **Feature flag** `ai.rental_agent` (off until staff enables it).
- **Prompt** `rentora.rental_agent` v1 — Bengali-first system prompt with the
  honesty contract, tool-description rules and consent flow.
- **Agent** `ai.rental_agent`, provider `llm`, model `gpt-4o-mini`,
  6 tools, `max_turns=6`, `max_tool_calls=20`, `max_tokens=4000`,
  `timeout=60s`.

The SDK resolves provider + prompt through the Phase 18 registries. With no
built-in provider configured, runs terminate with `provider_not_configured`
— the same honest failure mode as every other agent.

---

## 3. Tools

All read-only tools return `{"ok": true, "data": {...}}` or
`{"ok": false, "error": "..."}`. Domain "no data" is **not** a failure: the
tool stays `ok:true` and marks `available:false` (e.g. no room found,
lat/lng absent, segment sample too small).

| Tool | Reads | Returns |
|------|-------|---------|
| `rental_agent.search` | `copilot.services.retrieve_rooms` | `rooms[]` (grounded cards), `median_rent`, `peak_price`, `cheapest`, `total_found`, `available` |
| `rental_agent.room_details` | `rooms` + property-intelligence badge | one `room` card + `available` |
| `rental_agent.commute` | `rooms.geo` / `streets` / `landmarks` map-intel | `minutes`, `distance_km`, `estimate`, `mode`, `detail`, `origin`, `destination` |
| `rental_agent.price_compare` | `pricing.services.insight` / serializers safe payload | `segment` panel, percentile points, `overpriced`, position vs median |
| `rental_agent.area_overview` | `MarketStat` | `median_rent`, `avg_rent`, `trend`, `sample_size` (or `available:false`) |
| `rental_agent.bookmark` | `wishlist` model | `STATE_CHANGING` → `AgentProposal` (PENDING, 5-min TTL) |

The **`room` card** is the single shared shape (28 keys) used by search,
room_details, bookmark proposals and every chat message: id, title,
price_bdt + price_text + currency, area + area_display, room_type +
room_type_display, gender_preference, size_sqft, amenities[], address,
verified, featured, available, lat, lng, image, url. It is built only from
public fields (privacy first).

---

## 4. Conversation & consent flow

### Chat turns (`POST /api/v1/rental/chat/`)

- Creates a conversation on first message (`title` from the first turn),
  continues later turns (id in payload or `X-Rentora-Conversation` header).
- Runs *eagerly* (synchronously) in the request when the broker is empty;
  under a real Celery broker it returns `{"conversation_id", "run_key",
  "status", "task_id"}` and the client polls `GET /runs/<key>/`.
- `403 feature_unavailable` when the flag is off (checked *before*
  dispatching the task).

### Enriched transcript (`GET /conversations/<pk>/`)

The UI never renders the raw SDK message list. `conversation_payload`
rebuilds a tenant-safe transcript:

- `messages[]` — each with `id`, `role`, `content`, `created_at` and
  **`cards`** (the stored tool-result room cards attached to the following
  assistant text frame via `_walk_messages`).
- `proposals[]` — pinned proposals with status + room card + summary
  (`pending` → `applied/rejected/expired`).
- `suggestions[]` — quick-reply chips generated from the latest intent
  (`{label, text}`).
- `latest_run`, `agent` metadata, `feature_enabled`.

### Bookmark consent

```
bookmark tool (STATE_CHANGING)
  → self-consent granted (token-holding turn, not PROGRAMMATIC)
    → status PENDING → APPROVED ({actor, reason: "self-consent", origin: "rental-agent"})
      → _expire_sibling_bookmark_proposals (all conversations, same owner)
      → apply: Wishlist entry once (idempotent), locked proposal status → applied
```

- `POST /proposals/<key>/approve/` with `{note}` → applies the bookmark,
  returns `{"proposal_key", "status"}`.
- `POST /proposals/<key>/reject/` → marks rejected.
- Owner-only (`403 not_proposal_owner`); concurrency-safe
  (`select_for_update`); PENDING-only transitions (`409` otherwise).
- Privacy: proposal actions, notes and `reviewed_at` are rendered only to the
  owner; the sync "Apply" enforces worker isolation by never running as a
  non-staff system actor unless self-consent, and never exposes tenant notes
  to the proposal author-context of the sync worker.

---

## 5. SDK hardening this phase

Two defects surfaced while building the tenant UI and were fixed in the shared
SDK (they affect *every* agent — documented as such):

1. **Depth-truncation of structured tool results** — `_sanitized_outcome`
   nulled anything nested deeper than 4 levels. The tool-result envelope
   `{ok → data → rooms → card → fields}` died at level 4, so room cards were
   persisted as `{"id": null, …}` and the LLM received nulls (a grounding
   hazard the regression test guards against). Fix: depth limit 4 → 8 and
   dict/list item caps 50 → 200.
2. **Persistence truncation of Bangla payloads** — `_persist_message`
   truncated tool payloads at 8000 chars, but `_json_dumps` uses
   `ensure_ascii=True`, expanding বাংলা 6× — mid-JSON truncation. Fix:
   `_persist_message(limit=…)` kwarg; tool-result messages persist with
   `limit=200_000`.

New SDK regression test: `test_deep_structured_tool_result_survives_persistence`
(executor throws if the taxidermy result's cards are nulled).

---

## 6. Frontend

- **`services/rentalAgentService.ts`** — typed clients for chat, run polling,
  conversation payload, proposal approve/reject, conversations list.
- **`hooks/useRentalAgent.ts`** — conversation state machine: optimistic user
  bubble → POST chat → poll run to terminal → reload enriched payload (so
  cards/proposals/chips are always the backend snapshot). Includes
  single-flight `sending` guard, honest error banners from the API envelope,
  unmount-safe polling.
- **`components/RentalAgentPanel/RentalAgentPanel.tsx`** — chat UI inside the
  Copilot widget: EN/BN prompt examples, grounded room cards with "View"
  (opens the real RoomModal), amber **"await approval"** proposal rows with
  Approve/Reject, suggestion chips, "feature off" banner when the flag is
  disabled.
- **Mount point** — new **Rental Agent** tab (src/index of the AI Tools
  panel); the widget defaults to it and lists it in the toggle hint.

---

## 7. Engineering

- 42 new `rental_agent` tests + 1 new SDK regression test in `agents`
  (suite: rental_agent 42 OK, agents 39 OK, combined 81 OK, adjacent app
  suites 886 OK — all green).
- ruff-clean, `manage.py check` clean, frontend `tsc` strict + ESLint +
  Prettier clean.
- Seedable via `python manage.py register_rental_agent` (idempotent; flag
  ships disabled — enable in the staff feature-flag UI to go live).