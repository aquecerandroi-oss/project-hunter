"""Shadow records and never fills; live refuses, always.

The live case is the one the directive names by hand — "Manter
ENABLE_LIVE_TRADING=false" (§6) — so the test asks the question the way an
attacker would: is there *any* call, with any flag, that reaches a real venue?
"""

from __future__ import annotations

import ast
import inspect
import uuid
from decimal import Decimal

import pytest

from hunter_core.domain.enums import ExecutionMode, ExitReason
from hunter_core.execution.adapter import LiveTradingDisabled
from hunter_core.execution.entries import MarketEntryOrder
from hunter_core.execution.intents import ExitAttempt, ExitIntent
from hunter_core.execution.live import LiveExecutionAdapter
from hunter_core.execution.shadow import ShadowExecutionAdapter
from hunter_core.execution.triggers import ProtectedPosition
from hunter_core.settings import Settings, get_settings

from .conftest import DEEP_BOOK, NOW, StubFees, StubFilters, approved_decision, seconds, trade


def _order() -> MarketEntryOrder:
    return MarketEntryOrder(
        decision=approved_decision(
            proposal_id=uuid.UUID(int=5),
            qty=str(Decimal("3")),
            entry_ref=str(Decimal("100")),
            stop=str(Decimal("95")),
        ),
        qty=Decimal("3"),
        decision_at=NOW - seconds(0.5),
    )


def _attempt() -> ExitAttempt:
    intent = ExitIntent(
        intent_id=uuid.UUID(int=21),
        portfolio_id=uuid.UUID(int=6),
        position_id=uuid.UUID(int=8),
        protection_key="stop",
        reason=ExitReason.STOP,
        intended_qty=Decimal("10"),
        trigger_price=Decimal("95"),
    )
    return ExitAttempt.for_intent(intent, qty=Decimal("10"), decision_at=NOW - seconds(0.5))


def test_shadow_records_the_entry_and_fills_nothing(filters: StubFilters, fees: StubFees) -> None:
    """PIPELINE.md §8.6: identical to paper in everything except the balance."""
    adapter = ShadowExecutionAdapter()
    report = adapter.submit_market_entry(
        _order(), DEEP_BOOK, trade("100"), filters, fees, NOW, avg_price=Decimal("100")
    )
    assert report.status == "recorded"
    assert report.mode is ExecutionMode.SHADOW
    assert report.filled_qty == 0
    assert report.levels == ()
    assert (report.net_base_delta, report.net_quote_delta) == (0, 0)
    assert adapter.submissions == (report,)


def test_shadow_records_a_protection_attempt_without_selling_anything(
    filters: StubFilters, fees: StubFees
) -> None:
    adapter = ShadowExecutionAdapter()
    report = adapter.submit_protection_exit(
        _attempt(), Decimal("10"), DEEP_BOOK, trade("95"), filters, fees, NOW
    )
    assert (report.status, report.filled_qty, report.remaining_cancelled) == ("recorded", 0, False)
    assert len(adapter.submissions) == 1


def test_shadow_still_evaluates_triggers_because_that_is_not_an_effect() -> None:
    position = ProtectedPosition(
        position_id=uuid.UUID(int=8), qty=Decimal("10"), stop_price=Decimal("95")
    )
    assert ShadowExecutionAdapter().check_triggers(position, [trade("94")], NOW).kind == "stop"


def test_the_live_adapter_cannot_even_be_built_while_the_flag_is_false() -> None:
    get_settings.cache_clear()
    with pytest.raises(LiveTradingDisabled, match="ENABLE_LIVE_TRADING"):
        LiveExecutionAdapter()


def test_every_live_method_refuses_even_with_the_flag_flipped_on(
    filters: StubFilters, fees: StubFees
) -> None:
    """No implementation exists, and the flag does not create one.

    A future operator who sets ``ENABLE_LIVE_TRADING=true`` gets an exception,
    not an order: live trading is Phase 4 and this class is an interface with a
    refusal in it.
    """
    adapter = LiveExecutionAdapter(settings=Settings(enable_live_trading=True))
    assert adapter.mode is ExecutionMode.LIVE
    with pytest.raises(LiveTradingDisabled):
        adapter.submit_market_entry(_order(), DEEP_BOOK, trade("100"), filters, fees, NOW)
    with pytest.raises(LiveTradingDisabled):
        adapter.submit_protection_exit(
            _attempt(), Decimal("10"), DEEP_BOOK, trade("95"), filters, fees, NOW
        )
    with pytest.raises(LiveTradingDisabled):
        adapter.check_triggers(
            ProtectedPosition(
                position_id=uuid.UUID(int=8), qty=Decimal("10"), stop_price=Decimal("95")
            ),
            [trade("94")],
            NOW,
        )


def test_the_live_module_imports_nothing_that_could_reach_a_venue() -> None:
    """The proof that there is no path to real money is the absence of one.

    Read from the import graph, not from prose: every module ``live.py`` pulls in
    is a local value object or the settings. No HTTP client, no exchange
    package, no credential store — so "not implemented" is a fact about the
    code, not a promise in a docstring.
    """
    import hunter_core.execution.live as live_module

    tree = ast.parse(inspect.getsource(live_module))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= {"__future__", "collections", "decimal", "typing", "hunter_core"}
    assert not any(
        name.startswith(("http", "requests", "aiohttp", "websocket")) for name in imported
    )
