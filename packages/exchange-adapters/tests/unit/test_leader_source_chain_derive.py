"""Copy-trade pilot (H-037): a followed wallet's LeaderEvent from one getTransaction result, offline.

Real mainnet transactions of third parties already committed as fixtures (T4.12): the buy of
``rpc_tx_buy_raw.json`` (wallet ``AsRQ...``), the sell of ``rpc_tx_probe_raw.json`` (public bot
``sssss...``), and the PumpSwap swaps of ``pumpswap/t1a_*``. The failed-transaction case is the same
buy with ``meta.err`` set — a labelled synthetic edit.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from hunter_exchanges.pumpfun.leader_source_chain_derive import leader_events_from_transaction

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).parents[1] / "fixtures"
BUYER = "AsRQHoHxfBYqvxJZxK9RtJUnRZcCwUoh9KNpVxH6Jhnd"
SELLER = "sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d"
MINT = "5ejAEbzxiZuwUNgZcoryoAY8gA5oCAVJZx5AyDnApump"
OBS = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)


def _tx(name: str) -> dict[str, Any]:
    body = cast("dict[str, Any]", json.loads((FIXTURES / name).read_text()))
    return cast("dict[str, Any]", body.get("result", body))  # t1a_* files are the bare result


def _lamport_change(tx: dict[str, Any], wallet: str) -> int:
    keys = tx["transaction"]["message"]["accountKeys"]
    i = keys.index(wallet)
    return int(tx["meta"]["postBalances"][i]) - int(tx["meta"]["preBalances"][i])


def _held(tx: dict[str, Any], label: str, wallet: str, mint: str) -> int:
    return sum(
        int(b["uiTokenAmount"]["amount"])
        for b in tx["meta"][label]
        if b.get("owner") == wallet and b["mint"] == mint
    )


def test_the_real_curve_buy_becomes_a_buy_event_with_exact_atoms_and_lamports() -> None:
    tx = _tx("pumpfun/rpc_tx_buy_raw.json")
    read = leader_events_from_transaction(
        tx, wallet=BUYER, signature="SIG-B", first_seen_at=OBS, fields_complete_at=OBS
    )
    assert read.reason is None
    (ev,) = read.events
    assert (ev.wallet, ev.mint, ev.side, ev.signature) == (BUYER, MINT, "buy", "SIG-B")
    # the same number two other ways: the wallet's own token balances and the TradeEvent's amount
    assert ev.token_delta_atoms == _held(tx, "postTokenBalances", BUYER, MINT) - _held(
        tx, "preTokenBalances", BUYER, MINT
    )
    assert ev.token_delta_atoms == 22_628_881_309_131
    assert ev.position_after_atoms == _held(tx, "postTokenBalances", BUYER, MINT)
    assert ev.sol_delta_lamports == _lamport_change(tx, BUYER) < 0
    assert (ev.slot, ev.source, ev.confirmed, ev.kind) == (446369982, "chain", True, "swap")
    assert ev.block_time == datetime.fromtimestamp(1789197249, tz=UTC) and ev.first_seen_at == OBS


def test_the_real_curve_sell_is_a_sell_with_the_position_left() -> None:
    tx = _tx("pumpfun/rpc_tx_probe_raw.json")
    (ev,) = leader_events_from_transaction(
        tx, wallet=SELLER, signature="SIG-S", first_seen_at=OBS, fields_complete_at=OBS
    ).events
    assert ev.side == "sell" and ev.token_delta_atoms == -16_800_146_527_261
    assert ev.position_after_atoms == _held(tx, "postTokenBalances", SELLER, ev.mint)
    assert ev.sol_delta_lamports == _lamport_change(tx, SELLER) > 0


def test_a_wallet_that_only_paid_or_watched_is_not_a_trade() -> None:
    read = leader_events_from_transaction(
        _tx("pumpfun/rpc_tx_probe_raw.json"),
        wallet="6nAh8drzAYfFZuTFFRgwRdV8tNndFiX1E8NGRAGzSk5F",
        signature="S",
        first_seen_at=OBS,
        fields_complete_at=OBS,
    )
    assert read.events == () and read.reason == "not_a_trade"


def test_a_failed_transaction_is_never_an_event() -> None:
    tx = copy.deepcopy(_tx("pumpfun/rpc_tx_buy_raw.json"))
    tx["meta"]["err"] = {"InstructionError": [0, "Custom"]}  # synthetic edit of the real buy
    read = leader_events_from_transaction(
        tx, wallet=BUYER, signature="S", first_seen_at=OBS, fields_complete_at=OBS
    )
    assert read.events == () and read.reason == "tx_failed"


def test_a_pumpswap_swap_is_attributed_by_its_own_event_and_priced_from_the_balances() -> None:
    from hunter_exchanges.pumpfun.program_logs import read_transaction_logs

    found = 0
    for path in sorted((FIXTURES / "pumpswap").glob("t1a_rpc_amm_*_raw.json")):
        tx = _tx(f"pumpswap/{path.name}")
        for rec in read_transaction_logs(tx, received_at=OBS).swaps:
            if rec.venue != "pool" or rec.base_mint is None or rec.quote_is_sol is not True:
                continue
            read = leader_events_from_transaction(
                tx, wallet=rec.wallet, signature="S", first_seen_at=OBS, fields_complete_at=OBS
            )
            event = next((e for e in read.events if e.mint == rec.base_mint), None)
            if event is None:  # e.g. the balances net to zero when the wallet swapped both ways
                continue
            found += 1
            assert event.token_delta_atoms == _held(
                tx, "postTokenBalances", rec.wallet, rec.base_mint
            ) - _held(tx, "preTokenBalances", rec.wallet, rec.base_mint)
            assert event.side == ("buy" if event.token_delta_atoms > 0 else "sell")
            assert read.reserves[rec.base_mint].venue == "pool"
    assert found >= 2  # the fixtures hold several direct pool swaps with a resolved base mint


CURVE = "ChDRd2ZZ1NTFZ2sx6PAWH9iaL7wv3jSdnCFMzSBxNCaS"  # owner of the bonding curve's token account


def test_a_wallet_whose_tokens_moved_without_a_swap_event_of_its_own_is_not_a_trade() -> None:
    """The curve's token balance fell by exactly what the leader got and its SOL rose, yet it is not
    the trader: only a swap event attributed to the wallet (KB-0184 readers) proves a trade."""
    tx = _tx("pumpfun/rpc_tx_buy_raw.json")
    assert _held(tx, "preTokenBalances", CURVE, MINT) != _held(tx, "postTokenBalances", CURVE, MINT)
    read = leader_events_from_transaction(
        tx, wallet=CURVE, signature="S", first_seen_at=OBS, fields_complete_at=OBS
    )
    assert read.events == () and read.reason == "not_a_trade"


def test_a_transaction_without_logs_is_unreadable_never_assumed_to_be_no_trade() -> None:
    tx = copy.deepcopy(_tx("pumpfun/rpc_tx_buy_raw.json"))
    del tx["meta"]["logMessages"]
    read = leader_events_from_transaction(
        tx, wallet=BUYER, signature="S", first_seen_at=OBS, fields_complete_at=OBS
    )
    assert read.events == () and read.reason == "logs_unreadable"


def test_a_swap_event_that_disagrees_with_the_balance_sign_is_refused() -> None:
    tx = copy.deepcopy(_tx("pumpfun/rpc_tx_buy_raw.json"))
    mine = next(b for b in tx["meta"]["postTokenBalances"] if b["owner"] == BUYER)
    pre = copy.deepcopy(mine)  # synthetic: the leader "already held" more than it ends with
    pre["uiTokenAmount"]["amount"] = str(int(mine["uiTokenAmount"]["amount"]) + 10)
    tx["meta"]["preTokenBalances"].append(pre)
    read = leader_events_from_transaction(
        tx, wallet=BUYER, signature="S", first_seen_at=OBS, fields_complete_at=OBS
    )
    assert read.events == () and read.reason == "sign_mismatch"


def test_the_curve_reserves_after_the_trade_ride_along_for_the_ideal_price() -> None:
    read = leader_events_from_transaction(
        _tx("pumpfun/rpc_tx_buy_raw.json"),
        wallet=BUYER,
        signature="S",
        first_seen_at=OBS,
        fields_complete_at=OBS,
    )
    r = read.reserves[MINT]
    assert r.venue == "curve" and r.sol_reserves > 0 and r.token_reserves > 0


def test_a_legible_buy_followed_by_a_truncated_log_is_kept_but_flagged_partial() -> None:
    """The truncated suffix may hide another trade of the wallet: the legible one is delivered AND the
    loss is carried (the caller turns it into a gap)."""
    tx = copy.deepcopy(_tx("pumpfun/rpc_tx_buy_raw.json"))
    tx["meta"]["logMessages"].append("Log truncated")
    read = leader_events_from_transaction(
        tx, wallet=BUYER, signature="S", first_seen_at=OBS, fields_complete_at=OBS
    )
    assert len(read.events) == 1 and read.partial is True
    clean = leader_events_from_transaction(
        _tx("pumpfun/rpc_tx_buy_raw.json"),
        wallet=BUYER,
        signature="S",
        first_seen_at=OBS,
        fields_complete_at=OBS,
    )
    assert clean.partial is False


def test_two_mints_for_the_wallet_in_one_transaction_build_without_a_sol_leg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import replace

    from hunter_exchanges.pumpfun import leader_source_chain_derive as module
    from hunter_exchanges.pumpfun.program_logs import read_transaction_logs

    tx = copy.deepcopy(_tx("pumpfun/rpc_tx_buy_raw.json"))
    tx["meta"]["postTokenBalances"].append(
        {
            "accountIndex": 9,
            "mint": "SecondMint",
            "owner": BUYER,
            "uiTokenAmount": {"amount": "7", "decimals": 6},
        }
    )
    real = read_transaction_logs(tx, received_at=OBS)
    second = replace(real.swaps[0], mint="SecondMint")
    fake = replace(real, swaps=(*real.swaps, second))

    def fake_reader(*_args: object, **_kwargs: object) -> object:
        return fake

    monkeypatch.setattr(module, "read_transaction_logs", fake_reader)
    read = leader_events_from_transaction(
        tx, wallet=BUYER, signature="S", first_seen_at=OBS, fields_complete_at=OBS
    )
    assert sorted(e.mint for e in read.events) == [MINT, "SecondMint"]
    assert all(e.multi_mint and e.sol_delta_lamports is None for e in read.events)


def test_a_second_swap_whose_mint_could_not_be_resolved_makes_the_read_partial_and_dropsthe_sol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import replace

    from hunter_exchanges.pumpfun import leader_source_chain_derive as module
    from hunter_exchanges.pumpfun.program_logs import read_transaction_logs

    tx = _tx("pumpfun/rpc_tx_buy_raw.json")
    real = read_transaction_logs(tx, received_at=OBS)
    pool_swap = replace(real.swaps[0], venue="pool", mint=None, base_mint=None, quote_is_sol=None)
    fake = replace(real, swaps=(*real.swaps, pool_swap))

    def fake_reader(*_args: object, **_kwargs: object) -> object:
        return fake

    monkeypatch.setattr(module, "read_transaction_logs", fake_reader)
    read = module.leader_events_from_transaction(
        tx, wallet=BUYER, signature="S", first_seen_at=OBS, fields_complete_at=OBS
    )
    assert len(read.events) == 1 and read.partial is True
    assert read.events[0].sol_delta_lamports is None  # the debit may include the hidden swap


def test_a_truncated_log_makes_the_sol_attribution_ambiguous_too() -> None:
    tx = copy.deepcopy(_tx("pumpfun/rpc_tx_buy_raw.json"))
    tx["meta"]["logMessages"].append("Log truncated")
    (event,) = leader_events_from_transaction(
        tx, wallet=BUYER, signature="S", first_seen_at=OBS, fields_complete_at=OBS
    ).events
    assert event.sol_delta_lamports is None
