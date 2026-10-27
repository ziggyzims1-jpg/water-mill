# AI in the mill

Every place an AI agent is used, adapted or governed in Water Mill, in one
document for the owner and a collaborator. It describes only what exists today,
and every claim names the file it comes from; if a file and this page ever
disagree, the file is right and this page is stale. Vocabulary is
[`CONTEXT.md`](../CONTEXT.md); the position is [`STATUS.md`](STATUS.md).

`watermill validate` prints a WARNING (never a failure) when a crew agent or a
skill that canon distributes is not named on this page (`watermill/sync.py`,
`unmentioned_in_ai_doc`; a name counts as mentioned when it appears here as a
whole word, case-insensitively). What stops a new agent or skill from shipping
undescribed is the gate: `tests/test_sync.py`,
`test_the_real_factorys_ai_doc_names_every_agent_and_skill`, fails `make verify`
for water-mill's own copy of this page.

Contents: 1 Harnesses, 2 The crew, 3 Rules and where they live, 4 Skills,
5 The context graph, 6 Agent-run tracking, 7 Observability, 8 Cloud constraints,
9 Canon and sync, 10 The trial harness, 11 Adding a project, 12 What the docs
do not say.

## 1. Harnesses

There are two ways an agent works here. They are different things and must not
be confused:

- **Claude Code sessions** (this section and most of this page): a person, or an
  orchestrator session, runs Claude Code and the crew agents are subagents of it.
  Nothing in `watermill/` spawns the crew.
- **`watermill run`**: the headless loop (`watermill/engine.py`) claims a bead,
  hands it to an agent command, and verifies what reached the repository. Its
  safety model is [`SAFETY.md`](SAFETY.md); the project's own agent command and the
  gate are in the contract. The context graph is offered to that agent as a tool
  when the contract's `knowledge.recall` is true (`README.md`, "Running one").
  Per `CLAUDE.md` the number that governs this loop is nights run: 0.

### Claude Code on the laptop

The workshop folder `~/Documents/code` holds the repos and a shared `.claude/`
(`CONTEXT.md`, "Workshop"). Its `CLAUDE.md` is mastered in
`canon/workshop/CLAUDE.md` and written there by `watermill sync workshop`, which
is laptop-only (section 9). Each repo has its own `CLAUDE.md`; millstone additionally reads the `CLAUDE.md`
of every subfolder it touches (`millstone.md`, step 4), and bolter counts the
`CLAUDE.md` conventions of the folders a diff touches as documented standards
(`bolter.md`, step 2).

### Claude Code in cloud sessions

A cloud session starts from a clean clone with `CLAUDE_CODE_REMOTE=true`. What
that changes is section 8. The setup it needs is `scripts/cloud-setup.sh`.

### `.claude/settings.json` (this repo)

Three kinds of entry, and only one is managed by canon:

| Entry | What it does | Owner of the entry |
|---|---|---|
| `hooks.SessionStart` (matcher `""`) | runs `bash "$CLAUDE_PROJECT_DIR/scripts/cloud-setup.sh"; bd prime --hook-json` with a 600 s timeout, in one command because hooks for one event may run in parallel (`CLAUDE.md`, "Working here") | this repo |
| `hooks.PreToolUse` (matcher `Bash`) | the git guardrail below | canon (`canon/settings.managed.json`) |
| `permissions.allow` | `Bash(bin/watermill remember:*)` and the same with the laptop's absolute path, so recording a finding does not prompt | this repo |

- **`cloud-setup.sh`** is a no-op unless `CLAUDE_CODE_REMOTE=true` (or `--force`,
  for tests only: never on a laptop, because it imports every sibling checkout's
  `issues.jsonl` into that repo's live database). In a cloud container it installs
  `bd` pinned to 1.2.2, puts `BD_DOLT_AUTO_PUSH=false` into `CLAUDE_ENV_FILE`
  (and warns if that variable is empty, because then every later `bd` command
  must set it itself), builds the beads database of water-mill and of every
  sibling checkout that has a `.beads/` from its tracked `issues.jsonl` alone
  (no Dolt remote, no tracked file or commit changed), re-imports the jsonl on
  every run, and runs `make install`. A failed `make install` is logged, never
  fatal. Tests: `tests/test_cloud_setup.py`.
- **As an environment setup script.** A copy pasted into the environment's
  setup box, or fetched to `/tmp`, is not at `<checkout>/scripts/`, so it scans
  `CLOUD_SETUP_ROOT` (default `/home/user`, where cloud sessions clone their
  repos) and runs `make install` only for a `water-mill/` it finds there. Before
  2026-10-27 such a copy ran `make -C / install`, exited 2, and the environment
  refused to start every new session. The script is public, so the setup box
  can fetch it rather than carry a copy that drifts:
  `curl -fsSL https://raw.githubusercontent.com/ziggyzims1-jpg/water-mill/main/scripts/cloud-setup.sh | bash`.
- **A routine does not get the hook.** The SessionStart hook only fires when the
  session's cwd is inside a repo that carries it; a routine's orchestrator starts
  in `/home/user`, which is not a repo. It must run
  `bash <checkout>/water-mill/scripts/cloud-setup.sh` by hand, first
  (`scripts/cloud-setup.sh` header; `CLAUDE.md`).
- **`scripts/sync-factory.sh`** fast-forwards the water-mill checkout (only on a
  clean `main`, bounded by a timeout, always exit 0, nothing on stdout) and prints
  `watermill review --lag` to stderr, so other repos' agents do not read a stale
  graph. It is written to run inside a SessionStart hook ahead of
  `bd prime --hook-json`; **it is not wired in this repo's `.claude/settings.json`**
  (section 12).
- **The git guardrail** is `.claude/hooks/block-dangerous-git.py`, a stdlib-only
  Python script (so it behaves the same on macOS bash 3.2 and the Linux cloud
  image) that tokenises the command with `shlex`. It denies `git stash` in every
  form (including `git -C <dir> stash`), `reset --hard`, `clean -f`/`--force`,
  `branch -D`, `checkout .` and `restore .`, and `push --force`, `-f`,
  `--force-with-lease`, `--force-if-includes` and `+refspec`. It allows plain
  `push`, `commit`, `worktree`, `checkout <branch>`, the pinned lease
  `--force-with-lease=<ref>:<sha>` (the cloud session-branch reset) and anything
  inside a here-document body. The settings command fails open (`exit 0`) when the
  script file is missing, so a missing script never wedges a session; the reverse
  hazard (a hook naming a gitignored script blocked every Bash call) is why sync
  refuses in that case (section 9). Why it exists: ADR-0004 (a stash/pop done to
  prove a test fails popped another agent's changes, 2026-08-30). Adapted from
  mattpocock-skills 1.2.3 (MIT). Tests: `tests/test_git_guardrail.py`.
- **`.claude/watermill-managed.json`** records which files and which settings
  entries sync put there, so an entry dropped from canon is removed next time and
  nothing the repo wrote itself is ever touched (`canon/README.md`;
  `watermill/sync.py`).

## 2. The crew

Four single-purpose agents take one bead to a landed change, **in this order**:
millstone, bolter, sluice, tailrace (ADR-0001, `CLAUDE.md` "Auto-mill follow-ups").
The definitions are mastered in `canon/common/.claude/agents/<name>.md` and
rendered into `.claude/agents/` of every target; edit canon, never the copy.
Millstone, bolter and sluice are told to work in their own git worktree (tailrace
makes one only to resolve a merge conflict, step 3, or in cloud mode for its
post-merge commits); all four are told to write a handoff before signing off even
when blocked, and to stop and report **BLOCKED** (quoting the
denial) rather than retry when a tool call is denied (ADR-0011).

| Agent | Job | Writes to the branch? |
|---|---|---|
| **millstone** | The implementer: one bead in, one pull request out. Works in its own worktree, tests at seams (it lists the seams it chose in the PR body and handoff), shows the new tests failing on the base (`Red before green`), follows `diagnosing-bugs` for a bug bead, opens the PR and writes the first handoff section | yes: its own branch |
| **bolter** | The standards reviewer, **report-only**: checks the diff against `CODING_STANDARDS.md`, `docs/adr/`, `CONTEXT.md`, folder `CLAUDE.md` conventions and a fixed set of 12 Fowler smells (advisory). A broken documented standard is *blocking*; a smell never blocks. May mark an advisory `[auto-mill candidate]` | never: no push, no commit |
| **sluice** | The spec reviewer and independent verifier: checks the PR against its bead (Goal, Approach, Verification, Out of scope), the fence, runs the suites in its own worktree, bounces a PR with no red-before-green evidence (docs-only excepted), fixes in-scope problems on the branch, and acts on bolter's blocking findings (fix, or rebut in its handoff). Files `auto-mill` beads. **The only reviewer that pushes**, including bolter's run record | yes |
| **tailrace** | The lander: verifies the PR's checks with a settle window, squash-merges, closes the bead, marks the handoff `**LANDED**`, files what landing taught into the graph. Merges strictly one at a time | merges only |

The **orchestrator** is not an agent definition: it is the top-level Claude Code
session that spawns the crew one after another, carries their handoffs and bead
changes to main, and decides when a BLOCKED report goes to the owner
(`CONTEXT.md`). It runs the crew serially; the trial's arm A brief says "one after
another, never in parallel and never skipping a step" (`watermill/trial.py`,
`brief`).

Role detail lives in the agent files; this page does not duplicate it. Things
worth knowing without opening them:

- Millstone, bolter and sluice start with `watermill recall` (owner rule
  f-20260925-aa9b36). All four get a `wm-run-...` tag from `watermill agents
  whoami` early and run `watermill agents record ... --pr <n>` only at sign-off
  (section 6).
- The fence (`fence.paths` in the contract) is off limits to the crew unless the
  bead itself directs the fenced change (`millstone.md`, step 4).
- `millstone.md` forbids `git stash` and gives the patch-file alternative.
- Each agent has a **Cloud mode** section that applies only when
  `CLAUDE_CODE_REMOTE` is exactly `true` (section 8).

### Auto-mill follow-ups (owner's rule, 2026-10-14)

Sluice files a bead for a clearly-defined smell (it names the file, the smell
and a concrete fix), labelled `auto-mill`, priority P3, in the same repo. The
orchestrator that lands the parent bead runs each one through the full crew
(millstone, bolter, sluice, tailrace) right after, without asking. The limits
are the rule (ADR-0002):

- **Depth 1.** A smell found while working an `auto-mill` bead is filed as an
  ordinary bead, never labelled `auto-mill`, never auto-run.
- **At most 2 per parent bead.**
- **Never auto-run anything touching the fence, security code, the schema or CI.**
  Those are filed as ordinary beads for the owner.
- P3, same repo as the parent, nothing cross-repo.

Masters: `canon/workshop/CLAUDE.md` (the workshop rule), repeated in `CLAUDE.md`,
`canon/common/.claude/agents/sluice.md` (step 5d), `tailrace.md` (step 4a: it
reports the beads, it does not run them) and here.

## 3. Every rule and where it lives

A rule is only as good as the place it is enforced. `CLAUDE.md` ranks the
destinations for a lesson: the **gate** (unignorable) and `fence.paths` (checked
against the diff) first; `notes` in the contract only for what neither can express
(it reaches the prompt as advice and is never checked); the **context graph** last
and weakest (`CLAUDE.md`, "Knowledge has four destinations"; ADR-0007).

| Where | What it holds | Enforced by |
|---|---|---|
| `canon/workshop/CLAUDE.md` -> `~/Documents/code/CLAUDE.md` | Workshop-wide rules: beads live in git and are pushed (ADR-0003); every agent writes a handoff before signing off (ADR-0009); the auto-mill rule (ADR-0002) | nothing mechanical; read by every session opened under the workshop |
| `CLAUDE.md` in each repo | That repo's conventions and where its handoffs go; this repo's is the water-mill rulebook (refusal vs failure exit codes, `tail_lines=0`, `removeprefix`, caps between tasks, and so on) | the gate where a test pins it; otherwise review (bolter treats a broken `CLAUDE.md` convention as blocking) |
| `CODING_STANDARDS.md`, `docs/adr/`, `CONTEXT.md` (per repo, seeded by water-mill-fwm.6) | What is enforced or agreed, the decisions made and why, the glossary | bolter's review; sluice resolves its blocking findings |
| The contract: `watermill.yaml` in the project, or a vendored `projects/<name>.yaml` | The gate, `backup_check`, git base/target/remote, the queue and review commands, `fence.paths`, `notes`, `knowledge`, `caps`. Unknown keys are refused. The project's own file always wins over a vendored one | preflight, the gate, the fence check against the diff (`docs/CONTRACT.md`, `docs/SAFETY.md`) |
| `projects.yaml` | Which repositories the factory drives and a project's `sync_exempt` opt-outs | `watermill validate`, `sync` |
| `.claude/settings.json` hooks | The git guardrail (section 1) | the harness, before the command runs |
| `docs/SAFETY.md` | The safety model; read it before changing `engine.py`, `preflight.py`, `gitwork.py` or `caps.py` | review |
| `docs/policies/INTEGRATIONS.md` | External-provider modules are fenced by default and ungated only after a human wires one, proves it live and files a wiring record (ADR-0008) | the fence |
| `docs/TRIAL.md` | The trial protocol; changes only by dated amendment (section 10) | `watermill/trial.py`, `tests/test_trial.py` |
| Handoffs (below) | What an agent did, what failed, what to read first | convention (ADR-0009); `landed.py` reads `**LANDED**` |
| Beads in git (below) | The work queue, reachable from any machine | convention (ADR-0003) |

**Handoffs.** No agent ends its turn without one. Per bead, one file named by the
bead id with its project prefix removed and lower-cased, each agent appending a
dated section (`## Millstone`, `## Bolter`, `## Sluice`, `## Tailrace`); the
lander marks it `**LANDED**` (`canon/workshop/CLAUDE.md`). The directory is
repo-specific and each repo's `CLAUDE.md` says where: `HANDOFF-mill/` here,
`brain/handoffs/mill/` in zimmy-life-tracker and the cells (the crew files default
to the latter). On the laptop a handoff is never part of the PR; in cloud mode it
is committed on the session branch and reaches main through the orchestrator's one
session docs PR (`CONTEXT.md`, "Handoff"). Session-level handoffs by an
orchestrator are different files in the repo root: `HANDOFF.md` (the first
session's snapshot, whose top points at the newer `HANDOFF-2026-08-28.md`) and
dated snapshots such as `HANDOFF-2026-08-28.md` and `HANDOFF-2026-10-13.md`. The rule for all of them: say
what failed, name files and functions, no diffs, one page.

**Beads in git (ADR-0003).** Any session or agent that creates, updates, closes or
defers a bead commits and pushes `.beads/issues.jsonl` (a `chore(beads): ...`
commit) before signing off; bd writes with no push are invisible off the machine.
`.beads/interactions.jsonl` is local-only (`.gitignore`). `CLAUDE.md` adds: use
`bd` for all task tracking, never markdown TODO lists, and `bd remember` rather
than `MEMORY.md` for persistent knowledge.

**Owner memory.** Several ADRs cite Claude "memory notes" as their source
(`mill-crew-in-repos`, `beads-push-to-git`, `watermill-git-stash-hazard`,
`claude-cloud-sessions-constraints`). Those notes live in the owner's Claude
memory, not in this repository, and this page cannot describe their contents
beyond what each ADR quotes from them. The repo-side rule is the one in
`CLAUDE.md`: durable knowledge goes in beads (`bd remember`), ADRs and the
context graph, which are reviewable and travel with a checkout.

**Promotion.** A lesson is promoted into Water Mill when it has appeared twice,
in two repositories; until then it lives in that project's contract and
calibration record (`CLAUDE.md`; `docs/ONBOARDING.md`, "When a lesson belongs to
Water Mill instead").

## 4. Skills

Eleven skills are adapted for beads from **mattpocock-skills 1.2.3**
(<https://github.com/mattpocock/skills>, MIT, Copyright (c) 2026 Matt Pocock).
They are mastered in `canon/common/.claude/skills/<name>/SKILL.md`, rendered into
every target's `.claude/skills/`, each carrying an attribution block and pointing
at the one shared `.claude/skills/MATTPOCOCK-SKILLS-LICENSE`; upstream's
per-skill `agents/openai.yaml` (Codex UI metadata) is carried along untouched.
Where upstream talked to an issue tracker the skill now says `bd`. Tests:
`tests/test_skills.py`. A target's `.gitignore` must not drop `.claude/skills/`
or the files are never committed (section 9).

| Skill | What it is for | Used by the crew? |
|---|---|---|
| `tdd` | Test-driven development: tests at seams, the red-green loop | Its rules are written into `millstone.md` (seams, red before green); the skill itself is for interactive sessions |
| `diagnosing-bugs` | Diagnosis loop for hard bugs: build the failing check first | Named in `millstone.md` (bug beads) and `sluice.md`; same as above |
| `code-review` | Review since a fixed point along Standards and Spec axes | `bolter.md` is adapted from its Standards axis; sluice's review is the Spec axis |
| `domain-modeling` | Sharpen a domain model; write `CONTEXT.md` and ADRs | Available; no crew file names it. It is how the `CONTEXT.md` and `docs/adr/` that bolter reads are authored |
| `grilling` | Stress-test a plan or decision by relentless questioning | Available, interactive |
| `grill-with-docs` | Grilling that also writes ADRs and glossary as it goes (`disable-model-invocation`) | Available, interactive |
| `codebase-design` | Deep-module vocabulary, seams, deepening | Available; the "seam" language in millstone/bolter shares its vocabulary |
| `wayfinder` | Plan a huge chunk of work as a map of decision tickets: an epic labelled `wayfinder:map`, child beads as tickets, `bd dep add` for blocking, `bd ready --parent <map> -u` as the frontier (`disable-model-invocation`) | **Made available only**; the mill does not run it |
| `wizard` | Generate an interactive bash wizard for steps only a human can do | **Made available only** |
| `improve-codebase-architecture` | Scan for deepening opportunities and present an HTML report (`disable-model-invocation`) | **Made available only** |
| `to-questionnaire` | Turn a decision you cannot answer into a questionnaire for someone else (`disable-model-invocation`) | **Made available only** |

"Available" means the skill is installed in every synced repo for any Claude Code
session to invoke; "used by the crew" means a crew file names it or is adapted
from it. The owner's decision (epic water-mill-fwm) is that wayfinder, wizard,
improve-codebase-architecture and to-questionnaire are not run by the mill.

## 5. The context graph

What the factory has learned, queried rather than loaded. Full treatment:
[`KNOWLEDGE.md`](KNOWLEDGE.md); decisions: ADR-0012, ADR-0013, ADR-0014.

- **Sources** (three append-only JSONL files, rebuilt in memory on every call, no
  database, no lock): `runs/index.jsonl` (runs), `runs/tasks.jsonl` (tasks and
  root causes) and `knowledge/findings.jsonl` (findings; the only one committed).
  `watermill/recall.py` builds the graph and answers; `watermill/knowledge.py`
  stores findings.
- **Ask:** `watermill recall "<query>" [--cell NAME] [--everywhere] [--since
  YYYY-MM-DD] [--cause C] [--limit N] [--json]`; open one hit with `--detail
  <id>`. It returns a few one-line hits under a character budget and says how many
  it left. Millstone, bolter and sluice run it first. `watermill recall --usage` shows what
  was asked and what came back empty (`watermill/usage.py`, never readable by an
  agent).
- **Mid-task tool:** `watermill/mcp.py` serves the same graph over stdio to an
  agent started by `watermill run` when the contract enables it (`--recall` /
  `--no-recall` override per run). Provenance (cell, run, task) is stamped by the
  engine from the command line it built, not claimed by the agent.
- **Write:** `watermill remember <cell> {failure|lesson|measurement|success}
  "<one sentence>" --cause <bucket> --tag <t> [--path P] [--task BEAD]
  [--supersedes ID --why ...] [--on DATE] [--destination fence|gate|note|record]`.
  `--cause` is required; `pending` leaves it to the owner. The crew agents run
  `watermill remember` directly (`bolter.md` step 5, `sluice.md` step 5a,
  `tailrace.md` step 5), so their findings are live at once. Quarantine applies
  only to the MCP `propose` tool an agent under `watermill run` calls mid-task:
  a proposal is never returned to any agent until a person runs `watermill
  proposals --promote` (or `--reject`) (`KNOWLEDGE.md`). Tags: bolter always adds
  `--tag bolter`; sluice and tailrace tag by topic; a trial session tags
  `trial:A` or `trial:B` (section 10). `watermill confirm <id>` says a finding
  still holds; a belief that changed is superseded, never edited.
- **Who writes what:** millstone does not write to the graph (its handoff's
  "Lessons for the graph" are what sluice and tailrace file); bolter files a
  finding only for a blocking, repeatable trap and never commits
  `knowledge/findings.jsonl`; sluice files one per fix it pushed; tailrace commits
  the findings file (`millstone.md`, handoff section; `bolter.md` step 5;
  `sluice.md` step 5a; `tailrace.md` step 5). The `cause` buckets `none`,
  `gate-hole` and `agent-error` are the owner's alone.
- **The monthly sweep:** `watermill review` (read-only; `--record` records that it
  happened; `--check` exits non-zero when the sweep is overdue; `--lag` lists beads
  landed with no finding). `watermill/review.py`. Not to be confused with
  `watermill agents sweep` (section 6).

## 6. Agent-run tracking

Two stores, one schema (the docstring of `watermill/agentlog.py` is the schema;
ADR-0018):

- **`runs/agents.jsonl`** (gitignored, local): one line per unit of agent work of
  any kind, `key`-folded so a re-run never duplicates. `watermill agents sweep`
  fills it from three sources: handoff notes and bead JSONL
  (`watermill/crewlog.py`, `source: "handoff"`), the recorded lines below, and
  Claude Code transcripts under `~/.claude/projects` (`watermill/sessionlog.py`,
  `source: "transcript"`; counters, timestamps and ids only, never message text).
- **`knowledge/agent-runs/<role>-<bead>-<agent id>.jsonl`** (tracked): the agent's
  own sign-off facts, one file per run so two PRs never conflict on it
  (`watermill/recorded.py`, `source: "recorded"`). It is the only record that
  survives a cloud container. Procedure for an agent:
  `TAG=$($WM/bin/watermill agents whoami)` early, in its own tool call, then at
  sign-off `$WM/bin/watermill agents record --transcript auto --run-tag "$TAG"
  --role <millstone|bolter|sluice|tailrace|solo|orchestrator> --bead <id> --pr <n>
  [--verdict V] [--sluice-rounds N] [--arm A|B] [--outcome landed|unlanded|blocked]`.
  Recording early captures seconds of a run and no PR, which is why it is a
  sign-off step. Bolter cannot push, so it quotes its record line in its handoff
  and report and sluice commits it. Flags are enums, integers or a validated bead
  id; nothing free-form is stored.
- **Read it:** `watermill agents compare [--kind K --vs K --since DATE --min-n N]`
  compares crew against other agents with small-sample statistics
  (`watermill/agentcompare.py`, `watermill/stats.py`); it keeps *per run* and *per
  bead* figures apart and never mixes them (`docs/OBSERVABILITY.md`, "`watermill
  agents compare`"). Do not lower `--min-n` to get a p-value.

## 7. Observability

[`OBSERVABILITY.md`](OBSERVABILITY.md) is the reference. In short:

- **`watermill ship`** reads `runs/index.jsonl`, `runs/tasks.jsonl` and
  `runs/agents.jsonl` and pushes what is new to Loki (`watermill/shipper.py`).
  Credentials are environment only: `LOKI_URL`, `LOKI_USER`, `LOKI_TOKEN`.
  `--dry-run` prints the payload, `--resend` re-ships. It is its own command with
  its own exit code and never part of a run, so a Loki outage cannot hang a night
  (ADR-0016). The high-water mark advances only after a push returned.
- **Labels are low-cardinality and allow-listed.** Run and task ids go in the
  line, never in a label. Agent lines are labelled `source="agent"` with
  `agent_kind` bucketed to `mill-crew`, `session`, `subagent`, `other`.
- **Before the first agent ship** raise Loki's `reject_old_samples_max_age`
  above the age of the oldest record in `runs/agents.jsonl`, or Loki answers 400
  and every later ship fails on the same lines (`docs/OBSERVABILITY.md`, "Shipping
  agent work to Loki").
- **Grafana:** `docs/grafana/agent-performance.json` is an importable dashboard
  over the agent stream. The first panel to build and alert on is
  `count_over_time(...[24h])`, because a night that never ran looks exactly like a
  quiet night (`CLAUDE.md`, "Silence is a failure mode").
- **`watermill publish`** PUTs a status snapshot of every project to Zimmy
  (`watermill/publish.py`; unknown is omitted, never zeroed). Also a reader, also
  off the run loop.

## 8. Cloud constraints

Learned 2026-10-13 and recorded in ADR-0010. They apply when
`CLAUDE_CODE_REMOTE` is exactly `true`; anything else is the laptop. Each crew
agent's "Cloud mode" section is the operative text (`canon/common/.claude/agents/`).

- **GitHub is REST only.** Never `gh pr ...`, `gh run ...` or `gh api graphql`
  (GraphQL returns 403). Use `gh api repos/$SLUG/...`. The `actions/*` API is
  403; read check-runs instead. `gh auth status` may say invalid while `gh api`
  works.
- **The session branch is the PR branch.** The session may push only its own
  `claude/...` branch. `SB=$(git branch --show-current)`; worktrees are detached
  (`git worktree add --detach "$WT" origin/main`, or `origin/$SB` to continue);
  publish with `git push origin HEAD:refs/heads/$SB`. Do not create or push
  `bead/<slug>`, never push `main`, never delete `$SB`. One bead per session at a
  time. If `$SB` is not a `claude/...` branch, stop and report BLOCKED.
- **bd.** Prefix every command with `BD_DOLT_AUTO_PUSH=false`; run
  `bd import -i .beads/issues.jsonl` first if you are the first agent to touch
  bd (the container's database can be stale); never `bd dolt push`, never push
  `refs/dolt/*` (the proxy rejects anything but a branch).
- **Beads travel as `.beads/issues.jsonl` commits** on the session branch, carried
  to main by the repo's beads-sync workflow, and **never in a PR** (an
  `issues.jsonl` in a PR conflicts on line order alone). Do not commit
  `.beads/interactions.jsonl`.
- **Import before export, and compare sorted.** Exporting from a database a pull
  left stale reverts closures and drops beads (it happened on 2026-10-14), so a
  closing agent does `git pull --ff-only`, `bd import`, then `bd export`, and
  checks `diff <(git show HEAD:.beads/issues.jsonl | sort) <(sort .beads/issues.jsonl)`
  shows only the one bead's old and new line (export and beads-sync order lines
  differently). Anything else: do not commit, report NEEDS_MANUAL
  (`tailrace.md`, step 4; it is the laptop rule too, and the cloud mode adds the
  first-agent `bd import`).
- **Handoffs and agent-run records are committed on `$SB`**; the container is
  thrown away. During review they are staged in `$STAGE`
  (`$REPO/../.mill-stage/<repo>/<slug>/`, outside every worktree) and only
  tailrace commits them, after the merge (owner, 2026-10-15: Actions minutes).
  Every push to `$SB` while its PR is open runs the whole `verify`, so the PR
  only ever receives code: millstone's one push and sluice's one push of fixes
  when it has any. `verify` runs on pull requests only (a newer push cancels the
  run it replaces) and not again on main after a merge; tailrace's step 0b first
  makes sure the head already holds everything main has but bead updates.
  After the merges the orchestrator opens one docs-only PR with them
  and resets `$SB` to main with `--force-with-lease` only after that PR merged
  (the pinned lease the guardrail allows). No bead opens a bookkeeping PR.
- **`$WM`** (the water-mill checkout) exists in a cell's session only if the
  orchestrator attached it. If absent, skip every `watermill` command (recall,
  whoami, record, remember, review --lag), say so in the handoff, and carry on;
  the lessons then go in the handoff under "Lessons for the graph".
- **Landing** is a REST merge of the head sha that was verified
  (`gh api -X PUT repos/$SLUG/pulls/<pr>/merge -f merge_method=squash -f sha=...`):
  409 means the head moved, 405 means not mergeable (merge main into `$SB` in a
  detached worktree and verify again).
- **Remote isolation:** the Agent tool's `isolation: "remote"` silently falls back
  to a local worktree on the laptop, so a real cloud run is started from
  claude.ai/code (ADR-0010).
- **The workshop folder is unreachable** from a cloud session; `watermill sync
  workshop` skips itself there.

## 9. Canon and `watermill sync`

[`canon/README.md`](../canon/README.md) is the reference; the mechanics are
`watermill/sync.py`; the decision is ADR-0006.

**Layout.** `canon/common/<path>` goes to `<path>` in every target (each registered
project, water-mill itself and the workshop); `canon/project/<path>` to git
projects only; `canon/workshop/<path>` to the workshop only (`~/Documents/code`,
override with `WATERMILL_WORKSHOP`); `canon/settings.managed.json` is merged into
each target's `.claude/settings.json`. Today `common/` holds the four crew agents,
the guardrail hook and the 11 skills with their licence; `workshop/` holds
`CLAUDE.md`.

**What a target receives.**

- Each file with a header line "managed by water-mill (`<canon path>`); edit it
  there, then run `watermill sync`", placed after front matter or a shebang so the
  file still parses. JSON cannot carry a comment and is copied as is.
- A **settings merge**: only `hooks` and `permissions` can be managed, and only the
  entries listed in `canon/settings.managed.json`. The repo's own entries are
  never touched; what was merged is recorded in `.claude/watermill-managed.json`.
- A **pull request per git repo**, never a push to its base branch: branch
  `sync/water-mill-<content digest>` (so running twice proposes once), title
  `chore(sync): water-mill canon`. Sync never merges; the repo's CI and the landing
  step do.

**Commands.**

```bash
./bin/watermill sync <project> --dry-run   # what would change; writes and opens nothing
./bin/watermill sync <project>             # opens the CI-gated PR in that repo
./bin/watermill sync water-mill            # the factory is a target of its own canon
./bin/watermill sync workshop              # direct write, laptop only
./bin/watermill sync --all                 # water-mill, every active project, then the workshop
./bin/watermill validate [project] [--sync-path DIR]
```

- **The workshop** is not a git repository, so it is written directly, and only on
  the laptop: in a cloud session, or when `<workshop>/.claude` does not exist, the
  step is skipped with a message. Its master stays here in
  `canon/workshop/CLAUDE.md`, so **after canon/workshop/CLAUDE.md changes the owner
  must run `watermill sync workshop` on the laptop**.
- **The gitignore refusal (water-mill-fwm.9).** If a target's `.gitignore` would
  keep a file sync writes out of the commit (for instance `.claude/skills/` or the
  hook script), sync refuses (exit 3), opens no PR, names the rule, and removes only
  a branch it created. Without this a half-synced PR once shipped a settings hook
  without its script.
- **`sync_exempt`** in `projects.yaml` is a map of glob to reason: an opt-out for
  one project, reported by `validate` and never failing it. No project currently
  uses one (`tests/test_sync.py`, `test_hillel_is_registered_without_an_exemption`);
  Hillel-Programming is synced in full, crew files included (owner correction
  2026-10-14; ADR-0006), and the local `~/Documents/code/Hillel` folder, which is
  not a repo, is left alone (epic water-mill-fwm).
- **`validate`** parses every contract and checks drift of every synced file in
  water-mill and in each registered project against canon: a differing or missing
  copy fails it (exit 1), as does a settings hook naming a missing file under
  `$CLAUDE_PROJECT_DIR`. `--sync-path DIR` adds a report-only check of an
  unregistered folder such as the workshop. **New:** it also prints
  `WARNING: docs/AI.md does not mention: ...` for any canon agent or skill this
  page does not name; the warning does not change the exit code.
- **Edit canon, never a copy.** A synced copy that was edited in place is drift and
  fails `validate`. Targets of the current epic: water-mill, zimmy-life-tracker,
  watermill-cell-template, zim-dashboard-demo-cell-1b, cheme-solver, the
  workshop and Hillel-Programming (`projects.yaml`; epic water-mill-fwm).

## 10. The trial harness

The trial is **live, not shelved**. It asks one question, pre-registered: does the
mill crew land beads with fewer escaped defects than one default Claude given the
same bead? Protocol and analysis plan: [`TRIAL.md`](TRIAL.md) (written before data,
amended only by dated amendment before the data it affects is looked at; ADR-0017).
Machinery: `watermill/trial.py`, CLI `watermill trial`, tests `tests/test_trial.py`.
All state is in `knowledge/trial/` (tracked).

**Where it stands.** The first batch (8 ZIM cell beads, seed 20261013) was
cancelled before any bead ran or was scored, because the crew was being changed
(epic water-mill-fwm). Its ledger was moved unedited to
`knowledge/trial/archive/2026-10-14-cancelled.jsonl` with a closing `cancelled`
line saying why, and the `trial:` labels were removed. Nothing reads `archive/`.
There is currently no `knowledge/trial/ledger.jsonl`: the next `trial enroll` finds
an empty ledger and draws a fresh seed. The harness itself did not change. The later
amendment (2026-10-14) defines arm A as the four-agent crew.

### Design

| | Arm A (crew) | Arm B (solo) |
|---|---|---|
| Session | one top-level orchestrator session | one top-level general-purpose Claude session |
| Work | runs millstone, bolter, sluice, tailrace as subagents, serially | implements, runs the gate, opens the PR, lands it; **no review agent** (the brief names all four crew agents and forbids them) |
| Ends | PR merged after sluice approves and every check is green; bead closed | PR merged after every check is green; bead closed |
| Merge | tailrace | the session itself (owner's decision 2026-10-13; the switch is `ARM_B_SELF_MERGES` in `trial.py`) |

Identical for both: the bead text, the repo's gate and fence, the knowledge steps
(recall at start; `remember` with `--tag trial:A|B`), a handoff, and the **landing
rule word for word** (`trial._landing`): wait for every check-run on the PR head to
be completed and green, then squash-merge exactly that head with subject
`<PR title> (#<n>)` and body `Bead <id>.`, as a tool call of its own. The one
designed difference is the review step, so the trial measures the whole crew
*process*, not which part of it does the work (`TRIAL.md` s9). **One trial bead per
top-level session**, because the session's cost-state is cumulative.

**Eligibility** (`trial.eligibility`): the repo is registered, enabled and checked
out here; the bead is not an epic and is `open`; it is not labelled `hand-only`; it
names no `fence.paths` entry as one it may edit unless it carries `fence-directed`
(the bead itself directs it) or `fence-clear` (names a fenced path, edits none);
and it is not already in the ledger. The rule errs towards excluding. Water-mill's
own beads are not in the trial.

### Randomisation

`watermill trial enroll <repo> <bead>... | --ready [--dry-run] [--seed N]`
(`<repo>` may be `all` with `--ready`).

- **Stratified by repo, balanced blocks of four**: each block of four consecutive
  enrolments in a repo is exactly two A and two B in an order shuffled by
  `random.Random(f"{seed}:{repo}:{block}")`. A partial tail block is possible and
  `enroll` reports it; balance is exact only in full blocks, so enrol in multiples
  of four per repo.
- **Seeded and logged**: one master seed per trial, drawn once, stored as the
  ledger's first line and copied to every enrol line with its block and position.
  `--seed` is accepted only while the ledger has none.
- **Order cannot steer it**: beads in one call are sorted by id first, and an id
  given twice takes one position.
- **No re-randomising**: a bead already in the ledger is refused and there is no
  command to remove or redraw one; the ledger is opened append-only.
- **Recorded before work starts** in the ledger and as the bead label
  `trial:A` / `trial:B` (the label must also be committed in that repo's
  `.beads/issues.jsonl`).
- `--dry-run` writes nothing and, with the same `--seed`, shows exactly what the
  real run assigns. **Honest limit** (`TRIAL.md` s3): anyone who knows the seed and
  the sequence can predict an arm, so the owner fixes the beads first and reviews
  the dry run; a bead is never enrolled because of the arm it would get.
- `knowledge/trial/ledger.jsonl` and `results.jsonl` are `merge=union`
  (`.gitattributes`), so two machines that enrol from one base both keep their
  lines; `trial.ledger_problems` then finds a bead enrolled twice, two beads on one
  block position, a second seed or a bead started by two sessions. `enroll`,
  `start` and `brief` refuse while any exists and `status` prints it first. It is a
  protocol failure, resolved by the owner, never by appending. **Enrol from one
  machine.**

### Blinding and blind scoring

- Escapes are scored **after** 14 days, by an agent or person who is not told the
  arm. `watermill trial scorepack` builds the scorer's prompt from each due bead's
  own text, the repo path, the landing commit and date, and the rubric
  (`trial.RUBRIC`: severities blocker, bug, test-gap, quality). It contains no arm,
  no label, no ledger path and **no PR number**, and beads are in hash order, not
  enrolment order. A bead is "due" when it is collected, landed, 14 days old and
  has no final score (`trial.due_for_scoring`).
- Both arms land with the same squash message shape, so main looks the same. The
  scorer is told to read `origin/main` only, always through `trial.BLIND_PATHSPEC`,
  which excludes `brain/`, `knowledge/`, `.beads/` and `HANDOFF*` (handoffs, run
  records, findings and labels name the arm). It is told not to open PRs, branches
  or authors on GitHub and not to `bd show` the scored beads, and it is not given
  `watermill recall`.
- Both briefs tell the session to keep the words "trial" and "arm" out of PRs,
  commits and bead text. **Findings** carry the arm tag (`trial:A|B`) on purpose,
  so the graph grows from both arms; the scorer never sees them.
- `watermill trial score <bead> --none | --escape SEVERITY:REF[:SUMMARY]
  [--scorer LABEL] [--early]` files the result. A score filed before 14 days
  (`--early`) is provisional and ignored by `status`; scores are append-only, latest
  wins.
- **Residual leaks, stated in the protocol** (`TRIAL.md` s7): the scorer could
  ignore its instructions; a landed diff's style can differ by arm; a defect under
  an excluded path would be missed. The result must be reported with that limit.

### Outcomes and looks

- **Primary**: the proportion of landed, scored beads with at least one escape of
  severity bug or worse within 14 days, arm A against arm B, by two-sided Fisher's
  exact test at alpha 0.05, with Wilson intervals and Newcombe's difference
  interval. A sensitivity line treats every bead not landed within 30 days of
  enrolment as a failure.
- **Secondary** (exploratory, no multiplicity correction): cost (laptop beads only),
  duration, first-push CI green, landed rate; owner corrections are descriptive.
- **Looks**: interim at 30 scored beads per arm, final at 60. There is **no early
  stopping on p-values**, no alpha is spent at the interim, and no p-value is
  printed before it (below 8 per arm `status` says "too few to say").
- **Missing data** stays in the ledger as "in progress" and is listed, not dropped.

### The harm stop, pause and resume

The only reason to stop early besides a broken harness is pre-registered
(2026-10-14, water-mill-kt6): any trial bead, in either arm, that has landed and is
found to carry a **blocker-class escape** (breaks prod, loses or corrupts data,
leaks a secret or personal data, bypasses auth); or an arm B run that edits a
fenced path, ignores a READ ONLY / Out of scope mark, or merges with a failing
check. It is judged on that one defect alone, never on arm counts or rates.

- `watermill trial pause --reason "..."` appends a `pause` ledger line;
  `enroll` and `start` then refuse and `status` prints PAUSED with the reason.
  `watermill trial resume --reason "..."` is the owner's written decision, made on
  the defect and its handling alone, and lists the pauses it clears so a union
  merge cannot reorder one away. Beads already in their window keep being observed
  and scored; the offending change is reverted on main and the bead stays in the
  ledger as scored.
- **Detecting the trigger is a human judgement**; no automation does it, and only
  the owner runs pause and resume.

### The session guards

`watermill trial start <bead>` is every trial session's first action; it records
`CLAUDE_CODE_SESSION_ID`, the arm and the surface (`cloud` when
`CLAUDE_CODE_REMOTE=true`) as a ledger `start` line, and refuses a second bead in
one session. That ledger line is the marker the guards use:

- **Refused from a session that ran `trial start`** (exit non-zero, in
  `trial._refuse_trial_session`, reached from `cmd_trial` for enroll, score and
  scorepack and from `trial._set_pause` for pause and resume): `pause`, `resume`,
  `enroll` (not `--dry-run`), `score` and `scorepack`.
- **Open to every session:** `collect`, `status`, `brief`, `start` and
  `enroll --dry-run`. (The briefs still tell a session never to run
  `collect` or to edit `knowledge/trial/`.)
- The owner's own terminal has no such session id, so it is never blocked. Crew
  subagents inherit the orchestrator's `CLAUDE_CODE_SESSION_ID`, so in arm A the
  guard binds millstone, bolter, sluice and tailrace too.
- **Limits:** the guard does not catch a session that skipped `trial start` or that
  unsets the variable; it stops mistakes, not a determined session, and the brief
  covers the rest.

### The briefs

`watermill trial brief <bead> [--surface laptop|cloud]` prints the exact prompt for
the session, from the ledger's arm. Arm A's brief makes the session the
**orchestrator** of exactly one bead: run the crew as subagents one after another,
put the trial tag line verbatim into each crew agent's prompt, do not implement or
review yourself, follow the agents' own definitions, and sign off with an
orchestrator handoff and `agents record --role orchestrator --arm A`. Arm B's brief
makes the session a single general-purpose Claude that must not use the four crew
agents or delegate review, writes `brain/handoffs/solo/<slug>.md`, lands its own PR
under the same rule and signs off with `agents record --role solo --arm B`. Both
briefs carry the denial rule (ADR-0011), the owner-only-commands ban and the
knowledge steps. `tests/test_trial.py` pins that both briefs name every agent in
`canon/`. A cloud brief adds the cloud flow (section 8).

### Collect, cost and status

- `watermill trial collect [--dry-run] [--pr BEAD=N] [--cost-usd BEAD=USD]
  [--sessions-dir DIR]`, after the session has exited. For each started bead it
  reads the PR through the REST API (merged, first-green CI, owner commits) and,
  on the laptop, the session transcript's last `cost-state` line (numbers only; the
  session must have stopped being written for five minutes). It appends a result
  line only when something changed; the latest line per bead wins.
- **Cloud, plainly**: a cloud session cannot read its own final cost-state and its
  transcript does not return to the laptop. The brief has it run `agents record` at
  sign-off, stored as `cost_basis: recorded-snapshot`; arm A's snapshot is the
  orchestrator only, so it is a floor that flatters the crew. `status` compares cost
  on laptop beads only (`COMPARED_COST_BASES`) and says how many it left out. The
  owner may supply the true figure with `collect --cost-usd BEAD=USD`
  (`cost_basis: manual`, reported, never compared). Duration, CI, landing and
  escapes do not depend on the surface.
- `watermill trial status [--json]` at any time: per-arm counts, the stage
  (`pre-interim`, `interim`, `final`), ledger problems, a PAUSED notice, and the
  withheld p-value rule above.

### How to start a new trial

1. **Check the ground.** `ls knowledge/trial/`: only `archive/` should be there
   (or a ledger you mean to continue). `watermill trial status` shows any ledger
   problem or pause. The target repos must be registered, enabled and checked out
   (`watermill projects`), and their crew files current (`watermill sync <project>`
   merged; `watermill validate` clean) so arm A means the four-agent crew. If you
   want to change anything about the design, write a dated amendment to
   `docs/TRIAL.md` first.
2. **Pick beads, then look at the arms.** Choose the beads by the eligibility
   rules, not by arm. `./bin/watermill trial enroll <repo> --ready --dry-run
   [--seed N]` (or name the beads) lists ineligible beads with the reason and shows
   the assignment. Enrol in multiples of four per repo for exact balance.
3. **Enrol, from your own terminal** (not from a trial session):
   `./bin/watermill trial enroll <repo> <bead>... [--seed N]` writes the seed and
   enrol lines to `knowledge/trial/ledger.jsonl` and labels each bead. If a label
   fails it prints the `bd label add` command to run. Commit `knowledge/trial/` and
   each repo's `.beads/issues.jsonl`.
4. **Brief and run, one bead per fresh top-level session.**
   `./bin/watermill trial brief <bead> --surface laptop` (or `cloud`), paste the
   output as the opening prompt of a new Claude Code session. Its first action is
   `trial start`. In a cloud session attach water-mill, or `trial start`, `recall`
   and `remember` cannot run.
5. **Collect** once the session has exited: `./bin/watermill trial collect`
   (add `--pr BEAD=N` if the PR cannot be found from the agents' records,
   `--cost-usd` for a cloud bead's true cost). Commit `knowledge/trial/`.
6. **Score, 14 days after each landing**: `./bin/watermill trial scorepack`, give
   the prompt to a blind scorer (fresh agent or person, no recall, no handoffs),
   then `./bin/watermill trial score <bead> --none` or `--escape SEV:REF:SUMMARY`.
7. **Watch the stop rule.** If a landed trial bead carries a blocker-class defect,
   or an arm B run breaches the fence, run `./bin/watermill trial pause --reason
   "..."` and decide on that defect alone before any `resume`.
8. **Read `status`** (`--json` for a machine form) at the interim (30 per arm) and
   final (60 per arm) looks, and report the leak limits of section 7 of
   `TRIAL.md` with the result.

## 11. Adding a project

[`ONBOARDING.md`](ONBOARDING.md) is the full procedure. Four prerequisites, in
order, because each makes the next safe: a gate that catches real breakage
(`watermill doctor --gate`), a verified restore (`commands.backup_check`), a fence
(`watermill validate` reports a non-zero count) and a queue deep enough that the
agent never invents work. A project missing any of them can be registered and
driven supervised, but must not run overnight.

```bash
./bin/watermill init ../my-project            # writes a commented watermill.yaml
$EDITOR ../my-project/watermill.yaml
./bin/watermill add my-project ../my-project  # registers it, then runs sync last (--no-sync to skip)
./bin/watermill validate my-project
```

`watermill add` is the registration command (there is no `register` subcommand;
`watermill --help` lists the commands). It runs `sync` as its last step, so the
new project gets a canon PR (crew agents, skills, guardrail hook, managed settings)
in the same motion; a failure there never un-registers the project, and
`watermill sync <name>` repeats the step. A project that cannot take a contract
file yet gets a vendored one in `projects/<name>.yaml` with `contract:` in
`projects.yaml`. For the crew to work in the new repo it also wants a
`CLAUDE.md` naming where its handoffs go, and `CODING_STANDARDS.md`, `CONTEXT.md`
and `docs/adr/` (which bolter reviews against; a missing one is never a finding by
itself). A cell stamped from `watermill-cell-template` is synced like any project.

## 12. What the docs do not say

Said plainly, so nobody reads silence as a fact:

- **Owner memory contents.** See section 3: only the notes' names and what each ADR
  quotes of them are in the repository.
- **Where `scripts/sync-factory.sh` is wired.** It is designed for a SessionStart
  hook but is not in this repo's `.claude/settings.json`; whether it is wired in
  the owner's user-level or a sibling repo's settings is not recorded here.
- **Where the beads-sync workflow lives.** The crew files and `cloud-setup.sh`
  rely on it carrying `.beads/issues.jsonl` from a session branch to main; this
  repo's `.github/workflows/` holds only `verify.yml`.
- **Unattended use.** `README.md` states it is not approved: caps have only been
  proven with stub agents, and nights run is 0 (`docs/CALIBRATION.md`).
- **Agent behaviour.** The stub agents test control flow, not agent behaviour; a
  green suite is not an argument that the loop is ready (`CLAUDE.md`).
