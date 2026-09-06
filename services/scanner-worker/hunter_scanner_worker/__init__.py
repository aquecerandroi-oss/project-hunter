"""hunter_scanner_worker -- features, anomalies, regime and opportunities.

``HUNTER_ROLE=scanner``. Consumes the ``market.*`` streams, evaluates every
monitored market against the engines of ``hunter_indicators`` and persists what
it concluded: ``feature_snapshots``, ``anomalies``, ``market_regimes``,
``opportunities`` (+ history) and ``feature_baselines``. Publishes through the
transactional outbox; never calls an exchange.
"""

from hunter_core.runtime import RoleRegistry
from hunter_scanner_worker.main import run_scanner

__version__ = "0.1.0"

RoleRegistry["scanner"] = run_scanner

__all__ = ["run_scanner"]
