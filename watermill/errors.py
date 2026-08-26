"""Every way Water Mill refuses.

The distinction that matters is between a *refusal* and a *failure*. A refusal
means the orchestrator declined to start or to continue because a precondition
did not hold; nothing was changed and nothing needs recovering. A failure means
work was attempted and did not land. They exit with different codes because a
cron wrapper needs to tell them apart: a refusal repeated every night is a
configuration problem, a failure repeated every night is a project problem.
"""


class WatermillError(Exception):
    """Base for everything this package raises deliberately."""

    exit_code = 1


class ContractError(WatermillError):
    """A project contract is missing, malformed, or declares something unusable.

    Raised at load time, before any project command runs. A contract that does
    not parse must never be partially applied: a half-read contract is how a
    fence ends up empty while the run believes it has one.
    """

    exit_code = 2


class RegistryError(WatermillError):
    """The project registry is missing, malformed, or names an unknown project."""

    exit_code = 2


class PreflightRefusal(WatermillError):
    """A precondition did not hold, so the run never started.

    Nothing has been modified when this is raised. Preflight runs before any
    claim is taken and before any agent is invoked.
    """

    exit_code = 3


class CapReached(WatermillError):
    """A cap halted the run. Not an error: this is the system working."""

    exit_code = 0


class FenceViolation(WatermillError):
    """A task modified a path the contract declares off-limits.

    Always accompanied by a discard of that task's work. The fence is checked
    against the diff rather than trusted to the prompt, because an instruction
    is a request and a diff is evidence.
    """

    exit_code = 4
