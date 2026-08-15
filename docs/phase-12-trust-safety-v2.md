# Phase 12 — Trust & Safety V2 (Marketplace Integrity)

Rentora's trust layer used to be landlord-side only: a landlord uploads a NID/passport,
an admin reviews it, and approved owners carry the **KYC-verified** badge. Phase 12 turns
Rentora into a **two-sided marketplace integrity system** — identity, content and
behaviour on *both* sides of every transaction, with a unified admin operations center
and a complete audit trail behind every decision.

Feature-specific docs: [`TENANT_KYC.md`](TENANT_KYC.md) (12.1) ·
[`CHAT_SAFETY.md`](CHAT_SAFETY.md) (12.3).

---

## 1. Executive Summary

Phase 12 ships ten features across three pillars:

| Pillar    | Features                                                                                     |
| --------- | -------------------------------------------------------------------------------------------- |
| Identity  | Tenant KYC, verified-tenant badge                                                            |
| Content   | Photo moderation, review moderation, review spam protection                                  |
| Behaviour | Chat safety engine, report / block, dispute resolution, deposit protection, admin Trust & Safety Operations Center, audit trail |

Every user-facing action has loading / success / error / empty / permission-denied states.
Every sensitive action (KYC decision, report action, moderation decision, dispute
decision, deposit outcome) writes an audit entry and notifies the affected parties.
Existing functionality was extended — never replaced: the fraud engine, pHash pipeline,
KYC infrastructure, booking/deposit model, notification system and audit log are all
reused.

## 2. Problem

- Tenants had no way to prove they are real people, so landlords treated every inquiry
  as a possible scam.
- Chat was unmoderated: payment-redirect scams, phishing URLs and off-platform bKash
  requests could reach tenants with no warning.
- Reviews and listing photos were published instantly — no spam, duplicate-image or
  abuse protection.
- Booking disputes and security deposits had no structured workflow: "who has my
  deposit, and what happens next?" was opaque.
- Admin tooling was spread across separate panels with no single trust overview and no
  unified trail.

## 3. Goals

- **Two-sided trust** — tenants can be identity-verified, with a privacy contract as
  strict as the landlord side (landlords see only a badge, never the document).
- **Safe chat** — deterministic, high-confidence safety rules surface warnings, flag
  and block threats without deleting legitimate messages.
- **Held, not hidden** — risky reviews/photos go to a moderation queue instead of the
  public feed; nothing is silently dropped.
- **Structured conflict** — disputes get evidence, statuses, admin decisions and
  deposit outcomes that are honest about what the platform does and does not hold.
- **One operations center** — every queue, one dashboard, one audit trail.

## 4. Architecture

```
                    TRUST & SAFETY
                          |
        ┌─────────────────┼─────────────────┐
        ↓                 ↓                 ↓
    IDENTITY           CONTENT            BEHAVIOR
        |                 |                 |
   Tenant KYC        Photo Review        Chat Safety
   Landlord KYC      Review Moderation   Fraud Detection
        |                 |                 |
        └─────────────────┼─────────────────┘
                          ↓
                   RISK / TRUST LAYER
                          |
              ┌───────────┼───────────┐
              ↓           ↓           ↓
           Booking     Deposit      Dispute
              |           |           |
              └───────────┼───────────┘
                          ↓
                    ADMIN CONTROL
                          |
                   Audit / Evidence
```

New backend apps: `moderation` (photo + review moderation), `disputes` (dispute +
deposit workflow), plus a read-only audit endpoint in the existing `audit` app. Chat
report/block and tenant KYC extend the existing `chat` and `users` apps. The frontend
gains six panels: `AdminReportsPanel`, `AdminModerationPanel`, `AdminDisputesPanel`,
`AdminTrustCenter` (with `ChatSafetyFeed` + `AuditTrailTab`), `DisputesTab`
(participant side) and `TenantKycCard` (already present from 12.1).

## 5. Features

### 5.1 Tenant KYC (Phase 12.1)

- Tenants upload a NID/passport from the Dashboard (`TenantKycCard`): MIME + extension
  validation, 5 MB cap, UUID-renamed private storage under `tenant_kyc/%Y/%m/`.
- Statuses: `not_started → pending → verified | rejected | needs_review | expired`.
- Verified records carry `expires_at` (365 days) — identity verification doesn't last
  forever.
- Landlords see **only** the coarse boolean; the document, NID number and file URL
  never cross the trust boundary.

### 5.2 Verified tenant badge (Phase 12.1)

- `VerifiedTenantBadge` — "✓ Identity Verified", tooltip *"Identity verified by
  Rentora."* Deliberately **not** "safe tenant" / "guaranteed" / "creditworthy".
- Rendered in the chat header (next to the participant's name), booking requests,
  roommate matches and the tenant profile.

### 5.3 Chat safety engine (Phase 12.3)

- Every chat message is assessed with deterministic rules + URL analysis + the existing
  fraud-detector signals.
- Outcomes: LOW (allow) · MEDIUM (warning banner) · HIGH (flag + warning) ·
  CRITICAL (message blocked and replaced with a safety notice — never silently
  deleted).
- Admin feed `GET /api/v1/chat/safety/events/` exposes metadata only — never message
  content.

### 5.4 Report / block (Phase 12.4)

- Report a user, a message (anchored to the exact message), a listing or a payment
  request across 7 categories: `scam`, `harassment`, `fake_listing`, `payment_fraud`,
  `impersonation`, `spam`, `other`.
- Structured tickets: `open → under_review → waiting_for_user | escalated →
  resolved | dismissed`.
- Admin actions: review, warn, restrict, suspend, escalate, resolve, dismiss — every
  action audited (`report.*`) and both parties notified.
- Block / unblock: blocked conversations are closed **server-side** in both directions;
  the composer locks with "You blocked X — this conversation is closed."

### 5.5 Photo moderation (Phase 12.5)

- Listing and review photos run through the shared pHash pipeline on upload.
- Duplicate/reused listing photos are flagged with matched-listing evidence; a
  blank-image guard prevents false positives.
- The moderation signal deliberately never writes the source image's own hash, so the
  fraud engine's lazy-hash design is undisturbed.

### 5.6 Review moderation + spam protection (Phase 12.5)

- Deterministic risk suite on every new review: suspicious URLs, phone/email contact
  harvesting, spam phrasing, all-caps/exclamation, gibberish, cross-user duplicate
  text, review velocity.
- High-risk reviews are **held** (`pending`/`flagged`) in the moderation queue instead
  of the public list; admin approval publishes, rejection removes and notifies.
- Only reviews on real, eligible bookings can be published at all ("✓ Verified
  Booking" label is earned, never decorative).

### 5.7 Dispute resolution (Phase 12.5)

- One structured dispute per approved booking; 6 categories: `deposit`,
  `property_condition`, `booking_cancellation`, `misrepresentation`, `payment`,
  `other`.
- Evidence is participant-only (text / photo / document), IDOR-guarded — the other
  party and admins see it, nobody else.
- Status lifecycle: `open → under_review → waiting_for_tenant | waiting_for_landlord
  → escalated → resolved | rejected`, each transition audited and notified.

### 5.8 Deposit protection (Phase 12.5)

- The existing security-deposit field on bookings is extended with explicit lifecycle
  outcomes: admin decisions `release_to_landlord`, `refund_to_tenant`, or partial —
  each marks the booking deposit `released`/`refunded` and is audited.
- **Honest wording**: the platform never calls deposits "escrow" or "protected funds" —
  it states what the state is and what happens next.

### 5.9 Admin Trust & Safety Operations Center (Phase 12)

- `/dashboard?tab=trust`: overview cards aggregating tenant-KYC pending, chat-safety
  events, open reports, moderation pending/flagged, open disputes — each card opens its
  queue as a sub-tab (KYC · Chat Safety · Reports · Moderation · Disputes · Audit Trail).

### 5.10 Audit trail (Phase 12)

- Read-only admin endpoint `GET /api/v1/audit/?prefix=` over the append-only
  `AuditLogEntry` table.
- Phase 12 domains: `tenant_kyc.*`, `chat.safety.*`, `report.*`, `user.blocked`,
  `content_moderated`, `dispute.*`, `deposit.*` — actor, action, entity, timestamp,
  reason, safe metadata. No sensitive content is ever stored in the trail.

## 6. Database changes

| App        | Migration            | Change                                                                  |
| ---------- | -------------------- | ----------------------------------------------------------------------- |
| `users`    | (12.1)               | `TenantVerification` — one-to-one with `User`; status, doc type, UUID file, review note, `reviewed_at`, `expires_at` |
| `chat`     | (12.3)               | `ChatSafetyEvent` — room, sender, message, risk level, outcome, detectors, detail |
| `chat`     | (12.4)               | `Report` — reporter/target/message, category, status, decision, admin note · `UserBlock` — user + blocked user |
| `moderation` | (12.5)             | `ReviewModeration` — review FK, status, risk score, signals · `PhotoModeration` — image FK, target type, room, status, risk score, signals |
| `disputes` | (12.5)               | `Dispute` — booking FK, opener, category, description, status, decision, decision amount, resolution, timeline · `DisputeEvidence` — dispute FK, kind, content/file |
| `audit`    | (12)                 | Reuses existing `AuditLogEntry`; no schema change                        |

All migrations are additive; nothing is dropped or renamed. `Booking` gains no new
columns — deposit outcomes reuse `security_deposit_paid` plus the dispute decision.

## 7. API changes

New endpoints (all under `/api/v1/`):

- **Tenant KYC**: `GET/POST /users/tenant-kyc/` · `GET /users/tenant-kyc/pending/` ·
  `POST /users/tenant-kyc/:user_id/review/`
- **Chat safety**: `GET /chat/safety/events/` (admin)
- **Reports**: `POST /chat/reports/` · `GET /chat/reports/admin/` ·
  `POST /chat/reports/:report_id/action/` (admin)
- **Block**: `POST /chat/block/` · `GET /chat/blocked/` · `DELETE /chat/block/:user_id/`
- **Moderation**: `GET /moderation/overview/` · `GET /moderation/reviews/` ·
  `POST /moderation/reviews/:id/action/` · `GET /moderation/photos/` ·
  `POST /moderation/photos/:id/action/` (all admin for the write side)
- **Disputes**: `GET/POST /disputes/` · `GET /disputes/:id/` ·
  `POST /disputes/:id/evidence/` · `GET /disputes/admin/` ·
  `POST /disputes/admin/:id/action/` (admin)
- **Audit**: `GET /audit/?prefix=` (admin, read-only)

All admin endpoints enforce staff/role RBAC; participant endpoints enforce ownership;
evidence endpoints are IDOR-guarded (404 for non-participants).

## 8. Frontend changes

| Surface            | What changed                                                              |
| ------------------ | ------------------------------------------------------------------------- |
| `ChatWindow`       | ⋮ menu (Report user / Block / Unblock), per-message report flag, confirm-block dialog, blocked-composer state |
| `AdminReportsPanel`| Ticket queue with status tabs + Dismiss / Warn / Suspend / Escalate actions |
| `AdminModerationPanel` | Reviews ↔ Photos queue switcher, risk-signal evidence, approve/reject  |
| `AdminDisputesPanel`  | Dispute list with evidence timeline + deposit decision (release/refund) |
| `DisputesTab`      | Participant side: open a dispute on an approved booking, evidence timeline |
| `AdminTrustCenter` | Overview cards + sub-tabs + `ChatSafetyFeed` + `AuditTrailTab`            |
| `Dashboard`        | New admin tabs: `reports`, `moderation`, `disputes`, `trust`              |
| Types/services     | `moderationService`, `disputeService`, `auditService`, `chatService` report/block methods, `mapReport` / moderation / dispute mappers |

Design follows the existing dark/light design system: status pills, evidence panels,
confirmation dialogs, empty states and loading skeletons everywhere.

## 9. Security model

- **NID privacy**: documents stored privately, UUID-renamed; served only via the
  auth-gated file endpoint; 404 (not 403) for non-owners; no NID data in logs,
  analytics or public responses.
- **RBAC**: every new endpoint checks role/staff; frontend hides admin tabs from
  non-admins.
- **IDOR**: dispute detail/evidence, KYC records and document files enforce ownership —
  verified by tests.
- **Block enforcement**: server-side, both directions; the client can't send into a
  blocked conversation.
- **File uploads**: MIME + extension + size validation; moderation photos stored via
  the existing image pipeline.
- **Audit**: every admin/decision action appends to the immutable-style trail; the
  Django admin view of `AuditLogEntry` is read-only.
- **No secrets**: the repository is public — no keys, tokens or credentials are
  committed; demo seeds use safe fake data (see Rule #4 compliance in the seed script).

## 10. Admin workflow

1. **Trust Center overview** shows aggregate risk at a glance (KYC pending, chat
   safety, reports, moderation, disputes).
2. Each queue opens as a sub-tab; admins review evidence *before* deciding.
3. Decisions are confirm-dialogs with an optional note; every one writes an audit
   entry and notifies the affected party.
4. Disputes carry a deposit decision (`release_to_landlord` / `refund_to_tenant` /
   partial) that resolves the booking's deposit state.
5. The Audit Trail tab filters by prefix for a complete, read-only history.

## 11. Testing

- **Backend (473 total)**: moderation suite (15) — held-vs-published reviews,
  duplicate-image flagging, blank-image guard, admin approve/reject + audit + notify;
  disputes suite (10) — create/eligibility, evidence IDOR, state transitions, deposit
  release/refund, authorization; chat report/block suite (19) — report create,
  duplicate reports, block/unblock, admin actions, permissions; audit endpoint tests;
  all pre-existing suites unchanged and green.
- **Frontend (312 total)**: `AdminModerationPanel`, `AdminDisputesPanel`,
  `AdminTrustCenter`, `AdminReportsPanel`, `chatService`/`moderationService`/
  `disputeService`, mappers — 10 new suites.
- **Security**: IDOR, RBAC, file security and sensitive-data-exposure cases covered by
  the dispute/evidence and KYC tests.
- `tsc --noEmit`, production build, eslint, prettier and ruff all clean.

## 12. Screenshots

Captured with the existing headless-Chrome tool
(`docs/tools/capture-screenshots.mjs`, demo data seeded by
`backend/scripts/seed_phase12_demo.py`). All use fake demo data — no real NID, no
secrets. Full gallery: `docs/screenshots/tenant-kyc-upload.png`,
`tenant-kyc-pending.png`, `verified-tenant-badge.png`, `report-block.png`,
`chat-safety-feed.png`, `moderation-reviews.png`, `moderation-photos.png`,
`dispute-admin.png`, `deposit-protection.png`, `trust-center.png`, `audit-trail.png`
(all linked from the README).

## 13. Known limitations

- Chat-safety analysis is deterministic rule + URL based; no learned ML model runs
  inline (a model could be added without changing the message pipeline).
- Photo "extreme manipulation / watermark" detection beyond pHash duplicates is future
  scope — the pipeline returns a held-photo risk score, but watermark text detection is
  not implemented.
- Deposit state is represented by booking fields + dispute decisions; there is no
  third-party escrow account, and the UI is deliberately honest about that.
- Tenant KYC review is manual (like landlord KYC); an automated document-verification
  provider is a possible future integration behind the same statuses.
- Screenshot automation needs the backend + frontend dev servers running (documented in
  the tool header).

## 14. Future improvements

- **AI chat safety v2** — learned classifier over the deterministic rule outputs, with
  a human-review fallback for low-confidence cases.
- **Tenant behaviour scoring** — verified bookings / completed rentals as transparent
  trust signals (never a single misleading "score").
- **Automated KYC provider** (document verification API) behind the existing statuses,
  with manual review retained as fallback.
- **Escrow-grade deposits** — real third-party holding only if/when the financial
  infrastructure supports it; wording will be updated to match reality.
- **Phase 13** — tenant-side marketplace growth (Bangla i18n, public rent index,
  agent accounts, referral v2).
