"""hunter_execution_worker — the paper wallet's engine (``HUNTER_ROLE=execution``).

Admission of what the API filed, the order cycle, the protection cycle,
mark-to-market and the kill switch — every one of them one transaction, under
the wallet's lock, with the durable rows as the only source of truth.

Registering the role at import time is the same idiom as the market-worker and
the scanner-worker: ``HUNTER_ROLE=all`` composes the registry, and a role that
only registered inside ``__main__`` would be missing from it.
"""

from hunter_core.runtime import RoleRegistry
from hunter_execution_worker.main import run_execution

__version__ = "0.1.0"

RoleRegistry["execution"] = run_execution

__all__ = ["run_execution"]
