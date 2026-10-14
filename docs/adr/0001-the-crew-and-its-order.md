---
status: accepted
---
# The crew is millstone, bolter, sluice, tailrace, in that order

Work goes through four single-purpose agents: millstone implements, bolter reviews standards (report-only), sluice reviews the spec and independently verifies (the only reviewer that pushes), tailrace lands. Bolter was added on 2026-10-14 so that sluice could spend its attention on whether the change does what the bead asked; splitting the roles keeps exactly one agent writing to a branch under review. Source: epic water-mill-fwm and child water-mill-fwm.4, `CLAUDE.md` ("Auto-mill follow-ups"), `canon/common/.claude/agents/`.

## Considered options

The earlier crew was millstone, sluice, tailrace (memory note `mill-crew-in-repos`, 2026-08-30). The epic keeps sluice's spec review and verification "as now" and adds standards review as a separate, report-only role.

## Consequences

Bolter's blocking findings (a broken documented standard or ADR) must be fixed or rebutted by sluice in the handoff; smells are advisory and never block. This is why `CODING_STANDARDS.md`, `docs/adr/` and `CONTEXT.md` exist in each repo (water-mill-fwm.6).
