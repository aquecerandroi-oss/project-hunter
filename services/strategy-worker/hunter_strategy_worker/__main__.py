"""``python -m hunter_strategy_worker`` — the ``HUNTER_ROLE=strategy`` entrypoint."""

from __future__ import annotations

import asyncio

from hunter_core.logging import get_logger
from hunter_core.runtime import WorkerRuntime
from hunter_core.settings import get_settings
from hunter_strategy_worker.main import run_strategy

logger = get_logger(__name__)


def main() -> None:
    settings = get_settings()
    runtime = WorkerRuntime(role="strategy", settings=settings)
    asyncio.run(runtime.run(run_strategy))


if __name__ == "__main__":
    main()
