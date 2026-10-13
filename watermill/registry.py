"""The project registry: which repositories this factory drives.

A contract describes a project; the registry describes the *factory's*
relationship to it -- where it is checked out, whether it is currently enabled,
and where to find its contract if the project does not yet carry one.

That split is the whole reason there are two files. A contract belongs in the
target repository, so it travels with the code it describes and a change to the
project's gate arrives in the same commit as the change to its Makefile. The
registry belongs here, because which machine has which checkout is not a
property of the project at all.

Until a project carries its own `watermill.yaml`, the registry may point at a
contract vendored under `projects/`. That is how a repository gets driven before
anyone has changed a line in it -- the factory adapts to the project first, and
the contract migrates into the project once it has proven right.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .contract import CONTRACT_FILENAME, Contract
from .errors import RegistryError

REGISTRY_FILENAME = "projects.yaml"
REGISTRY_VERSION = 1


@dataclass(frozen=True)
class Project:
    """One registered target."""

    name: str
    path: Path
    contract_path: Path | None
    enabled: bool
    root: Path
    crew_exempt: str = ""  # reason the crew-file drift check only reports

    @property
    def exists(self) -> bool:
        return self.path.is_dir()

    @property
    def is_git_repo(self) -> bool:
        return (self.path / ".git").exists()

    def resolve_contract_path(self) -> Path:
        """Where this project's contract lives.

        The project's own file wins over the vendored one. A repository that has
        adopted a contract is the authority on its own gate, and a stale copy
        under `projects/` silently overriding it is exactly the drift this
        precedence exists to prevent.
        """
        in_project = self.path / CONTRACT_FILENAME
        if in_project.is_file():
            return in_project
        if self.contract_path and self.contract_path.is_file():
            return self.contract_path
        raise RegistryError(
            f"{self.name}: no contract. Expected one at {in_project}, or a "
            f"vendored one named by the registry's `contract:` key."
        )

    def load_contract(self) -> Contract:
        contract = Contract.load(self.resolve_contract_path())
        if contract.name != self.name:
            raise RegistryError(
                f"registry calls this project {self.name!r} but its contract at "
                f"{contract.source} says {contract.name!r}. Refusing: the name is "
                "how a run, a log directory and a ledger entry are attributed."
            )
        return contract


@dataclass(frozen=True)
class Registry:
    """Every project this factory knows about."""

    projects: tuple[Project, ...]
    source: Path

    @classmethod
    def load(cls, root: Path) -> Registry:
        root = Path(root).resolve()
        path = root / REGISTRY_FILENAME
        if not path.is_file():
            raise RegistryError(
                f"no registry at {path}. Create one with: watermill add <name> <path>"
            )
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise RegistryError(f"{path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise RegistryError(f"{path}: expected a mapping at the top level")

        unknown = sorted(set(raw) - {"version", "projects"})
        if unknown:
            raise RegistryError(f"{path}: unknown key(s) {', '.join(unknown)}")

        version = int(raw.get("version", REGISTRY_VERSION))
        if version != REGISTRY_VERSION:
            raise RegistryError(f"{path}: unsupported registry version {version}")

        entries = raw.get("projects") or []
        if not isinstance(entries, list):
            raise RegistryError(f"{path}: `projects` must be a list")

        projects: list[Project] = []
        seen: set[str] = set()
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise RegistryError(f"{path}: projects[{index}] must be a mapping")
            allowed = {"name", "path", "contract", "enabled", "crew_exempt"}
            entry_unknown = sorted(set(entry) - allowed)
            if entry_unknown:
                raise RegistryError(
                    f"{path}: projects[{index}] unknown key(s) {', '.join(entry_unknown)}"
                )
            name = str(entry.get("name") or "").strip()
            if not name:
                raise RegistryError(f"{path}: projects[{index}] has no name")
            if name in seen:
                raise RegistryError(f"{path}: duplicate project {name!r}")
            seen.add(name)
            raw_path = str(entry.get("path") or "").strip()
            if not raw_path:
                raise RegistryError(f"{path}: {name} has no path")
            # Registry paths are relative to the factory root, so a checkout can
            # move as a unit without every entry needing an absolute rewrite.
            project_path = (root / raw_path).resolve() if not Path(raw_path).is_absolute() \
                else Path(raw_path).resolve()
            contract_raw = str(entry.get("contract") or "").strip()
            contract_path = (root / contract_raw).resolve() if contract_raw else None
            projects.append(
                Project(
                    name=name,
                    path=project_path,
                    contract_path=contract_path,
                    enabled=bool(entry.get("enabled", True)),
                    crew_exempt=str(entry.get("crew_exempt") or "").strip(),
                    root=root,
                )
            )
        return cls(projects=tuple(projects), source=path)

    def get(self, name: str) -> Project:
        for project in self.projects:
            if project.name == name:
                return project
        known = ", ".join(p.name for p in self.projects) or "none registered"
        raise RegistryError(f"unknown project {name!r}. Registered: {known}")

    @property
    def active(self) -> tuple[Project, ...]:
        return tuple(p for p in self.projects if p.enabled)
