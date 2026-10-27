"""The Makefile's recipe shell must not read the system bashrc.

Recipes run under `bash -eu`. Bash reads /etc/bash.bashrc even for a
non-interactive shell when its stdin is a socket and SHLVL is unset or 0 (the
"run by a remote shell daemon" rule), which is how an agent's tool shell can
look. Debian-style bashrc files then expand an unset `$PS1` on their first
line, `-u` turns that into an error, and a recipe fails on code that is fine:
in claudiverse the first `make install && make verify` of two crew runs
failed in `guard` this way and passed on a rerun (2026-10-27). `--norc` in
.SHELLFLAGS keeps the recipe shell from reading any startup file.
"""

from __future__ import annotations

import os
import socket
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_recipes_ignore_the_system_bashrc_when_stdin_is_a_socket(tmp_path):
    # A bashrc that fails under -u, as the container's /etc/bash.bashrc does.
    # BASH_ENV cannot stand in for it (bash reads BASH_ENV whatever the
    # flags), so the check is on the flags themselves: --norc must be there.
    flags = subprocess.run(
        ["make", "-s", "--eval", "print-flags: ; @echo '$(.SHELLFLAGS)'", "print-flags"],
        cwd=REPO, capture_output=True, text=True, check=True,
    ).stdout.split()
    assert "--norc" in flags, f".SHELLFLAGS lacks --norc: {flags}"

    # And the behaviour, where the system bashrc exists and breaks under -u.
    bashrc = Path("/etc/bash.bashrc")
    if not bashrc.exists() or "$PS1" not in bashrc.read_text(errors="ignore"):
        return
    env = {k: v for k, v in os.environ.items() if k not in ("SHLVL", "PS1")}
    a, _b = socket.socketpair()
    try:
        proc = subprocess.run(["make", "-s", "help"], cwd=REPO, env=env, stdin=a,
                              capture_output=True, text=True, timeout=60)
    finally:
        a.close()
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "unbound variable" not in proc.stderr
