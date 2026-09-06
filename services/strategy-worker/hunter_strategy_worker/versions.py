"""A short-lived cache of the activated strategy versions.

Reloaded every ``version_refresh_s`` so activating a version takes effect
without a restart, and so a version that is deprecated stops taking *new*
entries promptly. Trackings already open are unaffected: their frozen plan lives
in the outcome row, not here (SHADOW-LAB.md §1).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.logging import get_logger
from hunter_strategy_worker.catalogue import ActiveVersion, load_active_versions

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = get_logger(__name__)

__all__ = ["VersionCache"]


class VersionCache:
    """``load_active_versions`` with a TTL and a last-known-good fallback."""

    def __init__(self, ttl_s: float, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl_s = ttl_s
        self._clock = clock
        self._loaded_at: float | None = None
        self._versions: list[ActiveVersion] = []

    @property
    def versions(self) -> list[ActiveVersion]:
        """Whatever was last loaded, without touching the database."""
        return list(self._versions)

    async def get(self, factory: async_sessionmaker[AsyncSession]) -> list[ActiveVersion]:
        """The active versions, refreshed at most once per TTL."""
        now = self._clock()
        if self._loaded_at is not None and now - self._loaded_at < self._ttl_s:
            return list(self._versions)
        async with role_session(factory, db_role="hunter_worker") as session:
            versions = await load_active_versions(session)
        if [v.id for v in versions] != [v.id for v in self._versions]:
            logger.info(
                "shadow_active_versions",
                versions=[f"{v.strategy_key}:{v.version}" for v in versions],
            )
        self._versions, self._loaded_at = versions, now
        return list(versions)
