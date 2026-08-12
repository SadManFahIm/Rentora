# Security Policy

Rentora is a **public** repository: the source code is publicly readable by
design. That means the repository's security model is layered —

1. **Legal protection** (license terms restrict reuse — see `LICENSE`).
2. **Secret protection** (no credentials in the repo; everything comes from
   environment variables at deploy time).
3. **Automated detection** (secret scanning, dependency auditing, CodeQL in CI).
4. **Secure production defaults** (`config/settings/prod.py`: `DEBUG=False`,
   HTTPS-only, HSTS, restricted CORS, rate limiting).

Nothing in this policy claims a public repo "cannot be copied" — that is
technically impossible. What we guarantee is that *nothing sensitive ships in
the repo*, and that production runs hardened.

## Supported Versions

| Branch | Supported |
|--------|-----------|
| `main` | ✅ Active development |
| other branches | ❌ Experimental — PRs only |

## Reporting a Vulnerability

Found something? **Do not open a public issue.** Open a private report:

- **GitHub Security Advisories:** create a draft advisory at
  `https://github.com/SadmaFaahiim/Rentora/security/advisories` (preferred —
  it lets us coordinate privately before disclosure).
- **Email:** `security@rentora.example` — placeholder; the maintainer will
  replace this with a real inbox before public launch.

Please include:

- The affected endpoint/page and how to reproduce it.
- Impact (what an attacker could do).
- Suggested fix (optional — we welcome patches).

### Responsible disclosure timeline

1. We acknowledge the report within **5 business days**.
2. We confirm/refute and scope a fix within **14 business days**.
3. We coordinate a disclosure date with you before publishing.

## What We Check Automatically

- **Secret scanning** — Gitleaks in CI (`.github/workflows/security.yml`)
  scans every push/PR for credentials; GitHub secret scanning + push
  protection should be enabled in the repository settings too.
- **Dependency auditing** — `pip-audit` (backend) and `npm audit`
  (frontend) run in CI and are reported in the workflow log.
- **Static analysis** — GitHub CodeQL scans Python + JavaScript on push/PR
  and on a weekly schedule.
- **Dependency review** — PRs that change dependencies are checked for known
  vulnerable packages via `dependency-review`.

## Secret Handling

- `.env` / `.env.local` / `.pem` / `.key` / `credentials*.json` are
  git-ignored; only `.env.example` (placeholder values) is committed.
- Backend secrets (`SECRET_KEY`, DB password, Cloudinary secret, SMTP
  password, payment secrets) are **backend-only env vars** — never in the
  frontend bundle.
- If you suspect a secret was committed, **rotate it immediately**, then
  remove it from the file and history (see `docs/SECURITY_CHECKLIST.md`).

## Production Security Expectations

- `DEBUG=False`, `SECURE_SSL_REDIRECT=True`, HSTS enabled, secure cookies,
  `X_FRAME_OPTIONS=DENY`, restricted `CORS_ALLOWED_ORIGINS` — all enforced by
  `config/settings/prod.py` and covered by `docs/SECURITY_CHECKLIST.md`.
- Auth: JWT (30-min access / 7-day rotating refresh), bcrypt-free Django
  PBKDF2 hashing, email-OTP 2FA + passkeys, login/register rate-limited.
- File uploads: size + extension + content-type validation
  (`config/uploads.py`), KYC documents served through an authenticated
  owner/admin-only endpoint (never from public media).

See `docs/SECURITY_CHECKLIST.md` for the full checklist and
`docs/SECURITY_AUDIT.md` for the latest audit report.
