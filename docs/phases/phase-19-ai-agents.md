# Phase 19.0 — Agent SDK / Agentic AI Foundation

**Date**: August 29, 2026
**Status**: Shipped
**Scope**: The platform's first agentic-AI foundation — a guarded `agents` app with a bounded turn loop, a server-side tool-permission layer, human-review proposal lifecycle, Phase 18 provider/prompt/telemetry integration, and eager-safe Celery dispatch.

---

## Overview

Phase 19.0 builds the **Agent SDK** every later agentic phase (19.1 Property Intelligence Score → 19.2 AI Rental Agent → 19.3 Listing Autopilot) will sit on. It delivers the execution kernel, the permission and safety model, and the review operations surface:

1. **Agent registry** — `Agent` definitions (status, audience, permission ceiling, enabled tools, prompt key, provider, per-run guardrail limits), seeded by `register_agents` (feature `rentora.agent`, one disabled placeholder agent).
2. **Guarded session loop** — `AgentSession.execute()` turns a `Run` into a bounded, telemetried conversation: it resolves the provider through the Phase 18 registry, renders the system prompt through the Phase 18.2 prompt registry, and loops the model + tool calls under hard guardrails.
3. **Server-side tool permission layer** — the authoritative gate. Read-only tools execute immediately (audited); state-changing tools become proposals requiring staff approval; high-risk tools require admin approval. Proposals are concurrency-safe, idempotent, and TTL-expiring.
4. **API** — minimal public surface (catalog, own conversations/runs/messages) + an admin-only review/ops surface (`/api/v1/agents/`).
5. **Safety by construction** — no `autoretry` on the run task (never duplicate side effects), telemetry failures never break a run, mock provider is a test-only adapter that production refuses.

Everything routes model calls through `BaseProvider` + `TelemetryMixin` (`AIExecutionLog`) so the Phase 18.4 dashboards and alert rules see agent traffic for free.

---

## Models (`agents/models.py`)

| Model | Purpose | Key fields |
|-------|---------|------------|
| `Agent` | Registry entry | `key` (unique), `status` (`draft/active/paused/disabled`), `audience` (`staff/users/public`), `permission` (`viewer/operator/admin`), `feature` FK + `feature_id`, `prompt_key` (Phase 18.2), `provider`, `model_name`, `system_instructions`, `enabled_tools`, guardrail limits (`max_turns`, `max_tool_calls`, `max_tokens`, `max_cost_usd`, `timeout_seconds`), `metadata` |
| `AgentConversation` | A chat thread bound to one agent + user | `status` (`active/paused/closed`), `agent`, `user`, `title` |
| `AgentMessage` | Durable transcript | `role` (`system/user/assistant/tool`), `sequence`, `content`, `metadata` (tool_call frame), `conversation`, `run` |
| `AgentRun` | One execution | `run_key` (UUID), `status` (`pending/running/completed/terminated/failed/cancelled`), `termination_reason`, `error_message`, tokens (`input/output/total`), `estimated_cost_usd`, `turn_count`, `tool_call_count`, `consecutive_tool_failures`, `prompt_key`/`prompt_version` attribution, `provider`/`model_name`, `metadata` |
| `AgentToolCall` | Audited tool invocation | `tool_name`, `arguments` (sanitized), `permission_decision` (`read_allowed/proposed/denied`), `execution_status` (`requested/executed/proposed/denied/failed`), `result` (sanitized, depth-bounded), `error_message`, `actor`, `duration_ms` |
| `AgentProposal` | Human-review gate for state-changing calls | `proposal_key` (UUID), `status` (`pending/approved/rejected/expired/applied/failed`), `approval_required` (`any_staff/admin`), `action` (tool + arguments snapshot), `application_result`, `expires_at` (TTL), `reviewed_by/at`, `applied_by/at`, audit/notification hooks |

Proposal status flow: `pending → approved → applied` (or `rejected` / `expired`; `failed` if the apply step errored). `applied` is a **terminal, idempotent** state — replaying `apply_proposal` is a no-op that re-returns the stored result.

---

## Tool registry (`agents/tools.py`)

- **`AgentTool`** — `name`, `description`, `input_schema` (JSON Schema, jsonschema-validated), `capability` (`read_only` / `state_changing` / `high_risk`), `executor`, `audit` flag. Executor failures are wrapped into a safe `{"ok": false, "error": ...}` envelope (never raises).
- **`AgentToolRegistry`** — global registry, `register`/`get`/`all`/`verify_arguments`/`clear`.
- **Built-ins** — `rentora.info` (read-only introspection, debug-gated) plus `debug.echo` / `debug.marker` (state-changing demo tools). Debug tools register only when `AGENTS_DEBUG_TOOLS=True` or under `ENVIRONMENT=test`.

**Permission model** (server-side, authoritative — the model only *requests*):

| Tool capability | Agent permission ceiling | Verdict |
|-----------------|--------------------------|---------|
| `read_only` | any | `read_allowed` → execute + audit immediately |
| `state_changing` | `operator` / `admin` | `proposed` → proposal for staff review |
| `high_risk` | `admin` only | `proposed` → proposal requiring **admin** approval |
| denied / unregistered / not in allowlist | — | `denied` → tool failure frame |

---

## Providers (`agents/providers.py`)

Every provider subclasses `TelemetryMixin + BaseProvider` (Phase 18) under feature `rentora.agent`, so each model call writes an `AIExecutionLog` row automatically.

- **`ChatLlmProvider`** (`llm`) — OpenAI-compatible chat completions over `requests` (`AGENTS_LLM_API_BASE` / `AGENTS_LLM_API_KEY` / `AGENTS_LLM_MODEL`). Never echoes non-2xx response bodies verbatim; malformed responses become controlled `ProviderFailure`s.
- **`MockAgentProvider`** (`mock_llm`) — deterministic scripted adapter for tests/local bring-up via a `mock_plan` list (steps: `text`, `tool_call`, `pass`, `usage` with optional `cost_usd`, `error`, `raise`; ends with a `done` turn). **Explicitly refused outside `ENVIRONMENT=test` / `AGENTS_DEBUG_TOOLS=True`** — without a configured provider runs terminate with `provider_not_configured` instead of inventing answers.
- **`resolve_provider`** — selection order: agent's `provider` → `AI_AGENT_LLM_PROVIDER` setting → linked feature's default provider.

---

## Session loop (`agents/session.py`)

`AgentSession(conversation, actor).execute(run)` — **never raises**; the run always lands in `completed` / `terminated` / `failed`.

1. **Validate** — conversation active, agent active, audience check (`staff`/`users`), linked feature available.
2. **Resolve** provider (refuses mock outside test/debug).
3. **Build system prompt** — Phase 18.2 `render_prompt(prompt_key, context)`; if no active prompt version exists it falls back to the agent's inline `system_instructions` (clearing prompt attribution) rather than refusing to run; runs with neither fail fast with `agent_has_no_prompt_configured`.
4. **Loop** — bounded `while` with guardrails checked at the top of every turn:
   - turns, tool calls, tokens, **estimated cost** (exact provider-reported `cost_usd` when present, else Phase 18 `calculate_estimated_cost`), wall-clock timeout, consecutive tool failures.
   - On guardrail: terminate with a machine-readable `termination_reason` (`max_turns_exceeded`, `max_tool_calls_exceeded`, `max_tokens_exceeded`, `max_cost_exceeded`, `timeout`, `consecutive_tool_failures`) and a polite assistant message.
   - Model responses: `text` → persist assistant message and finish; `tool_call` → plan through the permission layer; `pass` (metadata-only turn) → accumulate tokens/cost and continue; unknown kinds → counted as a tool failure.
5. **Telemetry enrichment** — every model turn attaches prompt attribution + incremental estimated cost to the run's `AIExecutionLog` (`_enrich_telemetry`). Enrichment is wrapped: a failing telemetry write must never break the run.
6. **Finalize** — persist totals/status, touch conversation `last_activity_at`, fan out `notify_run_outcome` (Phase 18.4 `ai_alert` notification on failed/terminated) — all best-effort with `suppress`.
7. **Eval hook** — `create_agent_eval_run` snapshots a completed run into the Phase 18.3 evaluation layer for regression tracking.

## Proposal lifecycle (`agents/services.py`)

- `create_proposal` (session-internal), `approve_proposal`, `reject_proposal`, `apply_proposal`, `expire_proposals`.
- `approval_required="any_staff"` enforces `is_admin_user` (staff or role=admin); `"admin"` enforces a **role-level** check (`is_superuser` or `role == "admin"`) so a plain staff member cannot approve high-risk actions.
- Every transition uses `select_for_update()` rows inside `transaction.atomic`; expiry writes happen through the expiring task (never "mark-then-raise" inside an atomic block that would roll back).
- Applying a proposal executes the snapshotted tool with a context envelope (`actor`, run user/agent/conversation) and records the sanitized result; replay on an `applied` proposal returns the stored result (idempotent no-op — **never** re-executes the tool).
- All approve/reject/apply transitions are audited via `log_action` (`agent.proposal.approved/rejected/applied`).

## Tasks (`agents/tasks.py`)

| Task | Schedule | Purpose |
|------|----------|---------|
| `agents.execute_agent_run` | run-triggered (`.delay`) | Thin dispatch for one run. **No `autoretry_for`** — retrying could re-apply side effects or duplicate proposals. Contains its own idempotency guard (refuses re-running a finished run). |
| `agents.expire_proposals` | beat every 5 min (`expire-agent-proposals`) | Expire `pending`/`approved`-but-unapplied proposals past their TTL (`AGENTS_PROPOSAL_TTL_SECONDS`, default 86400). |

Eager Celery (no broker configured) executes runs synchronously — the default dev/test behavior.

## API (`/api/v1/agents/`)

Public (audience-aware catalog + own conversations):

- `GET /agents/`, `GET /agents/<key>/` — public catalog
- `POST /conversations/`, `GET /conversations/`, `GET /conversations/<id>/`
- `GET /conversations/<id>/messages/`, `GET /conversations/<id>/runs/` — owner-scoped reads

Admin (staff or role=admin; `AdminOrReadPermission`):

- Registry: `GET/POST /admin/registry/`, `GET/PATCH /admin/registry/<key>/`, `POST .../activate/`, `POST .../deactivate/`
- Ops: `GET /admin/runs/`, `GET /admin/runs/<run_key>/`, `POST /admin/runs/<run_key>/evaluate/`, `GET /admin/tool-calls/`
- Proposals: `GET /admin/proposals/`, `GET /admin/proposals/<proposal_key>/`, `POST .../approve/`, `POST .../reject/`, `POST .../apply/`

All admin views (12) derive from `AdminAPIView` (`permission_classes = [AdminOrReadPermission]`) — the earlier base-class-as-permission bug (`class X(IsAdmin, APIView)`) was corrected in this phase.

## Settings (`config/settings/base.py`, Phase 19 block)

`AGENTS_ENABLED` (master switch), `AI_AGENT_LLM_PROVIDER` (empty = no auto-runs), `AGENTS_LLM_API_BASE/KEY/MODEL/TIMEOUT_SECONDS`, default guardrail limits (`AGENTS_DEFAULT_MAX_TURNS=6`, `AGENTS_DEFAULT_MAX_TOOL_CALLS=20`, `AGENTS_DEFAULT_MAX_TOKENS=4000`, `AGENTS_DEFAULT_TIMEOUT_SECONDS=180`, `AGENTS_DEFAULT_MAX_COST_USD=2.0`), `AGENTS_MAX_CONSECUTIVE_TOOL_FAILURES=3`, `AGENTS_PROPOSAL_TTL_SECONDS=86400`, `AGENTS_CONTEXT_WINDOW_MESSAGES=40`, `AGENTS_DEBUG_TOOLS=False`. Beat task `expire-agent-proposals` added.

## Engineering

- **38 new backend tests** (1449 BE total, all green) covering: tool registry + schema validation, session loop (text-only, read-tool audit, state-changing proposal, high-risk admin ceiling, denied/unregistered tools, consecutive-failure termination, provider failure, max-cost guardrail via reported cost, provider-not-configured, mock-refused-in-production), prompt-registry attribution, proposal lifecycle (approve→apply-exactly-once + idempotent replay, no-apply-without-approval, reject, admin-only ceiling, expiry via task), telemetry row enrichment, and API flows (start conversation + send message, RBAC, proposal approve/apply via API).
- 1 new app, 6 models, 1 migration (`agents` 0001), all routes under `api/v1/agents/`.
- Rendered answer for replay protection: proposals can never become actionable after reject/expire; run task refuses to re-run finished runs; apply is idempotent.
- ruff-clean; `manage.py check` clean; full backend suite green (1449).

## Guardrails summary

| Guardrail | Default | Enforced at |
|-----------|---------|-------------|
| Max turns | 6 | top of each loop iteration |
| Max tool calls | 20 | top of each loop iteration |
| Max tokens | 4000 | top of each loop iteration |
| Max estimated cost USD | 2.00 | top of each loop iteration |
| Wall-clock timeout | 180 s | top of each loop iteration |
| Consecutive tool failures | 3 | top of each loop iteration |

Per-agent overrides win; a guardrail stop persists a `termination_reason` for the Phase 18.4 dashboards.