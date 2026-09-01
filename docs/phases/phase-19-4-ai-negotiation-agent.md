# Phase 19.4 — AI Negotiation Agent (bidirectional rent negotiation)

Phase 19.0 built the guarded Agent SDK; Phase 19.1 added explainable Property
Intelligence; Phase 19.2 shipped the tenant-facing Rental Agent; Phase 19.3
added the landlord-side Listing Autopilot. This phase ships the
**Negotiation Agent**: a bidirectional, peer-aware chat agent that helps
both tenants and landlords negotiate rent through a structured,
consent-gated workflow.

The agent lives in its own `negotiation_agent` app with 9 negotiation states,
8 tool permissions (3 tiers), a one-to-one conversation model per party, and
a proposal lifecycle that never bypasses explicit human consent. The AI
**never** books or makes payments autonomously.

---

## 1. Design goals & non-goals

**Bidirectional, peer-aware** — both tenant and landlord interact with the
agent. The agent sees only the negotiating party's context and never leaks
private data from the other side.

**Consent before action** — every price offer or binding action flows through
the Agent SDK's proposal card. The user must click Approve before the agent
sends the offer. Accept, reject, withdraw, and finalize all require explicit
human consent — the agent cannot self-approve.

**No autonomous booking or payment** — finalize produces a handoff message
suggesting next steps; it never triggers a booking or payment flow.

**Non-goals** — no chat between parties (both talk to the agent, not each
other), no multi-offer auctions, no autonomous booking, no payment processing,
no duplicate of existing tools (reuses `room.by_id`, `price.compare`,
`property.intelligence`).

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Frontend (React)                     │
│  NegotiationPanel ← useNegotiationAgent ← negService    │
│  Dashboard "negotiations" tab (all roles)                │
│  AiToolsPanel "negotiate" tab (contextual)               │
└───────────────┬─────────────────────────────────────────┘
                │ POST /api/v1/negotiation/chat/
                │ GET  /api/v1/negotiation/negotiations/
                │ GET  /api/v1/negotiation/conversations/
                │ POST /api/v1/negotiation/consent/<key>/approve|reject/
                └──────────────────┬──────────────────────┘
                                   ▼
┌──────────────────────────────────────────────────────────┐
│                negotiation_agent (Django)                 │
│  NegotiationMessage  ── OneToOne ──  ChatRoom            │
│  NegotiationOffer    (draft → review → sent → accepted)  │
│  AgentProposal       (SDK consent cards)                  │
│                                                          │
│  Views:                                                  │
│    NegotiationChatView       (creates + continues)       │
│    NegotiationConversationListView                        │
│    NegotiationConversationDetailView                      │
│    NegotiationDetailView                                  │
│    NegotiationConsentView (approve / reject)              │
│    NegotiationRejectView / CancelView / WithdrawView      │
│    NegotiationOfferRejectView                             │
└──────────────────────────────────────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────────────────────┐
│               Agent SDK (Phase 19.0)                     │
│  AgentSession → agent.run(turns=6, tools=8, budget=300)  │
│  Tools: READ_ONLY (2) + STATE_CHANGING (4) + HIGH_RISK (2) │
│  Reused: room.by_id, price.compare, property.intelligence │
│                                                          │
│  Consent: proposal-card approval for every agent action;  │
│           self-consent for participant-owned actions      │
└──────────────────────────────────────────────────────────┘
```

---

## 3. Negotiation states

| State | Meaning |
|-------|---------|
| `initiated` | Negotiation created (tenant → room owner); landlord can respond |
| `active` | Acknowledged; agent can draft offers for the acting party |
| `offer_pending` | An offer has been sent to the peer awaiting a decision |
| `counter_offer_pending` | A counter-offer is pending |
| `accepted` | Peer accepted the offer; finalize available |
| `rejected` | One party rejected the negotiation; terminal |
| `expired` | Negotiation / offer window elapsed; terminal |
| `cancelled` | Initiator cancelled; terminal |
| `closed` | Finalized; terminal |

Terminal states are immutable (`accepted`/`rejected`/`expired`/`cancelled`/
`closed`); legal moves are enforced by a server-side transition table, never
by the LLM.

## 4. Tool permission tiers

The agent uses **8 negotiation tools** (3 tiers) plus reused `room.by_id`,
`price.compare`, `property.intelligence`:

| Tool | Tier | Description |
|------|------|-------------|
| `negotiation.context` | READ_ONLY | Participant-scoped snapshot: listing card, price insight, PI badge, offers, the acting party's OWN boundaries, recent peer chat. **Never** the counterparty's private constraints |
| `negotiation.history` | READ_ONLY | Auditable event timeline |
| `negotiation.set_boundary` | STATE_CHANGING | Record the acting user's own explicit bounds (private per party) |
| `negotiation.create_offer` | STATE_CHANGING | Draft a rent offer (DRAFT — not sent) |
| `negotiation.counter_offer` | STATE_CHANGING | Draft a counter offer (DRAFT) |
| `message.send` | STATE_CHANGING | Post a drafted offer into the real tenant↔landlord chat thread (its OWN approval) |
| `negotiation.accept` | HIGH_RISK | Accept the peer's outstanding SENT offer (never books/pays) |
| `negotiation.finalize` | HIGH_RISK | Close an ACCEPTED negotiation + booking hand-off (never books) |

Empty cells above are not tools — the 8 are exactly the negotiation-specific
ones above; `room.by_id` / `price.compare` / `property.intelligence` are reused
from earlier phases (no duplication).

## 5. Consent model

- **Draft ≠ send** — every STATE_CHANGING tool creates a human-review proposal
  first (SDK `apply_proposal`, self-consent for participant-owned actions);
  the user approves it in chat before anything is applied.
- **Agent creates offer** → DRAFT, no peer impact → user approves → offer is
  sent → peer sees it in the real chat thread.
- **`message.send`** — requires *its own* separate approval: writing a draft
  never puts it in front of the peer.
- **Accept / finalize** (HIGH_RISK) → explicit in-chat approval required;
  never self-approves; neither ever books or creates a payment/deposit.
- **Reject / withdraw / cancel** are plain-user API actions (not agent tools),
  scoped to participants.

## 6. Frontend

- **`negotiationAgentService.ts`** — API client (types, chat, list, detail,
  conversation list/detail, run poll, consent, reject/cancel/withdraw/offer
  reject endpoints)
- **`useNegotiationAgent`** — hook mirroring `useRentalAgent` (conversation
  resume via `resolveBoundConversation`, 1500ms polling, run state, send/approve/
  reject/withdraw/rejectOffer actions)
- **`NegotiationPanel`** — summary card (status, room, peer, price range,
  offers with withdraw/reject/accept-via-chat, timeline toggle), message
  scroll, consent cards, suggestion chips, chat input, negotiation rail
  (dashboard only, when no `roomId`)
- **Dashboard "negotiations" tab** — all roles; deep-link via
  `/dashboard?tab=negotiations`
- **AiToolsPanel "negotiate" tab** — contextual (when `listingId` is set);
  legacy `NegotiateTab` removed

---

## 7. Seeding

```bash
python manage.py register_negotiation_agent
```

Registers flag `ai.negotiation_agent` (disabled by default), prompt
`rentora.negotiation_agent` v1, agent `ai.negotiation_agent` in the Phase 18
registries. Idempotent — safe to run repeatedly.

---

## 8. API endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/negotiation/chat/` | authenticated | Create or continue a negotiation conversation |
| GET | `/api/v1/negotiation/negotiations/` | authenticated | List own negotiations |
| GET | `/api/v1/negotiation/negotiations/<key>/` | participant | Negotiation detail |
| GET | `/api/v1/negotiation/conversations/` | authenticated | List own negotiation conversations |
| GET | `/api/v1/negotiation/conversations/<key>/` | participant | Enriched transcript + cards |
| GET | `/api/v1/negotiation/runs/<key>/` | participant | Run status poll |
| POST | `/api/v1/negotiation/consent/<key>/approve/` | owner | Approve a proposal |
| POST | `/api/v1/negotiation/consent/<key>/reject/` | owner | Reject a proposal |
| POST | `/api/v1/negotiation/negotiations/<key>/reject/` | participant | Reject the negotiation |
| POST | `/api/v1/negotiation/negotiations/<key>/cancel/` | participant | Cancel the negotiation |
| POST | `/api/v1/negotiation/offers/<key>/reject/` | participant | Reject a specific offer |
| POST | `/api/v1/negotiation/offers/<key>/withdraw/` | sender | Withdraw own offer |

---

## 9. Engineering

- **Backend** — 53 new `negotiation_agent` tests across 10 test classes
  (API, consent flow, context tools, creation, expiry, hallucination guard,
  seeding, state machine, tool registration, user actions), ruff-clean, 92
  combined backend tests (negotiation_agent + agents) green
- **Frontend** — 27 new tests across 3 files (`negotiationAgentService.test.ts`
  (8), `useNegotiationAgent.test.tsx` (8), `NegotiationPanel.test.tsx` (11));
  449 frontend tests total all green; TS strict + ESLint + Prettier clean;
  production build clean
- **Bugfix** — fixed pre-existing flaky `api.test.ts` timeout (mocked bare
  `axios.post` in refresh interceptor test); exported `UseNegotiationAgentReturn`
  type from hook

---

## 10. Security

- Peer isolation: each party sees only their own conversation history and
  negotiation context; no cross-party data leakage
- Self-consent pattern: the user's own chat turn is the authorization for
  agent-initiated actions (same proven pattern as Phase 19.2)
- HIGH_RISK tools (`negotiation.finalize`) require explicit approval card
- Feature flag disabled by default; agent not active until seeded
- All writes throttled (120/h), all reads throttled (300/h)
- Audit logging on all state transitions
