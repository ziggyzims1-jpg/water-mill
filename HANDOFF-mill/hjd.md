# Handoff — water-mill-hjd

## Millstone (2026-10-14)
- **Where things stand:** branch bead/hjd, PR #59 (https://github.com/ziggyzims1-jpg/water-mill/pull/59). `make verify` green (847 passed). Not blocked.
- **Failing check for the exact bug:** `.venv/bin/python -m pytest tests/test_publish.py -k user_agent` on base: `AssertionError: assert 'Python-urllib/3.13' == 'watermill/0.1.0'` (real local HTTP server records the UA header). Hypothesis that proved true: push() in watermill/publish.py sets no User-Agent, so urllib's default goes out.
- **Tried / did not work:** a `sed -i` on publish.py failed with a garbled path ("atermill/publish.py") twice; used Edit instead. First verify run failed lint because the `__version__` import was missing.
- **Lessons for the graph:** watermill.publish.push must send `User-Agent: watermill/<__version__>` because Cloudflare BIC 403s urllib's default UA (error 1010). The publish tests use a real socket server, so header assertions go through `cli.main(["publish"])`.
- **Seams:** `watermill publish` via cli.main against a local ThreadingHTTPServer (the existing `zimmy` fixture, extended to record User-Agent).
- **Look here first:** watermill/publish.py push() headers.
- **Open questions:** none. Owner's alternative (WAF rule skipping BIC for /api/watermill) is untouched and could be added as belt-and-braces.
- **Follow-ups:** watermill/shipper.py push() also uses default UA; it targets Loki/Grafana Cloud, not Cloudflare-fronted Zimmy, so left alone; worth a UA there only if Grafana ever blocks it.

## Bolter (2026-10-14)
- **Sources:** CODING_STANDARDS.md, docs/adr/0001-0018, CONTEXT.md, CLAUDE.md, ruff.toml (via CODING_STANDARDS). Missing: CONTRIBUTING.md (not a finding). Recall run; nothing relevant to UA headers.
- **Blocking:** none. publish.py:530-539 keeps the existing `noqa: S310` justification, stays a separate command (ADR 0016), conventional-commit subject, test drives cli.main against a real socket server (seam, independent expected value).
- **Advisory:**
  - Docs drift (judgement): docs/PUBLISH.md:85-88 lists the request headers (Content-Type, X-API-Key) and now omits User-Agent; add "and `User-Agent: watermill/<version>` (Cloudflare BIC 403s urllib's default, error 1010)". [auto-mill candidate]
  - Possible Duplicated Code (judgement, mild): shipper.py:298 builds the same urllib Request shape with the default UA; if a UA is ever added there, extract a shared `_user_agent()`/header helper rather than a second literal. Not worth a bead now (Speculative Generality otherwise).
- **Findings:** none -- no blocking finding, so no repeatable trap to record.
- **Run record:** /private/tmp/claude-501/-Users-andrewzimmerman-Documents-code/1f77a9c6-cafb-41c6-b875-6daaa0451fba/scratchpad/wt-bolter-hjd/knowledge/agent-runs/bolter-water-mill-hjd-a668f11ad233.jsonl (copy at /private/tmp/claude-501/-Users-andrewzimmerman-Documents-code/1f77a9c6-cafb-41c6-b875-6daaa0451fba/scratchpad/bolter-hjd-record/knowledge/agent-runs/bolter-water-mill-hjd-a668f11ad233.jsonl); one line shown in report. Sluice commits it.

## Sluice (2026-10-14)
- **Verdict:** approve_after_fixes. push() in watermill/publish.py now sends `User-Agent: watermill/<__version__>`; bead Goal met, scope limited to publish.py, tests/test_publish.py, docs/PUBLISH.md and run records. No fenced paths touched.
- **Red before green:** reproduced. origin/main's publish.py plus the branch test: `test_push_sends_a_custom_user_agent_not_pythons_default` fails (urllib default UA).
- **Mutations:** header dropped (== base) -> test fails; hard-coded `"watermill/1"` -> test fails; restored -> 54 passed. Test asserts the header as received by a real socket server, so it is meaningful.
- **Independent verify:** `make verify` in wt-sluice-hjd: 847 passed, verify passed.
- **Bolter:** no blocking findings. Advisory 1 (docs/PUBLISH.md step 3 omitted User-Agent) fixed in 3ff8765 per orchestrator. Advisory 2 (shipper.py duplicates Request shape) left as directed; no auto-mill beads filed.
- **Findings:** one lesson recorded (header changes in publish.push must update docs/PUBLISH.md step 3), cause incomplete-files.
- **Not fixed / concerns:** shipper.py still sends the default UA (Loki, not Cloudflare-fronted); fine unless Grafana blocks it. Owner's WAF-rule alternative is untouched.
- **For the lander:** branch carries millstone, bolter and sluice run records under knowledge/agent-runs/. Nothing likely to conflict.

## Tailrace (2026-10-14)
**LANDED** PR #59 squash-merged, sha-guarded at 3ca60f602350e26946c33c7d1ddd7ced47f65568; merge commit 8016330e309d729ce6d4cc6472b935121a015630. verify check green (40s). Remote branch bead/hjd deleted (ls-remote empty). No conflicts.
- auto-mill: none (`bd list -l auto-mill`: No issues found).
- bd close: "Closed water-mill-hjd ... Merged in PR #59", no warnings. Sorted compare differed only in water-mill-hjd and water-mill-mcn (expected, claimed by parallel millstone).
- Findings: sluice's f-20261014-c5abb7 plus the millstone UA lesson filed by tailrace (cause pending).
- Nothing for the human by hand. Owner's WAF-rule alternative remains untouched.
