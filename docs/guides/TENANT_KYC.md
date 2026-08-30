# Phase 12.1 — Tenant KYC (Two-Sided Trust)

Rentora's trust layer has always been landlord-side: a landlord uploads an NID/passport,
an admin reviews it, and approved owners carry the **KYC-verified** badge. Phase 12 moves
the marketplace to **two-sided trust** — tenants get the same identity-verification
infrastructure, with a privacy contract that is *stricter* on the tenant side.

## What this gives tenants

A tenant can verify their identity once (NID or passport upload) from the Dashboard. On
approval they carry an **"Identity Verified"** badge that landlords see in chat, on
roommate matches and in their booking experience — a real trust signal that their inquiry
is from a real person.

The badge is deliberately **non-misleading**:

- It only claims *identity verification passed* — it never implies "safe tenant",
  "guaranteed tenant" or "creditworthy".
- Its tooltip says exactly what it means: **"Identity verified by Rentora."**

## Privacy contract (the important part)

Landlords **never** see the document, the NID number, or any raw verification data. The
only signal that crosses the trust boundary is the coarse boolean `tenant_verified` on
public serializers (chat participants, room/roommate owner payloads, auth user payload).

- Tenant documents are stored under `tenant_kyc/%Y/%m/` and **renamed to a UUID** on
  upload, so an original filename containing an NID number never reaches storage, logs,
  or error reporting.
- Documents are only ever served through the authenticated endpoint
  `GET /api/v1/users/tenant-kyc/<user_id>/file/` — never `MEDIA_URL`. Non-owners get a
  **404** (not 403), so a guessed user id doesn't even confirm a verification exists.
- `GET /api/v1/users/tenant-kyc/` returns only the *caller's own* record.
- No NID data is logged. Audit entries record the action, the reviewer's note and the
  verification id — never the document contents or filename.

## Lifecycle & statuses

```
not_started → pending → verified | rejected | needs_review
                 ↑  (re-submit)  ↓
             rejected/expired/needs_review
```

| Status        | Meaning                                                        |
| ------------- | -------------------------------------------------------------- |
| `not_started` | No verification record yet.                                    |
| `pending`     | Document submitted, awaiting admin review.                     |
| `verified`    | Approved — badge live for 365 days (`expires_at` set).         |
| `rejected`    | Denied with a reviewer note; re-submission allowed.            |
| `needs_review`| Admin asked for a clearer document; re-submission allowed.     |
| `expired`     | A verified record past its 365-day window (lazily detected).   |

Every transition is written to the append-only audit log (`tenant_kyc.submitted`,
`tenant_kyc.approved`, `tenant_kyc.rejected`, `tenant_kyc.needs_review`) and the tenant is
notified in-app; rejections additionally get a branded transactional email with the
reviewer's note and a re-upload CTA.

## API

All endpoints under `/api/v1/users/`, all authenticated:

| Method | Path                                   | Who            | Purpose                                        |
| ------ | -------------------------------------- | -------------- | ---------------------------------------------- |
| GET    | `tenant-kyc/`                          | Owner          | My verification record (null if never started) |
| POST   | `tenant-kyc/`                          | Owner          | Submit / re-submit a document (multipart)      |
| GET    | `tenant-kyc/<user_id>/file/`           | Owner / admin  | Auth-gated document bytes (404 otherwise)      |
| GET    | `tenant-kyc/pending/`                  | Admin          | Review queue                                   |
| POST   | `tenant-kyc/<user_id>/review/`         | Admin          | `approved` \| `rejected` \| `needs_review`     |

### Upload validation (server-side)

- `doc_type` must be `nid` or `passport`.
- Content type must be JPG / PNG / WebP / PDF (mirrors the landlord KYC guardrails).
- File must be ≤ 5 MB and non-empty.
- Re-submission blocked while `pending`; blocked entirely once `verified`.
- Review requires a note for `rejected` / `needs_review` (so the tenant always knows
  what to fix).

## Badge surfaces

`User.tenant_verified` is now exposed on:

- `CustomUserDetailsSerializer` (`/api/v1/auth/user/`) — the tenant's own dashboard state.
- `ChatUserSerializer` — chat participants show the `✓ Identity Verified` mark.
- `RoomOwnerSerializer` — room + roommate-match payloads.

The frontend renders the badge via `VerifiedTenantBadge` (chat, profiles) and manages the
full lifecycle from the `TenantKycCard` on the Dashboard. Admins review tenant
applications from a new **Tenant KYC** section in the existing KYC review panel.

## Testing

`backend/users/test_tenant_kyc.py` — 28 tests covering upload validation, authorization
(owner/admin-only documents, 404-for-strangers, 403 for non-admin review), every status
transition, admin review (approve/reject/needs-review), the audit trail, the rejection
email, lazy expiry, and badge visibility. Frontend: `TenantKycCard.test.tsx`,
`VerifiedTenantBadge.test.tsx` and the extended `AdminKycPanel.test.tsx`.
