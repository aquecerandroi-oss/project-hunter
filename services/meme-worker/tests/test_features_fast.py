"""T4.16 — the 15-second row (``features_fast.build_fast_row``): the pure
package's instantaneous features beside the tape of the last 60 s and the
holders reading of the instant, every value with its reason — and the
look-ahead proof on every input: a photo, a trade or a reading received
after ``as_of`` changes nothing in the row."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_indicators.meme.fast import FastPoint
from hunter_meme_worker.features_fast import FEATURES_15S_VERSION, FastInputs, build_fast_row
from hunter_meme_worker.features_tape import HoldersObservation, TapeTrade, tape_for

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 12, 17, 30, 0, tzinfo=UTC)
AS_OF = T0 + timedelta(seconds=2)
CREATED = T0 - timedelta(seconds=150)
INITIAL = Decimal("793100000")
MINT = "FASTmint111111111111111111111111111111111111"
CREATOR = "CREATOR11111111111111111111111111111111111"


def _points() -> list[FastPoint]:
    series = {-75: "29", -60: "30", -45: "31", -30: "33", -15: "34", 0: "36"}
    return [
        FastPoint(
            observed_at=T0 + timedelta(seconds=s),
            received_at=T0 + timedelta(seconds=s + 1),
            mcap_sol=Decimal(v),
            real_token_reserves=Decimal(780_000_000) - Decimal(1_000_000) * (s + 75) // 15,
        )
        for s, v in series.items()
    ]


def _reading(seconds: int, holders: int, *, late: bool = False) -> HoldersObservation:
    observed = T0 + timedelta(seconds=seconds)
    return HoldersObservation(
        observed_at=observed,
        received_at=AS_OF + timedelta(seconds=1) if late else observed + timedelta(seconds=1),
        source="trenches_ws:new",
        holders=holders,
        top10_share=Decimal("0.4"),
        dev_share=Decimal("0.05"),
        snipers=1,
    )


def _trade(seconds: int, side: str, trader: str, sol: int, *, late: bool = False) -> TapeTrade:
    at = T0 + timedelta(seconds=seconds)
    return TapeTrade(
        block_time=at,
        received_at=AS_OF + timedelta(seconds=1) if late else at + timedelta(seconds=1),
        trader=trader,
        side=side,
        sol_lamports=sol,
    )


def _tape(*extra: TapeTrade) -> list[TapeTrade]:
    buys = [_trade(-50 + i * 3, "buy", f"B{i}", 100_000_000) for i in range(12)]
    sells = [_trade(-40 + i * 5, "sell", f"S{i}", 50_000_000) for i in range(6)]
    return [*buys, *sells, *extra]


def _inputs(**overrides: object) -> FastInputs:
    base: dict[str, object] = {
        "mint": MINT,
        "as_of": AS_OF,
        "created_at": CREATED,
        "initial_real_token_reserves": INITIAL,
        "points": _points(),
        "snapshot_source": "solana_rpc",
        "readings": [_reading(-40, 3), _reading(-20, 5)],
        "tape": tape_for(
            _tape(), end_time=AS_OF, creator=CREATOR, covered_since=T0 - timedelta(minutes=2)
        ),
        "tape_absence_reason": "no_trade_feed",
    }
    base.update(overrides)
    return FastInputs(**base)  # type: ignore[arg-type]


def test_the_row_folds_the_photos_the_tape_and_the_holders_of_the_instant() -> None:
    row = build_fast_row(_inputs())
    assert (row.as_of, row.mint, row.features_version) == (AS_OF, MINT, FEATURES_15S_VERSION)
    assert row.age_s == 152 and row.snapshots_120s == 6
    assert row.snapshot_observed_at == T0 and row.snapshot_source == "solana_rpc"
    assert row.mcap_sol == Decimal("36.0000000000") and row.mcap_delta_60s == Decimal(
        "6.0000000000"
    )
    assert row.mcap_slope_60s is not None and row.window_reason is None
    assert row.progress_rising is True and row.progress_reason is None
    assert (row.holders, row.holders_prev, row.holders_rising, row.holders_reason) == (
        5,
        3,
        True,
        None,
    )
    assert (row.buys_60s, row.sells_60s, row.unique_buyers_60s) == (12, 6, 12)
    assert row.net_sol_flow_60s == Decimal("0.9") and row.curve_volume_60s_sol == Decimal("1.5")
    assert row.tape_reason is None and row.creator_net_seller is False
    assert row.creator_net_seller_reason is None
    assert (row.dev_share, row.dev_share_reason) == (Decimal("0.050000"), None)
    assert (row.snipers, row.snipers_reason) == (1, None)


def test_every_absent_source_is_named_in_the_row() -> None:
    blind = build_fast_row(
        _inputs(
            points=[], readings=[], tape=None, tape_absence_reason="not_polled", created_at=None
        )
    )
    assert blind.age_s is None and blind.snapshots_120s == 0
    assert (blind.mcap_sol, blind.snapshot_source, blind.window_reason) == (
        None,
        None,
        "no_snapshot",
    )
    assert blind.progress_reason == "no_snapshot"
    assert (blind.holders_rising, blind.holders_reason) == (None, "no_holders_reader")
    assert (blind.buys_60s, blind.tape_reason) == (None, "not_polled")
    assert (blind.creator_net_seller, blind.creator_net_seller_reason) == (None, "not_polled")
    assert (blind.dev_share_reason, blind.snipers_reason) == (
        "no_holders_reader",
        "no_holders_reader",
    )
    unknown_creator = tape_for(_tape(), end_time=AS_OF, creator=None, covered_since=T0)
    row = build_fast_row(_inputs(tape=unknown_creator))
    assert row.buys_60s == 12 and row.creator_net_seller is None
    assert row.creator_net_seller_reason == "no_trade_feed", "a pulled tape, an unknown creator"
    one_reading = build_fast_row(_inputs(readings=[_reading(-20, 5)]))
    assert (one_reading.holders, one_reading.holders_rising, one_reading.holders_reason) == (
        5,
        None,
        "too_few_readings",
    )


def test_a_photo_a_trade_or_a_reading_received_after_the_instant_changes_nothing() -> None:
    before = build_fast_row(_inputs())
    late_photo = FastPoint(
        observed_at=T0 + timedelta(seconds=1),
        received_at=AS_OF + timedelta(seconds=1),
        mcap_sol=Decimal("90"),
        real_token_reserves=Decimal("700000000"),
    )
    late_tape = tape_for(
        _tape(_trade(0, "sell", CREATOR, 900_000_000, late=True)),
        end_time=AS_OF,
        creator=CREATOR,
        covered_since=T0 - timedelta(minutes=2),
    )
    after = build_fast_row(
        _inputs(
            points=[*_points(), late_photo],
            readings=[_reading(-40, 3), _reading(-20, 5), _reading(0, 1, late=True)],
            tape=late_tape,
        )
    )
    assert after == before, "the future is not an input of the present"
    # One second later the same inputs are in, and the row says so.
    later = build_fast_row(
        replace(
            _inputs(
                points=[*_points(), late_photo],
                readings=[_reading(-40, 3), _reading(-20, 5), _reading(0, 1, late=True)],
                tape=tape_for(
                    _tape(_trade(0, "sell", CREATOR, 900_000_000, late=True)),
                    end_time=AS_OF + timedelta(seconds=1),
                    creator=CREATOR,
                    covered_since=T0 - timedelta(minutes=2),
                ),
            ),
            as_of=AS_OF + timedelta(seconds=1),
        )
    )
    assert later.mcap_sol == Decimal("90.0000000000")
    assert later.holders_rising is False and later.creator_net_seller is True
