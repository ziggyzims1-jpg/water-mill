"""Crew-file drift check (water-mill-mb6): copies must match water-mill's byte for byte."""

from __future__ import annotations

from watermill.cli import main
from watermill.crewdrift import AGENTS_DIR, CREW_FILES, compare


def _crew(root, text="crew\n"):
    d = root / AGENTS_DIR
    d.mkdir(parents=True)
    for name in CREW_FILES:
        (d / name).write_text(text)
    return root


def _factory(tmp_path, entry_extra=""):
    _crew(tmp_path)
    app = _crew(tmp_path / "app")
    (app / "watermill.yaml").write_text(
        "version: 1\nname: app\ncommands:\n  gate: make verify\ngit:\n  base_branch: main\n"
    )
    (tmp_path / "projects.yaml").write_text(
        "version: 1\nprojects:\n  - name: app\n    path: app\n" + entry_extra
    )
    return tmp_path, app


def test_identical_copies_are_clean(tmp_path):
    root, app = _factory(tmp_path)
    assert compare(root, app, "app").clean
    assert main(["--root", str(root), "validate"]) == 0


def test_an_altered_copy_fails_validate(tmp_path, capsys):
    root, app = _factory(tmp_path)
    (app / AGENTS_DIR / "sluice.md").write_text("crew\nstale rule\n")
    assert compare(root, app, "app").differing == ("sluice.md",)
    assert main(["--root", str(root), "validate"]) == 1
    assert "crew files DIFFER" in capsys.readouterr().out


def test_a_missing_copy_fails(tmp_path):
    root, app = _factory(tmp_path)
    (app / AGENTS_DIR / "tailrace.md").unlink()
    assert compare(root, app, "app").differing == ("tailrace.md (missing)",)


def test_an_exempt_project_reports_but_passes(tmp_path, capsys):
    root, app = _factory(tmp_path, "    crew_exempt: later bead\n")
    (app / AGENTS_DIR / "sluice.md").write_text("old\n")
    assert main(["--root", str(root), "validate"]) == 0
    assert "exempt: later bead" in capsys.readouterr().out


def test_an_unregistered_path_is_report_only(tmp_path, capsys):
    root, _ = _factory(tmp_path)
    other = _crew(tmp_path / "workshop", "different\n")
    assert main(["--root", str(root), "validate", "--crew-path", str(other)]) == 0
    assert "unregistered, report only" in capsys.readouterr().out
