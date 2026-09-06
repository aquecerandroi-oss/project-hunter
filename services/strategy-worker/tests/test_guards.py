"""Two guards that refuse rather than guess (Astra, S2 diff review).

- the worker only runs a version whose frozen ``code_ref`` is the code this
  process actually carries (must-fix 6);
- ``markets.is_monitored`` may only stand as evidence of eligibility at a bar's
  close while the monitored set has not changed since (must-fix 1/4).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.streams import DEFAULT_MAXLEN, Streams
from hunter_core.strategies.base import EvaluationState
from hunter_strategy_worker.catalogue import (
    code_ref_matches,
    load_active_versions,
    load_version_roster,
)
from hunter_strategy_worker.config import ShadowConfig
from hunter_strategy_worker.decide import evaluate_slot
from hunter_strategy_worker.eligibility import universe_changed_after
from hunter_strategy_worker.repo import load_market

from .builders import EXCHANGE, SYMBOL, activate_version, only_version, seed_market

pytestmark = pytest.mark.integration

CUT = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)


async def _publish_universe_change(redis: Any, *, exchange: str, ts: datetime) -> None:
    envelope = EventEnvelope(
        type=Streams.MARKET_UNIVERSE_CHANGED,
        producer="market-worker@test",
        key=exchange,
        ts=ts,
        payload={"added": [], "removed": [], "total": 0},
    )
    from hunter_core.events.produce import publish

    await publish(
        redis,
        Streams.MARKET_UNIVERSE_CHANGED,
        envelope,
        DEFAULT_MAXLEN[Streams.MARKET_UNIVERSE_CHANGED],
    )


_A = "hunter_core.strategies.momentum_v1@sha256:" + "a" * 64
_B = "hunter_core.strategies.momentum_v1@sha256:" + "b" * 64


@pytest.mark.unit
class TestFrozenCodeRule:
    def test_the_same_digest_runs(self) -> None:
        assert code_ref_matches(_A, _A, "k") is None

    def test_another_digest_is_refused(self) -> None:
        """Activate with digest A, ship B, restart: the worker must not evaluate
        B while recording provenance A."""
        assert code_ref_matches(_A, _B, "k") == "code_ref_mismatch"

    def test_the_superseded_tree_wide_spelling_is_a_mismatch_not_a_blank(self) -> None:
        """A row frozen before MUST-FIX 1 *was* frozen; it just names code that
        no longer exists under that spelling. Calling it "never frozen" would
        hide the reason ``--supersede`` is needed."""
        tree = "hunter_core.strategies@sha256:" + "c" * 64
        assert code_ref_matches(tree, _A, "k") == "code_ref_mismatch"

    def test_a_code_ref_that_is_not_a_digest_is_refused(self) -> None:
        """The seed's placeholder is not evidence of anything; the ops script is
        what writes the definitive one."""
        assert code_ref_matches("hunter_indicators.strategies.volume_v1", _A, "k") == (
            "code_ref_not_frozen"
        )
        assert code_ref_matches(None, _A, "k") == "code_ref_not_frozen"


class TestFrozenCodeGuard:
    async def test_a_version_frozen_against_other_code_is_not_loaded(
        self, db_session_factory: Any
    ) -> None:
        """``momentum`` is registered code, so what stops it here is the digest,
        not a missing implementation."""
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(
                session,
                key="momentum",
                code_ref="hunter_core.strategies.momentum_v1@sha256:" + "d" * 64,
            )
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            versions = await load_active_versions(session)
        assert "momentum" not in {v.strategy_key for v in versions}

    async def test_a_code_ref_naming_another_strategy_s_module_is_refused(
        self, db_session_factory: Any
    ) -> None:
        """Astra, S2 fixes review: resolving by module must not let a momentum
        row execute volume code. When both bindings answer they have to agree."""
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(
                session,
                key="momentum",
                version="v7",
                code_ref="hunter_core.strategies.volume_anomaly_v1@sha256:" + "e" * 64,
            )
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            roster = await load_version_roster(session)
        assert "momentum" not in {v.strategy_key for v in roster.versions}
        assert roster.rejected.get("no_code", 0) >= 1

    async def test_the_matching_digest_is_loaded(self, db_session_factory: Any) -> None:
        from hunter_strategy_worker.code_ref import version_code_ref

        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await seed_market(session)
            await activate_version(
                session, key="volume_anomaly", code_ref=version_code_ref("volume_anomaly_v1")
            )
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            versions = await load_active_versions(session)
        assert "volume_anomaly" in {v.strategy_key for v in versions}


class TestEligibilityEvidence:
    async def test_no_change_since_the_bar_means_the_flag_still_holds(
        self, redis_client: Any
    ) -> None:
        await _publish_universe_change(
            redis_client, exchange=EXCHANGE, ts=CUT - timedelta(minutes=10)
        )
        assert await universe_changed_after(redis_client, exchange=EXCHANGE, instant=CUT) is False

    async def test_a_change_after_the_bar_makes_the_flag_useless(self, redis_client: Any) -> None:
        await _publish_universe_change(
            redis_client, exchange=EXCHANGE, ts=CUT + timedelta(seconds=30)
        )
        assert await universe_changed_after(redis_client, exchange=EXCHANGE, instant=CUT) is True

    async def test_another_exchange_change_is_not_this_market_s_evidence(
        self, redis_client: Any
    ) -> None:
        await _publish_universe_change(
            redis_client, exchange="bybit", ts=CUT + timedelta(minutes=5)
        )
        await _publish_universe_change(
            redis_client, exchange=EXCHANGE, ts=CUT - timedelta(minutes=5)
        )
        assert await universe_changed_after(redis_client, exchange=EXCHANGE, instant=CUT) is False

    async def test_the_evaluation_is_unavailable_when_membership_is_unprovable(
        self, db_session_factory: Any, redis_client: Any
    ) -> None:
        """Unavailable proves nothing: no decision, and no re-arm."""
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            await session.execute(text("DELETE FROM shadow_episodes"))
            await seed_market(session)
            await activate_version(session)
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            versions = await load_active_versions(session)
            market = await load_market(session, EXCHANGE, SYMBOL)
        assert market is not None
        await _publish_universe_change(
            redis_client, exchange=EXCHANGE, ts=CUT + timedelta(seconds=30)
        )
        evaluation = await evaluate_slot(
            db_session_factory,
            redis_client,
            version=only_version(versions),
            market=market,
            bar_close=CUT,
            config=ShadowConfig(),
            clock=lambda: CUT + timedelta(seconds=40),
        )
        assert evaluation.state is EvaluationState.UNAVAILABLE
        assert evaluation.reason == "eligibility_unprovable:universe_changed"
        async with role_session(db_session_factory, db_role="hunter_worker") as session:
            episodes = await session.scalar(text("SELECT count(*) FROM shadow_episodes"))
        assert episodes == 0, "an unprovable bar never even opens a slot"
