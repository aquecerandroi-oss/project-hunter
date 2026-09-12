"""Builders for the meme engine's table tests: one healthy scenario, overridable per field.

The healthy case is a fresh coin two minutes old, 20 % up the curve, with a
creator who has not sold, a measurable holder picture, a complete 1 m organic
volume window and a wallet holding nothing — the case every check passes on,
so that each test changes exactly one input and names the refusal it expects.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from hunter_risk_meme import (
    MEME_PAPER_V0,
    CurveState,
    MemeContext,
    MemeDecision,
    MemeEntryProposal,
    MemeKillSwitchInputs,
    MemeLimits,
    MemeWalletState,
    evaluate_meme_entry,
)

MINT = "5ejAEbzxiZuwUNgZcoryoAY8gA5oCAVJZx5AyDnApump"
CREATOR = "AsRQHoHxfBYqvxJZxK9RtJUnRZcCwUoh9KNpVxH6Jhnd"
AS_OF = datetime(2026, 9, 12, 15, 30, tzinfo=UTC)  # 12:30 BRT
DAY_START = datetime(2026, 9, 12, 3, 0, tzinfo=UTC)  # 00:00 BRT
FEE_PCT = Decimal("0.0125")
INITIAL_REAL = 793_100_000_000_000
LAMPORTS = 1_000_000_000


def proposal(**over: Any) -> MemeEntryProposal:
    base: dict[str, Any] = {
        "proposal_id": "p1",
        "wallet_id": "w1",
        "mint": MINT,
        "requested_sol": Decimal("0.05"),
        "max_slippage_pct": Decimal("0.01"),
        "priority_fee_sol": Decimal("0.0001"),
        "mode": "paper",
    }
    base.update(over)
    return MemeEntryProposal(**base)


def wallet(**over: Any) -> MemeWalletState:
    base: dict[str, Any] = {
        "wallet_id": "w1",
        "as_of": AS_OF,
        "sol_balance": Decimal("1.0"),
        "day_start_sol_equity": Decimal("1.0"),
        "peak_sol_equity": Decimal("1.0"),
        "day_start_utc": DAY_START,
    }
    base.update(over)
    return MemeWalletState(**base)


def curve(**over: Any) -> CurveState:
    # 20 % of the real reserve sold: 30 SOL virtual + ~6.4 SOL real.
    base: dict[str, Any] = {
        "mint": MINT,
        "virtual_sol_reserves": 36_400_000_000,
        "virtual_token_reserves": 900_000_000_000_000,
        "real_sol_reserves": 6_400_000_000,
        "real_token_reserves": INITIAL_REAL * 8 // 10,
        "total_supply": 1_000_000_000_000_000,
        "complete": False,
        "creator": CREATOR,
        "is_mayhem_mode": False,
        "slot": 446_378_553,
        "commitment": "confirmed",
        "observed_at": AS_OF - timedelta(seconds=2),
        "source": "solana_rpc",
    }
    base.update(over)
    return CurveState(**base)


def context(**over: Any) -> MemeContext:
    base: dict[str, Any] = {
        "mint": MINT,
        "token_created_at": AS_OF - timedelta(seconds=120),
        "token_age_source": "meme_tokens.created_at",
        "initial_real_token_reserves": INITIAL_REAL,
        "organic_volume_1m_sol": Decimal("20"),
        "volume_ts": AS_OF - timedelta(seconds=30),
        "volume_window_complete": True,
        "bundled_share_pct": Decimal("0.05"),
        "top10_share_pct": Decimal("0.15"),
        "holder_denominator_valid": True,
        "creator_net_sol": Decimal("1.5"),
    }
    base.update(over)
    return MemeContext(**base)


def limits(**over: Any) -> MemeLimits:
    return MEME_PAPER_V0.model_validate({**MEME_PAPER_V0.model_dump(), **over})


def decide(
    *,
    p: MemeEntryProposal | None = None,
    w: MemeWalletState | None = None,
    lim: MemeLimits | None = None,
    c: CurveState | None = None,
    ctx: MemeContext | None = None,
    ks: MemeKillSwitchInputs | None = None,
    live_enabled: bool = False,
    creates_ata: bool = True,
) -> MemeDecision:
    return evaluate_meme_entry(
        p or proposal(),
        w or wallet(),
        lim or limits(),
        c or curve(),
        ctx or context(),
        ks or MemeKillSwitchInputs(),
        live_enabled=live_enabled,
        curve_fee_pct=FEE_PCT,
        creates_ata=creates_ata,
    )
