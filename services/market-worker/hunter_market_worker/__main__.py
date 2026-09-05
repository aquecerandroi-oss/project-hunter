"""``python -m hunter_market_worker`` — the ``HUNTER_ROLE=market`` entrypoint."""

from __future__ import annotations

import asyncio
import sys

from hunter_core.logging import get_logger
from hunter_core.runtime import WorkerRuntime
from hunter_core.settings import get_settings
from hunter_market_worker.config import UnsupportedExchangeError
from hunter_market_worker.main import run_market

logger = get_logger(__name__)


def main() -> None:
    settings = get_settings()
    runtime = WorkerRuntime(role="market", settings=settings)
    try:
        asyncio.run(runtime.run(run_market))
    except UnsupportedExchangeError as exc:
        logger.error("market_worker_exit", reason=str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
