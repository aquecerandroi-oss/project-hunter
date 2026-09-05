"""hunter_market_worker — WebSocket ingest, universe, recovery, persist (HUNTER_ROLE=market)."""

from hunter_core.runtime import RoleRegistry
from hunter_market_worker.main import run_market

__version__ = "0.0.0"

RoleRegistry["market"] = run_market
