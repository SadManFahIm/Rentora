# Phase 12.3 — Chat Safety Engine

Every chat message on Rentora passes through a rule-based safety engine before it is
stored or delivered. The engine detects the scam patterns that actually plague rental
marketplaces — off-platform payment requests, phishing links, urgency pressure,
impersonation, credential fishing — and responds proportionately: **warn → flag → block**.
It never silently censors, and it never claims certainty.

## Risk levels & what the engine does

| Risk       | Typical trigger                                   | Outcome          | What the user sees                          |
| ---------- | ------------------------------------------------- | ---------------- | ------------------------------------------- |
| LOW        | Urgency words ("hurry", "only 2 rooms left")      | allowed (silent) | — (recorded only if it repeats)             |
| MEDIUM     | Off-platform contact, shortener link, scam phrase | `warned`         | "Be careful sharing payment information."   |
| HIGH       | Payment redirect, impersonation, credential ask   | `flagged`        | "Potentially unsafe payment request detected." |
| CRITICAL   | 2+ distinct high-risk signals, or repeated high   | `blocked`        | Message replaced with "🚫 Message blocked for safety review." |

A message's risk is the **highest** detector hit, escalated one level when the same
sender trips the same detector repeatedly (urgency + repetition is how scams grind
people down). Two or more *distinct* high-risk signals together (e.g. impersonation +
payment redirect + credential request) are treated as **critical** — a stack of highs is
an active attack, not a coincidence.

## Detectors (`chat/safety.py`)

All regex-based, English **and** Bangla, deliberately precise to avoid false positives
(a plain "Do you accept bKash?" is fine — "send the deposit to my bKash 01712…" is not):

- `payment_redirect` — wallet (bKash/Nagad/Rocket/Upay) + number / payment verb; Bangla money-transfer phrases
- `advance_payment` — advance/booking money before viewing
- `phishing_url` — URL shorteners, raw-IP links, lookalike domains (rent0ra…, sslcommerz-…)
- `contact_redirect` — WhatsApp/Telegram/Viber/IMO contact asks, personal-number dumps
- `urgency` — hurry/act-now/only-N-left, Bangla equivalents
- `scam_phrase` — Western Union, transfer/processing fees
- `impersonation` — "I am the admin", "from Rentora support", Bangla equivalents
- `credential_request` — asks for OTP/password/PIN/NID

## Configurable policy

| Setting                     | Default    | Meaning                                   |
| --------------------------- | ---------- | ----------------------------------------- |
| `CHAT_SAFETY_ENABLED`       | `True`     | Master switch (env `CHAT_SAFETY_ENABLED`) |
| `CHAT_SAFETY_BLOCK_LEVEL`   | `critical` | Messages at/above this risk are blocked   |
| `CHAT_SAFETY_FLAG_LEVEL`    | `high`     | Messages at/above this risk are flagged   |

Tighten to `CHAT_SAFETY_BLOCK_LEVEL=medium` and the engine blocks medium-risk messages
too — same code, different posture, no deploy needed.

## Integration

Both message-creation paths run the pipeline (assess → apply policy → store):

- **REST** — `POST /api/v1/chat/rooms/<id>/messages/` (`MessageViewSet.create`)
- **WebSocket** — `ChatConsumer._save_message`

When a message is blocked, the *safety notice* is what gets stored and broadcast; the
sender's raw text is discarded — never persisted, never logged, never broadcast. The
message response carries a `safety` object so the client can surface warnings.

Admin visibility: `GET /api/v1/chat/safety/events/` (admin-only) returns recent events —
**metadata only** (detector keys, risk, outcome, sender, room), never message content.

## Privacy

- The engine stores **metadata only**: detector keys + short matched fragments in
  `ChatSafetyEvent.detectors`. Full conversation text is not duplicated anywhere.
- `ChatSafetyEvent` records what tripped and what the engine did — not the message.
- Blocked messages' raw content is never written to the database at all.

## Testing

`backend/chat/test_safety.py` — 24 tests: detector units (incl. no-false-positive for a
plain wallet mention), policy mapping (default + configurable block/flag levels,
disabled engine), REST integration (warn/flag/block with the spec's exact warning copy),
the **raw-content-never-stored** guarantee, repetition escalation, and admin-feed
authorization. Frontend: mapper test for the `safety` payload + the ChatWindow warning
banner / blocked-bubble styling (tsc + eslint + prettier clean).
