"""``python -m hunter_execution_worker`` — the ``HUNTER_ROLE=execution`` entrypoint."""

from __future__ import annotations

import asyncio

from hunter_core.logging import get_logger
from hunter_core.runtime import WorkerRuntime
from hunter_core.settings import get_settings
from hunter_execution_worker.main import run_execution

logger = get_logger(__name__)


def main() -> None:
    settings = get_settings()
    runtime = WorkerRuntime(role="execution", settings=settings)
    asyncio.run(runtime.run(run_execution))


if __name__ == "__main__":
    main()
