# Publishing to Zimmy

`watermill status` answers "where is the factory" to somebody at this checkout.
`watermill publish` answers the same question to a web page: it assembles one
JSON document describing every registered project and PUTs it to the Zimmy Life
Tracker, which stores the snapshot and draws a **Water Mill** tab from it.

```bash
export ZIMMY_URL=https://zimmy.local            # the app's base URL
export ZIMMY_API_KEY=zk_...                     # an admin key minted in Settings

./bin/watermill publish --dry-run               # print the document; send nothing
./bin/watermill publish --dry-run --out snap.json
./bin/watermill publish                         # PUT it
./bin/watermill publish --project zimmy-life-tracker
./bin/watermill publish --key-env ZIMMY_PI_KEY  # the key lives in another variable
```

Credentials are **environment, never the registry and never a contract** -- the
same rule `ship` follows for Loki. The key goes into one request header and is
never printed, not even in a failure message.

## It is a reader

Like `ship` and `land`, `publish` is its own command with its own exit code and
is **never part of a run**. Everything it invokes is a query:

| Source | Command | Never |
|---|---|---|
| Version, base branch head | `VERSION` file; `git rev-parse --short <base_branch>` | fetch, pull, checkout |
| Repository | `git remote get-url <remote>` | |
| Ready / in-progress | the contract's own `queue.ready` and `queue.stale` | claim, release, close |
| Totals and epics | `bd list --json --all --flat -n 0 --readonly --sandbox` | write, auto-push |
| Pull requests | `gh pr list --state open --json ...` | create, merge |
| Runs and tasks | `runs/index.jsonl`, `runs/tasks.jsonl` | append |

It never writes to the ledger. The only thing it writes anywhere is the
document, to Zimmy or -- with `--dry-run` -- to stdout or `--out`.

## Exit codes

Same distinction as everywhere else here.

| Code | Meaning |
|---|---|
| 0 | Sent, and Zimmy answered 2xx. Prints the snapshot id and `published_at` |
| 3 | **Refused**: no URL or no key. Nothing was assembled and nothing was sent. The message names the variable to set |
| 1 | **Failed**: the push was attempted and did not land -- a non-2xx answer (status and the first line of the body are printed) or a connection error |

A refusal every night is a configuration problem; a failure every night is a
Zimmy problem. A cron wrapper should tell them apart.

## Unknown is omitted, never zeroed

A `bd` that is not installed and a queue with nothing in it both produce "no
rows" from the outside, and a page that draws the first as `0 open` is lying in
the direction that makes a broken tool look like a finished project. So when a
source fails -- non-zero exit, unparsable output, no GitHub remote -- its keys
are **left out of the document** and an `attention` item of kind `drift` records
the first line of what the tool said. The page draws a gap and the reason.

`bd` prints a known warning on stderr when its JSONL export holds orphans. The
rows still parse, so that is surfaced once as a drift item and is not a failure.

## When to run it

**After a run, never during one.** A run holds a claim and may be mid-commit;
the snapshot should describe the morning, not the middle of the night. The
natural place is right after `ship`:

```cron
# 07:00 -- after the night's run has finished, shipped, and landed
0 7 * * *  cd /path/to/water-mill && ./bin/watermill ship && ./bin/watermill publish
```

Both commands are readers, so the order between them does not matter and a
failure in one does not affect the other's data. Neither should be chained onto
`watermill run` with `&&`: a Zimmy outage must not be able to fail a night.

## The Zimmy side

1. In Zimmy, **Settings → API keys**, mint an **admin** key. Copy it once; it is
   shown once.
2. Export it as `ZIMMY_API_KEY` on the machine that runs the factory.
3. `watermill publish` sends `PUT <ZIMMY_URL>/api/watermill` with
   `Content-Type: application/json` and the key as `X-API-Key: <key>` -- one of
   the two spellings Zimmy's `presented_key` accepts, and the one that cannot
   collide with a session's own `Authorization` header. It also sends
   `User-Agent: watermill/<version>`: Cloudflare's Browser Integrity Check in
   front of Zimmy 403s urllib's default `Python-urllib/3.x` (error 1010).
4. Zimmy stores the snapshot and answers 2xx with a JSON body carrying its `id`.
   The **Work → Water Mill** tab renders the latest one.

## The document (schema 1)

Every key is optional except `schema`, `published_at` and `projects`. A missing
key means *unknown*, and the page should say so rather than draw a zero.

```jsonc
{
  "schema": 1,
  "published_at": "2026-08-28T07:00:12+00:00",   // UTC, seconds
  "publisher": "watermill publish",
  "overall": {                                   // ledger.stats() across every project
    "runs": 9, "runs_refused": 6,
    "keep_rate": 1.0, "escalation_rate": 0.0,    // omitted until a task has been attempted
    "cents_per_kept_task": 614.5,                // omitted until a task has been kept
    "spend_cents": 1229,
    "kept_tasks": 2, "discarded_tasks": 0, "unannotated_tasks": 2
  },
  "projects": [
    {
      "name": "zimmy-life-tracker",
      "repo": "owner/name", "url": "https://github.com/owner/name",
      "target": "branch",                        // git.target from the contract
      "version": "4.6.25",                       // the VERSION file, if there is one
      "main_sha": "2b2db37",                     // git rev-parse --short <base_branch>
      "caps": {"max_tasks": 5, "max_hours": 3.0, "task_timeout_minutes": 30.0},
      "queue": {
        "ready": 28, "in_progress": 2,           // the contract's own queue commands
        "open": 33, "blocked": 0, "deferred": 0, "closed": 27,   // bd list
        "epics": [{"id": "...-jam", "title": "Accessibility remediation", "open": 0, "closed": 14}]
      },
      "runs": {
        "total": 9, "refused": 6, "kept": 2, "discarded": 0, "escalated": 0,
        "spend_cents": 1229,
        "last_started_at": "2026-08-27T10:04:30+00:00",
        "last_outcome": "spend cap: $8.43 reached the $5.00 ceiling",   // or "refused"
        "unannotated": 2                         // kept tasks with no root cause recorded
      },
      "recent_runs": [                           // the last 10, oldest first
        {"run_id": "20260827-060430", "started_at": "...", "supervised": true,
         "refused": false, "halt_reason": "...", "completed": 1, "failed": 0,
         "escalated": 0, "spend_cents": 843}
      ],
      "recent_tasks": [                          // the last 15, oldest first
        {"run_id": "...", "task_id": "zimmy-life-tracker-bzq", "title": "...",
         "outcome": "completed", "reason": "", "cost_cents": 843,
         "duration_seconds": 570.1, "commit": "3fc9624 fix(frontend): ...",
         "annotated": false}
      ],
      "prs": [                                   // open, from gh; absent if gh failed
        {"number": 98, "title": "...", "branch": "watermill/20260827-060430",
         "state": "open", "checks": "passing",   // pending | passing | failing | none
         "url": "...", "updated_at": "...",
         "task_id": "zimmy-life-tracker-bzq"}    // first bead id in title or branch, else null
      ],
      "attention": [                             // what a person should look at
        {"kind": "stale_claim",   "text": "<id> is claimed: <title>"},
        {"kind": "unannotated",   "text": "2 kept task(s) have no root cause recorded"},
        {"kind": "pr_waiting",    "text": "#98 ... is green and waiting"},
        {"kind": "verify_failed", "text": "#99 ... has a failing check"},
        {"kind": "queue_low",     "text": "3 ready task(s), fewer than the 5 a night may take"},
        {"kind": "drift",         "text": "gh pr list: <first line of stderr>"}
      ]
    }
  ],
  "notes": ""
}
```

### The attention rules

| Kind | Fires when |
|---|---|
| `stale_claim` | each task the contract's `queue.stale` command reports |
| `unannotated` | `runs.unannotated > 0` |
| `pr_waiting` | each open pull request whose checks are `passing` |
| `verify_failed` | each open pull request whose checks are `failing` |
| `queue_low` | `queue.ready < caps.max_tasks` (both must be known) |
| `drift` | a source failed or said something on stderr -- see above |

### The checks mapping

`statusCheckRollup` from `gh` is a list of check runs and status contexts.
`failing` if any concluded badly (`FAILURE`, `TIMED_OUT`, `CANCELLED`,
`ACTION_REQUIRED`, `STARTUP_FAILURE`, `ERROR`), whatever else is still running,
because that is the one a person has to look at; otherwise `pending` if any has
not concluded; `passing` only when every one concluded well; `none` for an empty
rollup, which is what a branch with no workflows reports and is not the same
thing as passing.

### Task ids

`<project>-<3 chars>` with an optional `.<n>` for a child, matched
case-insensitively with either `-` or a space between the words of the project
name -- one epic in the first target was created as `Zimmy Life Tracker-9i7`,
display name and all.
