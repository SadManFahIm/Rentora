# Security Policy and Procedures

**Document status:** Living document — updated as controls ship.
**Audience:** Security researchers, maintainers, and operators of Rentora.

Rentora is a **public** repository by design: the source code is open and
readable. This policy describes the layered security model that makes that safe,
what we protect, how to report a finding, and how the project responds.

> **Operating principle.** Nothing sensitive ships in the repository. Every
> credential, endpoint, upload and log line is designed under the assumption
> that the source code is public, the network is hostile, and a human operator
> makes mistakes. Production runs hardened; the repo stays bite-free.

---

## 1. Purpose and Scope

This policy covers:

- The **platform** — the `frontend/` SPA and the `backend/` Django service
  (API, Celery workers, Channels socket, Django admin).
- The **delivery pipeline** — GitHub Actions CI/CD, dependency management,
  pre-commit hooks, and artifact handling.
- The **operational surface** — secrets, media/upload storage, database,
  cache/broker, and third-party provider integrations (AI, payments, SMS).

Out of scope: third-party services consumers choose to embed (MapLibre,
Crisp-style widgets, analytics vendors) — their own policies govern them.

---

## 2. The Layered Security Model

The repository is public; the protection is defense-in-depth:

| Layer | Mechanism |
|-------|-----------|
| **Legal** | License terms restrict reuse — see `LICENSE`. |
| **Secrets** | No credentials in the repo or the frontend bundle; every secret is an environment variable injected at deploy time (`.env.example` holds placeholders only). |
| **Automated detection** | Gitleaks secret scanning, `pip-audit` / `npm audit` dependency audits, GitHub CodeQL (Python + JavaScript), and `dependency-review` run in CI on every push/PR. |
| **Production defaults** | `config/settings/prod.py`: `DEBUG=False`, HTTPS-only redirect, HSTS, secure cookies, `X_FRAME_OPTIONS=DENY`, restricted `CORS_ALLOWED_ORIGINS`, rate limiting — verified by `docs/SECURITY_CHECKLIST.md`. |
| **Hardened transport & headers** | CSP, `Referrer-Policy`, `X-Content-Type-Options: nosniff`, `Permissions-Policy` and HSTS on every response; RFC 9116 `/.well-known/security.txt`. |

Nothing here claims a public repo "cannot be copied" — that is technically
impossible. What we guarantee is that *nothing sensitive ships in the repo*,
and that production is deployed hardened.

---

## 3. Supported Versions

| Branch | Support |
|--------|---------|
| `main` | ✅ Active development — security fixes land here first. |
| Feature branches (`feature/*`) | ❌ Experimental — bugs and regressions expected; PRs only. |
| Prior tagged releases | ⚠️ Best-effort — fixes are backported on demand, not guaranteed. |

If you are running Rentora in production, track `main` (or a maintained fork)
and subscribe to security advisories via the GitHub repository settings.

---

## 4. Reporting a Vulnerability

**Please do not open a public issue for a security concern.** Report privately:

- **GitHub Security Advisories (preferred)** — create a private draft at
  `https://github.com/SadmaFaahiim/Rentora/security/advisories`. This lets us
  coordinate a fix and disclosure timing in private before anything ships.
- **Email** — `security@rentora.example` *(placeholder — the maintainer will
  replace this with the real inbox before public launch)*.

Include as much of the following as possible:

1. **Endpoint / page** — the URL, route, or function affected.
2. **Reproduction** — minimal steps, request payloads (trim any credentials),
   and the affected software versions (Django, DRF, React versions, commit).
3. **Impact** — what an attacker could actually do (escalation, data leak,
   DoS, abuse of an AI tool, payment manipulation, …).
4. **Suggested fix (optional)** — a patch or design change is welcome.

> **Good hygiene.** Never include live credentials, personal data from real
> users, or provider API keys in a report. Use a throwaway account and dummy
> values. If you did stumble on real data, tell us that separately so we can
> rotate/revoke it — do not paste it into a ticket.

### 4.1 Disclosure and response timeline

| Step | SLA |
|------|-----|
| Acknowledge receipt | **2 business days** |
| Triage: confirm / refute, severity, scope | **5 business days** |
| Fix, test, and backport (critical/high) | **14 business days**; longer for complex or low-severity issues |
| Coordinated public disclosure | Agreed with you before publication (target ≤ 90 days after fix) |

We follow **coordinated disclosure**: we credit reporters in the advisory (by
name or alias, your choice) unless you ask to stay anonymous. If a fix cannot
be completed within 14 days we will tell you the blocker and a revised ETA
rather than going quiet.

### 4.2 Severity guidance (CVSS v3.1)

- **Critical (9.0–10.0)** — remote code execution, unauthenticated data
  exposure of PII/documents, payment integrity compromise.
- **High (7.0–8.9)** — authenticated privilege escalation, cross-tenant data
  access, XSS on a privileged page, SSRF, prompt-injection leading to a
  state-changing tool execution.
- **Medium (4.0–6.9)** — CSRF on state-changing flows, stored XSS in
  moderated content, rate-limit bypass, telemetry leaks of sensitive strings.
- **Low (0.1–3.9)** — cosmetic information disclosure, missing security
  headers on non-critical routes, minor DoS without amplification.

Severity is assigned by the maintainers and re-assessed if our analysis or an
advisory changes understanding.

---

## 5. Threat Model (What We Protect Against)

| Threat | Mitigation |
|--------|-----------|
| Credential theft / replay | Short-lived JWT (30-min access, 7-day rotating refresh), Django PBKDF2 password hashing, email-OTP 2FA + WebAuthn passkeys, per-endpoint and login/register rate limits (configured via the shared throttle helpers). |
| Account enumeration | Masked identifiers (phones return `+8801••••78`), SMS-OTP challenges hashed server-side, generic error envelopes on auth failures. |
| Rental marketplace scams | ML fraud engine (listing auto-scan, duplicate-image reuse, shared-phone **fraud rings**), review/photo moderation queues, graph-based risk scoring (Phase 17), PII masking in fraud pipelines. |
| AI tool misuse | Server-side tool permission layer: read-only tools execute + are audited; **state-changing** tools become human-review proposals; **high-risk** tools need role-level admin approval; provider HTTP error bodies are never echoed; prompt templates reject secret-laden values at validation time. |
| Upload abuse | Size + extension + content-type validation (`config/uploads.py`), magic-bytes + decompression-bomb guard, dimension/weight caps (≤ 5 MB, ≤ 10 photos), **private storage** for KYC/tenant documents (never the public media root), owner/admin-authenticated serving only. |
| Data leakage in analytics | First-party analytics with a bounded payload; no PII in event properties; sensitive fields scrubbed from logs, analytics, URLs and CSVs. |
| Injection / drive-by | Parameterized queries via the ORM, fenced template rendering, strict CSP + `nosniff`, RFC 9116 `security.txt`, audited admin actions. |
| Abuse / spam / harassment | Reports (7 categories) + blocking enforced server-side, report-rate limiting and duplicate-report folding, chat-safety engine flagging/blocking CRITICAL content. |
| Double-spend / booking races | `select_for_update` re-checks on booking create, idempotency keys on revenue ledger + commissions, single-flight lock on payment grant tokens. |

---

## 6. Secret Handling

- `.env`, `.env.local`, `.pem`, `.key`, `credentials*.json` and similar are
  **git-ignored**; only `.env.example` (placeholders) is committed.
- Backend secrets (`SECRET_KEY`, database password, payment/Cloudinary/SMTP
  secrets) are backend-only environment variables — **never** compiled into the
  frontend bundle.
- Frontend secrets are limited to the runtime `env` module (`VITE_` vars with
  safe defaults) and non-sensitive identifiers.
- **If a secret is suspected of leaking:** rotate it immediately, then remove
  it from the file **and** from history, then open an advisory so we can check
  blast radius. See `docs/SECURITY_CHECKLIST.md`.

---

## 7. Automated Security Testing (CI)

Defined in `.github/workflows/` (see `security.yml`):

- **Secret scanning** — Gitleaks on every push and PR; GitHub secret scanning +
  push protection should additionally be enabled in repository settings.
- **Dependency auditing** — `pip-audit` (backend) and `npm audit` (frontend),
  reported in the workflow log on every run.
- **Static analysis** — GitHub CodeQL for Python and JavaScript on push/PR and
  on a weekly schedule.
- **Dependency review** — `dependency-review` gates PRs that change dependency
  manifests against known-vulnerable packages.
- **Lighthouse gate** — the built app is audited against a 70/70 minimum
  (Accessibility/Best-practices/SEO), so UI-level security hints regress loudly.

Local gates should match CI before you push: `ruff` + `manage.py check` for the
backend, `tsc` + ESLint + Prettier for the frontend (wired into the pre-commit
hook chain).

---

## 8. Incident Response

If an incident is suspected in a **deployed** environment:

1. **Contain** — stop credentials: revoke access tokens / API keys, roll the
   `SECRET_KEY` if rotation is authenticated; suspend affected accounts.
2. **Preserve evidence** — snapshot logs (structured JSON), app screenshots,
   request IDs (`X-Request-ID` correlation middleware), and any audit entries
   before changing state.
3. **Assess** — classify via the CVSS table above; check blast radius through
   the audit trail (append-only `AuditLogEntry`) and the AI execution log.
4. **Notify** — if personal data was involved, follow the local data-protection
   notification duties applicable to your deployment region.
5. **Fix & disclose** — ship the patch on `main`, backport if needed, and
   publish a GitHub Security Advisory with the timeline in §4.1.

The **audit trail** (append-only, read-only admin view) and **structured JSON
logging** are deliberately built to make steps 2–5 tractable.

---

## 9. Data Protection and Privacy

- **KYC documents** are private-storage objects served only through an
  authenticated owner/admin endpoint; landlords see a **✓ Identity Verified
  badge**, never the document, the NID number, or the file URL.
- **Fraud pipelines** mask PII (phones, NID, email) and sanitize failure
  reasons before they reach logs or provider results.
- **Analytics are first-party** with a bounded event payload; sensitive query
  strings and URLs are scrubbed before storage.
- **Copilot / AI** answers are **grounded**: every room card is rebuilt from
  stored public-only keys; no provider response is echoed unsanitized.
- Reviews note honestly when data is derived (e.g., statistical pixel vision,
  "not a valuation", moderation holds) rather than pretending certainty.

---

## 10. Checklist and Audits

- `docs/SECURITY_CHECKLIST.md` — the full, living checklist for production
  hardening.
- `docs/SECURITY_AUDIT.md` — the latest audit report.
- `docs/LIVE_VERIFICATION.md` — what was manually verified against a running
  stack, and how.

---

## 11. Contact

Privately report via the channels in §4. For everything else, open a normal
issue or PR — this policy itself is open to improvement.

_Last reviewed: 2026-08-30_