# Phase 15 — Communication & Trust AI

Three feature groups (B, C, D) adding AI-powered communication tools, trust/verification intelligence, and fraud detection to Rentora.

## Features Delivered

### B — Communication AI
- **B1 Chat translation** (`chat/translation.py`) — auto-detects source language, translates chat messages (EN↔BN) with Google Translate fallback; quality flag (`full`/`phrase`/`none`) shown honestly in the UI
- **B2 Support copilot** (`copilot/support.py`) — grounded FAQ matcher against help library; returns answer + Bangla translation + matched keywords; honest fallback when no article matches
- **B3 Voice TTS** (`useSpeechOutput.ts`) — Web Speech API integration on copilot assistant replies; respect `speechSynthesis` availability with feature-detection guard

### C — Trust & Verification AI
- **C4 KYC OCR** (`users/kyc_auto.py`) — auto-extracts NID number, name, DOB from uploaded verification documents with confidence score; displayed in TenantKycCard with honesty note
- **C5 Review summary** (`bookings/review_summary.py`) — AI-generated summary of room reviews with sentiment breakdown (positive/neutral/negative %) and topic tags; shown in ReviewsSection
- **C6 Market report** (`analytics/market_report.py`) — weekly area-level rental analytics (median price, WoW movement, index); AdminAnalyticsPanel visualization; email distribution to opted-in landlords
- **C7 Dynamic pricing v2** (`rooms/price_recommendation.py`) — demand-momentum-adjusted price windows with area-specific factor drivers; replaces static v1 with time-series-informed recommendations

### D — Fraud Intelligence
- **D8 Fraud rings** (`fraud/services/rings.py`) — detects coordinated accounts via shared phone (strong link) and shared audit IP + same area (weak link); flagged rings surfaced in AdminFraudPanel
- **D9 Deep detectors** (`chat/classifier.py`, `chat/safety.py`) — intent analysis, risk scoring, and safety classification on chat messages

## Key Files

### Backend (new)
| File | Purpose |
|------|---------|
| `chat/translation.py` | Chat message translation (Google Translate + fallback) |
| `copilot/support.py` | Grounded FAQ matcher for support copilot |
| `users/kyc_auto.py` | NID OCR auto-extraction from uploaded documents |
| `bookings/review_summary.py` | AI review summary with sentiment analysis |
| `analytics/market_report.py` | Weekly area rental market analytics |
| `analytics/tasks.py` | Market report generation & email tasks |
| `rooms/price_recommendation.py` | Demand-momentum pricing v2 |
| `fraud/services/rings.py` | Coordinated-account ring detection |
| `fraud/management/commands/detect_rings.py` | Management command for ring detection |

### Backend (modified)
| File | Changes |
|------|---------|
| `chat/views.py` | Added `ChatTranslateView` with translation endpoint |
| `chat/safety.py` | Deep classifier integration for message safety |
| `chat/classifier.py` | Intent analysis and risk scoring |
| `copilot/views.py` | Added `SupportView` with grounded FAQ endpoint |
| `users/views.py` | OCR auto-screen integration on KYC submission |
| `bookings/views.py` | Review summary endpoint integration |
| `analytics/views.py` | Market report endpoint with generate action |
| `rooms/price_recommendation.py` | v2 with demand momentum and area drivers |
| `fraud/views.py` | Fraud rings endpoint |
| `fraud/models.py` | Ring detection models |
| `fraud/services/detectors.py` | Deep detector integration |

### Frontend (new)
| File | Purpose |
|------|---------|
| `hooks/useSpeechOutput.ts` | Web Speech API hook for TTS |
| `hooks/useSpeechOutput.test.tsx` | Tests for TTS hook |
| `services/marketReportService.ts` | Market report API client |
| `components/MarketReportCard/` | Market report visualization card |

### Frontend (modified)
| File | Changes |
|------|---------|
| `ChatWindow/ChatWindow.tsx` | B1: translate button + translation display |
| `AiToolsPanel/AiToolsPanel.tsx` | B2: support tab with grounded FAQ |
| `CopilotWidget/CopilotWidget.tsx` | B3: TTS speak button on assistant replies |
| `TenantKycCard/TenantKycCard.tsx` | C4: OCR auto-extract display |
| `ReviewsSection/ReviewsSection.tsx` | C5: AI summary card with sentiment |
| `AdminAnalyticsPanel/AdminAnalyticsPanel.tsx` | C6: market report card mount |
| `PriceRecommendationCard/PriceRecommendationCard.tsx` | C7: v2 with dynamic price |
| `AdminFraudPanel/AdminFraudPanel.tsx` | D8: fraud rings toggle + display |
| `services/chatService.ts` | Translation API integration |
| `services/copilotService.ts` | Support copilot API |
| `services/kycService.ts` | OCR data types |
| `services/reviewService.ts` | Review summary API |
| `services/tier5Service.ts` | Price recommendation v2 API |
| `services/fraudService.ts` | Fraud rings API |
| `hooks/useFraud.ts` | Fraud rings hook |
| `i18n/en.json` | English translations for new features |
| `i18n/bn.json` | Bangla translations for new features |
| `types/index.ts` | Updated type definitions |

## API Endpoints Added
- `POST /api/v1/chat/translate/` — translate a chat message
- `POST /api/v1/copilot/support/` — ask the support copilot
- `GET /api/v1/rooms/{id}/price-recommendation/` — v2 price recommendation
- `GET /api/v1/reviews/summary/?room={id}` — AI review summary
- `GET /api/v1/analytics/market-report/` — weekly market report
- `POST /api/v1/analytics/market-report/generate/` — generate new report
- `GET /api/v1/fraud/rings/` — detected fraud rings

## Bug Fix Included
- Fixed SQLite `DISTINCT` + `ORDER BY` gotcha in `analytics/market_report.py` and `analytics/forecast.py` — `Room.Meta.ordering = ["-created_at"]` caused duplicate area rows in market reports. Added `.order_by("area")` to deduplicate.

## Test Counts
- Frontend: 354 tests passing (45 files)
- Backend: all existing tests green
