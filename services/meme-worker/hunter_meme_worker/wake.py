"""T4.52a: the radar's half of the proposal wake-up — the executor's half
(``ProposalWakeListener``) lives in ``services/meme-executor/hunter_meme_executor/wake.py``.

Redis pub/sub, not Postgres ``LISTEN``/``NOTIFY``: banned project-wide
(``docs/SPEC_REVIEW.md`` R7) because every connection in this stack goes
through a transaction-mode pooler, which a session-scoped ``LISTEN`` cannot
survive. Losing a publish only costs the executor's own fallback tick — never
a proposal, whose only source of truth stays ``meme_proposals`` itself.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from hunter_core.logging import get_logger
from hunter_core.redis import keys

if TYPE_CHECKING:
    from hunter_core.runtime import WorkerRuntime

__all__ = ["wake_publisher"]

logger = get_logger(__name__)


def wake_publisher(runtime: WorkerRuntime) -> Callable[[], Awaitable[None]]:
    """Fires the meme-executor's entries loop the instant a Lab tick commits a
    proposal (``LabContext.wake``, ``lab.py``)."""
    channel = keys.meme_proposals_wake()

    async def publish() -> None:
        try:
            await runtime.redis.publish(channel, b"1")  # type: ignore[reportUnknownMemberType]
        except Exception:
            logger.warning("meme_proposal_wake_publish_failed")

    return publish
