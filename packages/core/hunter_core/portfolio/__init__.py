"""The paper wallet's ledger — opening, attribution, state and equity curve.

DATABASE.md §18 and the M3 joint decision (``docs/plans/M3.md``). The public
surface is deliberately small, and deliberately **has no way to add money**:
:func:`open_paper_wallet` is the only function in this package that credits
cash, it runs once per wallet, and the schema's partial unique index plus the
anchor's immutability trigger make a second one unrepresentable. There is no
deposit and no reset (directive §1) — ``tests/unit/portfolio/
test_no_funding_route.py`` asserts that against the source itself.
"""

from hunter_core.portfolio.attribution import (
    OPENING_ROUNDING_POLICY,
    BrlAttribution,
    OpeningConversion,
    attribute_brl,
    convert_opening,
)
from hunter_core.portfolio.ledger import (
    EquityPoint,
    MarkedPosition,
    mark_positions,
    market_identity,
    record_equity_point,
    to_open_positions,
    to_pending_entries,
)
from hunter_core.portfolio.opening import (
    DEFAULT_CAPITAL_BRL,
    PAPER_FX_POLICY,
    FxObservationRejected,
    FxPolicy,
    OpeningResult,
    WalletAlreadyOpen,
    open_paper_wallet,
    validate_fx_observation,
)
from hunter_core.portfolio.state import (
    PortfolioStateBuild,
    WalletNotOpen,
    build_portfolio_state,
)

__all__ = [
    "DEFAULT_CAPITAL_BRL",
    "OPENING_ROUNDING_POLICY",
    "PAPER_FX_POLICY",
    "BrlAttribution",
    "EquityPoint",
    "FxObservationRejected",
    "FxPolicy",
    "MarkedPosition",
    "OpeningConversion",
    "OpeningResult",
    "PortfolioStateBuild",
    "WalletAlreadyOpen",
    "WalletNotOpen",
    "attribute_brl",
    "build_portfolio_state",
    "convert_opening",
    "mark_positions",
    "market_identity",
    "open_paper_wallet",
    "record_equity_point",
    "to_open_positions",
    "to_pending_entries",
    "validate_fx_observation",
]
