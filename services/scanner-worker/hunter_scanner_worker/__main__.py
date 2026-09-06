"""``python -m hunter_scanner_worker`` -- the ``HUNTER_ROLE=scanner`` entrypoint."""

from __future__ import annotations

import asyncio

from hunter_core.runtime import RoleRegistry, WorkerRuntime
from hunter_core.settings import get_settings
from hunter_scanner_worker.main import run_scanner

RoleRegistry["scanner"] = run_scanner


def main() -> None:
    settings = get_settings()
    runtime = WorkerRuntime(role="scanner", settings=settings)
    asyncio.run(runtime.run(run_scanner))


if __name__ == "__main__":
    main()
