---
status: accepted
---
# Reviewer-filed smell beads run through the crew, with hard limits

Owner's rule, 2026-10-14: sluice files a bead for a clearly-defined smell (file, smell, concrete fix), labelled `auto-mill`, P3, same repo, and the orchestrator that landed the parent runs it through the full crew right after. The limits are the rule: depth 1 (a smell found while working an `auto-mill` bead is filed normally and never auto-run), at most 2 per parent, and never anything touching the fence, security code, schema or CI. The limits keep self-generated work bounded; `docs/ONBOARDING.md` requires a queue deep enough that the agent never has to invent work. Source: epic water-mill-fwm, `CLAUDE.md` ("Auto-mill follow-ups"), `canon/workshop/CLAUDE.md`.
