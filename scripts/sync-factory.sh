#!/usr/bin/env bash
# Keep the water-mill checkout fresh at session start.
#
# The context graph (knowledge/findings.jsonl), the crew agent definitions and
# these scripts all live in water-mill, and every other repo's agents read them
# through a sibling checkout. A checkout that is days behind means agents
# recall a stale graph and append to a file that will conflict on push.
#
# Fast-forward only, and only when it is safe: on main, clean tree, not
# mid-merge. Anything else is left exactly as it is.
#
# After the fast-forward it also prints `watermill review --lag` (landed beads
# with no finding) to stderr, so a stale graph is visible at session start. If
# the flag does not exist yet the command fails and nothing is printed.
#
# This runs inside a SessionStart hook, so it must NEVER fail and NEVER print to
# stdout: `bd prime --hook-json` runs after it and its JSON must be the whole of
# stdout. Every exit is 0, stdout is discarded, and the one line it may write
# (on a successful update) goes to stderr. The pull is bounded by a timeout so a
# dead network or a slow iCloud-synced .git cannot hold the session.
#
# Usage: sync-factory.sh [water-mill dir]   (default: the checkout this lives in)

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)" || exit 0
DIR="${1:-$HERE}"
LIMIT="${SYNC_FACTORY_TIMEOUT:-20}"

main() {
  [ -d "$DIR/.git" ] || return 0
  export GIT_TERMINAL_PROMPT=0
  local branch before after
  branch="$(git -C "$DIR" symbolic-ref --short -q HEAD)" || return 0
  [ "$branch" = "main" ] || return 0
  [ -z "$(git -C "$DIR" status --porcelain --untracked-files=no)" ] || return 0
  [ ! -e "$DIR/.git/MERGE_HEAD" ] && [ ! -d "$DIR/.git/rebase-merge" ] \
    && [ ! -d "$DIR/.git/rebase-apply" ] || return 0
  before="$(git -C "$DIR" rev-parse HEAD)" || return 0
  git -C "$DIR" pull --ff-only --quiet origin main || return 0
  after="$(git -C "$DIR" rev-parse HEAD)" || return 0
  [ "$before" = "$after" ] || echo "sync-factory: water-mill ${before:0:7} -> ${after:0:7}" >&2
}

lag() {
  [ -x "$DIR/bin/watermill" ] || return 0
  local out
  out="$("$DIR/bin/watermill" review --lag 2>&1)" || return 0
  [ -z "$out" ] || printf '%s\n' "$out" >&2
}

# bash has no portable `timeout` (macOS lacks it), so bound main with a watchdog.
{ main; lag; } >/dev/null &
worker=$!
( sleep "$LIMIT"; kill "$worker" 2>/dev/null ) >/dev/null 2>&1 &
watchdog=$!
wait "$worker" >/dev/null 2>&1
kill "$watchdog" >/dev/null 2>&1
exit 0
