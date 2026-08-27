"""Running a command, and the ways one can fail to run at all."""

from __future__ import annotations

from watermill.proc import run

# -- a command that does not exist -----------------------------------------


def test_a_missing_command_is_a_failed_result_not_an_exception(tmp_path):
    """`doctor` exists to report every check. A traceback out of the first one
    reports none of them, which is worse than the missing command."""
    result = run("./definitely-not-here --check", cwd=tmp_path)
    assert not result.ok
    assert result.returncode == 127
    assert "definitely-not-here" in result.tail


def test_a_missing_command_says_which_one(tmp_path):
    result = run(".venv/bin/python scripts/drill.py", cwd=tmp_path)
    assert ".venv/bin/python" in result.tail


def test_a_missing_command_still_writes_its_log(tmp_path):
    log = tmp_path / "logs" / "out.log"
    result = run("./nope", cwd=tmp_path, log_path=log)
    assert result.returncode == 127
    assert log.is_file()
