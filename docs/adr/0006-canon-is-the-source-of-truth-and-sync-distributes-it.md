---
status: accepted
---
# Shared files have one master in `canon/`, distributed by `watermill sync`

The crew agents, 11 adapted skills, the guardrail hook and the managed settings entries live once in water-mill's `canon/`; `watermill sync <project>` opens a CI-gated PR per repo, merges only its own marked entries into `.claude/settings.json`, and writes a "managed by water-mill" header. `validate` fails on drift, so editing a synced copy is caught. Sync never merges its PR. Before this, the crew was hand-copied to four places that had to be kept identical (memory note `mill-crew-in-repos`, 2026-08-30). Source: epic water-mill-fwm, water-mill-fwm.2, `canon/README.md`.

## Consequences

The workshop folder is not a git repo and unreachable from cloud sessions, so its master stays in canon and the owner runs `watermill sync workshop` on the laptop. Hillel-Programming is synced in full, crew files included; the earlier hardcoded exemption was dropped (owner correction 2026-10-14, superseding water-mill-9tx).
