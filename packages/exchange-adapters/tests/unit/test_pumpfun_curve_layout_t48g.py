"""T4.8g — the ``BondingCurve`` account grew again with the 2026-10-08 redeploy: **166 bytes** on a
curve the new program has touched, **151** on one nobody traded since (the T4.8c/T4.8d layout is 125
decoded + 26 reserved = 151). Fifteen new bytes at the end of the reserved area.

Why it matters to the desk and nowhere else: simulating our own ``buy`` on three old 151-byte
curves (2026-10-08), two of them (a holder-reward coin and a plain one, both with a non-zero
``trailing_u64``) were re-allocated to 166 bytes and the trader paid the rent for the 15 bytes —
15 x 5080 = 76 200 lamports (payer delta = budget + network fee + 76 200, constant across two
budgets; the ATA rents of the same runs obey the same 5080 lamports/byte: 293 B = 1 488 440 and
298 B = 1 513 840); the third (a cashback coin whose ``trailing_u64`` is 0) did not grow. A SELL on
an old curve was NOT simulated (no holder found). It shows up as ``unexplained_lamports == 76 200``
in the fill — an observation, not a gate (``fills.py`` records it, nothing refuses on it); the
entry's pre-flight reserve (``scope.buy_reserve_sol``) does not include it (T4.8g review, open).

Everything the builders read is in the first 125 bytes and did not move: this file pins that both
layouts decode to the same named fields and that the 125..132 ``u64`` is the event's unnamed
``trailing_u64`` (HDko: 300 701 in the simulated buy, and the byte pair below).
"""

from __future__ import annotations

import base64
import json
import struct
from pathlib import Path
from typing import Any, cast

import pytest

from hunter_exchanges.pumpfun.decode import (
    LAYOUT_WITH_HOLDER_REWARD,
    decode_bonding_curve_account,
)

FIXTURES = Path(__file__).parents[1] / "fixtures/pumpfun"
RENT_PER_BYTE = 5080
OLD, NEW_HR, NEW_CLASSIC = (
    "t48g_rpc_curve_old151_HDko_raw.json",
    "t48g_rpc_curve_new166_5rL1_raw.json",
    "t48g_rpc_curve_new166_2Pi6_raw.json",
)


def _value(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES / name).read_text())["result"]["value"])


def _raw(name: str) -> bytes:
    return base64.b64decode(_value(name)["data"][0])


def test_the_two_layouts_are_151_and_166_bytes() -> None:
    assert len(_raw(OLD)) == 151 == _value(OLD)["space"]
    assert len(_raw(NEW_HR)) == len(_raw(NEW_CLASSIC)) == 166
    assert (166 - 151) * RENT_PER_BYTE == 76_200


@pytest.mark.parametrize("name", [OLD, NEW_HR, NEW_CLASSIC])
def test_the_decoder_reads_the_named_prefix_of_either_layout(name: str) -> None:
    value = _value(name)
    curve = decode_bonding_curve_account(value["data"][0], owner=value["owner"])
    assert curve.layout == LAYOUT_WITH_HOLDER_REWARD
    assert curve.complete is False
    assert curve.virtual_token_reserves > 0 and curve.virtual_sol_reserves > 0
    assert curve.real_token_reserves > 0 and curve.token_total_supply > 0


def test_holder_reward_flag_and_the_unnamed_u64_sit_where_the_decoder_and_the_event_say() -> None:
    hr_old, hr_new, classic = (
        decode_bonding_curve_account(_value(n)["data"][0], owner=_value(n)["owner"])
        for n in (OLD, NEW_HR, NEW_CLASSIC)
    )
    assert (hr_old.is_holder_reward, hr_new.is_holder_reward, classic.is_holder_reward) == (
        True,
        True,
        False,
    )
    # bytes 125..132: the u64 the redeployed program also writes in TradeEvent.trailing_u64
    assert struct.unpack_from("<Q", _raw(OLD), 125)[0] == 300_701  # HDko, simulated buy 2026-10-08
    assert struct.unpack_from("<Q", _raw(NEW_HR), 125)[0] == 2_747_193  # 5rL1, simulated buy
    assert struct.unpack_from("<Q", _raw(NEW_CLASSIC), 125)[0] == 0  # a classic coin: never written
    # the 26 reserved bytes of the old layout are zero past that u64 (HDko, 151 B); both
    # new-layout coins carry the same non-zero value at offset 143 (a field the old one lacks)
    assert set(_raw(OLD)[133:]) == {0}
    for name in (NEW_HR, NEW_CLASSIC):
        assert struct.unpack_from("<I", _raw(name), 143)[0] == 0x06FC23AC
    assert struct.unpack_from("<Q", _raw(NEW_HR), 133)[0] == 4_349_721  # HR-only, unnamed


def test_the_simulation_shows_the_curve_growing_and_the_trader_paying_for_it() -> None:
    """The causal chain behind the 76 200 (T4.8g, Astra's request to pin it): our own ``buy``
    simulated on the old 151-byte curve of HDko, post-state of BOTH the payer and the curve taken
    from the simulation itself (``t48g_simulation_curve_growth_raw.json``, slot 454645917). HDko is
    an untraded coin — the curve's lamports before were the same 1 718 102 in two reads minutes
    apart, so nothing else moved it."""
    rec = json.loads((FIXTURES / "t48g_simulation_curve_growth_raw.json").read_text())
    assert rec["err"] is None and rec["post"]["curve"]["data_len"] == 166
    assert rec["pre"]["curve"]["data_len"] == 151 == len(_raw(OLD))
    growth = (166 - 151) * RENT_PER_BYTE
    event = rec["event"]
    curve_gain = rec["post"]["curve"]["lamports"] - rec["pre"]["curve"]["lamports"]
    assert curve_gain == event["sol_amount"] + growth  # the curve receives the SOL leg + the rent
    payer_cost = rec["pre"]["user"]["lamports"] - rec["post"]["user"]["lamports"]
    budget = event["sol_amount"] + event["fee"] + event["creator_fee"]
    assert budget == 50_000_000  # 0.05 SOL, to the lamport
    assert payer_cost == budget + 5_001 + growth  # budget + network fee + the growth
    assert event["trailing_u64"] == struct.unpack_from("<Q", _raw(OLD), 125)[0] == 300_701
