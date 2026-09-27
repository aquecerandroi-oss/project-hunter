"""T4.98 (EXP-M26 L1) — guard: the real-money exit does not read the support
line. ``operator/5`` and ``operator/6`` carry ``exit_on_line_break: true`` in
``meme_rule_sets.params``, but the executor's exit is ``hunter_risk_meme
.decide_exit`` over ``exit_params`` (target, trailing, time) plus the observed
exits; ``line_broken`` exists only in the paper Lab (``lines_exit.py``). On the
VPS, 0 of 161 live positions ever closed ``line_broken`` (26/09/2026).

This pins that fact: whoever adds the line to the live exit must bring the
paper side's causal, fresh-support contract (``support_at``) with it — this
test fails first and says where to look.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_meme_executor.exit_common import exit_params
from hunter_risk_meme import EXIT_REASONS, PositionForExit, decide_exit, limits_from_env

pytestmark = pytest.mark.unit

LIMITS = limits_from_env(
    {
        "MEME_WALLET_MAX_SOL": "0.5",
        "MEME_MAX_SOL_PER_TRADE": "0.07",
        "MEME_DAILY_LOSS_CAP_SOL": "0.1",
        "MEME_MAX_OPEN_POSITIONS": "2",
        "MEME_COOLDOWN_S": "3600",
    }
)
OPERATOR_6_EXIT = {
    "target_x": "1.15",
    "trailing_pct": "10",
    "max_hold_s": 300,
    "exit_on_line_break": True,
    "line_break_snapshots": 2,
    "line_support_max_age_s": 120,
}
ENTRY = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


def test_the_live_exit_has_no_line_broken_reason() -> None:
    assert "line_broken" not in EXIT_REASONS


def test_the_line_keys_do_not_change_the_live_exit_params() -> None:
    without = {k: v for k, v in OPERATOR_6_EXIT.items() if "line" not in k}
    assert exit_params(OPERATOR_6_EXIT, LIMITS) == exit_params(without, LIMITS)


def test_a_price_far_below_any_line_sells_only_by_the_live_rules() -> None:
    position = PositionForExit(
        position_id="p1",
        mint="5ejAEbzxiZuwUNgZcoryoAY8gA5oCAVJZx5AyDnApump",
        entry_at=ENTRY,
        sol_spent=Decimal("0.07"),
        token_amount=1_000_000,
        peak_mark_sol=Decimal("0.07"),
    )
    params = exit_params(OPERATOR_6_EXIT, LIMITS)
    held = ENTRY + timedelta(seconds=60)
    assert decide_exit(position, Decimal("0.0665"), held, params) is None, "-5 %: no live rule"
    assert decide_exit(position, Decimal("0.0620"), held, params) == "trailing"
