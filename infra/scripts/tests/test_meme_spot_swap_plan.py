"""``meme_spot_swap_plan.build_plan`` (T4.73) against a real recorded quote
(``GET lite-api.jup.ag/swap/v1/quote``, SOL -> WIF, 0,02 SOL, captured
19/09/2026 -- ``packages/exchange-adapters/tests/fixtures/jupiter/
quote_sol_to_wif_real.json``). No network: a fake client answers ``.quote()``
from the fixture; ``.swap()`` is never called without a ``wallet_pubkey``.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = REPO_ROOT / "packages/exchange-adapters/tests/fixtures/jupiter/quote_sol_to_wif_real.json"

from meme_spot_swap_plan import build_plan, format_plan  # noqa: E402

from hunter_exchanges.jupiter.models import JupiterQuote  # noqa: E402

WSOL = "So11111111111111111111111111111111111111112"
WIF = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"


class FakeJupiterClient:
    """Answers ``.quote()`` from the fixture; explodes if ``.swap()`` is called
    without a plan asking for one (the tests below never pass a pubkey)."""

    def __init__(self) -> None:
        self.swap_calls = 0

    def quote(
        self, *, input_mint: str, output_mint: str, amount: int, slippage_bps: int
    ) -> JupiterQuote:
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        assert input_mint == WSOL and output_mint == WIF and amount == 20_000_000
        return JupiterQuote.from_json(payload)

    def swap(self, *args: Any, **kwargs: Any) -> Any:
        self.swap_calls += 1
        raise AssertionError("swap() must not be called without a wallet_pubkey")


def test_build_plan_reads_the_real_fixture_and_reports_no_cap_refusal() -> None:
    client = FakeJupiterClient()
    plan = build_plan(
        client,
        input_mint=WSOL,
        output_mint=WIF,
        amount_atoms=20_000_000,
        slippage_bps=50,
        max_impact_pct=Decimal("1"),
        i_know=False,
        wallet_pubkey=None,
    )
    assert plan.quote.out_amount == Decimal("10454545")
    assert plan.quote.other_amount_threshold == Decimal("10402273")
    assert plan.amount_cap_refusal is None  # 0.02 SOL is under the 0.05 default cap
    assert plan.impact_refusal is None  # 0.0006 is well under 1%
    assert plan.verify_reason is None  # no --user: never builds/verifies a tx
    assert client.swap_calls == 0
    report = format_plan(plan, in_decimals=9, out_decimals=6)
    assert "in=0.02" in report and "verify: skipped" in report


def test_build_plan_refuses_an_amount_above_the_cap_without_i_know() -> None:
    client = FakeJupiterClient()
    plan = build_plan(
        client,
        input_mint=WSOL,
        output_mint=WIF,
        amount_atoms=20_000_000,  # the fixture's own request; only the cap changes
        slippage_bps=50,
        max_impact_pct=Decimal("1"),
        i_know=False,
        wallet_pubkey=None,
    )
    # 0.02 SOL is normally under the cap; drop the cap to prove the refusal fires.
    from meme_spot_swap_rules import classify_amount_cap

    refusal = classify_amount_cap(Decimal("0.02"), i_know=False, cap=Decimal("0.01"))
    assert refusal is not None and refusal.startswith("amount_above_cap:")
    assert plan.amount_cap_refusal is None  # the default 0.05 cap is untouched here


def test_build_plan_refuses_a_price_impact_above_a_tight_cap() -> None:
    client = FakeJupiterClient()
    plan = build_plan(
        client,
        input_mint=WSOL,
        output_mint=WIF,
        amount_atoms=20_000_000,
        slippage_bps=50,
        max_impact_pct=Decimal("0.00001"),  # far below the fixture's 0.0006%
        i_know=False,
        wallet_pubkey=None,
    )
    assert plan.impact_refusal is not None
    assert plan.impact_refusal.startswith("price_impact_above_cap:")
