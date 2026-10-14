# ~/Documents/code — the workshop

Repos here: `water-mill` (the orchestrator), `zimmy-life-tracker` (its first
target), `watermill-cell-template` and the `*-cell-*` client cells stamped
from it. The mill crew (`millstone` → `bolter` → `sluice` → `tailrace`) lives in
`.claude/agents/`, rendered from water-mill's `canon/` by `watermill sync`.

## Beads live in git — push them (owner's rule, 2026-09-03)

Beads are only useful to Andrew if they're reachable from any machine. Every
repo with a `.beads/` tracks `issues.jsonl` in git, and the bd git hooks
(`bd hooks install`) re-export it on commit. The rule: any session or agent
that creates, updates, closes, or defers beads commits and pushes
`.beads/issues.jsonl` (a `chore(beads): …` commit is fine) before signing
off — bd writes with no git push are invisible off this machine.

## Every agent writes a handoff before signing off

No agent — orchestrator, millstone, sluice, tailrace, or an ad-hoc helper —
ends its turn without a handoff note. A compaction summary is a mechanical
squeeze of a transcript; a handoff is written by the agent that still holds the
context and knows which of the last forty tool calls mattered.

- **Orchestrator / session-level work in a repo:** that repo's `handoff` skill
  (`zimmy-life-tracker/.claude/skills/handoff/SKILL.md`) →
  `brain/handoffs/<role>.md`, overwritten. Water-mill uses `HANDOFF.md`.
- **Mill crew, per bead:** `brain/handoffs/mill/<slug>.md` (water-mill keeps
  them in `HANDOFF-mill/`; each repo's `CLAUDE.md` says where), one file per
  bead, each agent appending its own dated section (`## Millstone`,
  `## Bolter`, `## Sluice`, `## Tailrace`). The lander marks the file `**LANDED**`.
- **Ad-hoc agents** (a general-purpose helper working a branch): end the final
  report with a `## Handoff` section in the same shape — where things stand,
  what was tried and did not work, do this first, open questions.

The rule for all of them: say what failed, name files and functions, no diffs,
one page. Written even when blocked — especially when blocked.

## Auto-mill: smells filed by the reviewer run through the crew next (owner's rule, 2026-10-14)

Sluice files a bead for a clearly-defined smell (it names the file, the smell
and a concrete fix) labelled `auto-mill`, priority P3, in the same repo. The
orchestrator that lands the parent bead runs each `auto-mill` bead through the
full crew (millstone, bolter, sluice, tailrace) right after, without asking.
The limits are the rule, not a suggestion:

- **Depth 1.** A smell found while working an `auto-mill` bead is filed as an
  ordinary bead, never labelled `auto-mill`, never auto-run.
- **At most 2 per parent bead.**
- **Never auto-run anything touching the fence, security code, the schema or
  CI.** Those are filed as ordinary beads for the owner.
- P3, same repo as the parent, nothing cross-repo.

The master copy of this rule is `canon/workshop/CLAUDE.md` in water-mill, and it
is repeated in water-mill's own `CLAUDE.md`, `sluice.md`, `tailrace.md` and
`docs/AI.md`.

## Where the AI setup is described

`water-mill/docs/AI.md` describes every AI adaptation across these repos: the
harnesses and hooks, the crew, the rules and where each lives, the skills, cloud
constraints, `watermill sync` and the trial harness.
