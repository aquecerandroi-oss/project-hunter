"""``--explain-ledger``: one line per evaluated bar, and why the bar did nothing.

T3.33f. The replay already counts states (``evaluations_by_state`` in the run's
receipt) and persists decisions, but a run with **zero** decisions leaves no
evidence of what refused them — ``breakout v1`` spent 31 days answering
``geometry_invalidation`` and the only way to know it was to guess (notes-T3.33e).
The explain ledger is that evidence: the strategy's own ``Evaluation``
(``state``, ``reason``, ``detail``) of every bar the run visited, in a file, with
no new table and no new evaluation path.

What is proved here:

1. the row is exactly the five fields of the contract, JSON-typed;
2. a shard per market, merged in the order the markets were dispatched, and
   appended to (two slices of the same run share one ledger);
3. over a real replay, **one line per evaluated bar**: the ledger's histogram is
   the run's ``states`` histogram, bar for bar;
4. the ledger is subject to the same no-look-ahead proof as the decision:
   rewriting every candle after the bar — final or not — does not move a single
   line, and a cut moved into the future is caught by that same comparison.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.domain.enums import ShadowCohort
from hunter_core.strategies.base import Evaluation, EvaluationState
from hunter_strategy_worker import decide
from hunter_strategy_worker.catalogue import load_active_versions
from hunter_strategy_worker.config import ShadowConfig
from hunter_strategy_worker.context import build_market_context
from hunter_strategy_worker.replay import run
from hunter_strategy_worker.replay.budget import load_budget
from hunter_strategy_worker.replay.explain import (
    ExplainLedger,
    ExplainRow,
    merge_shards,
    shard_path,
)
from hunter_strategy_worker.replay.ledger import ReplayRun
from hunter_strategy_worker.replay.simulate import ReplayWindow, replay_market
from hunter_strategy_worker.repo import load_market

from .builders import (
    EXCHANGE,
    SYMBOL,
    activate_version,
    ensure_partitions,
    insert_candles,
    isolate_catalogue,
    only_version,
    seed_market,
)
from .test_replay_engine import CUT, TRIGGER_BAR, replay_series

WINDOW = ReplayWindow(CUT - timedelta(minutes=60), CUT)
ONE_BAR = ReplayWindow(TRIGGER_BAR, TRIGGER_BAR + timedelta(minutes=5))
"""Exactly the bar under test, as in ``test_replay_lookahead.py``: with the
whole hour in the window the later bars would *legitimately* read the rewritten
candles — those minutes are their own past, not their future."""
FUTURE_FROM = TRIGGER_BAR
"""The mutation starts at the cut itself, not five minutes after it
(``test_replay_lookahead.py`` leaves that gap): the bar under test closes at
``TRIGGER_BAR`` and its context stops at ``open_time <= TRIGGER_BAR - 1min``, so
the minute that *opens* at the cut is already the future. Rewriting it too is
what makes the proof cover the boundary instead of a safe distance from it
(Astra, revisão T3.33f, nice-to-have)."""
CHEAT_LOOKAHEAD = timedelta(minutes=30)
BAR = datetime(2026, 9, 5, 11, 0, tzinfo=UTC)


def _read(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


@pytest.mark.unit
class TestTheRow:
    def test_it_is_the_five_fields_and_nothing_else(self) -> None:
        """The contract of the file, so a reader can be written against it."""
        row = ExplainRow(
            bar_close=BAR,
            market="binance:BTCUSDT",
            state="rejected",
            reason="geometry_invalidation",
            detail={"base_low_15m": "100.5"},
        )
        assert list(row.to_jsonable()) == ["bar_close", "market", "state", "reason", "detail"]
        assert row.to_jsonable() == {
            "bar_close": "2026-09-05T11:00:00+00:00",
            "market": "binance:BTCUSDT",
            "state": "rejected",
            "reason": "geometry_invalidation",
            "detail": {"base_low_15m": "100.5"},
        }

    def test_the_detail_stays_an_object_and_the_instant_is_utc(self, tmp_path: Path) -> None:
        """``detail`` is the strategy's own map, already stringified: written as a
        JSON object so a query can reach a key without re-parsing a string.

        The instant is normalised to UTC (``ensure_utc``), which is also why a
        naive one cannot be recorded at all — the same rule the rest of the
        codebase lives by."""
        brasilia = datetime(2026, 9, 5, 8, 0, tzinfo=timezone(timedelta(hours=-3)))
        path = tmp_path / "explain.jsonl"
        with ExplainLedger(path, market="binance:BTCUSDT") as ledger:
            ledger.record(
                brasilia,
                Evaluation(
                    None, EvaluationState.NOT_TRIGGERED, "rvol_low", {"relative_volume_15m": "0.8"}
                ),
            )
        (row,) = _read(path)
        assert row["bar_close"] == "2026-09-05T11:00:00+00:00"
        assert row["detail"] == {"relative_volume_15m": "0.8"}
        assert row["state"] == "not_triggered"

    def test_a_naive_instant_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "explain.jsonl"
        with (
            ExplainLedger(path, market="binance:BTCUSDT") as ledger,
            pytest.raises(ValueError, match="naive datetime"),
        ):
            ledger.record(
                datetime(2026, 9, 5, 11, 0),  # noqa: DTZ001 - the point of the test
                Evaluation(None, EvaluationState.UNAVAILABLE, "warmup"),
            )

    def test_a_ledger_that_recorded_nothing_still_exists_and_is_empty(self, tmp_path: Path) -> None:
        """An empty slice is a fact about the slice, never a missing file."""
        path = tmp_path / "explain.jsonl"
        with ExplainLedger(path, market="binance:BTCUSDT") as ledger:
            assert ledger.rows == 0
        assert path.exists()
        assert _read(path) == []


@pytest.mark.unit
class TestTheShards:
    """One writer per market process; the parent merges. Two processes appending
    to one file is not atomic on Windows, and a merged file is what the brief
    asks for — so the shard is the unit that is written and the ledger is the
    unit that is read."""

    def test_a_shard_is_named_after_its_market(self, tmp_path: Path) -> None:
        base = tmp_path / "explain.jsonl"
        first = shard_path(base, exchange="binance", symbol="BTCUSDT")
        second = shard_path(base, exchange="binance", symbol="ETHUSDT")
        assert first != second
        assert first.parent == base.parent
        assert base.name in first.name

    def test_merge_concatenates_in_dispatch_order_and_removes_the_shards(
        self, tmp_path: Path
    ) -> None:
        base = tmp_path / "explain.jsonl"
        shards: list[Path] = []
        for symbol in ("BTCUSDT", "ETHUSDT"):
            shard = shard_path(base, exchange=EXCHANGE, symbol=symbol)
            with ExplainLedger(shard, market=f"{EXCHANGE}:{symbol}") as ledger:
                ledger.record(BAR, Evaluation(None, EvaluationState.UNAVAILABLE, "warmup"))
            shards.append(shard)
        assert merge_shards(base, shards) == 2
        assert [row["market"] for row in _read(base)] == ["binance:BTCUSDT", "binance:ETHUSDT"]
        assert [shard.exists() for shard in shards] == [False, False]

    def test_a_merge_that_cannot_write_keeps_every_shard(self, tmp_path: Path) -> None:
        """The shard is the only other copy: it is deleted after the ledger is
        closed, never while it is open (Astra, revisão T3.33f, must-fix 2).

        Here the destination cannot be opened at all; the same ordering is what
        protects a ``close`` that fails on a full disk.
        """
        base = tmp_path / "explain.jsonl"
        base.mkdir()  # a directory where the ledger wants a file
        shard = shard_path(base, exchange=EXCHANGE, symbol=SYMBOL)
        with ExplainLedger(shard, market=f"{EXCHANGE}:{SYMBOL}") as ledger:
            ledger.record(BAR, Evaluation(None, EvaluationState.NOT_TRIGGERED, "no_breakout"))
        with pytest.raises(OSError):
            merge_shards(base, [shard])
        assert shard.exists()
        assert len(_read(shard)) == 1

    def test_a_second_slice_appends_to_the_same_ledger(self, tmp_path: Path) -> None:
        """Two slices of one run are one population; the file follows the run,
        not the slice (same rule as ``--ledger``'s ``append_jsonl``)."""
        base = tmp_path / "explain.jsonl"
        for minute in (0, 15):
            shard = shard_path(base, exchange=EXCHANGE, symbol=SYMBOL)
            with ExplainLedger(shard, market=f"{EXCHANGE}:{SYMBOL}") as ledger:
                ledger.record(
                    BAR + timedelta(minutes=minute),
                    Evaluation(None, EvaluationState.NOT_TRIGGERED, "no_breakout"),
                )
            merge_shards(base, [shard])
        assert [row["bar_close"][11:16] for row in _read(base)] == ["11:00", "11:15"]


@pytest.mark.unit
class TestTheFlag:
    """``--explain-ledger`` is off by default and reaches ``replay_run`` when on."""

    def test_it_is_off_by_default(self) -> None:
        args = run._parser().parse_args(  # pyright: ignore[reportPrivateUsage]
            ["--version", "breakout:v2", "--from", "2026-08-08", "--to", "2026-09-08"]
        )
        assert args.explain_ledger is None

    async def test_the_path_reaches_the_run(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        seen: dict[str, Any] = {}

        async def fake_run(plan: Any, **kwargs: Any) -> Any:
            seen.update(kwargs)
            return _receipt()

        monkeypatch.setattr(run, "replay_run", fake_run)
        wanted = tmp_path / "explain.jsonl"
        args = run._parser().parse_args(  # pyright: ignore[reportPrivateUsage]
            [
                "--version",
                "breakout:v2",
                "--from",
                "2026-08-08",
                "--to",
                "2026-09-08",
                "--explain-ledger",
                str(wanted),
                "--workers",
                "2",
            ]
        )
        await run._run(args, _plan(), load_budget())  # pyright: ignore[reportPrivateUsage]
        assert seen["explain_path"] == wanted
        assert seen["ledger_path"] is None


def _receipt() -> ReplayRun:
    return ReplayRun(
        run_id=uuid.uuid4(),
        cohort=ShadowCohort.replay(uuid.uuid4()),
        strategy_version_id=uuid.uuid4(),
        version_label="breakout v2",
        window_from=datetime(2026, 8, 8, tzinfo=UTC),
        window_to=datetime(2026, 9, 8, tzinfo=UTC),
        markets=(f"{EXCHANGE}:{SYMBOL}",),
        started_at=CUT,
        finished_at=CUT,
        bars_evaluated=0,
        signals=0,
        outcomes_resolved=0,
        outcomes_open=0,
        seconds=1.0,
        decision_lag_s=2,
        workers=1,
    )


def _plan() -> Any:
    """A plan whose only use here is to be forwarded — ``replay_run`` is faked."""
    return SimpleNamespace(cohort=ShadowCohort.replay(uuid.uuid4()))


@pytest.fixture
async def explain_db(db_session_factory: Any) -> dict[str, Any]:
    """A market, the seeded series and one runnable version — the Lab, emptied."""
    key = f"replay_explain_{uuid.uuid4().hex[:8]}"
    async with db_session_factory() as owner, owner.begin():
        await ensure_partitions(owner, CUT)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        for table in ("shadow_outbox", "shadow_episodes", "signal_outcomes", "agent_signals"):
            await session.execute(text(f"DELETE FROM {table}"))  # noqa: S608
        await session.execute(text("DELETE FROM candles"))
        _exchange_id, market_id = await seed_market(session)
        await activate_version(session, key=key)
        await insert_candles(session, market_id, replay_series())
    async with db_session_factory() as owner, owner.begin():
        await isolate_catalogue(owner, keep=key)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        versions = await load_active_versions(session)
        market = await load_market(session, EXCHANGE, SYMBOL)
    assert market is not None
    return {
        "factory": db_session_factory,
        "version": only_version(versions, key),
        "market": market,
        "market_id": market_id,
    }


async def _replay_with_ledger(
    db: dict[str, Any], path: Path, *, window: ReplayWindow = WINDOW
) -> Any:
    cohort = ShadowCohort.replay(uuid.uuid4())
    config = ShadowConfig(cohort=cohort, eligibility_max_lag_s=300, context_minutes=1560)
    market = db["market"]
    shard = shard_path(path, exchange=market.exchange, symbol=market.symbol)
    with ExplainLedger(shard, market=f"{market.exchange}:{market.symbol}") as ledger:
        result = await replay_market(
            db["factory"],
            version=db["version"],
            market=market,
            window=window,
            config=config,
            explain=ledger,
        )
    merge_shards(path, [shard])
    return result


async def _rewrite_the_future(db: dict[str, Any], *, final: bool = True) -> None:
    async with role_session(db["factory"], db_role="hunter_worker") as session:
        await session.execute(
            text(
                "UPDATE candles SET volume = volume * 50, open = open * 1.5, "
                "high = high * 1.5, low = low * 1.5, close = close * 1.5, "
                "is_final = :final WHERE market_id = :market_id AND open_time >= :cut"
            ),
            {"market_id": db["market_id"], "cut": FUTURE_FROM, "final": final},
        )


@pytest.mark.integration
class TestOverARealReplay:
    async def test_one_line_per_evaluated_bar(
        self, explain_db: dict[str, Any], tmp_path: Path
    ) -> None:
        path = tmp_path / "explain.jsonl"
        result = await _replay_with_ledger(explain_db, path)
        rows = _read(path)
        assert len(rows) == result.bars == 12
        histogram: dict[str, int] = {}
        for row in rows:
            histogram[row["state"]] = histogram.get(row["state"], 0) + 1
        assert histogram == dict(result.states)

    async def test_the_bar_that_decided_says_so_and_the_others_say_why_not(
        self, explain_db: dict[str, Any], tmp_path: Path
    ) -> None:
        """The reasons are the strategy's, not the ledger's: nothing here maps,
        renames or invents a code."""
        path = tmp_path / "explain.jsonl"
        await _replay_with_ledger(explain_db, path)
        rows = _read(path)
        triggered = [row for row in rows if row["state"] == "triggered"]
        assert [row["bar_close"] for row in triggered] == [TRIGGER_BAR.isoformat()]
        assert triggered[0]["reason"] == "signal"
        assert {row["reason"] for row in rows if row["state"] != "triggered"}
        assert all(row["market"] == f"{EXCHANGE}:{SYMBOL}" for row in rows)


@pytest.mark.integration
class TestTheLedgerCannotReadTheFuture:
    """The same mutation proof of ``test_replay_lookahead.py``, applied to the
    new surface: a diagnostic that moved when the future moved would be a leak
    that happens to be written to a file instead of a signal."""

    async def test_rewriting_every_later_candle_changes_no_line(
        self, explain_db: dict[str, Any], tmp_path: Path
    ) -> None:
        before = tmp_path / "before.jsonl"
        rows = await _replay_with_ledger(explain_db, before, window=ONE_BAR)
        assert rows.states == {"triggered": 1}, "the bar under test must answer something"
        await _rewrite_the_future(explain_db)
        after = tmp_path / "after.jsonl"
        await _replay_with_ledger(explain_db, after, window=ONE_BAR)
        assert _read(after) == _read(before)

    async def test_a_candle_that_is_not_final_changes_no_line_either(
        self, explain_db: dict[str, Any], tmp_path: Path
    ) -> None:
        before = tmp_path / "before.jsonl"
        await _replay_with_ledger(explain_db, before, window=ONE_BAR)
        await _rewrite_the_future(explain_db, final=False)
        after = tmp_path / "after.jsonl"
        await _replay_with_ledger(explain_db, after, window=ONE_BAR)
        assert _read(after) == _read(before)

    async def test_the_cheat_is_caught_by_the_ledger_too(
        self, explain_db: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Contra-proof. Without it the two tests above could pass on a ledger
        that recorded a constant."""

        async def cheating_context(
            session: Any, redis: Any, *, source_bar_close: datetime, **kwargs: Any
        ) -> Any:
            return await build_market_context(
                session, redis, source_bar_close=source_bar_close + CHEAT_LOOKAHEAD, **kwargs
            )

        monkeypatch.setattr(decide, "build_market_context", cheating_context)
        before = tmp_path / "before.jsonl"
        await _replay_with_ledger(explain_db, before, window=ONE_BAR)
        await _rewrite_the_future(explain_db)
        after = tmp_path / "after.jsonl"
        await _replay_with_ledger(explain_db, after, window=ONE_BAR)
        assert _read(after) != _read(before), (
            "the cheating engine read candles after the bar and the ledger did not notice"
        )
