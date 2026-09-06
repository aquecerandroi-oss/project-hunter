"""An active roster nobody can run must be loud — MUST-FIX 1(b).

``main.py`` already refuses to start without ``0002_shadow_lab`` because "a
worker that runs while dropping every signal is the worst possible failure
mode". A worker whose every ``active`` version is skipped for a ``code_ref``
mismatch is exactly that failure mode arriving later, and until now it was
invisible: the versions were logged one by one and ``/ready`` stayed green.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_strategy_worker.catalogue import VersionRoster, load_version_roster
from hunter_strategy_worker.code_ref import version_code_ref
from hunter_strategy_worker.config import ShadowConfig
from hunter_strategy_worker.consumer import ConsumerHealth
from hunter_strategy_worker.health import readiness_checks
from hunter_strategy_worker.outbox import OutboxHealth

from .builders import activate_version, seed_market

CONFIG = ShadowConfig()


@pytest.mark.unit
class TestBlindRoster:
    def test_an_empty_catalogue_is_not_blind(self) -> None:
        """No activated version is a legitimate state (before the ops script
        runs); it is not the same as an activated version nobody can run."""
        assert VersionRoster([], active_rows=0, rejected={}).blind is False

    def test_active_rows_with_no_runnable_version_is_blind(self) -> None:
        roster = VersionRoster([], active_rows=2, rejected={"code_ref_mismatch": 2})
        assert roster.blind is True

    def test_one_runnable_version_is_enough_to_run(self) -> None:
        roster = VersionRoster([object()], active_rows=2, rejected={"no_code": 1})  # type: ignore[list-item]
        assert roster.blind is False


@pytest.mark.integration
class TestRosterCounts:
    async def test_a_frozen_mismatch_is_counted_and_named(self, db_session_factory: Any) -> None:
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(
                session,
                key="roster_mismatch",
                code_ref="hunter_core.strategies.volume_anomaly_v1@sha256:" + "0" * 64,
            )
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            roster = await load_version_roster(session)
        assert roster.active_rows > len(roster.versions)
        assert roster.rejected.get("code_ref_mismatch", 0) >= 1

    async def test_a_version_frozen_with_this_code_is_runnable(
        self, db_session_factory: Any
    ) -> None:
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(
                session, key="volume_anomaly", code_ref=version_code_ref("volume_anomaly_v1")
            )
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            roster = await load_version_roster(session)
        assert "volume_anomaly" in {v.strategy_key for v in roster.versions}
        assert roster.blind is False


@pytest.mark.integration
class TestReadiness:
    async def test_ready_turns_red_when_no_active_version_is_runnable(
        self, db_session_factory: Any
    ) -> None:
        """The whole point: silence with a green light is the failure mode."""
        checks = {
            check.__name__: check
            for check in readiness_checks(
                db_session_factory, CONFIG, ConsumerHealth(), OutboxHealth()
            )
        }
        assert "shadow_versions" in checks
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(
                session, key="volume_anomaly", code_ref=version_code_ref("volume_anomaly_v1")
            )
        assert await checks["shadow_versions"]() is True
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            # ``status`` is the one lifecycle field the freeze trigger leaves
            # mutable (DATABASE.md §16.1), so the scenario is arranged and undone
            # without fighting it — and without deleting an activated row, which
            # the trigger refuses on purpose.
            await session.execute(
                text(
                    "UPDATE strategy_versions SET status = 'deprecated' "
                    "WHERE status = 'active' AND activated_at IS NOT NULL"
                )
            )
            await activate_version(
                session,
                key="roster_blind",
                code_ref="hunter_core.strategies.volume_anomaly_v1@sha256:" + "1" * 64,
            )
        try:
            assert await checks["shadow_versions"]() is False
        finally:
            async with role_session(db_session_factory, db_role="hunter_worker") as session:
                await session.execute(
                    text(
                        "UPDATE strategy_versions v SET status = 'deprecated' "
                        "FROM strategies s WHERE s.id = v.strategy_id AND s.key = 'roster_blind'"
                    )
                )
                await session.execute(
                    text(
                        "UPDATE strategy_versions v SET status = 'active' FROM strategies s "
                        "WHERE s.id = v.strategy_id AND s.key = 'volume_anomaly'"
                    )
                )
