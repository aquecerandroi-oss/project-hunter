"""``meme_daily_ficha_queries.py`` — the pure aggregation helpers, no database.

Run: ``uv run pytest infra/scripts/tests/test_meme_daily_ficha_queries.py -q``
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from meme_daily_ficha_queries import TICKET_SOL, _paper_arms  # noqa: E402

pytestmark = pytest.mark.unit


def _bet(rule_set: str, status: str, pnl_sol: str | None) -> dict[str, object]:
    return {
        "rule_set": rule_set,
        "status": status,
        "pnl_sol": None if pnl_sol is None else Decimal(pnl_sol),
    }


def test_paper_arm_with_no_closed_bet_shows_no_average_never_a_false_zero() -> None:
    """Astra (T4.92 review): all-open arm dividing 0 by a nonzero denominator
    would print a misleading "0 %" instead of admitting no result is known yet."""
    arms = _paper_arms([_bet("recuo_v1/1", "open", None), _bet("recuo_v1/1", "open", None)])
    assert len(arms) == 1
    assert arms[0].entries == 2
    assert arms[0].avg_pct_per_ticket is None


def test_paper_arm_average_normalizes_every_pnl_to_the_fixed_ticket() -> None:
    """Matches the diary's own "média/entrada" convention (verified against
    recuo_v1/1, absorb_v0 and refused_probe_v0/1 on the real VPS data,
    T4.92): total pnl over every entry (open or closed), divided by the fixed
    mesa-real ticket -- not each rule set's own bet size."""
    arms = _paper_arms(
        [_bet("x/1", "closed", "0.02"), _bet("x/1", "closed", "-0.01"), _bet("x/1", "open", None)]
    )
    arm = arms[0]
    assert arm.entries == 3 and arm.wins == 1
    assert arm.pnl_sol == Decimal("0.01")
    expected = (Decimal("0.01") / 3) / TICKET_SOL * 100
    assert arm.avg_pct_per_ticket == expected
