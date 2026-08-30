<!--
  Title convention: <type>(<scope>): <summary>
  e.g. feat(rental-agent): phishing-resistant proposal signing
       fix(analytics): strip doubled /api/v1 prefix
       docs(security): professional SECURITY.md policy
       chore(ci): pin ruff version
-->
## Summary

_One or two sentences describing what this PR does._

## What & why

- **What** — _what changed (feature / fix / refactor), with file or app names._
- **Why** — _the problem being solved and why this approach._

## Files touched

- `backend/<app>/…` — …
- `frontend/src/…` — …

## Testing

- [ ] `make check` (lint + format + typecheck + backend/frontend tests) passes locally
- [ ] CI is fully green (Vitest+build, Django tests, gitleaks, Playwright, contract/schema drift, npm audit, Lighthouse)
- [ ] Manual verification performed (steps) —
- [ ] Migration included / not needed (circle one) — 

## Screenshots

_Add screenshots for any UI change into the PR body (capture via_
_`frontend/scripts/capture_*.mjs`, store under `docs/screenshots/`)._

| Before          | After           |
| --------------- | --------------- |
| _paste_         | _paste_         |

## Rollout / rollback

- How this ships (feature flag? flag name?) —
- One-click rollback plan —