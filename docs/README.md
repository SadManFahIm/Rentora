# Rentora documentation

Documentation is grouped by purpose so the repo stays navigable as it grows.

| Path | Content |
|------|---------|
| [`architecture.md`](architecture.md) | System design, data model, flows, deployment |
| [`api-reference.md`](api-reference.md) | Full endpoint reference + curl examples |
| [`adr/`](adr/) | Architecture Decision Records (0001, 0002, …) |
| [`phases/`](phases/) | Per-phase specs — Phase 12…19.2, tier 1–5 upgrades |
| [`guides/`](guides/) | Feature deep-dives — Copilot, map, PWA, auth, search, payments |
| [`ops/`](ops/) | Operational runbooks — backup/restore |
| [`security/`](security/) | Security audit report + production checklist |
| [`screenshots/`](screenshots/) | Demo gallery, phase-by-phase (79 shots) |
| [`tools/`](tools/) | Repo tooling — API verify, schema drift, screenshot capture |

New docs: phase specs go in `phases/`, feature deep-dives in `guides/`,
cross-cutting decisions in `adr/`. Screenshots from the capture scripts always
land in `screenshots/`.