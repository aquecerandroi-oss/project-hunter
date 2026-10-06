"""Helpers over the REAL ``getTransaction`` fixtures of wave 1a (H-030) for the engine tests.

The fixtures live in ``packages/exchange-adapters/tests/fixtures`` (provenance:
``t1a_provenance.json`` there; read, never copied). The records come from the adapter's own
log reader (``read_program_logs``); the witnesses come from the chain apart from the record:
the event's own pre-trade reserves and the swap instruction's accounts (pool, base mint,
quote mint are accounts 0, 3 and 4 of a PumpSwap ``buy``/``sell``, KB-0184).
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from hunter_exchanges.pumpfun.program_logs import read_program_logs
from hunter_exchanges.pumpfun.swap_record import SwapRecord
from hunter_exchanges.pumpswap.buy_event import BUY_EVENT_DISCRIMINATOR, BuyEvent, decode_buy_event
from hunter_exchanges.pumpswap.decode import PUMPSWAP_PROGRAM_ID
from hunter_exchanges.pumpswap.sell_event import (
    SELL_EVENT_DISCRIMINATOR,
    SellEvent,
    decode_sell_event,
)
from hunter_indicators.meme.wallets.bridge import PoolMints

FIXTURES = Path(__file__).parents[3] / "exchange-adapters" / "tests" / "fixtures"
RECEIVED = datetime(2026, 10, 6, 0, 0, tzinfo=UTC)

AMM_BUY = "t1a_rpc_amm_buy_5SmrD75SgxDd_raw.json"  # the 38 387 041-lamport buy (KB-0184 item 3)
AMM_BUY_NEXT = "t1a_rpc_amm_buy_2EjiTbbdkX2L_raw.json"  # the next buy of the same pool
AMM_BUY_EXACT = "t1a_rpc_amm_buy_exact_5tKuWqTWBw8y_raw.json"
AMM_BUY_EXACT_2 = "t1a_rpc_amm_buy_exact_3YxgSPJioUJp_raw.json"
AMM_BUY_ROUTED = "t1a_rpc_amm_buy_routed_2HzxLVTqSFWq_raw.json"
AMM_SELL_CASHBACK_X2 = "t1a_rpc_amm_sell_cashback_two_events_3gYxvcFECiai_raw.json"
V1_AMM_BUY = "t1a_rpc_v1_amm_buy_exact_holder_rewards_4JMsAJNT9otk_raw.json"
V1_AMM_SELL = "t1a_rpc_v1_amm_sell_5Ls5TV77aYS3_raw.json"
WSOL_QUOTED = (
    AMM_BUY,
    AMM_BUY_NEXT,
    AMM_BUY_EXACT,
    AMM_BUY_EXACT_2,
    AMM_BUY_ROUTED,
    AMM_SELL_CASHBACK_X2,
    V1_AMM_BUY,
    V1_AMM_SELL,
)
# Pools whose BASE is WSOL and whose quote is another token (accounts 3/4 of the instruction):
# the record's "sol_lamports" there are atoms of that token.
SOL_IS_BASE = (
    "t1a_rpc_amm_buy_nocreator_4jyiFoCoVoWt_raw.json",
    "t1a_rpc_amm_sell_551G1CF8C3Bx_raw.json",
    "t1a_rpc_amm_sell_4xuvoJjc286y_raw.json",
)
V1_PUMP_BUY = "t1a_rpc_v1_pump_buy_4b5YwBKdr5_raw.json"


def tx(name: str, directory: str = "pumpswap") -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES / directory / name).read_text()))


def records(t: dict[str, Any]) -> tuple[SwapRecord, ...]:
    read = read_program_logs(
        signature=str(t["transaction"]["signatures"][0]),
        slot=int(t["slot"]),
        logs=[str(line) for line in t["meta"]["logMessages"]],
        received_at=RECEIVED,
    )
    assert not read.gap and read.problems == ()
    return read.swaps


def pool_events(t: dict[str, Any]) -> list[BuyEvent | SellEvent]:
    """The PumpSwap swap events of the logs, decoded: their reserves are the pool BEFORE the trade."""
    out: list[BuyEvent | SellEvent] = []
    for line in cast(list[str], t["meta"]["logMessages"]):
        if not line.startswith("Program data: "):
            continue
        body = base64.b64decode(line[len("Program data: ") :])
        if body[:8] == BUY_EVENT_DISCRIMINATOR:
            out.append(decode_buy_event(body))
        elif body[:8] == SELL_EVENT_DISCRIMINATOR:
            out.append(decode_sell_event(body))
    return out


def _keys(t: dict[str, Any]) -> list[str]:
    loaded = cast(dict[str, list[str]], t["meta"].get("loadedAddresses") or {})
    static = cast(list[str], t["transaction"]["message"]["accountKeys"])
    return [*static, *loaded.get("writable", []), *loaded.get("readonly", [])]


def chain_pool_mints(t: dict[str, Any], pool: str) -> PoolMints:
    """Base and quote mints of ``pool`` read from the swap instruction's own accounts."""
    keys = _keys(t)
    instructions = list(cast(list[dict[str, Any]], t["transaction"]["message"]["instructions"]))
    for group in cast(list[dict[str, Any]], t["meta"]["innerInstructions"]):
        instructions += cast(list[dict[str, Any]], group["instructions"])
    for ix in instructions:
        accounts = [keys[i] for i in cast(list[int], ix["accounts"])]
        if keys[ix["programIdIndex"]] == PUMPSWAP_PROGRAM_ID and accounts[:1] == [pool]:
            return PoolMints(pool=pool, base_mint=accounts[3], quote_mint=accounts[4])
    raise AssertionError(f"no PumpSwap swap instruction on {pool}")
