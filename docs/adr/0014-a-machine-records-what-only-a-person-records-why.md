---
status: accepted
---
# Root cause is supplied by a person; a machine may only hint

`tasklog.py` writes one line per task automatically and leaves `root_cause` empty until someone who watched supplies it. A `hint` is allowed, but never for the buckets in `HUMAN_ONLY` (`gate-hole`, `none`, `agent-error`), because work that passes every check and is still wrong is invisible to the thing running the checks, and a guess stored where a judgement belongs counts as one. Source: `CLAUDE.md` (Conventions), `watermill/tasklog.py`.
