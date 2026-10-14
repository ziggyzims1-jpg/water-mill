---
status: accepted
---
# The fence is named in the prompt and checked against the diff

`fence.paths` is both told to the agent and compared with `git diff --name-only` (staged, unstaged, untracked and committed) after it exits; a task that touches a fenced path is discarded whatever else it did. A prompt is a request and a diff check is evidence. The fence holds the gate and anything that could weaken it, the schema, and whatever encodes the project's hardest-won decisions. A mechanisable lesson goes into the gate or the fence, and only the remainder into advisory `notes`. Source: `docs/SAFETY.md` (layer 2), `docs/CONTRACT.md` (`fence.paths`), `CLAUDE.md` ("Knowledge has four destinations").
