"""T3.86 — one stamp governs both volumes, and the table says what each case does.

``RISK_ENGINE.md`` §3.1 ("Idade do volume") gives the 24 h figure and the
minute reference a **single** ``volume_ts``. That is a claim about provenance,
not only about arithmetic: it is only true while the producer reads both
numbers from the same observation. The producer that broke it
(``hunter_execution_worker.bridge_inputs``, T3.86) took the 24 h figure from a
ticker snapshot of another instant and the stamp from the candles, so the
engine applied ``max_volume_age_s`` to one number and believed the other.

The engine's own behaviour under that stamp is what this table pins: the
passing case, the failing case, and the two ways the input can be unknown —
each with the cascade it is supposed to cause. Every row is a pure call; the
instant is ``portfolio.as_of`` and nothing here reads a clock.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_risk.decision import CheckState, RiskDecision
from hunter_risk.evaluate import evaluate
from hunter_risk.kill_switch import KillSwitchInputs
from hunter_risk.limits import PAPER_V1
from hunter_risk.observations import stale_volume_reason

from .factories import NOW, beta, liquidity, portfolio, proposal, spec

pytestmark = pytest.mark.unit

FLOOR = PAPER_V1.min_liquidity_usd_24h
MAX_AGE = PAPER_V1.max_volume_age_s


def decide(**over: Any) -> RiskDecision:
    kwargs: dict[str, Any] = {
        "proposal": proposal(),
        "portfolio": portfolio(),
        "limits": PAPER_V1,
        "liquidity": liquidity(),
        "kill_switch": KillSwitchInputs(),
        "beta": beta(),
        "spec": spec(),
    }
    return evaluate(**(kwargs | over))


def state_of(decision: RiskDecision, name: str) -> CheckState:
    return next(check.state for check in decision.checks if check.name == name)


@pytest.mark.parametrize(
    ("case", "over", "expected"),
    [
        ("no piso, no prazo", {}, CheckState.PASSED),
        (
            "exatamente no piso passa",
            {"quote_volume_24h": FLOOR},
            CheckState.PASSED,
        ),
        (
            "um centavo abaixo do piso reprova",
            {"quote_volume_24h": FLOOR - Decimal("0.01")},
            CheckState.FAILED,
        ),
        (
            "sem numero de 24 h nao vira zero",
            {"quote_volume_24h": None},
            CheckState.UNAVAILABLE,
        ),
        (
            "carimbo vencido invalida o numero, por maior que ele seja",
            {"volume_ts": NOW - timedelta(seconds=MAX_AGE + 1)},
            CheckState.UNAVAILABLE,
        ),
        (
            "no limite da idade ainda vale",
            {"volume_ts": NOW - timedelta(seconds=MAX_AGE)},
            CheckState.PASSED,
        ),
        ("sem carimbo nao ha insumo", {"volume_ts": None}, CheckState.UNAVAILABLE),
        (
            "carimbo no futuro e relogio quebrado, nao frescor",
            {"volume_ts": NOW + timedelta(seconds=1)},
            CheckState.UNAVAILABLE,
        ),
    ],
)
def test_check_9_by_table(case: str, over: dict[str, Any], expected: CheckState) -> None:
    got = decide(liquidity=liquidity(**over))
    assert state_of(got, "liquidity_24h") is expected, case
    assert got.approved is (expected is CheckState.PASSED), case


def test_one_stale_stamp_takes_both_volumes_and_the_sizing_with_it() -> None:
    """The single stamp is only honest if it invalidates **both** numbers.

    A 24 h figure whose stamp is old cannot keep sizing alive through the
    minute reference, and vice versa: §3.1 says the cascade goes to
    ``participation``, ``sizing``, ``slippage_estimate``, ``cash`` and
    ``exposure_after``, by the declared reason.
    """
    got = decide(liquidity=liquidity(volume_ts=NOW - timedelta(minutes=45)))
    assert state_of(got, "liquidity_24h") is CheckState.UNAVAILABLE
    assert state_of(got, "participation") is CheckState.UNAVAILABLE
    assert got.sizing is None
    assert got.approved is False


def test_the_reason_names_the_age_so_the_producer_can_be_found() -> None:
    """``stale_volume_reason`` is the message the worker's log quotes.

    It has to carry the measured age and the limit, because "the volume is
    stale" sends an operator nowhere: 600 s against 120 s says the feed
    stopped ten minutes ago.
    """
    stale = liquidity(volume_ts=NOW - timedelta(seconds=600))
    reason = stale_volume_reason(portfolio(), PAPER_V1, stale)
    assert reason is not None
    assert "600" in reason
    assert str(MAX_AGE) in reason
    assert stale_volume_reason(portfolio(), PAPER_V1, liquidity()) is None
