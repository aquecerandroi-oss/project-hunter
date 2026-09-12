"""Synthetic bets and inputs shared by the daily-close unit tests — labelled
fixtures, never production data (CLAUDE.md: mocks live only in tests)."""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from meme_close_lessons import ClosedBet, day_lessons, leave_top_out  # noqa: E402
from meme_close_render import CloseInputs, Coverage, ExpAllTime, OperatorDay  # noqa: E402

DAY = date(2026, 9, 12)
NOON_UTC = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)  # 09:00 BRT


def synthetic_bet(i: int, **overrides: Any) -> ClosedBet:
    base: dict[str, Any] = {
        "mint": f"M{i}",
        "rule_set": "meme_paper_v0/1",
        "exp_ref": "EXP-M1",
        "kind": "research_only",
        "entry_at": NOON_UTC + timedelta(hours=i % 6, minutes=i),
        "exit_at": NOON_UTC + timedelta(hours=i % 6, minutes=i + 5),
        "exit_reason": "target" if i % 2 == 0 else "max_loss",
        "r_multiple": Decimal("0.3") if i % 2 == 0 else Decimal("-0.5"),
        "pnl_sol": Decimal("0.015") if i % 2 == 0 else Decimal("-0.025"),
        "initial_risk_sol": Decimal("0.05"),
        "age_at_entry_s": 100 + i,
        "progress_pct": Decimal(5 + i),
        "snipers": i % 3,
        "top10_share": Decimal("0.2"),
        "dev_share": Decimal("0.05"),
        "same_slot": i < 12,
        "creator_prior_1h": 0,
        "symbol_dup_24h": 0,
    }
    base.update(overrides)
    return ClosedBet(**base)


def synthetic_bets(n: int) -> list[ClosedBet]:
    """The first 12 (same slot) died at −1 R; the rest alternate +0.3/−0.5."""
    return [
        synthetic_bet(i, r_multiple=Decimal("-1"), exit_reason="dead")
        if i < 12
        else synthetic_bet(i)
        for i in range(n)
    ]


def close_inputs(bets: list[ClosedBet], **overrides: Any) -> CloseInputs:
    base: dict[str, Any] = {
        "day": DAY,
        "generated_at": datetime(2026, 9, 13, 3, 10, tzinfo=UTC),
        "bets": bets,
        "lessons": day_lessons(bets),
        "top_out": leave_top_out(bets),
        "coverage": Coverage(
            rows=1200,
            with_progress=900,
            with_tape=600,
            with_line=300,
            with_hype=300,
            mints=80,
            minutes=1400,
            ticks=1380,
            first_tick=datetime(2026, 9, 12, 3, 0, tzinfo=UTC),
            last_tick=datetime(2026, 9, 13, 2, 59, tzinfo=UTC),
            gaps=2,
            rows_evaluated=1150,
            refusals={
                "meme_paper_v0": {"creator_net_seller_unknown": 700, "age_out_of_window": 400}
            },
        ),
        "operator": OperatorDay(
            proposed=5,
            approved=2,
            rejected=1,
            expired=2,
            filled=2,
            unfilled=0,
            manual=1,
            latency_s=(40, 75, 130),
            r_approved=(Decimal("0.2"), Decimal("-0.5")),
        ),
        "reals": (),
        "all_time": [
            ExpAllTime(
                rule_set="meme_paper_v0/1",
                exp_ref="EXP-M1",
                kind="research_only",
                n=len(bets),
                days=1,
                mean=Decimal("-0.3"),
                ci95=None,
                total=Decimal("-10"),
                target_share=Decimal("35"),
                dead_or_time_share=Decimal("30"),
                best_r=Decimal("0.3"),
                without_best=Decimal("-10.3"),
                today_n=len(bets),
                today_total=Decimal("-10"),
                today_reasons={"dead": 12, "target": 14, "max_loss": 14},
            )
        ],
        "predictions": {"EXP-M1": "P3 — … **Veredito previsto: `descartar`.**"},
    }
    base.update(overrides)
    return CloseInputs(**base)
