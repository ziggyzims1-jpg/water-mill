---
status: accepted
---
# A denied tool call is reported as BLOCKED, never retried or routed around

Owner's rule, 2026-09-24. When the permission system or classifier denies a command the agent stops that step and reports BLOCKED to the orchestrator, quoting the command and the reason verbatim; the orchestrator decides and takes anything serious to the owner. The trigger was a tailrace that retried denials until they cleared: the merges were authorized, but retrying past a denial defeats it. Source: memory note `mill-permission-denial-escalation`, `canon/common/.claude/agents/*.md` ("When a tool call is denied").
