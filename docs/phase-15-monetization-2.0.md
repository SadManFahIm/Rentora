# Phase 15 — Monetization 2.0 (Revenue) — Implementation Plan

> **Naming note:** the previous release shipped as "Phase 15 — Communication & Trust AI".
> This spec is titled "Phase 15: Monetization 2.0" by the product owner. This document
> uses the spec's label verbatim; release history keeps both entries. Branch:
> `feat/phase-15-monetization-2`.

## 1. Goal

Turn Rentora from a one-time-revenue marketplace (listing-tier promotions only) into a
multi-sided monetization platform: recurring landlord SaaS, a broker network, corporate
housing, an add-on marketplace, and insurance/credit partner services — all on one
central, idempotent, audit-trailed revenue ledger with server-side entitlement
enforcement. Fully backward compatible; existing endpoints, payloads and tests must keep
passing.

## 2. Architecture decisions (modular monolith)

- **New apps** (match the existing one-app-per-domain convention):
  | App | Domain | Why separate |
  |---|---|---|
  | `subscriptions` | Recurring plans, entitlements, checkout, renewals | Reusable entitlement core for all domains |
  | `monetization` | Commission engine, `RevenueLedgerEntry`, `Payout`, admin revenue dashboard | Central money domain shared by brokers/corporate/marketplace/insurance |
  | `brokers` | Broker profile, verification, referral attribution, commissions | Tenant→broker revenue flow |
  | `corporate` | Corporate accounts, member RBAC, bulk booking, invoices | B2B domain |
  | `marketplace` | Add-on providers, services, orders, cross-sell | B2C add-on domain |
  | `partner_services` | Insurance/credit partner abstractions | External-partner domain |
- **No external deps added.** Reuse `payments` gateway (SSLCommerz/bKash), `audit.services.log_action`,
  `notifications.utils.create_notification` + `notifications.emails.send_html_email`, the
  `users` KYC auto-screen pattern, and the `rooms` bulk-create partial-success pattern.
- **Money discipline:** all amounts `Decimal`, computed server-side only, never from the
  client. Every revenue mutation is idempotent (unique `idempotency_key`) and audit-trailed.
- **Feature flags:** env-driven settings following the existing `os.getenv("X","True") == "True"`
  convention in `config/settings/base.py`.
- **Entitlements:** server-side only via `subscriptions.services.entitlements.check_entitlement`.
  Premium feature *downgrades gracefully* (v1 data) instead of hard-failing.

## 3. Domain model (per app)

### `subscriptions`
- `Plan` — code, name, description, `price_monthly`/`price_yearly` Decimal, `features` JSON
  (list of feature keys), `active`.
- `Subscription` — user, plan, `status` (PENDING/ACTIVE/CANCELED/EXPIRED/PAST_DUE),
  `current_period_start/end`, `auto_renew`, `cancel_at_period_end`, nullable `payment`.
- `check_entitlement(user, feature)` — active plan carries feature, else flag falls back.
- Checkout reuses `Payment` (new `payment_type=subscription`) + gateway initiate; success
  callback activates the subscription (`payments` calls `subscriptions.services.activate_on_payment`).
- Celery beat: `process_subscription_renewals` (expire/notify), `send_renewal_reminders`
  (3 days before end). One-tap `renew` via new checkout.

### `monetization`
- `CommissionRule` — scope (BROKER/CORPORATE/MARKETPLACE/INSURANCE/CREDIT), `rate` Decimal, `active`.
- `Commission` — kind, `recipient` FK user, `amount`+`rate` Decimal, `status`
  (PENDING/PAID/CANCELED), generic `reference_type/reference_id`, `idempotency_key` unique.
- `RevenueLedgerEntry` — `entry_type`, `scope`, user FK, `gross/platform/partner` Decimal,
  `currency` (BDT), generic reference, `idempotency_key` unique, `detail` JSON.
- `Payout` — recipient FK, amount, `status` (PENDING/APPROVED/PAID/REJECTED/CANCELED),
  method (bkash/nagad/bank), masked account JSON, period.
- Services: `commissions.create_commission` (idempotent), `ledger.record_entry` (idempotent),
  `payouts` (request/approve/reject/mark-paid with audit + notification).

### `brokers`
- `BrokerProfile` — user OneToOne, license no., `status` (UNVERIFIED/PENDING/VERIFIED/REJECTED/SUSPENDED),
  unique `referral_code`.
- `BrokerVerification` — profile FK, `status`, documents JSON, deterministic screen
  (mirrors `users.kyc_auto`), reviewed_by.
- Attribution: `Booking.broker_referral` nullable FK; on booking APPROVED a broker
  `Commission` is created (idempotent) from `CommissionRule.broker`.
- Payout: available balance = PENDING commissions − non-rejected/non-canceled payouts.

### `corporate`
- `CorporateAccount` — name, email, phone, address, `status` (PENDING/ACTIVE/SUSPENDED), owner.
- `CorporateMember` — account FK, user FK, `role` (ADMIN/MEMBER), unique pair.
- Bulk booking: `POST /corporate/bulk-booking/` reuses the `rooms/bulk/` partial-success
  pattern — create/reuse member users (unusable password), create PENDING Bookings,
  return `{created, created_count, errors}`.
- `CorporateInvoice` — sequential `CORP-####`, period, amount = Σ approved bookings' monthly
  rent in period, status (DRAFT/SENT/PAID/OVERDUE).

### `marketplace`
- `AddonProvider` — user OneToOne, business_name, `status` (PENDING/ACTIVE/SUSPENDED).
- `AddonService` — provider, category (cleaning/relocation/repairs/furniture/utilities/insurance),
  title, description, `price` Decimal, unit, is_active, rating.
- `AddonOrder` — service, tenant, broker (nullable attribution), qty, `total`, `status`
  (PENDING/CONFIRMED/COMPLETED/CANCELED/REFUNDED).
- Cross-sell: `recommend_addons(booking)` (category×area×tenant-interest heuristic).
- Commission on CONFIRMED + ledger entry (idempotent).

### `partner_services`
- `Partner` — code, name, kind (INSURANCE/CREDIT), api_endpoint, enabled.
- `InsuranceProduct` — partner, code, name, coverage JSON, `price_monthly`, is_active.
- `InsuranceQuote` — user, product, room nullable, `status` (QUOTED/REQUESTED/ISSUED/DECLINED/CANCELED),
  quote_data JSON, broker nullable.
- Provider pattern mirrors `users.kyc_provider`: interface + deterministic rule-based impl,
  optional HTTP gateway via settings (`INSURANCE_PROVIDER` = "rule"|"http").
- Credit: `check_credit_eligibility(user)` — deterministic adapter, gated by `CREDIT_ENABLED`.

## 4. APIs (`/api/v1/`)

| App | Endpoint | Method | Auth | Notes |
|---|---|---|---|---|
| subscriptions | `plans/` | GET | any | public catalog |
| subscriptions | `subscription/me/` | GET/POST | user | current sub / create checkout (returns gateway URL) |
| subscriptions | `subscription/{id}/cancel/` · `renew/` | POST | owner | |
| monetization | `revenue/dashboard/` | GET | admin | totals, MRR, pending payouts |
| monetization | `payouts/requests/` | GET | admin | all payout requests |
| monetization | `payouts/{id}/approve/` · `reject/` · `mark-paid/` | POST | admin | |
| brokers | `brokers/profile/` | GET/PUT | broker/admin | self profile |
| brokers | `brokers/register/` | POST | user | create profile + verification |
| brokers | `brokers/{id}/review/` | POST | admin | approve/reject |
| brokers | `brokers/dashboard/` | GET | broker/admin | commissions + balance |
| brokers | `brokers/commissions/` · `brokers/payouts/` | GET | broker | own |
| brokers | `brokers/payouts/request/` | POST | broker | amount ≤ balance |
| corporate | `corporate/accounts/` | GET/POST | user | own account |
| corporate | `corporate/accounts/{id}/members/` | GET/POST | admin-of-account | |
| corporate | `corporate/bulk-booking/` | POST | admin-of-account | partial success |
| corporate | `corporate/invoices/` | GET | member | own account invoices |
| corporate | `corporate/admin/` | GET | platform admin | accounts + invoices |
| marketplace | `marketplace/services/` | GET/POST | any/provider | list + create (provider) |
| marketplace | `marketplace/services/{id}/` | GET/PUT | any/provider-owner | |
| marketplace | `marketplace/orders/` | GET/POST | user | create order (tenant) |
| marketplace | `marketplace/orders/{id}/confirm/` | POST | provider-owner | → commission |
| marketplace | `marketplace/recommend/?booking_id=` | GET | user | cross-sell |
| partner_services | `partner-services/insurance/products/` | GET | any | |
| partner_services | `partner-services/insurance/quotes/` | POST/GET | user | quote / own quotes |
| partner_services | `partner-services/insurance/{id}/issue/` | POST | user | → commission + ledger |
| partner_services | `partner-services/credit/eligibility/` | GET | user | |

Modified existing: `payments` — add `payment_type=subscription` + activation hook in
`_apply_success_side_effects`; `rooms.price_recommendation` — entitlement-gated v2 via
`subscriptions.services.predict` (falls back to v1); `bookings.Booking` — add nullable
`broker_referral`; `users.User.Role` — add `BROKER`.

## 5. Migrations & settings

- 6 new apps → own `0001_initial.py` each (plain `makemigrations`).
- `users` (Role.BROKER), `payments` (PaymentType.subscription + `subscription` FK), `bookings`
  (broker_referral FK) migrations.
- `INSTALLED_APPS` += the 6 apps; `CELERY_BEAT_SCHEDULE` += renewal/reminder tasks.
- Flags: `SUBSCRIPTIONS_ENABLED`, `BROKER_NETWORK_ENABLED`, `CORPORATE_ENABLED`,
  `MARKETPLACE_ENABLED`, `INSURANCE_ENABLED`, `CREDIT_ENABLED`, `MONETIZATION_LEDGER_ENABLED`,
  `INSURANCE_PROVIDER` ("rule"), `INSURANCE_GATEWAY_URL`.
- Seed: `manage.py seed_monetization` (default plans, commission rules, partners, sample
  services/products). Optional data migration for defaults so tests/CI are deterministic.

## 6. Dependencies

None new. Reuse: `payments.services.sslcommerz|bkash`, `audit.services.log_action`,
`notifications.utils.create_notification`, `notifications.emails.send_html_email`,
`users.kyc_auto` (pattern), `rooms/views.py` bulk pattern, `pricing`/`analytics` for prediction.

## 7. Risks & mitigations

- **Scope creep / overengineering** → central apps reuse shared money services; no microservices;
  only what generates revenue is built.
- **Idempotency bugs (double commission/ledger)** → unique `idempotency_key` on Commission +
  ledger; `get_or_create` + `transaction.atomic` + `select_for_update` where mutating balances.
- **Entitlement bypass** → every paid feature checked server-side; client flags are cosmetic.
- **Broken existing payments** → payments app only *adds* a payment_type + a hook; all existing
  `TERMINAL_STATUSES`/throttle/audit behavior untouched; full existing test suite must pass.
- **Money precision** → `Decimal` everywhere; no float math in any revenue path.

## 8. Testing & hardening

- Django `APITestCase` + `force_authenticate` per app (matching existing style).
- Coverage of: entitlement checks, idempotent commissions/ledger, payout balance math,
  bulk-booking partial success, RBAC isolation (member vs admin vs platform admin),
  gateway activation of subscriptions, v2 price-prediction fallback.
- Run full suite: `python manage.py test` (must stay green, ~824+ tests) + `ruff check .`.
- Frontend: vitest (component tests for new panels), `tsc --noEmit`, `eslint`, `vite build`.

## 9. Delivery order

1. Monetization foundation (subscriptions + monetization core) → 2. Landlord SaaS (prediction
   abstraction) → 3. Brokers → 4. Corporate → 5. Marketplace → 6. Insurance/credit → 7. Admin
   revenue → 8. Seed + settings/URLs/migrations → 9. Tests/hardening → 10. Frontend → 11. Docs.

## 10. Implementation status (done)

- **Backend:** all 6 apps implemented (models/services/serializers/views/urls/admin + tasks/signals), settings flags + beat schedule, role/payment/booking migrations, `seed_monetization`, 60 new app tests + full suite green (884 tests) and `ruff check .` clean.
- **Frontend:** `UserRole.broker` + `PaymentType.subscription` added; `subscriptionService`, `monetizationService`, `brokerService`, `corporateService`, `marketplaceService`, `partnerService` (+ hooks) following the api.ts/mapper/query-key conventions; Dashboard tabs `monetization` (Subscription + Marketplace + Insurance panels), `broker`, `corporate`, `revenue` (admin); new `/services` page + Navbar link; EN/BN `nav.services` keys. Verified: tsc clean, eslint 0 errors, 373 vitest tests, `vite build` OK.
- **README:** changelog entry, roadmap row, and a "Monetization 2.0 (Revenue)" API reference section added.
