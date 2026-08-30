# ADR-0001: Use Architecture Decision Records

- **Status:** accepted
- **Date:** 2026-08-30
- **Context:** Rentora ships one phase a day. Fast-moving features (AI agents,
  monetization, trust & safety) accumulate architectural choices that are
  easy to forget or re-litigate without a written record.

## Decision

Record consequential architecture decisions as **ADR files** in
`docs/adr/`, one per decision:

- **Numbering:** `NNNN-short-slug.md`, monotonic (0001, 0002, …).
- **Template:** Status · Date · Context · Decision · Consequences.
- **When to write one:** a decision affects more than one layer/app, changes a
  public contract, adds a dependency, or changes the deploy shape.
- **Review:** a PR that ships a new ADR is reviewed like any other code; ADRs
  are *living* — superseded decisions get a "Superseded by ADR-NNNN" status
  line rather than deletion.

## Consequences

- Decisions are auditable and reproducible, matching the platform's
  phase-documentation culture.
- Minor implementation details stay out of ADRs — they belong in phase docs.
- ADR-0002 records the platform's founding conventions as the seed set.