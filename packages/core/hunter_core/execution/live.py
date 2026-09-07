"""``LiveExecutionAdapter``: the interface that exists so that nothing else has to lie.

``docs/RISK_ENGINE.md`` §8 and the directive §6 both end in the same sentence:
``ENABLE_LIVE_TRADING=false``, and the live adapter raises
:class:`~hunter_core.execution.adapter.LiveTradingDisabled`. This module is that
sentence, and nothing more.

Two refusals, on purpose:

- **construction** fails while the flag is false, so a worker that wires the
  wrong mode dies at start-up rather than at the first order;
- **every method** fails even when the flag is true, because there is no
  implementation to reach. Real money is Phase 4; a flag does not conjure the
  code, and an adapter that "would work if enabled" is exactly the object that
  gets enabled by accident.

There is deliberately no HTTP client, no credential, no venue name and no URL in
this file — that absence is asserted by a test.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any, Never

from hunter_core.domain.enums import ExecutionMode
from hunter_core.execution.adapter import LiveTradingDisabled
from hunter_core.settings import Settings, get_settings

__all__ = ["LiveExecutionAdapter"]

_UNAVAILABLE = "live execution is not implemented: real money is Phase 4"


class LiveExecutionAdapter:
    """Present as an interface; refuses as a matter of contract."""

    mode = ExecutionMode.LIVE

    def __init__(self, *, settings: Settings | None = None) -> None:
        resolved = settings or get_settings()
        if not resolved.enable_live_trading:
            raise LiveTradingDisabled(
                "ENABLE_LIVE_TRADING is false: no live adapter may exist in this process"
            )

    def submit_market_entry(self, *_args: Any, **_kwargs: Any) -> Never:
        raise LiveTradingDisabled(_UNAVAILABLE)

    def submit_protection_exit(self, *_args: Any, **_kwargs: Any) -> Never:
        raise LiveTradingDisabled(_UNAVAILABLE)

    def check_triggers(self, *_args: Sequence[object] | object, **_kwargs: object) -> Never:
        raise LiveTradingDisabled(_UNAVAILABLE)

    def cancel(self, _order_id: object) -> Never:
        raise LiveTradingDisabled(_UNAVAILABLE)

    def mark_to_market(self, _positions: object, _prices: Decimal | object) -> Never:
        raise LiveTradingDisabled(_UNAVAILABLE)
