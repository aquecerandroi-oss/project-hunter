"""T4.45 — the creator's flow derived from the chain against the **recorded** dev
buy, and the four cases where it is not derived at all.

Why this exists (measured 16/09/2026,
``obsidian/03-TRADING/Meme/Balanco-2026-09-16-mesa-real.md``): 27 of the day's 58
real orders were refused ``creator_flow_unknown``. The 1-minute fold's
``creator_sold`` lands +123 to +441 s after the coin exists and the entry window
is 30–300 s, so the executor kept asking a question no table could answer yet.

Why it is safe to derive now and was not before (T4.28g §2.3): the base is
``meme_tokens.creator_initial_tokens`` — the allocation observed **at the create
instant** (``0048``) — not the indexer's current ``devHoldingsPercent``. With a
current photograph as the base, a creator who dumped everything at +20 s reads as
"holds ≥ base" and **passes** check 10; that failure is asserted below as the one
this design refuses to have.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_meme_executor.creator_flow import (
    CHAIN_FLOW_SOURCE,
    DEFAULT_SELL_TOLERANCE_PCT,
    creator_flow_from_chain,
    needs_chain_creator_flow,
)
from hunter_meme_executor.repo import TokenContext

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 16, 20, 30, tzinfo=UTC)
INITIAL = Decimal("30877830.227113")
SUBUNITS = Decimal(1_000_000)


def token(**overrides: object) -> TokenContext:
    values: dict[str, object] = {
        "created_at": NOW - timedelta(seconds=90),
        "creator": "CEC8SGJea2R4gUrL9C3cCJDa9ChhLie2NmCSFZfwD2hD",
        "initial_real_token_reserves": 793_100_000,
        "completed_at": None,
        "migrated_at": None,
        "curve_volume_1m_sol": Decimal("4.2"),
        "features_end_time": NOW - timedelta(seconds=20),
        "creator_sold": None,
        "top10_share": Decimal("0.2"),
        "bundled_share": Decimal("0.05"),
        "creator_initial_tokens": INITIAL,
        "creator_initial_sol": Decimal("0.888892813"),
    }
    values.update(overrides)
    return TokenContext(**values)  # type: ignore[arg-type]


def _flow(balance_tokens: Decimal, *, tolerance: Decimal = DEFAULT_SELL_TOLERANCE_PCT):
    return creator_flow_from_chain(
        initial_tokens=INITIAL,
        balance_subunits=int(balance_tokens * SUBUNITS),
        tolerance_pct=tolerance,
        observed_at=NOW,
    )


class TestWhenTheChainAnswers:
    def test_a_creator_still_holding_his_allocation_is_a_net_buyer(self) -> None:
        flow = _flow(INITIAL)
        assert flow.net_sol == Decimal(1)
        assert flow.source == CHAIN_FLOW_SOURCE == "chain_ata_vs_initial"

    def test_more_than_the_allocation_is_still_a_net_buyer(self) -> None:
        """He bought again on his own curve. Not a seller."""
        assert _flow(INITIAL * 2).net_sol == Decimal(1)

    def test_the_boundary_sits_between_two_subunits_and_is_tested_there(self) -> None:
        """2 % is dust and rounding, not a dump: the threshold itself passes. The
        chain counts in sub-units, so "exactly the threshold" is usually not
        expressible — the two neighbouring sub-units are, and they are what a
        real balance can be. Stated as a test so nobody flips the comparison to
        ``<=`` (which would call a creator who still holds everything a seller on
        a coin whose allocation happens to land on a sub-unit)."""
        threshold = INITIAL * (Decimal(1) - DEFAULT_SELL_TOLERANCE_PCT)
        exact = (threshold * SUBUNITS).to_integral_value(rounding="ROUND_CEILING")

        def at(subunits: Decimal) -> Decimal:
            return creator_flow_from_chain(
                initial_tokens=INITIAL,
                balance_subunits=int(subunits),
                tolerance_pct=DEFAULT_SELL_TOLERANCE_PCT,
                observed_at=NOW,
            ).net_sol

        assert at(exact) == Decimal(1), "at or above the threshold he still holds"
        assert at(exact - 1) == Decimal(-1), "one sub-unit under it, he sold"

    def test_an_empty_or_missing_account_is_a_dump_not_an_unknown(self) -> None:
        """The account we read is the creator's ATA for **this** mint, derived
        from the mint's own token program. A recorded allocation with nothing in
        the account means the tokens left — and the safe direction is the one
        that refuses: ``creator_net_seller``."""
        assert _flow(Decimal(0)).net_sol == Decimal(-1)

    def test_the_tolerance_is_a_parameter_not_a_constant(self) -> None:
        held = INITIAL * Decimal("0.95")
        assert _flow(held, tolerance=Decimal("0.02")).net_sol == Decimal(-1)
        assert _flow(held, tolerance=Decimal("0.10")).net_sol == Decimal(1)

    def test_the_json_states_the_provenance_and_both_numbers(self) -> None:
        """A number in the admission row without its source is a number nobody
        can audit six weeks later."""
        payload = _flow(Decimal(0)).as_json()
        assert payload["source"] == "chain_ata_vs_initial"
        assert payload["initial_tokens"] == str(INITIAL)
        assert payload["balance_tokens"] == "0"
        assert payload["tolerance_pct"] == str(DEFAULT_SELL_TOLERANCE_PCT)
        assert payload["net_sol"] == "-1"
        assert payload["observed_at"] == NOW.isoformat()


class TestWhenItIsNotDerivedAtAll:
    def test_an_unknown_allocation_stays_unknown(self) -> None:
        """The coins created before ``0048``, and every mint whose ``create``
        frame we never saw. Deriving here is the T4.28g failure: with no base,
        "balance ≥ base" is vacuously true and a rugged coin passes check 10."""
        assert not needs_chain_creator_flow(token(creator_initial_tokens=None))

    def test_a_creator_who_bought_nothing_gives_no_base_either(self) -> None:
        """``initialBuy = 0`` is measured, but a base of zero makes every balance
        ``>= 0`` — it answers "did he sell?" with "no" for a creator who never
        held anything to sell. ``> 0`` is the rule, and it lives here."""
        assert not needs_chain_creator_flow(token(creator_initial_tokens=Decimal(0)))

    def test_a_tape_that_saw_the_sale_settles_it_without_an_rpc_call(self) -> None:
        """``creator_sold = true`` is a trade on the tape — a fact. The chain
        cannot un-sell it, so no RPC call is spent and the engine refuses on the
        tape's own value."""
        assert not needs_chain_creator_flow(token(creator_sold=True))

    def test_a_tape_that_saw_no_sale_yet_does_not_silence_the_chain(self) -> None:
        """T4.56 — the COVER hole (R56 §3.2, 17/09/2026 19:46:56 → 19:47:20 BRT).
        The fold's ``false`` means "no sale in the tape covered so far", and the
        tape received the creator's 20 SOL sale 37,7 s late. Before T4.56 this
        ``false`` had precedence and the chain was not asked; the desk bought a
        coin the chain had refused 23 s earlier. Now ``false`` is silence for the
        purpose of this read: the balance is checked."""
        assert needs_chain_creator_flow(token(creator_sold=False))

    def test_a_coin_with_no_known_creator_cannot_be_read(self) -> None:
        assert not needs_chain_creator_flow(token(creator=None))

    def test_the_common_case_is_exactly_the_one_that_was_being_refused(self) -> None:
        """``creator_sold`` still NULL at decision time, allocation recorded:
        this is the 27 orders of 16/09."""
        assert needs_chain_creator_flow(token())
