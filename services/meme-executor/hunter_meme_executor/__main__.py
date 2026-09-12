"""``python -m hunter_meme_executor`` -- the ``HUNTER_ROLE=meme_executor`` entrypoint."""

from __future__ import annotations

import asyncio

from hunter_core.runtime import RoleRegistry, WorkerRuntime
from hunter_core.settings import get_settings
from hunter_meme_executor.config import INSTANCE, ROLE
from hunter_meme_executor.main import run_meme_executor

RoleRegistry["meme_executor"] = run_meme_executor


def main() -> None:
    settings = get_settings()
    # Role ``meme`` with the fixed instance ``executor``: the heartbeat key is exactly
    # ``hb:meme:executor`` (the brief's), next to the radar's ``hb:meme:radar``. One
    # wallet, one signer, one process — a second replica would fight the same
    # signing locks and is refused by the deployment, not by the heartbeat.
    runtime = WorkerRuntime(role=ROLE, settings=settings, instance=INSTANCE)
    asyncio.run(runtime.run(run_meme_executor))


if __name__ == "__main__":
    main()
