#!/usr/bin/env python3
# managed by water-mill (canon/common/.claude/hooks/block-dangerous-git.py); edit it there, then run `watermill sync`
# ruff: noqa: E501 (the sync header below is one long line in every target)
"""PreToolUse(Bash) hook: refuse destructive git commands.

Adapted from mattpocock-skills 1.2.3, misc/git-guardrails-claude-code
(block-dangerous-git.sh), MIT licence, Copyright (c) Matt Pocock.
https://github.com/mattpocock/skills

Why Python and not the upstream bash+jq+grep: the hook must behave the same on
macOS (bash 3.2, often no jq) and on the Linux cloud image, and a grep over the
raw command line cannot tell `git -C dir stash` from `echo "git stash"` or see
a command inside `$( )`. Here the command is tokenised with shlex, split into
simple commands at ; & | ( ) and newlines, and each one is read as
`[env] git [global options] <subcommand> <args>`. Python 3 is on both.

Blocked: git stash (any form); reset --hard; clean -f/--force; branch -D;
checkout/restore of the whole tree (`.`); push --force, -f, --force-with-lease,
--force-if-includes, +refspec. Everything else is allowed.

Input: the PreToolUse JSON on stdin. Output: a deny decision naming the rule.
A hook that cannot read its input allows the call (it must never wedge a
session); the deny rules are the only thing it enforces.
"""

import json
import os
import shlex
import sys

# git options that take a value as the next token (when not written --opt=value)
GLOBAL_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace",
                     "--exec-path", "--super-prefix", "--config-env"}
WRAPPERS = {"env", "command", "sudo", "time", "nohup", "exec", "xargs", "builtin",
            "nice", "!", "then", "do", "else", "{"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
OPERATORS = {";", "&", "|", "&&", "||", "(", ")", ";;", "|&", "&>", ">", ">>", "<"}


def _short(args, letters):
    """True if any short-option cluster (-abc) in args contains one of letters."""
    return any(a.startswith("-") and not a.startswith("--") and len(a) > 1
               and any(c in letters for c in a[1:]) for a in args)


def _opts(args):
    """Arguments before a bare `--` (after it everything is a path)."""
    return args[:args.index("--")] if "--" in args else args


def rule_for(sub, args):
    """The rule name a git subcommand violates, or None."""
    opts = _opts(args)
    if sub == "stash":
        return "git stash (the stash stack is shared by every worktree; snapshot with a patch file)"
    if sub == "reset" and "--hard" in opts:
        return "git reset --hard"
    if sub == "clean" and ("--force" in opts or _short(opts, "f")):
        return "git clean -f (deletes untracked files)"
    if sub == "branch" and (_short(opts, "D") or (
            ("--delete" in opts or _short(opts, "d")) and ("--force" in opts or _short(opts, "f")))):
        return "git branch -D (force delete; use -d)"
    if sub == "checkout" and "." in args:
        return "git checkout . (discards all working-tree changes)"
    if sub == "restore" and "." in args:
        staged_only = (("--staged" in opts or _short(opts, "S"))
                       and "--worktree" not in opts and not _short(opts, "W"))
        if not staged_only:
            return "git restore . (discards all working-tree changes)"
    if sub == "push":
        if (any(a == "--force" or a.startswith(("--force-with-lease", "--force-if-includes"))
                for a in opts) or _short(opts, "f")):
            return "git push --force / -f / --force-with-lease"
        if any(a.startswith("+") and len(a) > 1 for a in opts):
            return "git push +refspec (a forced update)"
    return None


def git_subcommand(words):
    """(subcommand, args) if `words` is a git invocation, else None."""
    i = 0
    while i < len(words):
        w = words[i]
        if "=" in w and not w.startswith("-") and w.split("=", 1)[0].replace("_", "a").isalnum():
            i += 1  # VAR=value prefix
        elif w in WRAPPERS or w.startswith("-") and i > 0 and os.path.basename(words[i - 1]) in WRAPPERS:
            i += 1
        else:
            break
    if i >= len(words) or os.path.basename(words[i]) != "git":
        return None
    i += 1
    while i < len(words) and words[i].startswith("-"):
        i += 2 if words[i] in GLOBAL_WITH_VALUE else 1
    if i >= len(words):
        return None
    return words[i], words[i + 1:]


def segments(command):
    """Simple commands (token lists) of a shell command line; nested -c scripts included."""
    lex = shlex.shlex(command.replace("`", ";").replace("\n", ";"), posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    lex.commenters = ""
    try:
        tokens = list(lex)
    except ValueError:
        tokens = command.split()  # unbalanced quote: still look at the words
    current, out = [], []
    for tok in tokens:
        if tok in OPERATORS or (tok and set(tok) <= set(";&|()<>")):
            if current:
                out.append(current)
            current = []
        elif tok == "$":  # the `$` of `$(`
            continue
        else:
            current.append(tok)
    if current:
        out.append(current)
    # bash -c "git stash" / eval "git stash": the script is one token; read it too.
    nested = []
    for seg in out:
        for j, tok in enumerate(seg):
            if j and (seg[j - 1] == "-c" and os.path.basename(seg[0]) in SHELLS
                      or seg[0] == "eval"):
                nested.extend(segments(tok))
    return out + nested


def violation(command):
    for seg in segments(command):
        found = git_subcommand(seg)
        if found:
            rule = rule_for(*found)
            if rule:
                return rule
    return None


def main():
    try:
        payload = json.load(sys.stdin)
        command = payload["tool_input"]["command"]
    except (ValueError, KeyError, TypeError):
        return 0
    if not isinstance(command, str):
        return 0
    rule = violation(command)
    if rule:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"BLOCKED by the git guardrail: {rule}. Command: {command!r}. "
                "The owner has forbidden this; do not retry or reword it. Report BLOCKED "
                "to the orchestrator if the task truly needs it."),
        }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
