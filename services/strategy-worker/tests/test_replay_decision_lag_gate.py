"""The replay pause gate's decision-lag reason and its resume hysteresis (T3.80).

T3.76 measured the live lane's own decision lag climb from a 26 s median to a
90 s median / 171 s p95 while a replay ran ``docker exec`` inside the live
worker's container — and neither ``outbox_lag_s`` nor the consumer group's own
``XINFO`` lag (T3.74b) ever moved. This file proves the new third signal
(``decision_lag_p50_s``/``_p95_s``, already on ``hb:strategy:shadow`` since
T3.74c) actually pauses the gate, and that resuming after it clears requires a
run of continuously-healthy readings, not just one.

No Docker, no real Redis: a small in-memory fake stands in for ``hgetall``
(the heartbeat), ``xinfo_groups`` (T3.74b's consumer-lag axis, always healthy
here — that axis is ``test_replay_contract.py::TestConsumerLagGate``'s job)
and ``get``/``set`` (the hysteresis marker this task adds).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest

from hunter_strategy_worker.config import CONSUMER_GROUP
from hunter_strategy_worker.replay.budget import ReplayBudget, live_lane_degraded
from hunter_strategy_worker.replay.decision_lag import DECISION_LAG_SINCE_KEY, decision_lag_reason
from hunter_strategy_worker.shard import consumer_groups, heartbeat_keys

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 10, 12, tzinfo=UTC)


class _FakeRedis:
    """``hgetall``/``xinfo_groups`` (already-healthy defaults) plus an
    in-memory ``get``/``set`` for the hysteresis marker."""

    def __init__(self, fields: dict[str, str] | None = None, *, lag: int = 0) -> None:
        self._fields = dict(fields or {})
        self._lag = lag
        self._store: dict[str, str] = {}

    async def hgetall(self, _key: str) -> dict[str, str]:
        return dict(self._fields)

    async def xinfo_groups(self, _stream: str) -> list[dict[Any, Any]]:
        return [{b"name": CONSUMER_GROUP.encode(), b"lag": self._lag}]

    async def set(self, key: str, value: str, *, ex: int | None = None) -> None:
        del ex
        self._store[key] = value

    async def get(self, key: str) -> str | None:
        return self._store.get(key)


def _healthy_heartbeat(**extra: str) -> dict[str, str]:
    return {"ts": NOW.isoformat(), "outbox_lag_s": "0.0", **extra}


class TestDecisionLagReason:
    """:func:`decision_lag_reason` in isolation, no full gate involved."""

    async def test_no_signal_yet_is_not_degraded_and_never_touches_redis(self) -> None:
        class _ExplodingRedis:
            async def get(self, _key: str) -> None:
                raise AssertionError("must not be called with no decision-lag data")

            async def set(self, *_args: Any, **_kwargs: Any) -> None:
                raise AssertionError("must not be called with no decision-lag data")

        reason = await decision_lag_reason(
            cast("Any", _ExplodingRedis()),
            {},
            p50_max_s=10.0,
            p95_max_s=30.0,
            resume_healthy_s=300.0,
            now=NOW,
        )
        assert reason is None

    async def test_a_reading_under_both_thresholds_is_healthy(self) -> None:
        redis = _FakeRedis()
        reason = await decision_lag_reason(
            cast("Any", redis),
            {"decision_lag_p50_s": "4.0", "decision_lag_p95_s": "9.0"},
            p50_max_s=10.0,
            p95_max_s=30.0,
            resume_healthy_s=300.0,
            now=NOW,
        )
        assert reason is None

    async def test_p50_past_its_threshold_pauses_and_records_the_since_marker(self) -> None:
        redis = _FakeRedis()
        reason = await decision_lag_reason(
            cast("Any", redis),
            {"decision_lag_p50_s": "94.0", "decision_lag_p95_s": "9.0"},
            p50_max_s=10.0,
            p95_max_s=30.0,
            resume_healthy_s=300.0,
            now=NOW,
        )
        assert reason == "decision_lag:p50=94s,p95=9s"
        assert await redis.get(DECISION_LAG_SINCE_KEY) == NOW.isoformat()

    async def test_p95_alone_past_its_threshold_also_pauses(self) -> None:
        redis = _FakeRedis()
        reason = await decision_lag_reason(
            cast("Any", redis),
            {"decision_lag_p50_s": "4.0", "decision_lag_p95_s": "171.0"},
            p50_max_s=10.0,
            p95_max_s=30.0,
            resume_healthy_s=300.0,
            now=NOW,
        )
        assert reason == "decision_lag:p50=4s,p95=171s"

    async def test_a_healthy_reading_soon_after_a_bad_one_still_cools_down(self) -> None:
        redis = _FakeRedis()
        await redis.set(DECISION_LAG_SINCE_KEY, (NOW - timedelta(seconds=60)).isoformat())
        reason = await decision_lag_reason(
            cast("Any", redis),
            {"decision_lag_p50_s": "3.0", "decision_lag_p95_s": "9.0"},
            p50_max_s=10.0,
            p95_max_s=30.0,
            resume_healthy_s=300.0,
            now=NOW,
        )
        assert reason == "decision_lag_cooldown:240s"

    async def test_a_healthy_reading_resumes_once_the_cooldown_elapses(self) -> None:
        redis = _FakeRedis()
        await redis.set(DECISION_LAG_SINCE_KEY, (NOW - timedelta(seconds=301)).isoformat())
        reason = await decision_lag_reason(
            cast("Any", redis),
            {"decision_lag_p50_s": "3.0", "decision_lag_p95_s": "9.0"},
            p50_max_s=10.0,
            p95_max_s=30.0,
            resume_healthy_s=300.0,
            now=NOW,
        )
        assert reason is None

    async def test_exactly_at_the_cooldown_boundary_still_waits(self) -> None:
        redis = _FakeRedis()
        await redis.set(DECISION_LAG_SINCE_KEY, (NOW - timedelta(seconds=300)).isoformat())
        reason = await decision_lag_reason(
            cast("Any", redis),
            {"decision_lag_p50_s": "3.0", "decision_lag_p95_s": "9.0"},
            p50_max_s=10.0,
            p95_max_s=30.0,
            resume_healthy_s=300.0,
            now=NOW,
        )
        assert reason is None, "elapsed == resume_healthy_s must resume, not wait one more tick"

    async def test_a_bad_reading_during_cooldown_resets_the_marker(self) -> None:
        """A healthy blip inside a longer degraded episode must not let the
        clock keep counting from the *first* bad reading -- every bad reading
        pushes the marker forward."""
        redis = _FakeRedis()
        await redis.set(DECISION_LAG_SINCE_KEY, (NOW - timedelta(seconds=299)).isoformat())
        reason = await decision_lag_reason(
            cast("Any", redis),
            {"decision_lag_p50_s": "94.0", "decision_lag_p95_s": "9.0"},
            p50_max_s=10.0,
            p95_max_s=30.0,
            resume_healthy_s=300.0,
            now=NOW,
        )
        assert reason == "decision_lag:p50=94s,p95=9s"
        assert await redis.get(DECISION_LAG_SINCE_KEY) == NOW.isoformat()

    async def test_redis_down_on_the_cooldown_read_pauses_rather_than_resuming(self) -> None:
        class _FailingGetRedis(_FakeRedis):
            async def get(self, key: str) -> str | None:
                raise RuntimeError("redis down")

        redis = _FailingGetRedis()
        reason = await decision_lag_reason(
            cast("Any", redis),
            {"decision_lag_p50_s": "3.0", "decision_lag_p95_s": "9.0"},
            p50_max_s=10.0,
            p95_max_s=30.0,
            resume_healthy_s=300.0,
            now=NOW,
        )
        assert reason == "decision_lag_since_unreadable"

    async def test_redis_down_on_the_write_still_reports_the_pause(self) -> None:
        class _FailingSetRedis(_FakeRedis):
            async def set(self, *_args: Any, **_kwargs: Any) -> None:
                raise RuntimeError("redis down")

        redis = _FailingSetRedis()
        reason = await decision_lag_reason(
            cast("Any", redis),
            {"decision_lag_p50_s": "94.0", "decision_lag_p95_s": "9.0"},
            p50_max_s=10.0,
            p95_max_s=30.0,
            resume_healthy_s=300.0,
            now=NOW,
        )
        assert reason == "decision_lag:p50=94s,p95=9s"


class TestTheFullGateSurfacesDecisionLag:
    """:func:`live_lane_degraded`, wired end to end (T3.80)."""

    async def test_a_degraded_decision_lag_pauses_the_whole_gate(self) -> None:
        redis = _FakeRedis(
            _healthy_heartbeat(decision_lag_p50_s="94.0", decision_lag_p95_s="171.0")
        )
        reason = await live_lane_degraded(cast("Any", redis), ReplayBudget(), now=NOW)
        assert reason == "decision_lag:p50=94s,p95=171s"

    async def test_a_healthy_decision_lag_does_not_pause(self) -> None:
        redis = _FakeRedis(_healthy_heartbeat(decision_lag_p50_s="2.0", decision_lag_p95_s="4.0"))
        reason = await live_lane_degraded(cast("Any", redis), ReplayBudget(), now=NOW)
        assert reason is None

    async def test_a_heartbeat_with_no_decision_lag_fields_at_all_still_passes(self) -> None:
        """Every gate test that predates T3.80 uses a heartbeat fixture with no
        decision-lag fields; the new check must not break any of them."""
        redis = _FakeRedis(_healthy_heartbeat())
        reason = await live_lane_degraded(cast("Any", redis), ReplayBudget(), now=NOW)
        assert reason is None

    async def test_decision_lag_is_checked_before_the_consumer_group_lag(self) -> None:
        """Both axes degraded at once: the reason names decision_lag, the
        cheaper heartbeat-only check, before paying for the XINFO round trip."""
        redis = _FakeRedis(
            _healthy_heartbeat(decision_lag_p50_s="94.0", decision_lag_p95_s="171.0"), lag=999
        )
        reason = await live_lane_degraded(cast("Any", redis), ReplayBudget(), now=NOW)
        assert reason == "decision_lag:p50=94s,p95=171s"

    async def test_a_recovering_lane_still_pauses_the_gate_during_cooldown(self) -> None:
        redis = _FakeRedis(_healthy_heartbeat(decision_lag_p50_s="2.0", decision_lag_p95_s="4.0"))
        await redis.set(DECISION_LAG_SINCE_KEY, (NOW - timedelta(seconds=30)).isoformat())
        reason = await live_lane_degraded(cast("Any", redis), ReplayBudget(), now=NOW)
        assert reason == "decision_lag_cooldown:270s"

    async def test_custom_thresholds_from_the_budget_are_honoured(self) -> None:
        redis = _FakeRedis(_healthy_heartbeat(decision_lag_p50_s="15.0", decision_lag_p95_s="9.0"))
        budget = ReplayBudget(decision_lag_p50_max_s=20.0)
        assert await live_lane_degraded(cast("Any", redis), budget, now=NOW) is None
        budget = ReplayBudget(decision_lag_p50_max_s=10.0)
        assert await live_lane_degraded(cast("Any", redis), budget, now=NOW) == (
            "decision_lag:p50=15s,p95=9s"
        )


class _ShardedFakeRedis:
    """A ``STRATEGY_SHARDS``-topology fake (T3.87): one heartbeat hash per
    shard key, one shared ``XINFO GROUPS`` answer for the whole stream (every
    shard's own group plus, optionally, an orphan), and the same in-memory
    ``get``/``set`` the hysteresis marker needs."""

    def __init__(
        self,
        heartbeats: dict[str, dict[str, str]],
        *,
        group_lags: dict[str, int] | None = None,
        extra_groups: dict[str, int] | None = None,
    ) -> None:
        self._heartbeats = heartbeats
        self._group_lags = dict(group_lags or {})
        self._extra_groups = dict(extra_groups or {})
        self._store: dict[str, str] = {}

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self._heartbeats.get(key, {}))

    async def xinfo_groups(self, _stream: str) -> list[dict[Any, Any]]:
        entries = [{b"name": name.encode(), b"lag": lag} for name, lag in self._group_lags.items()]
        entries += [
            {b"name": name.encode(), b"lag": lag} for name, lag in self._extra_groups.items()
        ]
        return entries

    async def set(self, key: str, value: str, *, ex: int | None = None) -> None:
        del ex
        self._store[key] = value

    async def get(self, key: str) -> str | None:
        return self._store.get(key)


class TestShardedTopology:
    """``STRATEGY_SHARDS > 1`` (T3.87): the gate derives keys/groups from
    :mod:`hunter_strategy_worker.shard`, takes the worst of the N shards on
    every axis, fails closed naming a missing shard, and ignores an orphan
    consumer group left behind by a resize (notes-T3.84.md §3)."""

    TOTAL = 4
    KEYS = heartbeat_keys(TOTAL)
    GROUPS = consumer_groups(TOTAL)

    def _healthy(self, **extra: str) -> dict[str, str]:
        return {"ts": NOW.isoformat(), "outbox_lag_s": "0.0", **extra}

    def _all_healthy_heartbeats(self) -> dict[str, dict[str, str]]:
        return {key: self._healthy() for key in self.KEYS}

    def _all_healthy_groups(self) -> dict[str, int]:
        return dict.fromkeys(self.GROUPS, 0)

    async def test_four_healthy_shards_do_not_pause(self) -> None:
        redis = _ShardedFakeRedis(
            self._all_healthy_heartbeats(), group_lags=self._all_healthy_groups()
        )
        budget = ReplayBudget(shard_total=self.TOTAL)
        assert await live_lane_degraded(cast("Any", redis), budget, now=NOW) is None

    async def test_one_missing_shard_heartbeat_fails_closed_and_names_it(self) -> None:
        heartbeats = self._all_healthy_heartbeats()
        del heartbeats[self.KEYS[2]]
        redis = _ShardedFakeRedis(heartbeats, group_lags=self._all_healthy_groups())
        budget = ReplayBudget(shard_total=self.TOTAL)
        assert await live_lane_degraded(cast("Any", redis), budget, now=NOW) == (
            f"heartbeat_missing:{self.KEYS[2]}"
        )

    async def test_the_staleness_reported_is_the_worst_of_the_four(self) -> None:
        heartbeats = self._all_healthy_heartbeats()
        stale = (NOW - timedelta(seconds=90)).isoformat()
        heartbeats[self.KEYS[1]] = self._healthy(ts=stale)
        redis = _ShardedFakeRedis(heartbeats, group_lags=self._all_healthy_groups())
        budget = ReplayBudget(shard_total=self.TOTAL)
        assert (
            await live_lane_degraded(cast("Any", redis), budget, now=NOW) == "heartbeat_stale:90s"
        )

    async def test_the_outbox_lag_reported_is_the_worst_of_the_four(self) -> None:
        heartbeats = self._all_healthy_heartbeats()
        heartbeats[self.KEYS[3]] = self._healthy(outbox_lag_s="185.0")
        redis = _ShardedFakeRedis(heartbeats, group_lags=self._all_healthy_groups())
        budget = ReplayBudget(shard_total=self.TOTAL)
        assert await live_lane_degraded(cast("Any", redis), budget, now=NOW) == "outbox_lag:185s"

    async def test_the_decision_lag_reported_is_the_worst_of_the_four(self) -> None:
        heartbeats = self._all_healthy_heartbeats()
        heartbeats[self.KEYS[0]] = self._healthy(decision_lag_p50_s="3.0", decision_lag_p95_s="9.0")
        heartbeats[self.KEYS[2]] = self._healthy(
            decision_lag_p50_s="94.0", decision_lag_p95_s="171.0"
        )
        redis = _ShardedFakeRedis(heartbeats, group_lags=self._all_healthy_groups())
        budget = ReplayBudget(shard_total=self.TOTAL)
        assert await live_lane_degraded(cast("Any", redis), budget, now=NOW) == (
            "decision_lag:p50=94s,p95=171s"
        )

    async def test_the_consumer_lag_reported_is_the_worst_of_the_four(self) -> None:
        lags = self._all_healthy_groups()
        lags[self.GROUPS[1]] = 250
        redis = _ShardedFakeRedis(self._all_healthy_heartbeats(), group_lags=lags)
        budget = ReplayBudget(shard_total=self.TOTAL)
        assert await live_lane_degraded(cast("Any", redis), budget, now=NOW) == "consumer_lag:250"

    async def test_the_orphan_pre_shard_group_is_ignored_and_logged(self) -> None:
        """The exact regression T3.84 measured: the abandoned
        ``strategy-worker.shadow`` group (no ``.NofM`` suffix) sat at
        ``lag=50000`` and climbing while all four live groups read ``lag=0``.
        It must never be counted toward the gate's own reading."""
        redis = _ShardedFakeRedis(
            self._all_healthy_heartbeats(),
            group_lags=self._all_healthy_groups(),
            extra_groups={CONSUMER_GROUP: 50_000},
        )
        budget = ReplayBudget(shard_total=self.TOTAL)
        assert await live_lane_degraded(cast("Any", redis), budget, now=NOW) is None

    async def test_a_shard_missing_from_the_stream_entirely_is_unreadable(self) -> None:
        lags = self._all_healthy_groups()
        del lags[self.GROUPS[0]]
        redis = _ShardedFakeRedis(self._all_healthy_heartbeats(), group_lags=lags)
        budget = ReplayBudget(shard_total=self.TOTAL)
        assert (
            await live_lane_degraded(cast("Any", redis), budget, now=NOW)
            == "consumer_lag_unreadable"
        )
