# Security Audit Report

**Date:** 2026-08-12 · **Scope:** full repository (backend + frontend + CI +
git history) · **Auditor:** automated scan + manual review

Summary of posture: **Good.** No credentials in the repo or history, hardened
production settings, server-side authorization with regression tests. Two
findings fixed during this audit (file-upload validation, `cryptography`
CVE). Remaining items are dev-only dependency advisories that need
major-version upgrades (approval required).

| Severity | Count | Status |
|----------|-------|--------|
| Critical | 0 | — |
| High | 2 | dependency advisories (dev/transitive) |
| Medium | 3 | dependency advisories (dev/transitive) |
| Low | 1 | file-upload validation — **fixed** |
| Informational | 4 | see below |

---

## Findings

### 1. File upload validation on room images — LOW — FIXED
- **Location:** `rooms/serializers.py` (`uploaded_images`), `rooms/models.py`
  (`RoomImage.image` bare `ImageField`)
- **Risk:** an uploader could submit arbitrarily large / non-image files as
  listing photos (image-bomb / storage abuse).
- **Fix (shipped):** `config/uploads.py` — 5 MB cap + extension +
  content-type allow-list, wired into the serializer. KYC documents were
  already validated in `users/views.py` (5 MB + content-type + extension).
- **Tests:** `rooms/tests_security.py` (non-image, oversized, valid).

### 2. Backend dependency — cryptography — HIGH — FIXED
- **Location:** `requirements.txt` pinned `cryptography==49.0.0`
- **Advisory:** PYSEC-2026-3552 · fixed in `50.0.0`
- **Action:** upgraded to `50.0.0`; `pip-audit` now clean.

### 3. Frontend dependency advisories — HIGH/MODERATE — DOCUMENTED (needs approval)
`npm audit` (2026-08-12): 4 remaining after `npm audit fix` (no non-breaking
fix available).

| Package | Severity | Issue | Installed | Fixed in | Notes |
|---------|----------|-------|-----------|----------|-------|
| `vite` | high | dev-server path traversal + Windows NTLM leak | 5.4.21 | 6.4.3+ (major) | **dev-only**; never reaches production |
| `nanoid` | high | custom-generator infinite loop | <3.3.17 (transitive) | 3.3.17+ | dev/transitive |
| `react-router-dom` | moderate | open redirect via `<Link>`/`useNavigate` | 6.30.4 | 7.17.0+ (major) | **breaking upgrade** (v6→v7 router migration) |
| `react-router` | moderate | (via above) | 6.30.4 | 7.17.0+ (major) | — |

- **Recommendation:** dedicate a follow-up PR to the `react-router` v6→v7
  migration (data-router APIs) and a Vite 6 upgrade; both are breaking-change
  upgrades that need review, not a silent bump. No production runtime
  exposure today (all dev-server/transitive).
- `esbuild` (moderate) was resolved by dedupe during `npm audit fix`.

### 4. Secrets in repo / history — NONE FOUND — PASS
- Gitleaks-pattern grep over all tracked files + full git history:
  **0 matches** for AWS/Google/OpenAI/GitHub-token/SECRET_KEY patterns.
- `backend/.env`, `frontend/.env`, `frontend/.env.local` are git-ignored;
  only `.env.example` (placeholders) is tracked.

### 5. Production settings — PASS
- `config/settings/prod.py`: `DEBUG=False`, `ALLOWED_HOSTS` env-driven,
  `SECURE_SSL_REDIRECT=True`, HSTS 1y + subdomains + preload, secure
  session/CSRF cookies, `SECURE_CONTENT_TYPE_NOSNIFF`,
  `SECURE_BROWSER_XSS_FILTER`, `X_FRAME_OPTIONS=DENY`, HTTPS proxy header.
- CORS: explicit allow-list from env — **no wildcard**.

### 6. Authentication / rate limiting — PASS
- JWT: 30-min access, 7-day rotating refresh (`SIMPLE_JWT`).
- Throttles: anon 100/hr, user 1000/hr, `auth` 10/hr (login/register/OTP),
  `payment_initiate` 5/hr.
- Passwords: Django PBKDF2; never logged or serialized.

### 7. Authorization / IDOR — PASS (tests added)
- Admin-only fraud endpoints return 403 for normal users.
- Users cannot update/delete other users' rooms (403).
- KYC documents: owner/admin-only; strangers get **404** (id-guessing can't
  confirm existence).
- Covered by `rooms/tests_security.py` (9 tests).

### 8. XSS / injection — PASS
- Room titles/descriptions sanitized (`config/sanitizers.py`) against stored
  XSS; ORM-only queries (no raw SQL).

---

## Informational

- **CSRF:** N/A in practice — the API is JWT-authenticated (no session
  cookie), so CSRF doesn't apply to API calls; Django CSRF remains enabled
  for the Django admin.
- **localStorage tokens:** the SPA keeps JWTs in `localStorage` (XSS-exposed
  by design). Acceptable for this stage; move to httpOnly cookies behind a
  CSRF-appropriate scheme when the auth surface grows.
- **License:** the repo has no LICENSE file yet — see README → License.
  "Public on GitHub" does **not** grant reuse rights; a license decision is
  required before third-party reuse is permitted or restricted.
- **SECURITY.md contact:** placeholder email — replace before launch.

---

## Follow-up (requires owner approval)

1. `react-router` v6 → v7 migration (fixes open-redirect CVEs).
2. Vite 6 upgrade (dev-only fixes; verify build + e2e).
3. Add GitHub repo settings: secret-scanning push protection, Dependabot
   alerts, branch protection on `main` (see `SECURITY_CHECKLIST.md`).
4. Decide the license (see README → License).
