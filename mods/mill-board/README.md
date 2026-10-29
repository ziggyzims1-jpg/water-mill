# mill-board

A Claude Code mod for the session that orchestrates the mill crew. It adds:

- **Mill board** pane: the child sessions the orchestrator is running (state,
  PR, a short note), the subagents running in this session, the beads in
  progress, and the follow-up beads filed since the session started (with
  their `auto-mill`, `human`, `fence` and `live-api` labels).
- **Questions for you** pane: every open question the orchestrator has for
  the owner, with its context and a **Mark answered** button.
- A line above the prompt: the 5-hour and weekly usage windows with time to
  reset, context fill, session cost and the number of open questions. A figure
  turns amber at 80% and red at 95%.

`/mill-board` and `/owner-questions` reopen the panes.

## Where it draws

Mods draw in a terminal session and in the desktop app's **Code** tab (a local
session, v2.1.286 or later). A **cloud** session runs the hooks but draws
nothing: `$.ui.open` answers `isPlaced: false` with reason `no-surface`
(docs: "Where mods run" in the mods overview). Run the orchestrating session
locally to see it.

## Where the data comes from

- **Beads** are read by the mod itself, every 5 minutes and on **Refresh
  beads**: `git fetch origin main`, then `origin/main:.beads/issues.jsonl`, for
  every folder beside the session's repo (or inside the session's folder, when
  that is a workshop folder and not a repo) that holds `.beads/issues.jsonl`.
- **Child sessions and questions** cannot be seen by a mod, so the
  orchestrator reports them through the tool the mod adds,
  `mcp__mill-board__update`: `sessions` replaces the list, `questions` adds or
  rewrites questions by id, `resolve` marks ids answered, `refreshBeads`
  re-reads the beads, and `diagnose` reports which surfaces are attached and
  whether each pane is placed.
- **Usage** comes from the engine (`session.measure`).

The board and the questions live in the session's state: a new session starts
empty until the orchestrator reports again.

## Install

At the prompt of a terminal session:

```
/plugin install mill-board --marketplace ziggyzims1-jpg/water-mill
```

From a shell: `claude plugin install mill-board --marketplace ziggyzims1-jpg/water-mill`.
In the desktop app, where `/plugin` does not run: click + next to the prompt
box, then Plugins, Add marketplace with `ziggyzims1-jpg/water-mill`, then Add
plugin.

## Developing

```bash
claude plugin validate mods/mill-board
claude plugin test mods/mill-board
claude --plugin-dir mods/mill-board     # run a session with it loaded
```
