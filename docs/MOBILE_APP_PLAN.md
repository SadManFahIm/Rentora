# Mobile App Plan (React Native) — not yet funded

A native Rentora app (React Native, iOS + Android) is a separate product
track from the web platform. **This phase does not build it.** This document
records the plan so it can be scoped, budgeted and executed as its own
project — it is intentionally a plan, not a changelog.

## Why it's not built in Phase 13

- The web platform covers the core marketplace today: browse/search, chat,
  bookings, payments, AI features, push notifications and the installable
  PWA already deliver a near-native mobile experience.
- A native app adds real cost: separate engineering, two store submissions
  and review cycles, native push/analytics plumbing, and ongoing maintenance
  across iOS + Android SDK churn.
- The web-feasible **reach** wins of Phase 13 (SMS OTP sign-in, WhatsApp
  share, SEO area pages) ship first and are what actually grow the user base
  in Bangladesh on any device.

## When to revisit

- Install/PWA retention plateaus or store-discovery demand is measured
  (users searching "Rentora app").
- A funded engineering slot exists for a dedicated mobile track.
- Native-only needs appear that the PWA cannot do reliably (e.g. deep
  system integrations, offline-first SDKs, NFC/keychain flows).

## Planned architecture

- **Framework:** React Native + TypeScript (Expo for tooling; ejected only if
  a native module demands it).
- **API reuse:** the existing Django REST API (`/api/v1/`) is the single
  source of truth — no parallel backend. JWT auth (access + refresh),
  passkeys, and the Phase 13 SMS OTP flow all map 1:1 to mobile.
- **State/data:** React Query + Zustand (mirroring the web frontend), so
  patterns, mappers and domain code port with minimal divergence.
- **Real-time:** Django Channels WebSocket for chat + notifications, same
  consumer contract as the web client.
- **Payments:** SSLCommerz / bKash **App-to-App** or webview redirect for
  payment, reusing the existing sandbox-tested flows.
- **Push:** Firebase Cloud Messaging (Android) + APNs (iOS) driving the
  existing in-app notification payloads.

## Phase plan (when funded)

| Milestone | Scope |
| --------- | ----- |
| **M1 — App shell** | Expo scaffold, navigation (React Navigation), auth screens (login / register / SMS OTP / passkeys), token storage (SecureStore), EN⇄BN i18n |
| **M2 — Core browse** | Room list + filters + search, room detail + modal, map view (MapLibre RN), wishlist, similar-rooms, Copilot chat screen |
| **M3 — Transact** | Booking request flow, payments (SSLCommerz/bKash), chat + notifications, saved-search alerts, referral invite |
| **M4 — Owner/tenant tools** | Landlord dashboard (listings, insights, fraud status, AI draft), tenant KYC upload, disputes, reviews + photos |
| **M5 — Store** | iOS + Android release builds, store assets, staged rollout, crash reporting (Sentry), version-gated API support |

## Guardrails

- Reuse the web API contracts verbatim (types generated from the OpenAPI
  schema, as the web contract check does today).
- Same security posture: no secrets in the app, refresh-token rotation,
  biometric-local auth optional (SecureStore), SMS OTP gated the same way.
- Feature parity is judged against the web *surfaces users actually use*,
  not 1:1 screen parity.