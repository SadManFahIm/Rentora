# Phase 17 — Graph & Deep Trust: Architecture Audit

**Date:** 22 Aug 2026
**Developer:** Sadman Chowdhury Fahim (NeoNexor Software)
**Branch:** `feat/phase-16-platform-hardening` (Phase 16 merged; Phase 17 branches off)

---

## Scope (from Phase 17 spec)

| Feature | Core | Phase 17 Goal |
|---|---|---|
| Scam-Network Graph | Behavioural graph with community detection | Real-time coordination fraud + shared-infrastructure rings |
| KYC OCR + Liveness + Face-Match | Document OCR → liveness selfie → NID-to-face comparison | On-device liveness detection, OCR with confidence thresholds, face-match providers |
| Photo-Geo Authenticity | GPS metadata extraction → cross-reference with room area | Device GPS spoofing detection, GPS tamper signals, geo-distance scoring |
| Fake-Review Detection | Review text + user behaviour signals → trust scores | NLP-based review analysis, behavioural pattern detection, moderation queue |
| Model Drift Monitoring + Retraining Dashboard | Retrain triggers + admin observability | Feature importance tracking, retrain scheduling, performance dashboards |

**Constraints:** Human-in-the-loop (no auto-ban from ML), AI provider abstraction (no single vendor), all features feature-flagged, PostgreSQL-based graph (no Neo4j), privacy/security enforced at model+API+job level.

---

## 1. Existing Systems Found

### Fraud Engine (`backend/fraud/`)
- **FraudReport** (OneToOne Room): severity (clean/low/medium/high), score (0-100), status (open/reviewed/dismissed)
- **FraudSignal** (FK → FraudReport): 9 detectors — `duplicate_listing`, `suspicious_price`, `missing_images`, `rapid_listing`, `unverified_owner`, `description_similarity`, `duplicate_image`, `manipulated_image`, `fraud_ring`
- `services/detectors.py`: weight-based scoring (HIGH=100, MEDIUM=60, LOW=25), score capped 100
- `services/rings.py`: graph-based ring detection (shared phone = strong edge; shared IP + same area = weak edge), connected-component BFS, collusion score 0-100, `detect_rings()` (weekly Celery task), `owner_ring_membership()` (per-room, called inside `run_scan`)
- `services/scanner.py`: `run_scan(room)` idempotent, replaces report + signals in a single pass
- Ring detection is a **review aid**, never automatic block

### KYC System (`backend/users/`)
- **KycDocument** (landlord KYC): `doc_type` (nid/passport), `file` (private media), `status` (pending/approved/rejected)
- **TenantVerification** (OneToOne User): lifecycle `not_started → pending → verified | rejected | needs_review | expired`; `auto_screen_score/result/detail`; file in private media with UUID renaming
- `kyc_provider.py`: `ProviderResult` dataclass, `RuleBasedProvider` (deterministic), pluggable via `KYC_PROVIDER` env var
- `kyc_ocr.py`: `extract_ocr_text(path)`, `parse_nid_text(text)` (regex-based NID parsing), `ocr_screen(verification)`
- `kyc_auto.py`: deterministic pre-screener, `auto_screen(verification)`, `APPROVE_SCORE` threshold
- Privacy: private storage, UUID-renamed files, no NID/log exposure
- Audit: `tenant_kyc.*` transitions logged to `AuditLogEntry`
- **Missing:** No liveness provider, no face-match provider, no formal consent model, no OCR confidence thresholds

### Review System (`backend/bookings/models.py`)
- **Review**: room, user, rating (1-5), comment, `verified_stay` (BooleanField, no FK to Booking), `reply`/`replied_at`, `photos` (JSONField), UniqueConstraint(room, user)
- Denormalized `Room.rating`/`total_reviews` via post_save/post_delete signals
- **Missing:** No trust scoring, no moderation queue, no LLM analysis, no behaviour signals

### AI Provider Pattern (7 independent implementations)
| Provider | Setting | Default | Gateway |
|---|---|---|---|
| Embedding | `EMBEDDING_PROVIDER` | `local` (cosine fallback) | Optional HTTP |
| Vision | `VISION_PROVIDER` | `local` (Pillow stats) | Optional HTTP |
| KYC | `KYC_PROVIDER` | `rules` | Optional HTTP |
| OCR | `KYC_OCR_PROVIDER` | `none` | `http` |
| Translation | `CHAT_TRANSLATE_PROVIDER` | `none` | `http` |
| SMS | `SMS_PROVIDER` | `console` | `http` |
| Insurance | (env var) | `none` | — |

All follow: `*_PROVIDER` env var → local deterministic default → optional HTTP gateway → fallback on failure. **No shared base class.**

### Background Jobs (`backend/config/settings/base.py`)
19+ Celery tasks across 10+ modules. Key for Phase 17:
- `scan-rooms-fraud` (daily 04:00 UTC)
- `detect-fraud-rings` (weekly Tue 02:00 UTC)
- `alert-kyc-sla-breaches`, `purge-expired-analytics`

### Feature Flags (`backend/feature_flags/`)
- `FeatureFlag` model: key, status, rollout_percentage, environments, roles, user_ids
- `is_enabled()` with MD5 bucketing + 30s cache
- Staff CRUD API at `/api/v1/flags/`
- **NOT wired into product code** — must be wired for Phase 17

### Experiments (`backend/experiments/`)
- Complete A/B infrastructure
- **NOT wired into product code** — no production callers

### Audit Logging (`backend/audit/`)
- `AuditLogEntry`: actor, action, target_type, target_id, ip_address, metadata
- Append-only, used by fraud review, KYC transitions, payment status changes

### Notification Framework (`backend/notifications/`)
- `Notification`: subject, body, category, url, is_read, metadata
- `create_notification()`, `create_fraud_flag_notification()`, email dispatch

### Analytics (`backend/analytics/`)
- `Event`: event, category, properties, session_id, created_at
- `record_event()`, `build_summary()`, `build_taxonomy()`
- Daily purge via Celery

### Domain Models
- **Room**: area (20 Dhaka areas enum), lat/lng (nullable), owner, tier, is_available
- **User**: role, nid_verified, tenant_verified, phone, referral_code, device_id
- **Booking**: statuses (pending/approved/rejected/cancelled/completed)
- **ImageVariant**: entity_type, entity_id, size_key, file (content-hash WebP)

### Vision System (`backend/rooms/vision.py`)
- `describe_room(photos)`: local Pillow stats + optional HTTP gateway
- Auto amenity tagging, AI image search via pHash (64-bit)

### Image Pipeline (`backend/images/`)
- WebP variants, content-hash filenames, immutable caching
- `config/images.py`: `strip_exif()` — EXIF **stripped for privacy** (location leak prevention)

---

## 2. Reusable Components

| Component | Reuse For Phase 17 | What to Extend |
|---|---|---|
| `fraud/services/detectors.py` | Add new detector types (photo_geo, review_trust, kyc_liveness) | Extend `Detector.choices`; add detector functions; adjust scoring weights |
| `fraud/services/rings.py` | Scam-network graph: edges, components, scoring | Add edge types (device_id, NID reuse, payment path, behavioral), temporal decay, community detection |
| `fraud/models.py` | `FraudSignal` stores per-detector evidence | Add new `Detector` choices; `detail` JSONField carries arbitrary evidence |
| `users/kyc_provider.py` | KYC provider pattern (`ProviderResult`, `run_provider()`) | Add liveness and face-match provider interfaces |
| `users/kyc_ocr.py` | OCR provider pattern, NID text parsing | Add confidence thresholds |
| `audit/models.py` | Audit trail for all Phase 17 sensitive actions | Extend `target_type` values; add Phase 17 action constants |
| `notifications/models.py` | In-app + email notifications for fraud/graph/KYC events | Add new `category` values; reuse `create_notification()` |
| `feature_flags/models.py` | Feature-flag all Phase 17 features | Wire `is_enabled()` into Phase 17 code paths; seed flags in `sync_flags` |
| `experiments/` | A/B test Phase 17 features | Wire experiment assignments into new flows |
| `analytics/Event` | Track Phase 17 events | Use `record_event()` with new event names |
| `config/ip.py` | IP extraction from request | Reuse for graph edge generation |
| `config/cache_utils.py` | `safe_cache_*` wrappers | Reuse for Phase 17 caching |
| `config/throttling.py` | `TrustedClientIPMixin`, rate limiting | Reuse for Phase 17 API endpoints |
| `config/storage.py` | `PrivateMediaStorage` | Reuse for liveness selfie storage |
| `images/services.py` | EXIF stripping (privacy) | Note: GPS must be extracted **before** stripping for photo-geo |

---

## 3. Partial Implementations

### Ring Detection (Partially Done)
- **Done:** `fraud/services/rings.py` — phone (strong) and IP+area (weak) edges, connected components, collusion score, admin endpoint, weekly beat task
- **Missing:** No device fingerprint edges, no payment path edges, no NID reuse, no behavioral clustering, no temporal decay, no real-time alerting, no community detection beyond basic BFS

### KYC Pre-Screening (Partially Done)
- **Done:** `kyc_auto.py` pre-screener, `kyc_ocr.py` OCR extraction, `kyc_provider.py` pluggable rule-based provider
- **Missing:** No liveness detection, no face-match, no OCR confidence thresholds, no consent tracking, no liveness selfie storage

### Fraud Signal Pipeline (Partially Done)
- **Done:** 9 detectors, weight-based scoring, `run_scan()` idempotent
- **Missing:** No photo-geo detector, no review-trust detector, no cross-user behavioral signals, no ML model integration, no model versioning

---

## 4. Missing Infrastructure

| Gap | Description | Priority |
|---|---|---|
| **Graph persistence layer** | Ring detection is in-memory. Phase 17 needs persistent graph for temporal analysis, community detection, cross-entity edges. PostgreSQL adjacency lists or materialized edge table. | HIGH |
| **Liveness provider interface** | No `LivenessProvider`. Need: capture→challenge→verify contract, provider result dataclass. | HIGH |
| **Face-match provider interface** | No `FaceMatchProvider`. Need: NID photo→selfie comparison, similarity score, anti-spoofing. | HIGH |
| **Consent model** | No formal consent tracking for liveness/selfie collection. Need: user consent record with revocation. | HIGH |
| **Review moderation queue** | Reviews publish instantly. No moderation status, no hold queue, no flagging. | HIGH |
| **Review trust scoring** | No trust score. Need: text analysis, behavioral signals, verified-stay weighting. | HIGH |
| **EXIF extraction (before strip)** | `strip_exif()` destroys GPS. Photo-geo needs GPS extraction **before** stripping — must capture at upload time. | MEDIUM |
| **Model version tracking** | No ML model registry. Need: version, training date, metrics, drift status. | MEDIUM |
| **Model drift monitoring** | No drift detection. Need: metric tracking, threshold alerts, retrain triggers. | MEDIUM |
| **Retraining pipeline** | No automated retrain. Need: data collection, training trigger, deployment, A/B rollout. | MEDIUM |
| **Photo authenticity detector** | No GPS spoofing/EXIF manipulation/location mismatch detector. | MEDIUM |
| **Review behavior signals** | No review velocity, rating anomaly, or cross-user pattern tracking. | MEDIUM |
| **Real-time graph update** | Ring detection is batch-only. Need event-driven edge updates. | LOW |

---

## 5. Required Database Changes

### New Models

| Model | App | Purpose |
|---|---|---|
| `GraphNode` | `fraud` | Persistent graph node (user/room/device/payment), type, metadata, last_seen |
| `GraphEdge` | `fraud` | Persistent edge: type (phone/ip/device/nid/payment/behavioral), strength, evidence, first_seen, last_seen |
| `LivenessChallenge` | `users` | Liveness check lifecycle: user, status, challenge_type, provider_response, created_at |
| `LivenessConsent` | `users` | Consent record: user, consent_type, granted_at, revoked_at, ip_address |
| `ReviewModeration` | `bookings` | Moderation queue: review, status (pending/approved/rejected/escalated), moderator, decided_at |
| `ReviewTrustScore` | `bookings` | Trust scoring: review FK, score (0-100), signals (JSONField), model_version |
| `PhotoGeoSignal` | `rooms` | GPS extraction: room, source_photo, lat, lng, accuracy, extraction_method |
| `ModelVersion` | `ai_features` | ML model registry: name, version, training_date, metrics, status, artifacts_path |
| `DriftMetric` | `ai_features` | Time-series: model_version FK, metric_name, value, window, threshold_breached |
| `RetrainRequest` | `ai_features` | Retrain trigger: model_version FK, reason, status, triggered_by |

### Existing Model Modifications

| Model | Change |
|---|---|
| `Room` | Add `gps_lat_extracted`, `gps_lng_extracted` (DecimalField, nullable), `photo_gps_accuracy` (CharField) |
| `Review` | Add `moderation_status` (CharField, default="approved"), `trust_score` (IntegerField, nullable) |
| `FraudSignal` | Extend `Detector.choices`: `photo_geo_mismatch`, `liveness_failed`, `face_match_failed`, `review_fake`, `review_spam`, `kyc_liveness_missing` |
| `User` | Add `device_ids` (JSONField, default=list) |
| `TenantVerification` | Add `liveness_status` (CharField, nullable), `liveness_score` (IntegerField, nullable), `face_match_status` (CharField, nullable), `face_match_score` (IntegerField, nullable) |

---

## 6. Required API Changes

### New Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v1/fraud/graph/` | GET | Full graph overview (admin only) — nodes, edges, communities |
| `/api/v1/fraud/graph/nodes/` | GET | List graph nodes with filters (type, risk_level) |
| `/api/v1/fraud/graph/edges/` | GET | List graph edges with filters (type, strength) |
| `/api/v1/fraud/rings/` | GET | Existing ring endpoint (already implemented) |
| `/api/v1/kyc/liveness/` | POST | Initiate liveness challenge (returns challenge for client SDK) |
| `/api/v1/kyc/liveness/verify/` | POST | Submit liveness result (provider response) |
| `/api/v1/kyc/face-match/` | POST | Submit selfie for NID-to-face comparison |
| `/api/v1/kyc/consent/` | POST/GET | Record/check consent for liveness/face_match |
| `/api/v1/rooms/{id}/photo-geo/` | POST | Extract GPS from uploaded photos |
| `/api/v1/reviews/{id}/moderation/` | POST | Flag/escalate review (admin/trust desk) |
| `/api/v1/reviews/{id}/trust/` | GET | View trust score + signals (admin) |
| `/api/v1/admin/ml/models/` | GET | List model versions + status (admin) |
| `/api/v1/admin/ml/drift/` | GET | Drift metrics dashboard data (admin) |
| `/api/v1/admin/ml/retrain/` | POST | Trigger retrain request (admin) |
| `/api/v1/flags/phase17.*` | CRUD | Phase 17 feature flags (existing `/api/v1/flags/` endpoint) |

### Existing Endpoints to Modify

| Endpoint | Change |
|---|---|
| `POST /api/v1/rooms/{id}/images/` | Extract GPS from EXIF before stripping; store on `PhotoGeoSignal` + `Room` |
| `POST /api/v1/bookings/{id}/review/` | Route through moderation queue (if feature flag enabled) |
| `GET /api/v1/rooms/{id}/` | Include `gps_lat_extracted`, `gps_lng_extracted` in serializer |
| `GET /api/v1/rooms/{id}/reviews/` | Filter by `moderation_status`, include `trust_score` (admin only) |
| `GET /api/v1/admin/fraud/` | Include graph data, new signal types |

---

## 7. Required Background Jobs

| Task | Schedule | Purpose |
|---|---|---|
| `rebuild-fraud-graph` | Weekly (Sun 03:00 UTC) | Full graph rebuild from audit logs, phone, IP, device, payment data |
| `update-graph-incremental` | Every 6 hours | Incremental graph update from new audit entries |
| `scan-review-trust` | Daily (05:00 UTC) | Compute trust scores for un-scored reviews |
| `detect-review-anomalies` | Daily (05:30 UTC) | Detect rating distribution anomalies, review velocity spikes |
| `check-model-drift` | Daily (06:00 UTC) | Compare recent predictions vs baseline; alert if threshold breached |
| `purge-expired-liveness` | Daily (03:30 UTC) | Clean up expired liveness challenges older than 30 days |
| `alert-graph-anomalies` | Every 6 hours | Alert admin when new large ring or suspicious community detected |

All tasks follow existing patterns: `autoretry_for`, `ack_late=True`, `retry_backoff=True`, `max_retries=3`, `soft_time_limit`/`time_limit`.

---

## 8. Required Frontend/Admin Changes

### Admin Dashboard
- **Trust & Safety Center**: extend existing Phase 12 T&S dashboard with graph visualization (nodes/edges), new queue tabs for review moderation, liveness review
- **ML Operations Dashboard**: model version list, drift metrics charts (Chart.js), retrain request trigger
- **Graph Explorer**: interactive graph view showing users, rooms, devices, payment connections (could use vis.js or similar)

### Tenant/Landlord Flows
- **Liveness check flow**: capture selfie → submit → show result (pass/fail/pending review)
- **Review submission**: if feature flag enabled, route through moderation queue (show "pending moderation" state)
- **Photo upload**: backend extracts GPS automatically (no frontend change needed)

### Feature Flag Wiring
Seed the following flags in `sync_flags` command:
- `phase17.scam_graph` — enable graph persistence + community detection
- `phase17.kyc_liveness` — enable liveness check in KYC flow
- `phase17.kyc_face_match` — enable NID-to-face comparison
- `phase17.photo_geo` — enable GPS extraction + geo-distance scoring
- `phase17.review_moderation` — enable review moderation queue
- `phase17.review_trust` — enable review trust scoring
- `phase17.model_monitoring` — enable drift monitoring + retrain dashboard

---

## 9. External Provider Dependencies

| Feature | Provider Needed | Mock/Test Strategy | Priority |
|---|---|---|---|
| Liveness Detection | Liveness SDK (on-device: FaceTec, iProov, or open-source) | Mock provider returning pass/fail with configurable confidence | HIGH |
| Face-Match | Face comparison API (Amazon Rekognition, FaceTec, or self-hosted) | Mock provider returning similarity score | HIGH |
| NID OCR (enhanced) | Already has HTTP gateway pattern (`KYC_OCR_PROVIDER=http`) | Already mocked with `none` default | DONE |
| GPS/Reverse Geocoding | Room area is already 20-area enum; GPS→area mapping is deterministic | No external provider needed — use Haversine distance to area centroid | NONE |
| Review NLP/LLM | LLM API for review authenticity analysis (OpenAI, Anthropic, or local) | Mock provider with rule-based heuristics (keyword density, sentiment) | MEDIUM |
| Model Retraining | ML training infrastructure (GPU, training pipeline) | Admin manual trigger + training script (no automated pipeline needed initially) | LOW |

**Provider abstraction pattern:** Follow existing `*_PROVIDER` env var pattern. Each new provider gets:
1. Settings: `{FEATURE}_PROVIDER`, `{FEATURE}_GATEWAY_URL`, `{FEATURE}_GATEWAY_API_KEY`
2. Local mock/default provider class
3. Optional HTTP gateway provider
4. `get_provider()` / `run_provider()` function
5. Provider failure → distinguish `USER_FAILURE` (bad input) vs `PROVIDER_FAILURE` (gateway down) vs `SYSTEM_FAILURE` (unexpected)

---

## 10. Security & Privacy

### Data Classification

| Data | Sensitivity | Storage | Exposure |
|---|---|---|---|
| Liveness selfie | CRITICAL (biometric) | Private media, UUID-renamed, auto-expire 90d | Tenant + admin only |
| NID document | CRITICAL (identity) | Private media, UUID-renamed | Already implemented |
| GPS coordinates | HIGH (location) | Room model (decimal), never in logs/analytics/URLs | Room owner + admin |
| Device fingerprints | MEDIUM (behavioral) | User model (JSONField) | Admin only |
| Graph edges | MEDIUM (social) | PostgreSQL (GraphNode/GraphEdge) | Admin only |
| Review trust scores | LOW (derived) | Booking model (IntegerField) | Admin only + review author |
| Model metrics | LOW (operational) | AI features model | Admin only |

### Security Requirements
- **No auto-ban from ML scores**: trust scores and graph signals are review aids only; human decides
- **PII never in logs**: NID numbers, selfies, GPS, device IDs must not appear in Django logs, analytics events, error reports, or CSV exports
- **Graph data isolation**: graph endpoints require `is_staff`; graph data never exposed in public API
- **Liveness selfie retention**: auto-delete after 90 days via Celery task
- **Rate limiting**: all Phase 17 endpoints throttled via existing `TrustedClientIPMixin`
- **Audit trail**: every liveness check, face-match, moderation decision, graph edge creation logged to `AuditLogEntry`
- **Provider failure classification**: `USER_FAILURE` (bad input → user sees error), `PROVIDER_FAILURE` (gateway down → retry/fallback), `SYSTEM_FAILURE` (unexpected → alert + log)

---

## 11. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| **Graph rebuild performance** | Full graph rebuild on large user base could be slow | Incremental updates + full rebuild off-peak; index `GraphNode`/`GraphEdge` on type+last_seen |
| **Liveness provider availability** | If provider is down, KYC flow blocks | Graceful fallback: mark as `needs_review` for manual queue; never block user permanently |
| **EXIF stripping vs GPS extraction** | Current `strip_exif()` destroys GPS before Phase 17 can capture it | Extract GPS **before** stripping in the upload pipeline; store on `PhotoGeoSignal` immediately |
| **Review moderation backlog** | Enabling moderation queue creates new manual work for admin | Start with ML-scored auto-approve for high-trust reviews; only low-trust goes to queue |
| **Feature flag complexity** | 7 new flags increases cognitive load | Document cleanup plan for each flag; quarterly dead-flag audit |
| **Provider cost** | Liveness/face-match APIs may charge per check | Free-tier alternatives: on-device liveness SDK (no per-check cost), self-hosted face-match |
| **Privacy regulation** | Biometric data (liveness selfies) may be regulated | Explicit consent model, 90-day auto-deletion, user can request deletion |

---

## 12. Recommended Implementation Order

### Stage 1 — Audit (DONE)
This document.

### Stage 2 — Shared Trust/Fraud Infrastructure
- Graph persistence models (`GraphNode`, `GraphEdge`)
- Extend `FraudSignal.Detector` choices
- `LivenessConsent` model
- `ReviewModeration` model
- `ModelVersion` + `DriftMetric` models
- Wire `feature_flags` into Phase 17 code paths
- Seed Phase 17 feature flags in `sync_flags` command

### Stage 3 — Scam-Network Graph
- Persistent graph rebuild task (`rebuild-fraud-graph`)
- Incremental graph update task
- New edge types: device_id, NID reuse (stretch: payment path)
- Community detection (connected components + label propagation)
- Admin graph API endpoints
- Graph anomaly alerts

### Stage 4 — KYC OCR + Liveness + Face-Match
- `LivenessChallenge` model + provider interface
- `LivenessConsent` tracking
- Face-match provider interface
- Extend `TenantVerification` with liveness/face-match fields
- OCR confidence thresholds
- Liveness + face-match API endpoints
- Auto-delete liveness selfies after 90 days

### Stage 5 — Photo-Geo Authenticity
- Extract GPS from EXIF **before** `strip_exif()` in upload pipeline
- `PhotoGeoSignal` model
- GPS-to-area matching (Haversine to area centroids)
- GPS spoofing detection (area mismatch signal)
- New fraud detector: `photo_geo_mismatch`
- Room serializer extension

### Stage 6 — Fake-Review Detection
- Review moderation queue + API
- Review trust scoring (text analysis + behavioral signals)
- Review anomaly detection task
- New fraud detectors: `review_fake`, `review_spam`
- Wire into existing review flow (feature-flagged)
- Admin review moderation UI

### Stage 7 — Model Drift Monitoring + Retraining Dashboard
- `ModelVersion` registry
- `DriftMetric` time-series tracking
- `RetrainRequest` workflow
- Daily drift check task
- Admin ML dashboard (model versions, drift charts, retrain trigger)
- Feature importance tracking

### Stage 8 — Security/Privacy
- PII audit: ensure no NID/GPS/biometric data in logs/analytics
- Liveness selfie auto-deletion (90-day retention)
- Provider failure classification (USER_FAILURE/PROVIDER_FAILURE/SYSTEM_FAILURE)
- Rate limiting for new endpoints
- Audit trail for all Phase 17 actions
- Consent management (liveness/face_match)

### Stage 9 — Testing
- Unit tests for all new models, services, detectors
- Integration tests for provider fallbacks
- Integration tests for graph rebuild/incremental
- Frontend component tests
- Existing test suite regression (960+ tests must stay green)
- Load tests for graph rebuild

### Stage 10 — Documentation + Final Report
- Update `docs/architecture.md`
- Phase 17 implementation report (per feature: IMPLEMENTED / PARTIALLY IMPLEMENTED / MOCK / REQUIRES EXTERNAL PROVIDER / BLOCKED)
- Update `CLAUDE.md` with new commands/settings
- Update `docs/api-reference.md` with new endpoints
