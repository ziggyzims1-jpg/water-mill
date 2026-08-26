"""Water Mill: a multi-project orchestrator for supervised and unattended agent work.

The factory drives repositories it knows nothing about. What it knows is how to
refuse to start, how to bound a run, how to check that work is real rather than
reported, and how to write down what happened. Everything project-specific
arrives through a contract -- see `watermill/contract.py`.
"""

__version__ = "0.1.0"
