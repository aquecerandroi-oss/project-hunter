"""``history_v2`` in the scanner — the 27/09 disk decision, step 3(a).

``docs/design/retencao-e-disco-2026-09-27.md`` §6: ``opportunity_history`` wrote
~50 rows an hour per opportunity (63 G in September). The scanner now samples with
``history_v2`` (first sample, status/stage change, or ``SCANNER_HISTORY_INTERVAL_S``
elapsed, 300 s by default) and every row it still writes keeps the whole envelope
(``analysis.py``: the envelope is what makes "recompute this score" true).

Two corrections ride along, both about *what the next restart compares against*:
the ``opportunities`` row now carries the **last persisted** mark (it carried the
last *evaluated* one, which after a restart pushed the next heartbeat out by up to
one interval — Astra, 27/09), and each history row says which policy wrote it.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import pytest

from hunter_core.domain.enums import BaselineSampling, BaselineSource, OpportunityStatus
from hunter_indicators.baselines import ALGO_VERSION, BaselineKey, BaselineRevision, StoredBaseline
from hunter_indicators.opportunity import (
    EpisodeAction,
    EpisodeState,
    HistoryVerdict,
    StatusDecision,
)
from hunter_scanner_worker import collect, evaluate
from hunter_scanner_worker.baselines import BaselineCache
from hunter_scanner_worker.config import ScannerConfig, build_config
from hunter_scanner_worker.coverage import read_coverage
from hunter_scanner_worker.persist import WriteBatch
from hunter_scanner_worker.registry import MarketRegistry
from hunter_scanner_worker.rows import jsonable
from hunter_scanner_worker.scanner import Scanner
from hunter_scanner_worker.state import ScannerState

from .builders import EXCHANGE, MARKET_ID, ORIGIN, REF, SYMBOL, FakeHotState, series
from .policies import build_policy

CUT = ORIGIN + timedelta(minutes=1500)
OPPORTUNITY_ID = UUID("22222222-2222-7222-8222-222222222222")


def _baseline() -> StoredBaseline:
    """One usable ``relative_volume_5m`` bucket at the cut's hour (the shape
    ``test_pipeline.py`` uses): enough for a real score to come out."""
    window_end = CUT.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    return StoredBaseline(
        baseline_id=UUID(int=7),
        revision=BaselineRevision(
            key=BaselineKey(
                market_id=MARKET_ID, feature="relative_volume_5m", hour_of_day=CUT.hour
            ),
            feature_version=1,
            algo_version=ALGO_VERSION,
            window_start=window_end - timedelta(days=7),
            window_end=window_end,
            available_at=window_end,
            median=Decimal(1),
            mad=Decimal("0.1"),
            sample_size=400,
            expected_size=420,
            distinct_days=7,
            coverage=Decimal(400) / Decimal(420),
            source=BaselineSource.LIVE,
            sampling=BaselineSampling.PER_MINUTE,
            input_fingerprint="relative_volume_5m",
        ),
    )


def _scanner(config: ScannerConfig | None = None) -> Scanner:
    policy = build_policy()
    scanner = Scanner(
        config=config or ScannerConfig(exchange=EXCHANGE),
        policy=policy,
        registry=MarketRegistry(exchange=EXCHANGE),
        state=ScannerState(),
    )
    scanner.registry.apply([REF])
    scanner.cache = BaselineCache(gate=policy.gate, entries={MARKET_ID: (_baseline(),)})
    scanner.state.ensure(REF)
    return scanner


async def _advance(scanner: Scanner, hot: FakeHotState) -> Any:
    market = scanner.state.markets[SYMBOL]
    market.touch("tick", input_ts=CUT)
    scanner.coverage = await read_coverage(cast("Any", hot), EXCHANGE, now=CUT)
    return await scanner.advance(cast("Any", hot), market, WriteBatch(), now=CUT)


@pytest.fixture
def hot() -> FakeHotState:
    state = FakeHotState()
    state.load(candles=series(1500), as_of=CUT)
    state.publish_coverage(session_since=ORIGIN, covered_until=CUT)
    return state


class TestTheCadence:
    def test_the_default_interval_is_five_minutes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SCANNER_HISTORY_INTERVAL_S", raising=False)
        assert build_config().history_interval_s == 300.0
        assert ScannerConfig().history_interval_s == 300.0

    def test_the_environment_sets_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SCANNER_HISTORY_INTERVAL_S", "600")
        assert build_config().history_interval_s == 600.0

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("abc", 300.0),
            ("0", 1.0),
            ("-5", 1.0),
            # Quant review F4: timedelta(seconds=inf) raised OverflowError every cycle.
            ("inf", 300.0),
            ("nan", 300.0),
            ("1e20", 86_400.0),
        ],
    )
    def test_a_typo_never_disables_the_heartbeat(
        self, monkeypatch: pytest.MonkeyPatch, raw: str, expected: float
    ) -> None:
        monkeypatch.setenv("SCANNER_HISTORY_INTERVAL_S", raw)
        assert build_config().history_interval_s == expected


async def test_the_scanner_samples_with_history_v2_at_its_configured_interval(
    hot: FakeHotState, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[Any] = []
    real = evaluate.should_record_history

    def spy(previous: Any, now: Any, policy: Any) -> Any:
        seen.append(policy)
        return real(previous, now, policy)

    monkeypatch.setattr(evaluate, "should_record_history", spy)
    scanner = _scanner(ScannerConfig(exchange=EXCHANGE, history_interval_s=600.0))

    evaluation = await _advance(scanner, hot)

    assert evaluation is not None and evaluation.history is not None
    assert evaluation.history.policy_version == "history_v2"
    assert [(policy.version, policy.interval) for policy in seen] == [
        ("history_v2", timedelta(seconds=600))
    ]


async def _open_episode_evaluation(hot: FakeHotState, verdict: HistoryVerdict) -> Any:
    """A real evaluation, dressed as an update of an open WATCHING episode."""
    scanner = _scanner()
    evaluation = await _advance(scanner, hot)
    assert evaluation is not None and evaluation.history_mark is not None
    state = EpisodeState(
        status=OpportunityStatus.WATCHING,
        first_seen_at=CUT - timedelta(minutes=10),
        observation_ts=evaluation.observation_ts,
        score=Decimal("50"),
        peak_score=Decimal("55"),
    )
    decision = StatusDecision(
        action=EpisodeAction.UPDATE,
        status=OpportunityStatus.WATCHING,
        candidate=OpportunityStatus.WATCHING,
        state_in=state,
        state_out=state,
        thresholds_version="test",
    )
    mark = replace(evaluation.history_mark, status=OpportunityStatus.WATCHING)
    dressed = replace(evaluation, status=decision, history=verdict, history_mark=mark)
    market = scanner.state.markets[SYMBOL]
    market.opportunity_id = OPPORTUNITY_ID
    return dressed, market


async def test_a_sample_not_kept_leaves_the_last_persisted_mark_on_the_episode_row(
    hot: FakeHotState,
) -> None:
    skipped = HistoryVerdict(record=False, reasons=(), policy_version="history_v2")
    evaluation, market = await _open_episode_evaluation(hot, skipped)
    two_minutes_before = evaluation.history_mark.ts - timedelta(minutes=2)
    persisted = replace(evaluation.history_mark, ts=two_minutes_before)
    market.checkpoint = replace(market.checkpoint, history=persisted)
    batch = WriteBatch()

    collect.collect_opportunity("test", None, market, evaluation, batch, now=CUT)

    assert batch.history == []
    snapshot = batch.opportunities[0]["feature_snapshot"]
    assert snapshot["history_mark"] == jsonable(persisted.as_wire())
    assert snapshot["history_mark"] != jsonable(evaluation.history_mark.as_wire())


async def test_a_kept_sample_carries_its_envelope_and_the_policy_that_kept_it(
    hot: FakeHotState,
) -> None:
    kept = HistoryVerdict(
        record=True, reasons=("interval_elapsed",), policy_version="history_v2", interval_s=300
    )
    evaluation, market = await _open_episode_evaluation(hot, kept)
    batch = WriteBatch()

    collect.collect_opportunity("test", None, market, evaluation, batch, now=CUT)

    (row,) = batch.history
    envelope = row["envelope"]
    # Explainability: the preserved sample is whole — vector, versions, the mark.
    assert "vector" in envelope and "values" in envelope["vector"]
    assert envelope["history_mark"] == jsonable(evaluation.history_mark.as_wire())
    assert envelope["history_sample"] == {
        "policy_version": "history_v2",
        "reasons": ["interval_elapsed"],
        "interval_s": 300,
    }
    assert row["decomposition"]
    # The episode row moves to the mark that is now persisted, in the same batch.
    assert batch.opportunities[0]["feature_snapshot"]["history_mark"] == envelope["history_mark"]


async def test_the_policy_is_built_once_not_every_cycle(
    hot: FakeHotState, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Quant review F4: the policy was rebuilt on every ``advance``."""
    from hunter_scanner_worker import scanner as scanner_module

    built: list[timedelta] = []
    real = scanner_module.sparse_history_policy

    def spy(interval: timedelta) -> Any:
        built.append(interval)
        return real(interval)

    monkeypatch.setattr(scanner_module, "sparse_history_policy", spy)
    scanner = _scanner(ScannerConfig(exchange=EXCHANGE, history_interval_s=86_400.0))
    await _advance(scanner, hot)
    await _advance(scanner, hot)

    assert built == [timedelta(days=1)]


async def test_a_new_episode_starts_its_history_with_a_first_sample(
    hot: FakeHotState, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Quant review F5: an episode that opens a minute after the previous one
    expired was compared with the *previous* episode's last sample, and its first
    row could wait up to one interval — or say it existed for another reason."""
    scanner = _scanner()
    first = await _advance(scanner, hot)
    assert first is not None and first.history_mark is not None
    market = scanner.state.markets[SYMBOL]
    recent = replace(first.history_mark, ts=first.history_mark.ts - timedelta(seconds=30))
    market.checkpoint = replace(market.checkpoint, history=recent)
    real = evaluate.advance_status

    def opens(*args: Any, **kwargs: Any) -> Any:
        return replace(real(*args, **kwargs), action=EpisodeAction.OPEN)

    monkeypatch.setattr(evaluate, "advance_status", opens)
    market.last_score_at = None

    evaluation = await _advance(scanner, hot)

    assert evaluation is not None and evaluation.history is not None
    assert evaluation.history.reasons == ("first_sample",)
