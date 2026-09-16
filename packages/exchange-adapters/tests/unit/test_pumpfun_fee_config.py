"""T4.29c — the ``FeeConfig`` account of the pump.fun fee program.

Fixtures (real mainnet reads, 2026-09-16, public RPC, nothing signed):
- ``rpc_fee_config_raw.json`` — PDA ``["fee_config", pump program]``, slot 447 586 137;
- ``t429c_rpc_fee_config_amm_raw.json`` — PDA ``["fee_config", PumpSwap program]``,
  slot 447 586 368, the 25-tier table the ``fees.png`` of the public docs shows.
"""

from __future__ import annotations

import base64
import json
import struct
from pathlib import Path
from typing import Any, cast

import pytest

from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.fee_config import (
    FEE_CONFIG_DISCRIMINATOR,
    FEE_CONFIG_UNAVAILABLE_EVENT,
    FEE_PROGRAM_ID,
    PUMP_SWAP_PROGRAM_ID,
    FeeConfig,
    Fees,
    FeeTier,
    bonding_curve_market_cap_lamports,
    curve_fee_bps,
    decode_fee_config,
    fee_config_address,
    fees_for_market_cap,
)
from hunter_exchanges.pumpfun.quote import (
    BONDING_CURVE_FEE_TIER_2026_05_20,
    CurveReserves,
    FeeBps,
    quote_buy,
    quote_sell,
)
from hunter_exchanges.pumpfun.trade_event import decode_trade_event

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/pumpfun"
LAMPORTS_PER_SOL = 1_000_000_000


def _fixture(name: str) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads((FIXTURES / name).read_text(encoding="utf-8")))


def _account(name: str) -> tuple[str, str]:
    value = cast("dict[str, Any]", _fixture(name)["result"]["value"])
    return str(cast("list[str]", value["data"])[0]), str(value["owner"])


def _encode(config: FeeConfig) -> bytes:
    """Independent re-encoder (test-only): proves the decoder consumed exactly the
    bytes the layout claims, without shipping an encoder nothing would call."""

    def fees(f: Fees) -> bytes:
        return struct.pack("<QQQ", f.lp_fee_bps, f.protocol_fee_bps, f.creator_fee_bps)

    def tiers(items: tuple[FeeTier, ...]) -> bytes:
        out = struct.pack("<I", len(items))
        for tier in items:
            out += tier.market_cap_lamports_threshold.to_bytes(16, "little") + fees(tier.fees)
        return out

    from hunter_exchanges.pumpfun.solana_codec import pubkey_bytes

    body = (
        FEE_CONFIG_DISCRIMINATOR
        + bytes([config.bump])
        + pubkey_bytes(config.admin)
        + fees(config.flat_fees)
        + tiers(config.fee_tiers)
        + tiers(config.stable_fee_tiers)
    )
    if config.exotic_flat_fees is not None:
        body += fees(config.exotic_flat_fees)
    return body


# --------------------------------------------------------------------------- PDA


def test_fee_config_pda_matches_the_account_a_real_sell_passed() -> None:
    """The ``sell`` of 2026-09-15 (``t48c_rpc_tx_sell_raw.json``) carries the fee
    config at index 12 and the fee program at index 13 — the PDA derived here has
    to be that exact account, or we would be reading the wrong fees."""
    tx = cast("dict[str, Any]", _fixture("t48c_rpc_tx_sell_raw.json")["result"])
    message = cast("dict[str, Any]", cast("dict[str, Any]", tx["transaction"])["message"])
    keys = [str(key) for key in cast("list[Any]", message["accountKeys"])]
    instructions = cast("list[dict[str, Any]]", message["instructions"])
    accounts = next(
        [keys[int(i)] for i in cast("list[int]", ix["accounts"])]
        for ix in instructions
        if keys[int(cast(int, ix["programIdIndex"]))] == PUMP_PROGRAM_ID
    )
    assert accounts[12] == fee_config_address(PUMP_PROGRAM_ID)
    assert accounts[13] == FEE_PROGRAM_ID


def test_fee_config_pda_is_program_specific() -> None:
    assert fee_config_address(PUMP_PROGRAM_ID) == "8Wf5TiAheLUqBrKXeYg2JtAFFMWtKdG2BSFgqUcPVwTt"
    assert (
        fee_config_address(PUMP_SWAP_PROGRAM_ID) == "5PHirr8joyTMp9JMm6nW7hNDVyEYdkzDqazxPD7RaTjx"
    )


# ------------------------------------------------------------------------ decode


def test_decode_round_trip_on_the_real_bonding_curve_account() -> None:
    data, owner = _account("rpc_fee_config_raw.json")
    config = decode_fee_config(data, owner=owner)
    assert config.bump == 253
    assert config.admin == "FFWtrEQ4B4PKQoVuHYzZq8FabGkVatYzDpEVHsK5rrhF"
    assert config.flat_fees == Fees(lp_fee_bps=0, protocol_fee_bps=95, creator_fee_bps=30)
    # One tier, threshold 0: on the curve the fee does not depend on the market cap.
    assert config.fee_tiers == (
        FeeTier(0, Fees(lp_fee_bps=0, protocol_fee_bps=95, creator_fee_bps=30)),
    )
    assert config.stable_fee_tiers == config.fee_tiers
    assert config.exotic_flat_fees == Fees(lp_fee_bps=0, protocol_fee_bps=95, creator_fee_bps=30)
    raw = base64.b64decode(data)
    assert config.decoded_length == 177
    assert raw[: config.decoded_length] == _encode(config)
    assert config.trailing_bytes == len(raw) - config.decoded_length
    assert raw[config.decoded_length :] == b"\x00" * config.trailing_bytes


def test_decode_the_real_pumpswap_account_carries_the_published_tier_table() -> None:
    data, owner = _account("t429c_rpc_fee_config_amm_raw.json")
    config = decode_fee_config(data, owner=owner)
    assert len(config.fee_tiers) == 25
    assert config.fee_tiers[0] == FeeTier(0, Fees(2, 93, 30))
    assert config.fee_tiers[1] == FeeTier(420 * LAMPORTS_PER_SOL, Fees(20, 5, 95))
    assert config.fee_tiers[2] == FeeTier(1470 * LAMPORTS_PER_SOL, Fees(20, 5, 90))
    assert config.fee_tiers[-1] == FeeTier(98_240 * LAMPORTS_PER_SOL, Fees(20, 5, 5))
    assert [t.market_cap_lamports_threshold for t in config.fee_tiers] == sorted(
        t.market_cap_lamports_threshold for t in config.fee_tiers
    )
    raw = base64.b64decode(data)
    assert raw[: config.decoded_length] == _encode(config)


def test_decode_refuses_a_foreign_owner() -> None:
    data, _ = _account("rpc_fee_config_raw.json")
    with pytest.raises(MalformedMessage, match="not the pump.fun fee program"):
        decode_fee_config(data, owner=PUMP_PROGRAM_ID)


def test_decode_refuses_a_wrong_discriminator() -> None:
    raw = bytearray(base64.b64decode(_account("rpc_fee_config_raw.json")[0]))
    raw[0] ^= 0xFF
    with pytest.raises(MalformedMessage, match="discriminator"):
        decode_fee_config(base64.b64encode(bytes(raw)).decode(), owner=FEE_PROGRAM_ID)


def test_decode_refuses_a_truncated_account() -> None:
    raw = base64.b64decode(_account("t429c_rpc_fee_config_amm_raw.json")[0])[:200]
    with pytest.raises(MalformedMessage, match="truncated"):
        decode_fee_config(base64.b64encode(raw).decode(), owner=FEE_PROGRAM_ID)


def test_decode_refuses_a_tier_vector_longer_than_the_account() -> None:
    raw = bytearray(base64.b64decode(_account("rpc_fee_config_raw.json")[0]))
    struct.pack_into("<I", raw, 65, 10_000)  # fee_tiers length prefix
    with pytest.raises(MalformedMessage, match="truncated"):
        decode_fee_config(base64.b64encode(bytes(raw)).decode(), owner=FEE_PROGRAM_ID)


def test_decode_reads_an_account_without_the_exotic_flat_fees_tail() -> None:
    """``exotic_flat_fees`` is the newest field (in the GitHub IDL of commit
    ``8109141…``, not yet in the fee program's own on-chain IDL account). An account
    written before it existed simply ends after ``stable_fee_tiers``."""
    data, owner = _account("rpc_fee_config_raw.json")
    config = decode_fee_config(data, owner=owner)
    short = _encode(config)[: config.decoded_length - 24]
    older = decode_fee_config(base64.b64encode(short).decode(), owner=owner)
    assert older.exotic_flat_fees is None
    assert older.fee_tiers == config.fee_tiers


def test_fees_reject_negative_or_absurd_basis_points() -> None:
    with pytest.raises(ValueError, match="basis points"):
        Fees(lp_fee_bps=-1, protocol_fee_bps=0, creator_fee_bps=0)
    with pytest.raises(ValueError, match="basis points"):
        Fees(lp_fee_bps=0, protocol_fee_bps=10_000, creator_fee_bps=1)


# --------------------------------------------------------------- tier selection


def _tiers(*pairs: tuple[int, int]) -> tuple[FeeTier, ...]:
    return tuple(FeeTier(t, Fees(0, 95, creator)) for t, creator in pairs)


def _config(tiers: tuple[FeeTier, ...]) -> FeeConfig:
    return FeeConfig(
        bump=253,
        admin="FFWtrEQ4B4PKQoVuHYzZq8FabGkVatYzDpEVHsK5rrhF",
        flat_fees=Fees(0, 95, 30),
        fee_tiers=tiers,
        stable_fee_tiers=tiers,
        exotic_flat_fees=None,
        decoded_length=0,
        trailing_bytes=0,
    )


def test_tier_selection_takes_the_highest_threshold_at_or_below_the_market_cap() -> None:
    """``calculate_fee_tier`` (docs/FEE_PROGRAM_README.md of commit ``8109141…``,
    sha256 ``c03c0cc7…``): ``for (const tier of feeTiers.slice().reverse()) if
    (marketCap.gte(tier.marketCapLamportsThreshold)) return tier.fees;`` — the
    boundary belongs to the **upper** tier (``gte``)."""
    config = _config(_tiers((0, 30), (100, 20), (200, 10)))
    assert fees_for_market_cap(config, 99).creator_fee_bps == 30
    assert fees_for_market_cap(config, 100).creator_fee_bps == 20  # exactly on it
    assert fees_for_market_cap(config, 101).creator_fee_bps == 20
    assert fees_for_market_cap(config, 199).creator_fee_bps == 20
    assert fees_for_market_cap(config, 200).creator_fee_bps == 10
    assert fees_for_market_cap(config, 10**30).creator_fee_bps == 10


def test_market_cap_below_the_first_threshold_takes_the_first_tier() -> None:
    """``if (marketCap.lt(firstTier.marketCapLamportsThreshold)) return firstTier.fees;``"""
    config = _config(_tiers((50, 30), (100, 20)))
    assert fees_for_market_cap(config, 0).creator_fee_bps == 30
    assert fees_for_market_cap(config, 49).creator_fee_bps == 30
    assert fees_for_market_cap(config, 50).creator_fee_bps == 30


def test_tier_selection_on_the_real_pumpswap_table() -> None:
    config = decode_fee_config(
        _account("t429c_rpc_fee_config_amm_raw.json")[0], owner=FEE_PROGRAM_ID
    )
    below = 420 * LAMPORTS_PER_SOL - 1
    assert fees_for_market_cap(config, below) == Fees(2, 93, 30)
    assert fees_for_market_cap(config, 420 * LAMPORTS_PER_SOL) == Fees(20, 5, 95)
    assert fees_for_market_cap(config, 1470 * LAMPORTS_PER_SOL - 1) == Fees(20, 5, 95)
    assert fees_for_market_cap(config, 98_240 * LAMPORTS_PER_SOL) == Fees(20, 5, 5)


def test_tier_selection_on_the_real_bonding_curve_table_is_flat() -> None:
    config = decode_fee_config(_account("rpc_fee_config_raw.json")[0], owner=FEE_PROGRAM_ID)
    for mcap in (0, 1, 30 * LAMPORTS_PER_SOL, 85_000 * LAMPORTS_PER_SOL, 10**24):
        assert fees_for_market_cap(config, mcap) == Fees(0, 95, 30)


def test_tier_selection_refuses_an_empty_table_and_a_negative_market_cap() -> None:
    with pytest.raises(ValueError, match="fee_tiers is empty"):
        fees_for_market_cap(_config(()), 1)
    with pytest.raises(ValueError, match="market cap"):
        fees_for_market_cap(_config(_tiers((0, 30))), -1)


def test_bonding_curve_market_cap_is_the_sdk_formula() -> None:
    """``virtualSolReserves * mintSupply / virtualTokenReserves`` (integer division),
    FEE_PROGRAM_README ``bondingCurveMarketCap``. A virgin curve: 30 SOL virtual, 1.073e15
    virtual subunits, 1e15 supply -> 27.96 SOL."""
    mcap = bonding_curve_market_cap_lamports(
        mint_supply=1_000_000_000_000_000,
        virtual_sol_reserves=30 * LAMPORTS_PER_SOL,
        virtual_token_reserves=1_073_000_000_000_000,
    )
    assert mcap == 30 * LAMPORTS_PER_SOL * 1_000_000_000_000_000 // 1_073_000_000_000_000
    assert mcap == 27_958_993_476
    with pytest.raises(ValueError, match="virtual token reserves"):
        bonding_curve_market_cap_lamports(
            mint_supply=1, virtual_sol_reserves=1, virtual_token_reserves=0
        )


# ---------------------------------------------------------------- quote wiring


RESERVES = CurveReserves(
    virtual_sol=30 * LAMPORTS_PER_SOL,
    virtual_token=1_073_000_000_000_000,
    real_sol=0,
    real_token=793_100_000_000_000,
)


def test_curve_fee_bps_from_the_real_fee_config_equals_the_dated_constant_today() -> None:
    config = decode_fee_config(_account("rpc_fee_config_raw.json")[0], owner=FEE_PROGRAM_ID)
    fees, source = curve_fee_bps(config, market_cap_lamports=27_958_993_476)
    assert fees == FeeBps(protocol=95, creator=30) == BONDING_CURVE_FEE_TIER_2026_05_20
    assert source == "fee_config"


def test_curve_fee_bps_falls_back_to_the_documented_constant_when_unread() -> None:
    fees, source = curve_fee_bps(None, market_cap_lamports=27_958_993_476)
    assert fees is BONDING_CURVE_FEE_TIER_2026_05_20
    assert source == FEE_CONFIG_UNAVAILABLE_EVENT == "meme_fee_config_unavailable"


def test_curve_fee_bps_follows_a_tier_that_is_not_the_constant() -> None:
    """A hypothetical curve config with two tiers (the account has one today): at
    1 000 SOL of market cap the second tier's 10 bps creator fee is charged, not the
    constant's 30 — this is the whole point of reading the account."""
    tiers = (
        FeeTier(0, Fees(0, 95, 30)),
        FeeTier(1_000 * LAMPORTS_PER_SOL, Fees(0, 50, 10)),
    )
    config = _config(tiers)
    assert curve_fee_bps(config, market_cap_lamports=999 * LAMPORTS_PER_SOL)[0] == FeeBps(95, 30)
    assert curve_fee_bps(config, market_cap_lamports=1_000 * LAMPORTS_PER_SOL)[0] == FeeBps(50, 10)


def test_quote_buy_with_tiered_fees_vs_the_constant() -> None:
    """One SOL of tokens off the virgin curve above, ``quote_buy`` with each fee set:

    - pre-fee ``sol_amount`` is identical (fees never touch the curve maths);
    - constant 95+30 bps: ``protocol_fee`` = ceil(sol*95/1e4), ``creator_fee`` =
      ceil(sol*30/1e4) — 1,25 % on top;
    - tiered 50+10 bps: 0,60 % on top, i.e. 6 500 000 lamports cheaper on a 10 SOL buy.
    """
    tokens = 100_000_000_000_000  # 100 M subunits
    constant = quote_buy(RESERVES, tokens, BONDING_CURVE_FEE_TIER_2026_05_20, max_slippage_bps=100)
    tiered = quote_buy(RESERVES, tokens, FeeBps(protocol=50, creator=10), max_slippage_bps=100)
    assert constant.sol_amount == tiered.sol_amount == 3_083_247_688
    assert (constant.protocol_fee, constant.creator_fee) == (29_290_854, 9_249_744)
    assert (tiered.protocol_fee, tiered.creator_fee) == (15_416_239, 3_083_248)
    assert constant.total_cost - tiered.total_cost == 20_041_111


def test_curve_fee_bps_refuses_a_tier_that_charges_an_lp_fee() -> None:
    """The PumpSwap table charges ``lp_fee_bps``; a curve has no LP. If that shape
    ever reached the curve config, dropping the lp share would make every quote too
    cheap — refuse instead (the caller then falls back and logs)."""
    config = _config((FeeTier(0, Fees(20, 5, 95)),))
    with pytest.raises(ValueError, match="lp_fee_bps"):
        curve_fee_bps(config, market_cap_lamports=0)


def test_curve_fee_bps_floor_never_under_estimates() -> None:
    config = _config((FeeTier(0, Fees(0, 50, 10)),))
    fees, source = curve_fee_bps(
        config, market_cap_lamports=0, floor=BONDING_CURVE_FEE_TIER_2026_05_20
    )
    assert (fees, source) == (FeeBps(protocol=95, creator=30), "fee_config")


def test_stable_fee_tiers_are_selectable_and_differ_from_the_normal_table() -> None:
    """``stable_fee_tiers`` is a second table (stable quote mints). On the live
    PumpSwap account its second threshold is 59 SOL, not 420."""
    config = decode_fee_config(
        _account("t429c_rpc_fee_config_amm_raw.json")[0], owner=FEE_PROGRAM_ID
    )
    assert config.stable_fee_tiers[1].market_cap_lamports_threshold == 59 * LAMPORTS_PER_SOL
    assert fees_for_market_cap(config, 60 * LAMPORTS_PER_SOL, stable=True) == Fees(20, 5, 95)
    assert fees_for_market_cap(config, 60 * LAMPORTS_PER_SOL) == Fees(2, 93, 30)


# ----------------------------------------------- the holder-rewards sell, on mainnet


def test_holder_rewards_is_the_creator_fee_reported_twice_not_an_extra_charge() -> None:
    """T4.29c closed T4.8c's open question with a real simulation
    (``t429c_simulation_proof_hr_sell_raw.json``: sell of a full balance on the
    ``is_holder_reward = true`` curve ``Bo5vHuDB…``, 2026-09-16 18:21 UTC, 53 041 CU,
    never signed, never sent).

    The ``TradeEvent`` it emitted has ``holder_rewards_basis_points = 30`` and
    ``holder_rewards = 112 933`` — **identical** to ``creator_fee_basis_points`` /
    ``creator_fee``. So on an HR coin the creator fee is simply routed to holders; it
    is not a second fee. ``quote_sell`` with the tier's 95 + 30 bps reproduces the
    chain's own numbers to the lamport, which is why this package does not add a
    ``holder_rewards`` term.
    """
    record = _fixture("t429c_simulation_proof_hr_sell_raw.json")
    logs = cast("list[str]", cast("dict[str, Any]", record["simulation"])["logs"])
    payload = next(line for line in logs if line.startswith("Program data:")).split(" ", 2)[2]
    event = decode_trade_event(base64.b64decode(payload))
    assert event.is_buy is False
    assert event.holder_rewards_basis_points == event.creator_fee_basis_points == 30
    assert event.holder_rewards == event.creator_fee == 112_933
    assert event.fee_basis_points == 95

    quote = quote_sell(
        CurveReserves(
            virtual_sol=event.virtual_sol_reserves + event.sol_amount,
            virtual_token=event.virtual_token_reserves - event.token_amount,
            real_sol=event.real_sol_reserves + event.sol_amount,
            real_token=event.real_token_reserves - event.token_amount,
        ),
        event.token_amount,
        FeeBps(protocol=event.fee_basis_points, creator=event.creator_fee_basis_points),
        max_slippage_bps=500,
    )
    assert quote.sol_amount == event.sol_amount
    assert (quote.protocol_fee, quote.creator_fee) == (event.fee, event.creator_fee)
    assert quote.net_proceeds == event.sol_amount - event.fee - event.creator_fee


def test_the_simulated_fee_program_return_matches_the_decoded_fee_config() -> None:
    """The same simulation shows ``GetFeesWithQuoteMint`` returning
    ``AAAAAAAAAABfAAAAAAAAAB4AAAAAAAAA`` = lp 0 / protocol 95 / creator 30 — the exact
    tier :func:`fees_for_market_cap` selects from the account read at slot 447 586 137.
    The chain agreeing with our decoder is the point of the whole module."""
    record = _fixture("t429c_simulation_proof_hr_sell_raw.json")
    logs = cast("list[str]", cast("dict[str, Any]", record["simulation"])["logs"])
    returned = next(line for line in logs if line.startswith("Program return: pfeeUxB"))
    lp, protocol, creator = struct.unpack("<QQQ", base64.b64decode(returned.split(" ")[-1]))
    config = decode_fee_config(_account("rpc_fee_config_raw.json")[0], owner=FEE_PROGRAM_ID)
    assert Fees(lp, protocol, creator) == fees_for_market_cap(config, 10**12) == Fees(0, 95, 30)
