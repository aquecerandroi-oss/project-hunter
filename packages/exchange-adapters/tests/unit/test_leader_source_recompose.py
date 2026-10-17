"""Copy-trade pilot (H-037): recomposing a wallet's trades in an interval from chain history.

The copy lane asks this after a gap, to learn what a leader did while it was not looking. The answer is
either complete or says explicitly that it is not — a guess is never returned. Real third-party mainnet
transactions of T4.12 (the buy of ``AsRQ...``); the listing and the fetch are fakes that honour the
node's ``until``/``before``/``limit`` like the real thing.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

from hunter_exchanges.base import ExchangeUnavailable
from hunter_exchanges.pumpfun.leader_source_recompose import Recomposition, recompose
from hunter_exchanges.pumpfun.leader_source_rpc_guard import RpcRefused
from hunter_exchanges.pumpfun.rpc_wallet import SignatureInfo

pytestmark = pytest.mark.unit

FX = Path(__file__).parents[1] / "fixtures/pumpfun"
BUYER = "AsRQHoHxfBYqvxJZxK9RtJUnRZcCwUoh9KNpVxH6Jhnd"
BUY_TX = cast("dict[str, Any]", json.loads((FX / "rpc_tx_buy_raw.json").read_text())["result"])
SELL_TX = cast("dict[str, Any]", json.loads((FX / "rpc_tx_probe_raw.json").read_text())["result"])
T = 1_789_197_249  # blockTime of the real buy
NOW = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)


def at(seconds: int) -> datetime:
    return datetime.fromtimestamp(T + seconds, tz=UTC)


def tx_at(seconds: int, slot: int, *, base: dict[str, Any] = BUY_TX) -> dict[str, Any]:
    tx = copy.deepcopy(base)
    tx["blockTime"], tx["slot"] = T + seconds, slot
    return tx


class Chain:
    """A wallet's history, newest first, served the way ``getSignaturesForAddress`` serves it."""

    def __init__(self, entries: Sequence[tuple[str, int, dict[str, Any] | None]]) -> None:
        self.entries = entries  # (signature, seconds after T, tx)
        self.list_calls: list[tuple[str | None, int, str | None]] = []
        self.fetched: list[str] = []
        self.fail_list_after: int | None = None
        self.refuse = False

    async def lister(
        self, wallet: str, until: str | None, limit: int, before: str | None
    ) -> Sequence[SignatureInfo]:
        self.list_calls.append((until, limit, before))
        if self.fail_list_after is not None and len(self.list_calls) > self.fail_list_after:
            raise ExchangeUnavailable("down", exchange="pumpfun")
        sigs = [e for e in self.entries]
        if before is not None:
            sigs = sigs[[e[0] for e in sigs].index(before) + 1 :]
        return [
            SignatureInfo(sig, 1000 - i, datetime.fromtimestamp(T + secs, tz=UTC), False)
            for i, (sig, secs, _) in enumerate(sigs[:limit])
        ]

    async def fetch(self, signature: str) -> dict[str, Any] | None:
        self.fetched.append(signature)
        if self.refuse:
            raise RpcRefused("refused_403")
        return next((tx for sig, _, tx in self.entries if sig == signature), None)


async def run(chain: Chain, start: int, end: int, **kw: Any) -> Recomposition:
    return await recompose(
        BUYER,
        at(start),
        at(end),
        list_signatures=chain.lister,
        fetch_tx=chain.fetch,
        wall=lambda: NOW,
        **kw,
    )


async def test_the_trades_of_the_interval_come_back_oldest_first_with_the_position_per_mint() -> (
    None
):
    chain = Chain(
        [
            ("S3", 30, tx_at(30, 103)),
            ("S2", 20, tx_at(20, 102)),
            ("S1", 10, tx_at(10, 101)),
            ("S0", -50, tx_at(-50, 90)),  # before the interval: never fetched
        ]
    )
    result = await run(chain, 0, 100)
    assert result.complete and result.reasons == ()
    assert [e.signature for e in result.events] == ["S1", "S2", "S3"]
    assert [e.slot for e in result.events] == [101, 102, 103]
    assert all(
        e.confirmed and e.source == "chain" and e.first_seen_at == NOW for e in result.events
    )
    mint = result.events[0].mint
    assert result.positions_after == {mint: result.events[-1].position_after_atoms}
    assert (
        "S0" not in chain.fetched and result.signatures_seen == 4
    )  # listed, the one before the start included


async def test_a_transaction_that_is_not_a_trade_of_the_wallet_is_just_skipped() -> None:
    other = tx_at(10, 101, base=SELL_TX)  # someone else's sell that merely listed our wallet
    chain = Chain([("S2", 20, tx_at(20, 102)), ("S1", 10, other)])
    result = await run(chain, 0, 100)
    assert result.complete and [e.signature for e in result.events] == ["S2"]


async def test_the_end_of_the_interval_is_exclusive_and_the_start_inclusive() -> None:
    chain = Chain(
        [("SE", 100, tx_at(100, 105)), ("SA", 50, tx_at(50, 104)), ("SS", 0, tx_at(0, 103))]
    )
    result = await run(chain, 0, 100)
    assert [e.signature for e in result.events] == ["SS", "SA"]


async def test_hitting_the_signature_cap_inside_the_interval_is_an_explicit_incomplete() -> None:
    entries = [(f"S{i}", 900 - i, tx_at(900 - i, 5000 - i)) for i in range(250)]
    chain = Chain(entries)
    result = await run(chain, 0, 1000, cap=100)
    assert not result.complete and "signature_cap" in result.reasons
    assert result.signatures_seen == 100 and len(chain.fetched) <= 100
    assert all(call[1] <= 100 for call in chain.list_calls)


async def test_the_default_cap_is_one_thousand_signatures() -> None:
    from hunter_exchanges.pumpfun.leader_source_recompose import SIGNATURE_CAP

    assert SIGNATURE_CAP == 1000


async def test_history_that_ends_before_the_start_is_complete_even_with_few_signatures() -> None:
    chain = Chain([("S1", 10, tx_at(10, 101)), ("OLD", -999, tx_at(-999, 5))])
    result = await run(chain, 0, 100, cap=100)
    assert result.complete and [e.signature for e in result.events] == ["S1"]


async def test_a_listing_failure_is_incomplete_and_keeps_what_was_already_read() -> None:
    entries = [(f"S{i}", 900 - i, tx_at(900 - i, 5000 - i)) for i in range(250)]
    chain = Chain(entries)
    chain.fail_list_after = 1
    result = await run(chain, 0, 1000)
    assert not result.complete and "list_failed" in result.reasons
    assert result.signatures_seen == 100 and len(result.events) == 100


async def test_an_unreadable_or_missing_transaction_makes_it_incomplete_not_empty() -> None:
    truncated = tx_at(20, 102)
    truncated["meta"]["logMessages"].append("Log truncated")
    chain = Chain([("S3", 30, None), ("S2", 20, truncated), ("S1", 10, tx_at(10, 101))])
    result = await run(chain, 0, 100)
    assert not result.complete
    assert "tx_not_found:1" in result.reasons and "logs_partial:1" in result.reasons
    assert "S1" in [e.signature for e in result.events]  # what was readable is still delivered


async def test_a_refusal_from_the_node_stops_fetching_and_says_so() -> None:
    chain = Chain([("S2", 20, tx_at(20, 102)), ("S1", 10, tx_at(10, 101))])
    chain.refuse = True
    result = await run(chain, 0, 100)
    assert not result.complete and "rpc_refused" in result.reasons and result.events == ()
    assert len(chain.fetched) <= 8  # one wave at most, never a loop


async def test_a_pure_transfer_out_is_part_of_the_position_story() -> None:
    chain = Chain([("S1", 10, tx_at(10, 101))])
    from hunter_exchanges.pumpfun.leader_source_recompose import recompose as rc

    curve = (
        "ChDRd2ZZ1NTFZ2sx6PAWH9iaL7wv3jSdnCFMzSBxNCaS"  # the curve account loses tokens, no swap
    )
    result = await rc(
        curve, at(0), at(100), list_signatures=chain.lister, fetch_tx=chain.fetch, wall=lambda: NOW
    )
    (event,) = result.events
    assert event.kind == "transfer" and event.side == "sell"


async def test_bad_arguments_fail_closed() -> None:
    chain = Chain([])
    with pytest.raises(ValueError, match="wallet"):
        await recompose("*", at(0), at(1), list_signatures=chain.lister, fetch_tx=chain.fetch)
    with pytest.raises(ValueError, match="UTC"):
        await recompose(
            BUYER,
            datetime(2026, 1, 1),  # noqa: DTZ001 - naive on purpose
            at(1),
            list_signatures=chain.lister,
            fetch_tx=chain.fetch,
        )
    with pytest.raises(ValueError, match="end after"):
        await recompose(BUYER, at(10), at(10), list_signatures=chain.lister, fetch_tx=chain.fetch)
    with pytest.raises(ValueError, match="cap"):
        await recompose(
            BUYER, at(0), at(1), list_signatures=chain.lister, fetch_tx=chain.fetch, cap=0
        )
    assert timedelta(seconds=1) > timedelta(0)


CURVE = "ChDRd2ZZ1NTFZ2sx6PAWH9iaL7wv3jSdnCFMzSBxNCaS"  # its token balance is rewritten below


def curve_tx(pre: int, post: int, slot: int) -> dict[str, Any]:
    """A synthetic transfer-out of the curve account's tokens (no swap of its own): ``pre -> post``."""
    tx = tx_at(10, slot)
    for label, amount in (("preTokenBalances", pre), ("postTokenBalances", post)):
        for row in tx["meta"][label]:
            if row["owner"] == CURVE:
                row["uiTokenAmount"]["amount"] = str(amount)
    return tx


async def test_two_transfers_in_the_same_slot_keep_the_listing_order_not_the_signature_order() -> (
    None
):
    """The final position is the NEWEST transaction's, and 'newest' is the listing's word — a signature
    is not a clock. Here the newer one sorts first alphabetically; sorting by signature would end at 50."""
    chain = Chain([("aaa", 10, curve_tx(50, 0, 700)), ("zzz", 10, curve_tx(100, 50, 700))])
    result = await recompose(
        CURVE, at(0), at(100), list_signatures=chain.lister, fetch_tx=chain.fetch, wall=lambda: NOW
    )
    assert result.complete
    assert [e.signature for e in result.events] == ["zzz", "aaa"]  # oldest first
    assert next(iter(result.positions_after.values())) == 0


async def test_a_swap_with_unreadable_balances_makes_the_recomposition_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hunter_exchanges.pumpfun import leader_source_chain_derive as module

    def no_lamports(*_args: object) -> None:
        return None

    monkeypatch.setattr(module, "_lamport_change", no_lamports)
    chain = Chain([("S1", 10, tx_at(10, 101))])
    result = await run(chain, 0, 100)
    assert not result.complete and "tx_unreadable:1" in result.reasons
