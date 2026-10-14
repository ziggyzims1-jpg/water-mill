#!/usr/bin/env bash
# Make beads work, in EVERY sibling checkout, in a Claude Code cloud container.
#
# A cloud session starts from a clean clone: no `bd`, no beads database (it
# lives in Dolt, not in the clone), no .venv, and a GitHub proxy that rejects
# any push that is not a branch, so a `bd dolt push` (or a Dolt auto-push) to
# refs/dolt/data fails with 403.
#
# So here: install bd (pinned), and for water-mill and every sibling checkout
# that carries a .beads/ (zimmy-life-tracker, the cell template, a stamped
# cell, cheme-solver, Hillel-Programming...) build the local database from the
# tracked .beads/issues.jsonl (never from refs/dolt/data) with no Dolt remote,
# and force Dolt auto-push off for this container (BD_DOLT_AUTO_PUSH=false). No
# tracked file is changed or committed. Bead changes then travel as
# .beads/issues.jsonl commits on the session branch
# (`bd export -o .beads/issues.jsonl`), and the beads-sync workflow merges
# them into main. Finally `make install` for water-mill itself.
#
# Idempotent. Does nothing unless CLAUDE_CODE_REMOTE=true (or --force), so the
# SessionStart hook never touches a laptop's setup or sync config. Never pass
# --force on a laptop checkout: the script works on every sibling of the
# checkout it lives in (~/Documents/code there) and imports each jsonl into
# that repo's live db. --force is for tests, which copy the script into a temp
# <parent>/water-mill/scripts/ first (tests/test_cloud_setup.py).
#
# The SessionStart hook only fires when the session's cwd is inside a repo that
# carries it. A routine's orchestrator starts in /home/user (not a repo), so
# the hook does NOT fire there: a routine orchestrator must run
# `bash <checkout>/water-mill/scripts/cloud-setup.sh` by hand, first.
#
# Each repo's bd prefix is derived from its own issue ids, never hard-coded.

set -euo pipefail

if [[ "${CLAUDE_CODE_REMOTE:-}" != "true" && "${1:-}" != "--force" ]]; then
  exit 0
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PARENT="$(dirname "$HERE")"
log() { echo "cloud-setup: $*" >&2; }

# Pinned to the laptop's bd so the database schema and issues.jsonl format
# match; bd >= 1.2 also leaves Dolt auto-push off unless dolt.auto-push=true.
BD_VERSION=1.2.2

# Container-only, and never written to a tracked config.yaml: the env var
# overrides that file. CLAUDE_ENV_FILE carries it into the session's later
# Bash commands.
export BD_DOLT_AUTO_PUSH=false
if [[ -n "${CLAUDE_ENV_FILE:-}" ]]; then
  grep -qs '^export BD_DOLT_AUTO_PUSH=false$' "$CLAUDE_ENV_FILE" \
    || echo 'export BD_DOLT_AUTO_PUSH=false' >> "$CLAUDE_ENV_FILE"
else
  # Seen empty in a cloud Bash tool call: the setting then does not outlive
  # this script, so every later bd command needs it set on the command itself.
  log "CLAUDE_ENV_FILE is empty: BD_DOLT_AUTO_PUSH=false is not carried into later commands; set it on every bd command (BD_DOLT_AUTO_PUSH=false bd ...)"
fi

if ! command -v bd >/dev/null 2>&1; then
  log "installing bd (@beads/bd@$BD_VERSION)"
  npm install -g "@beads/bd@$BD_VERSION" >/dev/null 2>&1 || { log "bd install failed"; exit 0; }
else
  # Policy: a bd already on PATH is used as is, even when it is not the pin.
  # The container's existing database was built by that bd, and installing the
  # pin over it could strand that database on a schema the pin cannot read
  # (the first cloud run had bd 1.3.1 and a db it had built); the import below
  # reads JSONL either way. We say so on stderr instead of replacing it.
  have_bd="$(bd --version 2>/dev/null | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true)"
  [[ "$have_bd" == "$BD_VERSION" ]] \
    || log "using bd ${have_bd:-of unknown version} already on PATH (pin is $BD_VERSION); not reinstalling"
fi
bd metrics off >/dev/null 2>&1 || true

# The bd prefix of a repo: its issue ids are <prefix>-<suffix> where the suffix
# has no '-' (zimmy-life-tracker-6wo.1 -> zimmy-life-tracker). The most common
# prefix wins, so one stray id cannot move it. Falls back to the directory name
# when the jsonl has no issues yet. Only prefixes bd init accepts as a database
# name count (a letter or _, then letters, digits, _ or -): zimmy-life-tracker
# carries 103 zimmy-life-tracker-* ids and 101 newer "Zimmy Life Tracker-*" ones
# (its laptop db's prefix), and bd init --prefix "Zimmy Life Tracker" fails, so
# without the filter two more laptop beads would leave its cloud db unbuilt.
derive_prefix() {
  local jsonl="$1/.beads/issues.jsonl" prefix=""
  if [[ -s "$jsonl" ]]; then
    prefix="$(sed -nE 's/^\{("_type":"issue",)?"id":"([^"]+)".*/\2/p' "$jsonl" \
      | sed -E 's/-[^-]*$//' | { grep -E '^[A-Za-z_][A-Za-z0-9_-]*$' || true; } | sort | uniq -c | sort -rn | head -1 \
      | sed -E 's/^[[:space:]]*[0-9]+ //')"
  fi
  echo "${prefix:-$(basename "$1")}"
}

setup_repo() {
  local repo="$1" name prefix head saved init_commit exclude path
  name="$(basename "$repo")"
  cd "$repo"
  prefix="$(derive_prefix "$repo")"

  chmod 700 .beads
  git config beads.role >/dev/null 2>&1 || git config beads.role maintainer

  if bd ready >/dev/null 2>&1; then
    log "$name: beads database present"
  else
    log "$name: building beads database from .beads/issues.jsonl (prefix $prefix)"
    # bd init bootstraps from refs/dolt/data when config.yaml has a sync.remote
    # or the git origin carries that ref, and wires that URL in as the
    # database's Dolt remote. So for the init only: hide sync.remote, blank the
    # origin URL for bd's git calls (GIT_CONFIG_* env, git >= 2.31; nothing is
    # written), and set dolt.local-only so no remote is wired. The database then
    # comes from issues.jsonl alone and has no Dolt remote to push to. The
    # tracked config.yaml is put back byte for byte. Both spellings are dropped,
    # nested (`sync:` then `  remote:`) and flat (`sync.remote:`), so the same
    # script serves either config.yaml.
    head="$(git rev-parse HEAD)"
    saved="$(mktemp)"
    cp .beads/config.yaml "$saved"
    sed -E -e '/^[[:space:]]+remote:/d' -e '/^sync\.remote:/d' "$saved" > .beads/config.yaml
    BD_DOLT_LOCAL_ONLY=true GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=remote.origin.url GIT_CONFIG_VALUE_0= \
      bd init --prefix "$prefix" --non-interactive --skip-hooks --skip-agents --quiet >/dev/null 2>&1 \
      || log "$name: bd init failed"
    cp "$saved" .beads/config.yaml
    rm -f "$saved"
    # bd init also commits onto the current branch (.gitignore lines, an empty
    # .beads/interactions.jsonl, its config.yaml rewrite), which would ride
    # along on the session's pushes. Drop exactly that commit: paths it changed
    # go back to their committed state; paths it added stay on disk, excluded
    # from git.
    if [[ "$(git rev-parse HEAD)" != "$head" ]]; then
      if [[ "$(git rev-parse HEAD~1)" == "$head" && "$(git log -1 --format=%s)" == "bd init:"* ]]; then
        init_commit="$(git rev-parse HEAD)"
        git reset -q "$head"
        exclude="$(git rev-parse --git-path info/exclude)"
        mkdir -p "$(dirname "$exclude")"
        while IFS= read -r path; do
          if git cat-file -e "$head:$path" 2>/dev/null; then
            git checkout -q "$head" -- "$path"
          else
            grep -qsxF "/$path" "$exclude" || echo "/$path" >> "$exclude"
          fi
        done < <(git diff --name-only "$head" "$init_commit")
      else
        log "$name: HEAD moved during bd init and it is not bd init's own commit; check git log"
      fi
    fi
  fi

  # Always (db built above or already present): make the database match the
  # checked-out .beads/issues.jsonl. A container can ship a database older than
  # HEAD's jsonl (first cloud run: 27 issues vs 29, and `bd show` said "not
  # found"). Import is an upsert, so running it every time is idempotent. The
  # explicit path matters: a bare `bd import` reads the configurable import
  # location, not necessarily this file.
  if [[ -f .beads/issues.jsonl ]]; then
    bd import .beads/issues.jsonl >/dev/null 2>&1 || log "$name: bd import failed"
  fi
}

for repo in "$PARENT"/*/; do
  repo="${repo%/}"
  [[ -d "$repo/.beads" && -e "$repo/.git" ]] || continue
  # One repo failing must not leave the others without beads. errexit is
  # switched off around the subshell and back on inside it: bash ignores set -e
  # in anything run under || or if, so `( setup_repo ) || log` would carry on
  # past a failed step and never report the failure.
  set +e
  ( set -e; setup_repo "$repo" )
  rc=$?
  set -e
  (( rc == 0 )) || log "$(basename "$repo"): setup failed; run it by hand in $repo"
done

if [[ ! -x "$HERE/.venv/bin/python" ]]; then
  log "water-mill: make install"
  make -C "$HERE" install >/dev/null
fi

log "done (after bead writes: bd export -o .beads/issues.jsonl, commit, push the session branch)"
