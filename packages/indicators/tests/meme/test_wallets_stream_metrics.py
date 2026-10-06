"""The per-entity accumulator of the bounded engine against the untouched batch oracle.

``metrics.entity_metrics`` (batch, unchanged) is the oracle (Astra must-fix 5 of wallets-1c-bis):
folding the entity's per-mint books one mint at a time must give the very same
:class:`~hunter_indicators.meme.wallets.metrics.EntityMetrics`, with the exclusions (creator,
create block, MEV), neutral episodes in the median, incomplete, contaminated and open episodes.

Synthetic fixtures (not data): invented numbers, UTC.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from hunter_indicators.meme.wallets.episodes import window_books
from hunter_indicators.meme.wallets.lots import Lot
from hunter_indicators.meme.wallets.metrics import EntityFacts, entity_metrics
from hunter_indicators.meme.wallets.params import RankingParams
from hunter_indicators.meme.wallets.pricing import MintTape
from hunter_indicators.meme.wallets.stream_metrics import EntityTally
from hunter_indicators.meme.wallets.tape import CreateEvent, Fill, Gap
from packages.indicators.tests.meme.test_wallets_builders import SOL, T0, TOKEN, create, fill
from packages.indicators.tests.meme.test_wallets_ranking import S_EXIT_W, week

pytestmark = pytest.mark.unit

PAR = RankingParams()


def _extras() -> tuple[list[Fill], list[CreateEvent], list[Lot], list[Gap]]:
    s = 300_000
    fills = [
        # MEV: sold 2 slots after the buy
        fill(wallet="W", side="buy", slot=s, sol=SOL, atoms=10 * TOKEN, mint="MEV", fee_bps=0),
        fill(wallet="W", side="sell", slot=s + 2, sol=SOL, atoms=10 * TOKEN, mint="MEV", fee_bps=0),
        # neutral: back at cost minus the two tx fees (|result| < 1 % of cost), held 4 000 s
        fill(wallet="W", side="buy", slot=s + 100, sol=SOL, atoms=10 * TOKEN, mint="FLAT", fee_bps=0),
        fill(wallet="W", side="sell", slot=s + 10_100, sol=SOL, atoms=10 * TOKEN, mint="FLAT", fee_bps=0),
        # own mint (creator) and create block
        fill(wallet="W", side="buy", slot=s + 200, sol=SOL, atoms=10 * TOKEN, mint="OWN", fee_bps=0),
        fill(wallet="W", side="sell", slot=s + 900, sol=2 * SOL, atoms=10 * TOKEN, mint="OWN", fee_bps=0),
        fill(wallet="W", side="buy", slot=s + 301, sol=SOL, atoms=10 * TOKEN, mint="SNIPE", fee_bps=0),
        fill(wallet="W", side="sell", slot=s + 990, sol=2 * SOL, atoms=10 * TOKEN, mint="SNIPE", fee_bps=0),
        # open at the cut, inside a gap; a sale beyond the inventory (unmatched)
        fill(wallet="W", side="buy", slot=s + 500, sol=SOL, atoms=10 * TOKEN, mint="BAG", fee_bps=0),
        fill(wallet="W", side="sell", slot=s + 600, sol=SOL, atoms=TOKEN, mint="GHOST", fee_bps=0),
        # sale of a preserved lot of unknown cost (incomplete)
        fill(wallet="W", side="sell", slot=s + 700, sol=SOL, atoms=5 * TOKEN, mint="OLD", fee_bps=0, reserves=S_EXIT_W),
    ]  # fmt: skip
    creates = [create("OWN", "W", s + 150), create("SNIPE", "dev", s + 300)]
    old = Lot("W", "OLD", 5 * TOKEN, None, -10, T0 - timedelta(days=2))
    return fills, creates, [old], [Gap(s + 450, s + 460)]


def _inputs() -> tuple[list[Fill], dict[str, CreateEvent], list[Lot], list[Gap]]:
    base, creates = week("W", S_EXIT_W)
    extra, more, lots, gaps = _extras()
    return [*base, *extra], {c.mint: c for c in (*creates, *more)}, lots, gaps


def test_folding_per_mint_books_equals_the_batch_metrics_of_the_whole_book() -> None:
    fills, creates, lots, gaps = _inputs()
    mints = sorted({f.mint for f in fills} | {lot.mint for lot in lots})
    tapes = {m: MintTape([f for f in fills if f.mint == m]) for m in mints}
    whole = window_books(
        fills, owner_of=str, opening=lots, tapes=tapes, start=T0, days=7, gaps=gaps
    )
    facts = EntityFacts(wallets=frozenset({"W"}), c_pnl_lamports=7, trades_previous_day=3,
                        w_pnl_lamports=11, copies=2, copies_incomplete=1, copies_contaminated=1)  # fmt: skip
    oracle = entity_metrics(whole["W"], facts, creates=creates, funded_by={}, params=PAR)
    assert oracle.episodes_total == 21 + 6  # GHOST is only an unmatched sale: no episode
    assert oracle.incomplete_episodes == 1 and oracle.contaminated_episodes >= 1
    assert oracle.creator_share > 0 and oracle.create_block_share > 0
    tally = EntityTally(days=7)
    for m in mints:  # the bounded engine sees one mint at a time
        per_mint = window_books(
            [f for f in fills if f.mint == m],
            owner_of=str,
            opening=[lot for lot in lots if lot.mint == m],
            tapes={m: tapes[m]},
            start=T0,
            days=7,
            gaps=gaps,
        )
        if "W" in per_mint:  # the market buyer X has its own books
            tally.fold(per_mint["W"], frozenset({"W"}), creates, {}, PAR)
    assert tally.metrics("W", facts, PAR) == oracle


def test_an_empty_tally_matches_a_book_without_episodes() -> None:
    sale = fill(wallet="Z", side="sell", slot=10, sol=SOL, atoms=TOKEN, mint="GHOST")
    books = window_books([sale], owner_of=str, opening=(), tapes={"GHOST": MintTape([sale])},
                         start=T0, days=7)  # fmt: skip
    facts = EntityFacts(wallets=frozenset({"Z"}), c_pnl_lamports=0, trades_previous_day=1)
    oracle = entity_metrics(books["Z"], facts, creates={}, funded_by={}, params=PAR)
    tally = EntityTally(days=7)
    tally.fold(books["Z"], frozenset({"Z"}), {}, {}, PAR)
    assert tally.metrics("Z", facts, PAR) == oracle
    assert oracle.unmatched_share == 1.0 and oracle.largest_episode_lamports == 0
