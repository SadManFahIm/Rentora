# 🎤 Voice Search Playbook

> How Rentora's voice search works, what it supports today, how to test it and
> what is deliberately left for later. Everything here describes **implemented
> behaviour** — nothing is speculative.

---

## 1. Overview

Voice search is a **microphone button inside the room-search box** (`🎙` on the
Rooms page). Tap it, speak a query in **Bangla (or Banglish / English)**, and
the transcript is dropped into the search input — from there it flows through
the **same AI Smart Search pipeline** as typed text (intent parsing → filters →
ranking).

Voice is **purely additive**: the mic never replaces typing, and if speech
recognition is unavailable everything still works exactly as before.

## 2. Supported languages

| Language | Recognition locale | Notes |
|---|---|---|
| Bangla | `bn-BD` (default) | Primary target — the recognizer is configured for Bengali (Bangladesh) |
| Banglish / English | `bn-BD` + search parser | Dictation of romanized Banglish phrases ("uttora 10k er moddhe") is passed to the NL parser, which understands English, Bangla and mixed text regardless of how it was produced |

The recognition language is configurable per hook call (`lang` option); the
search page uses the default `bn-BD`.

## 3. Browser Web Speech API behaviour

- Uses the **Web Speech API** (`SpeechRecognition`, falling back to
  `webkitSpeechRecognition`, then `msSpeechRecognition`).
- Configured with `interimResults: false` (only the final transcript is used),
  `maxAlternatives: 1`, `continuous: false` (one utterance per tap).
- The first utterance result is used; then the hook transitions to
  `processing` while the transcript is handed to the caller (the search box).

## 4. Voice → text → search intent flow

```text
User taps 🎙 and speaks
        │
        ▼
Web Speech API (bn-BD)
        │  final transcript only
        ▼
useVoiceSearch.onTranscript
        │  fills the search input
        ▼
AI Smart Search (same pipeline as typed text)
        │  parse_nl_query (Bangla / English / Banglish)
        ▼
Intent chips + ranked results (semantic ranking, typo tolerance)
```

Voice adds no separate search path — the transcript simply becomes the query.

## 5. Supported example queries

After the transcript lands in the search box, the existing NL parser
understands (identical to typed queries):

| Category | Example |
|---|---|
| Budget | "দশ হাজার এর মধ্যে উত্তরা", "10k er moddhe", "under 15k" |
| Area | "উত্তরা", "Mirpur", "banani" (aliases + Bangla names) |
| Room type | "single room", "studio", "shared" |
| Amenities | "furnished", "AC", "wifi" |
| Gender preference | "male", "female" (Bangla + English) |
| Mixed | "উত্তরায় ১২ হাজারের মধ্যে furnished room" |

## 6. Fallback behaviour

| Situation | Behaviour |
|---|---|
| API unsupported (e.g. some Linux/Android WebViews) | Mic button shows the `unsupported` state; **typed search is untouched** |
| Microphone permission denied | `denied` state surfaced on the button; search keeps working |
| Recognition error | `error` state; no crash; retry by tapping again |
| Empty transcript | Nothing is inserted — no change to the current search |
| Recognition session ending without a result | Returns to `idle` |

The hook reports exactly one of: `idle · listening · processing ·
unsupported · denied · error`.

## 7. Permission handling

- The browser asks for **microphone permission** on first use (standard
  Web Speech API behaviour).
- Denial is caught (`not-allowed` / `service-not-allowed`) and surfaced as
  `denied` — the app never prompts again in the same session and never breaks.

## 8. Privacy considerations

- **No audio is recorded, stored or uploaded.** Only the text transcript is
  returned to the page (Web Speech API processes audio in the browser/service).
- The transcript is used exactly like a typed query — subject to the same
  search logging, nothing more.
- Voice search never captures passwords, tokens or payment data (it is only
  wired to the search input).

## 9. Mobile behaviour

- Works on Chrome/Edge mobile (Web Speech API support) — tap the mic, speak,
  results render through the normal mobile search UI.
- `continuous: false` keeps each tap a single, predictable utterance — ideal
  for one-handed use.
- Where the OS/browser lacks the API, the button degrades to the unsupported
  state; search remains fully usable.

## 10. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Mic button shows "unsupported" | Browser/WebView without Web Speech API (e.g. some embedded WebViews). Use typed search, or try Chrome/Edge. |
| "denied" on tap | Microphone permission blocked. Allow the site in browser settings, then retry. |
| Transcript appears but no results | The parser didn't find filters (e.g. unusual phrasing) — it falls back to **keyword search** (`hints: ["keyword search"]`), same as typing. |
| Nothing happens after speaking | Recognition returned an empty/failed result; tap again, speak clearly, and check the mic permission state. |

## 11. Testing procedure

Automated:

```bash
cd frontend && npx vitest run src/hooks/useVoiceSearch.test.tsx
```

The test suite mocks the Web Speech API and covers: transcript delivery,
unsupported API, denied permission, error handling, and cleanup on unmount.

Manual (Chrome):

1. Open **/rooms**.
2. Tap the 🎙 mic button → status becomes "listening" (button highlights).
3. Speak **"দশ হাজার এর মধ্যে উত্তরা"** → transcript appears in the search box.
4. Results + "AI understood" chips render (budget + area).
5. Deny the mic permission → button shows the denied state; typed search still works.

## 12. Supported / Partially supported / Future scope

| Capability | Status |
|---|---|
| Bangla (bn-BD) speech → text | ✅ Supported |
| English / Banglish dictation → NL search | ✅ Supported (via the same parser) |
| Budget / area / room-type / amenity / gender extraction | ✅ Supported (shared with typed AI search) |
| Move-in date extraction | ⏳ Not implemented (not in the parser today) |
| Metro/commute phrases ("metro er kache") | ✅ Supported via the search parser's metro keywords |
| Always-on / continuous listening | ❌ Deliberately off (`continuous: false`) |
| Server-side speech recognition (e.g. Whisper) | 🔜 Future scope — would add cost + upload; current in-browser approach is free and private |
