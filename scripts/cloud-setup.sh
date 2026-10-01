#!/usr/bin/env bash
# Bring a fresh Claude Code cloud container up to a working mill.
#
# A cloud session starts from a clean clone: no `bd`, no bootstrapped beads
# database (beads live in Dolt under refs/dolt/data, which a git clone does not
# materialise), and no .venv. Without this, the SessionStart `bd prime` hook
# fails, the crew agents (millstone/sluice/tailrace) cannot read the bead they
# are handed, and `make verify` refuses for want of .venv.
#
# Idempotent: every step checks before it acts, so it is safe on every session
# start. Runs for water-mill and for every sibling checkout that carries a
# .beads/ directory (zimmy-life-tracker, a stamped cell).
#
# Only does anything when CLAUDE_CODE_REMOTE=true, unless --force is given, so
# the hook never touches a laptop's setup.

set -euo pipefail

if [[ "${CLAUDE_CODE_REMOTE:-}" != "true" && "${1:-}" != "--force" ]]; then
  exit 0
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PARENT="$(dirname "$HERE")"

log() { echo "cloud-setup: $*" >&2; }

if ! command -v bd >/dev/null 2>&1; then
  log "installing bd (@beads/bd)"
  npm install -g @beads/bd >/dev/null 2>&1
fi
bd metrics off >/dev/null 2>&1 || log "bd metrics off failed (harmless)"

for repo in "$PARENT"/*/; do
  repo="${repo%/}"
  [[ -d "$repo/.beads" && -d "$repo/.git" ]] || continue
  name="$(basename "$repo")"
  chmod 700 "$repo/.beads"
  git -C "$repo" config beads.role >/dev/null 2>&1 \
    || git -C "$repo" config beads.role maintainer
  if (cd "$repo" && bd ready >/dev/null 2>&1); then
    log "$name: beads database present"
  else
    log "$name: bootstrapping beads from refs/dolt/data"
    (cd "$repo" && bd bootstrap >/dev/null 2>&1) \
      || log "$name: bd bootstrap failed; run it by hand in $repo"
  fi
done

if [[ ! -x "$HERE/.venv/bin/python" ]]; then
  log "water-mill: make install"
  make -C "$HERE" install >/dev/null
fi

log "done"
