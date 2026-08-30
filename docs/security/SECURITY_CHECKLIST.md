# Security Checklist

Working checklist for the public-repo hardening posture. Everything here is
either automated (CI) or verified by the audit in `SECURITY_AUDIT.md`. Run
through it before a release.

## Repository

- [x] No secrets committed to `main` (Gitleaks in CI; history scanned)
- [x] `backend/.env`, `frontend/.env`, `frontend/.env.local` git-ignored
- [x] `.env.example` files contain placeholders only
- [x] Git history checked for leaked credentials (see `SECURITY_AUDIT.md`)
- [x] License policy documented (see README → License)

## Backend

- [x] `DEBUG=False` in production (`config/settings/prod.py`)
- [x] `SECRET_KEY` from environment (never committed)
- [x] Authentication: JWT access 30 min / refresh 7 days with rotation
- [x] Passwords hashed with Django PBKDF2 (never logged or returned)
- [x] Authorization server-side on every sensitive endpoint
      (tests: `rooms/tests_security.py` — IDOR, admin-only, cross-user)
- [x] CORS restricted to an explicit allow-list (no wildcard)
- [x] CSRF not disabled; DRF sessions untouched by design (JWT-only auth)
- [x] Rate limiting: `anon 100/hr`, `user 1000/hr`, `auth 10/hr` (login,
      register, OTP), `payment_initiate 5/hr`
- [x] SQL via ORM only (no raw SQL with string interpolation)
- [x] Stored-XSS guard: titles/descriptions sanitized (`config/sanitizers.py`)
- [x] File uploads validated (size / extension / content-type) —
      room images `config/uploads.py`, KYC docs inline in the view
- [x] KYC documents served owner/admin-only (404 otherwise), never public
- [x] Error responses sanitized (unified envelope, no stack traces —
      `config/exceptions.py`)

## Frontend

- [x] No private API keys in the bundle (only public Cloudinary/config keys)
- [x] Tokens in `localStorage` for the SPA session (documented trade-off);
      no secrets in the bundle
- [x] User-generated content rendered safely (sanitized server-side first)

## Infrastructure / CI

- [x] GitHub Actions permissions minimized (`contents: read`)
- [x] Secret scanning workflow (Gitleaks)
- [x] Dependency auditing (pip-audit + npm audit)
- [x] CodeQL static analysis (Python + JS)
- [x] Dependency review on PRs
- [ ] GitHub repo settings (manual — owner only):
  - [ ] Enable **Secret scanning** → Push protection
  - [ ] Enable **Dependabot alerts** + **Dependabot security updates**
  - [ ] Enable **CodeQL** (or rely on the workflow in this repo)
  - [ ] Branch protection on `main`: require PR + CI checks + 1 review
  - [ ] Enable **Private vulnerability reporting**

## Release Gate

- [ ] `pip-audit` clean (backend)
- [ ] `npm audit` — no *new* high/critical introductions
      (known items tracked in `SECURITY_AUDIT.md`)
- [ ] Full backend + frontend test suites green
- [ ] `DEBUG=False` + HTTPS confirmed on the deployed environment
- [ ] Secrets rotated if any doubt about exposure

## Rotation procedure (if a secret leaks)

1. Rotate immediately (Django `SECRET_KEY`, DB password, Cloudinary, SMTP,
   payment credentials).
2. Remove the value from the current file and `git rm --cached` it.
3. Purge it from history **only with explicit approval** — rewriting public
   history rewrites every fork's view of the repo and requires force-push
   coordination. Weigh rotation vs. rewrite; usually rotation alone is enough.
