"""``python -m hunter_meme_worker`` -- the ``HUNTER_ROLE=meme`` entrypoint."""

from __future__ import annotations

import asyncio

from hunter_core.runtime import RoleRegistry, WorkerRuntime
from hunter_core.settings import get_settings
from hunter_meme_worker.config import INSTANCE, ROLE
from hunter_meme_worker.main import run_meme

RoleRegistry[ROLE] = run_meme


def main() -> None:
    settings = get_settings()
    runtime = WorkerRuntime(role=ROLE, settings=settings, instance=INSTANCE)
    # The instance name is fixed, so the heartbeat key is exactly ``hb:meme:radar``
    # -- PumpPortal serves one connection per client and documents that several
    # can earn an hourly ban, so this collector is a singleton by construction
    # (``config.INSTANCE`` states the consequence).
    asyncio.run(runtime.run(run_meme))


if __name__ == "__main__":
    main()
