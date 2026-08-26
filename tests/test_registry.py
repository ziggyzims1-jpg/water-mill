"""The registry, and the precedence rule between a vendored contract and a real one."""

from __future__ import annotations

import pytest

from watermill.errors import ContractError, RegistryError
from watermill.registry import Registry

CONTRACT = """\
version: 1
name: {name}
commands:
  gate: {gate}
git:
  base_branch: main
"""


def _factory(tmp_path, registry_body: str):
    (tmp_path / "projects.yaml").write_text("version: 1\n" + registry_body)
    return tmp_path


def test_loads_a_project(tmp_path):
    target = tmp_path / "app"
    target.mkdir()
    (target / "watermill.yaml").write_text(CONTRACT.format(name="app", gate="make test"))
    root = _factory(tmp_path, "projects:\n  - name: app\n    path: app\n")

    registry = Registry.load(root)

    assert [p.name for p in registry.projects] == ["app"]
    assert registry.get("app").load_contract().commands.gate == "make test"


def test_a_projects_own_contract_wins_over_a_vendored_one(tmp_path):
    """A repository that has adopted a contract is the authority on its own gate.

    The vendored copy exists so a project can be driven before anyone changes a
    line in it. Once the project carries its own, a stale vendored copy
    silently overriding it is exactly the drift this precedence prevents.
    """
    target = tmp_path / "app"
    target.mkdir()
    (target / "watermill.yaml").write_text(CONTRACT.format(name="app", gate="make real"))
    (tmp_path / "vendored.yaml").write_text(CONTRACT.format(name="app", gate="make stale"))
    root = _factory(
        tmp_path,
        "projects:\n  - name: app\n    path: app\n    contract: vendored.yaml\n",
    )

    assert Registry.load(root).get("app").load_contract().commands.gate == "make real"


def test_a_vendored_contract_is_used_when_the_project_has_none(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "vendored.yaml").write_text(CONTRACT.format(name="app", gate="make v"))
    root = _factory(
        tmp_path,
        "projects:\n  - name: app\n    path: app\n    contract: vendored.yaml\n",
    )

    assert Registry.load(root).get("app").load_contract().commands.gate == "make v"


def test_a_name_mismatch_is_refused(tmp_path):
    """The name attributes a run, a log directory and a ledger entry."""
    target = tmp_path / "app"
    target.mkdir()
    (target / "watermill.yaml").write_text(CONTRACT.format(name="other", gate="make t"))
    root = _factory(tmp_path, "projects:\n  - name: app\n    path: app\n")

    with pytest.raises(RegistryError, match="contract at .* says"):
        Registry.load(root).get("app").load_contract()


def test_a_missing_contract_is_refused_with_both_places_it_looked(tmp_path):
    (tmp_path / "app").mkdir()
    root = _factory(tmp_path, "projects:\n  - name: app\n    path: app\n")

    with pytest.raises(RegistryError, match="no contract"):
        Registry.load(root).get("app").load_contract()


def test_a_duplicate_project_is_refused(tmp_path):
    root = _factory(
        tmp_path,
        "projects:\n  - name: app\n    path: a\n  - name: app\n    path: b\n",
    )
    with pytest.raises(RegistryError, match="duplicate"):
        Registry.load(root)


def test_an_unknown_registry_key_is_refused(tmp_path):
    root = _factory(tmp_path, "projects:\n  - name: app\n    path: a\n    pathh: b\n")
    with pytest.raises(RegistryError, match="unknown key"):
        Registry.load(root)


def test_an_unknown_project_names_the_ones_that_exist(tmp_path):
    root = _factory(tmp_path, "projects:\n  - name: app\n    path: a\n")
    with pytest.raises(RegistryError, match="Registered: app"):
        Registry.load(root).get("nope")


def test_a_disabled_project_is_listed_but_not_active(tmp_path):
    root = _factory(
        tmp_path,
        "projects:\n  - name: app\n    path: a\n    enabled: false\n",
    )
    registry = Registry.load(root)
    assert len(registry.projects) == 1
    assert registry.active == ()


def test_a_missing_registry_says_how_to_make_one(tmp_path):
    with pytest.raises(RegistryError, match="watermill add"):
        Registry.load(tmp_path)


def test_a_broken_contract_refuses_at_load_rather_than_partly_applying(tmp_path):
    """A half-read contract is how a fence ends up empty."""
    target = tmp_path / "app"
    target.mkdir()
    (target / "watermill.yaml").write_text("version: 1\nname: app\ncommands: {}\n")
    root = _factory(tmp_path, "projects:\n  - name: app\n    path: app\n")

    with pytest.raises(ContractError):
        Registry.load(root).get("app").load_contract()
