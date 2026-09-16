"""T4.41 — which instrument names the window's numbers
(``features_tape_sources.choose_tape``) and the chain's own flow
(``features_tape_sources.chain_flow``).

KB-0116 (16/09) measured the inversion this file freezes: 96 % of the rows of
``meme_features_15s`` with a tape number already came from the batch
(``activity_1m``), which agrees with the chain in sign 85,7 % of the time
(median ratio 1,00, corr 0,835), while the minutes the fold credited to the
per-mint tape (``swap_api_trades``) had median ratio **0,00** and agreed in
sign 34,9 % — one page a minute credited to the whole minute. The batch now
wins; the per-mint tape fills what the batch did not cover and always names
the creator; the chain's delta of ``real_sol_reserves`` is the flow's third
source, with buys/sells/unique buyers unknown (``buyers_unknown``).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_indicators.meme.fast import FastPoint
from hunter_meme_worker.features_fast import FastInputs, build_fast_row
from hunter_meme_worker.features_tape import (
    ACTIVITY_1M,
    SWAP_API_TRADES,
    ActivityReading,
    TapeMinute,
    TapeTrade,
    activity_minute,
    tape_for,
)
from hunter_meme_worker.features_tape_sources import (
    BUYERS_UNKNOWN,
    CHAIN_DELTA,
    chain_flow,
    choose_tape,
)

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 16, 18, 30, 0, tzinfo=UTC)
AS_OF = T0 + timedelta(seconds=2)
MINT = "TAPEmint1111111111111111111111111111111111"
CREATOR = "CREATOR11111111111111111111111111111111111"
NOT_POLLED = "not_polled"


def _trade(seconds: int, side: str, trader: str, sol: int) -> TapeTrade:
    at = T0 + timedelta(seconds=seconds)
    return TapeTrade(
        block_time=at,
        received_at=at + timedelta(seconds=1),
        trader=trader,
        side=side,
        sol_lamports=sol,
    )


def _own_tape(*, creator_sells: bool = True) -> TapeMinute | None:
    """The per-mint tape of the minute: one buy of 0,1 SOL and, by default, a
    sell of 0,05 SOL by the creator — the only thing only it can say."""
    trades = [_trade(-30, "buy", "BUYER1", 100_000_000)]
    if creator_sells:
        trades.append(_trade(-20, "sell", CREATOR, 50_000_000))
    return tape_for(trades, end_time=AS_OF, creator=CREATOR, covered_since=T0 - timedelta(hours=1))


def _batch() -> TapeMinute:
    """The batch's ``1m`` window: 9 buys / 4 sells, 7 buyers, +2 SOL net over
    a window that ended one second before the instant."""
    reading = ActivityReading(
        mint=MINT,
        end_time=T0 + timedelta(seconds=1),
        received_at=T0 + timedelta(seconds=1),
        window_s=60,
        buys=9,
        sells=4,
        unique_buyers=7,
        buy_volume_usd=Decimal("600"),
        sell_volume_usd=Decimal("200"),
        sol_usd=Decimal("200"),
        sol_usd_observed_at=T0,
    )
    minute = activity_minute(reading)
    assert minute is not None
    return minute


def _points(
    *, sol: tuple[str, ...] = ("26", "27", "30", "31", "33"), late: bool = False
) -> list[FastPoint]:
    """Curve photos 36 s apart, the newest at ``T0``, each carrying the real
    SOL of the curve; ``late`` makes the newest one reach us after ``AS_OF``."""
    offsets = tuple(-36 * i for i in reversed(range(len(sol))))
    return [
        FastPoint(
            observed_at=T0 + timedelta(seconds=o),
            received_at=(
                AS_OF + timedelta(seconds=1) if (late and o == 0) else T0 + timedelta(seconds=o + 1)
            ),
            mcap_sol=Decimal(value) * 2,
            real_token_reserves=Decimal(780_000_000),
            real_sol_reserves=Decimal(value),
        )
        for o, value in zip(offsets, sol, strict=True)
    ]


# --- the fold's four cases ------------------------------------------------


def test_the_batch_wins_over_the_per_mint_tape() -> None:
    choice = choose_tape(batch=_batch(), tape=_own_tape(), absence=NOT_POLLED)
    minute = choice.minute
    assert minute is not None and choice.chain is None
    assert minute.source == ACTIVITY_1M and minute.as_of == T0 + timedelta(seconds=1)
    assert (minute.buys, minute.sells, minute.unique_buyers) == (9, 4, 7)
    assert minute.net_sol_flow == Decimal("2.0000000000"), "600−200 USD at 200 USD/SOL"
    assert minute.volume_sol == Decimal("4.0000000000")
    assert (minute.creator_sold, minute.creator_net_seller) == (True, True), (
        "only meme_trades names who traded: the batch's numbers keep the tape's creator"
    )


def test_the_per_mint_tape_only_fills_what_the_batch_did_not_cover() -> None:
    choice = choose_tape(batch=None, tape=_own_tape(), absence=NOT_POLLED)
    minute = choice.minute
    assert minute is not None and choice.chain is None
    assert minute.source == SWAP_API_TRADES and minute.as_of == AS_OF
    assert (minute.buys, minute.sells, minute.unique_buyers) == (1, 1, 1)
    assert minute.net_sol_flow == Decimal("0.0500000000")
    assert minute.creator_net_seller is True


def test_without_a_tape_the_chain_names_the_flow_and_nothing_else() -> None:
    chain = chain_flow(_points(), as_of=AS_OF)
    choice = choose_tape(batch=None, tape=None, chain=chain, absence=NOT_POLLED)
    assert choice.minute is None, "a delta of reserves is not a tape: the counts stay unknown"
    assert choice.chain is not None and choice.chain is chain
    assert choice.chain.source == CHAIN_DELTA
    assert choice.chain.net_sol_flow == Decimal("3.0000000000"), "33 − 30 SOL over 72 s"
    assert choice.chain.window_s == 72 and choice.chain.as_of == T0
    assert choice.absence == NOT_POLLED
    assert BUYERS_UNKNOWN == "buyers_unknown", "the gate's existing word for the counts"


def test_the_batch_keeps_a_creator_the_per_mint_tape_could_not_name() -> None:
    """The lending is one-way and only of what is known: a tape whose mint has
    no ``meme_tokens.creator`` says ``None``, and the batch's row keeps the
    ``None`` (the gate then refuses by name) instead of borrowing a False."""
    nameless = tape_for(
        [_trade(-30, "buy", "BUYER1", 100_000_000)],
        end_time=AS_OF,
        creator=None,
        covered_since=T0 - timedelta(hours=1),
    )
    assert nameless is not None and nameless.creator_net_seller is None
    minute = choose_tape(batch=_batch(), tape=nameless, absence=NOT_POLLED).minute
    assert minute is not None and minute.source == ACTIVITY_1M
    assert (minute.creator_sold, minute.creator_net_seller) == (None, None)
    quiet = choose_tape(
        batch=_batch(), tape=_own_tape(creator_sells=False), absence=NOT_POLLED
    ).minute
    assert quiet is not None
    assert (quiet.creator_sold, quiet.creator_net_seller) == (False, False), (
        "a creator who did not sell is a measured False, and the batch keeps it"
    )


def test_with_nothing_the_row_keeps_the_reason_it_had() -> None:
    choice = choose_tape(batch=None, tape=None, chain=None, absence=NOT_POLLED)
    assert (choice.minute, choice.chain, choice.absence) == (None, None, NOT_POLLED)


# --- the chain's delta ----------------------------------------------------


def test_the_chain_flow_ignores_photos_received_after_the_instant() -> None:
    late = chain_flow(_points(late=True), as_of=AS_OF)
    assert late is not None
    assert late.net_sol_flow == Decimal("4.0000000000"), "31 − 27: the late photo is not an input"
    assert late.as_of == T0 - timedelta(seconds=36)


def test_the_chain_flow_is_negative_when_the_curve_gave_sol_back() -> None:
    falling = chain_flow(_points(sol=("40", "38", "31")), as_of=AS_OF)
    assert falling is not None and falling.net_sol_flow == Decimal("-9.0000000000")


def test_the_chain_flow_refuses_a_window_it_cannot_honour() -> None:
    assert chain_flow([], as_of=AS_OF) is None
    no_reserves = [replace(p, real_sol_reserves=None) for p in _points()]
    assert chain_flow(no_reserves, as_of=AS_OF) is None, "no real SOL in the photos"
    assert chain_flow(_points()[-1:], as_of=AS_OF) is None, "one photo is not a delta"
    stale = [replace(p, observed_at=p.observed_at - timedelta(seconds=90)) for p in _points()]
    assert chain_flow(stale, as_of=AS_OF) is None, "the newest photo is older than the window"
    far = [_points()[2], _points()[-1]]
    assert chain_flow(far, as_of=AS_OF) is not None, "72 s apart: inside 2 × window_s"
    wide = [
        replace(_points()[0], observed_at=T0 - timedelta(seconds=200)),
        _points()[-1],
    ]
    assert chain_flow(wide, as_of=AS_OF) is None, "200 s apart is not a 60 s flow"


# --- the row the fold writes ---------------------------------------------


def test_the_row_carries_the_source_that_named_its_numbers() -> None:
    row = build_fast_row(
        FastInputs(
            mint=MINT,
            as_of=AS_OF,
            created_at=T0 - timedelta(seconds=100),
            initial_real_token_reserves=Decimal("793100000"),
            points=_points(),
            snapshot_source="solana_rpc",
            tape=choose_tape(batch=_batch(), tape=_own_tape(), absence=NOT_POLLED).minute,
        )
    )
    assert row.tape_source == ACTIVITY_1M and row.tape_window_s == 60
    assert row.tape_as_of == T0 + timedelta(seconds=1)
    assert (row.buys_60s, row.sells_60s, row.unique_buyers_60s) == (9, 4, 7)
    assert row.net_sol_flow_60s == Decimal("2.0000000000") and row.tape_reason is None
    assert row.creator_net_seller is True and row.creator_net_seller_reason is None
