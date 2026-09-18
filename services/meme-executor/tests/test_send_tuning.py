"""T4.55 — the send knobs from the environment, and the exit slippage reaching the
sell's ``min_sol_output``: 5 % for a normal exit, 15 % for ``creator_dump`` /
``rug_signal``, and the buy's 1 % untouched."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from hunter_exchanges.pumpfun.decode import BondingCurveAccount
from hunter_exchanges.pumpfun.global_state import decode_global_account
from hunter_exchanges.pumpfun.quote import SellQuote
from hunter_meme_executor.build import build_sell, decode_fills
from hunter_meme_executor.chain import CurveRead
from hunter_meme_executor.send_tuning import (
    ENV_EXIT_MAX_SLIPPAGE_PCT,
    ENV_PANIC_EXIT_MAX_SLIPPAGE_PCT,
    ENV_PRIORITY_FEE_FLOOR,
    ENV_PRIORITY_FEE_MAX_SOL,
    ENV_RESEND_INTERVAL_S,
    PANIC_EXIT_REASONS,
    SendTuning,
)
from hunter_risk_meme import MEME_PAPER_V0

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[3] / "packages/exchange-adapters/tests/fixtures/pumpfun"
USER = "AsRQHoHxfBYqvxJZxK9RtJUnRZcCwUoh9KNpVxH6Jhnd"
TOKEN_2022 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
BLOCKHASH = "BQ8v5pyUzayNkgPghSBd36pVgG14SGLExT5kwWkmYZWJ"


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _global_account() -> Any:
    g = _fixture("rpc_global_account_raw.json")["result"]["value"]
    return decode_global_account(g["data"][0], owner=g["owner"])


def _curve_read() -> CurveRead:
    """The same curve ``test_build_and_fills`` rebuilds from the recorded buy."""
    (fill,) = decode_fills(_fixture("rpc_tx_buy_raw.json")["result"])
    e = fill.event
    account = BondingCurveAccount(
        virtual_token_reserves=e.virtual_token_reserves + e.token_amount,
        virtual_sol_reserves=e.virtual_sol_reserves - e.sol_amount,
        real_token_reserves=e.real_token_reserves + e.token_amount,
        real_sol_reserves=1,
        token_total_supply=1_000_000_000_000_000,
        complete=False,
        creator=e.creator,
        is_mayhem_mode=False,
        is_cashback_coin=True,
        quote_mint="11111111111111111111111111111111",
    )
    return CurveRead(e.mint, account, TOKEN_2022, 446_378_553, datetime(2026, 9, 12, tzinfo=UTC))


def test_defaults_are_the_briefs() -> None:
    tuning = SendTuning.from_env({})
    assert tuning.priority_fee_floor_micro_lamports == 100_000
    assert tuning.priority_fee_max_sol == Decimal("0.002")
    assert tuning.exit_max_slippage_pct == Decimal(5)
    assert tuning.panic_exit_max_slippage_pct == Decimal(15)
    assert tuning.resend_interval_s == 2.0


def test_the_environment_is_read_and_nonsense_falls_back() -> None:
    tuning = SendTuning.from_env(
        {
            ENV_PRIORITY_FEE_FLOOR: "250000",
            ENV_PRIORITY_FEE_MAX_SOL: "0.001",
            ENV_EXIT_MAX_SLIPPAGE_PCT: "8",
            ENV_PANIC_EXIT_MAX_SLIPPAGE_PCT: "20",
            ENV_RESEND_INTERVAL_S: "1.5",
        }
    )
    assert tuning.priority_fee_floor_micro_lamports == 250_000
    assert tuning.priority_fee_max_sol == Decimal("0.001")
    assert tuning.exit_max_slippage_pct == Decimal(8)
    assert tuning.panic_exit_max_slippage_pct == Decimal(20)
    assert tuning.resend_interval_s == 1.5
    nonsense = SendTuning.from_env(
        {
            ENV_PRIORITY_FEE_FLOOR: "-1",
            ENV_PRIORITY_FEE_MAX_SOL: "zero",
            ENV_EXIT_MAX_SLIPPAGE_PCT: "75",  # above the quote's 50 % ceiling
            ENV_PANIC_EXIT_MAX_SLIPPAGE_PCT: "0",
            ENV_RESEND_INTERVAL_S: "-2",
        }
    )
    assert nonsense == SendTuning()


def test_exit_slippage_by_reason() -> None:
    tuning = SendTuning()
    assert PANIC_EXIT_REASONS == {"creator_dump", "rug_signal"}
    assert tuning.exit_slippage_bps("creator_dump") == 1_500
    assert tuning.exit_slippage_bps("rug_signal") == 1_500
    for reason in ("target", "trailing", "time_stop", "sell_now", "emergency_auto_close"):
        assert tuning.exit_slippage_bps(reason) == 500, reason
    # the buy's tolerance is the profile's and did not move
    assert int(MEME_PAPER_V0.max_slippage_pct * 10_000) == 100


def _sell(max_slippage_bps: int) -> SellQuote:
    built = build_sell(
        _curve_read(),
        _global_account(),
        user=USER,
        token_amount=1_000_000_000,
        max_slippage_bps=max_slippage_bps,
        blockhash=BLOCKHASH,
        last_valid_block_height=150,
        compute_unit_limit=400_000,
        compute_unit_price_micro_lamports=100_000,
    )
    assert isinstance(built.quote, SellQuote)
    assert built.intent.sol_limit == built.quote.min_sol_output
    assert built.verify(built.message) is not None
    return built.quote


def test_build_sell_min_out_at_5_and_15_per_cent() -> None:
    tuning = SendTuning()
    normal = _sell(tuning.exit_slippage_bps("time_stop"))
    panic = _sell(tuning.exit_slippage_bps("creator_dump"))
    one = _sell(100)
    assert normal.net_proceeds == panic.net_proceeds == one.net_proceeds
    net = normal.net_proceeds
    assert normal.min_sol_output == net * 9_500 // 10_000
    assert panic.min_sol_output == net * 8_500 // 10_000
    assert one.min_sol_output == net * 9_900 // 10_000
    assert panic.min_sol_output < normal.min_sol_output < one.min_sol_output
    # the PS case (R56 §2): a 14 % drop between quote and check is inside 15 %, not 1 % or 5 %
    dropped = net * 86 // 100
    assert dropped < one.min_sol_output and dropped < normal.min_sol_output
    assert dropped >= panic.min_sol_output
