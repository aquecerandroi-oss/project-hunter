"""The execution boundary: what an adapter is handed, and what it hands back.

``docs/ARCHITECTURE.md`` §6 names ``ExecutionAdapter`` "the only place with
execution effects". T3.4 splits that sentence in two, because the M3 joint
decision (``docs/plans/M3.md``, items 3 and 4) puts the *balance* somewhere else:

- the **adapter computes** — a pure function of an order, a book, a trade, the
  market's filters, the fee schedule and an instant handed in: no clock, no
  Redis, no Postgres, no balance;
- the **ledger applies** — **T3.5** turns an :class:`ExecutionReport` into cash,
  quantity and fees, in the transaction that also moves the intention and the
  participation ledger, under the wallet's lock. Two writers of one balance is
  the failure that split exists to prevent. T3.3 built the wallet state this
  report will feed; **nothing applies a report yet**, and saying otherwise (as
  this docstring did until the review of 2026-09-07, item 4) sends the next
  reader looking for an applier that does not exist.

Three invariants are enforced **in the constructor** of :class:`ExecutionReport`,
so a violation cannot be written down at all:

1. **no fabricated fill** — a filled quantity must be backed by the book levels
   it ate, and those levels must sum to exactly that quantity. A candle, a last
   price or an average never produces a fill (``docs/RISK_ENGINE.md`` §10);
2. **an entry is terminal** — whatever is unfilled is cancelled for good, never
   parcelled out silently;
3. **a protection attempt is not** — it never cancels the remainder, because the
   durable intention survives it (:mod:`hunter_core.execution.intents`).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

from pydantic import Field, model_validator

from hunter_core.domain.enums import ExecutionMode, OrderSide
from hunter_risk.base import RiskModel

if TYPE_CHECKING:  # pragma: no cover - imported for signatures only
    from collections.abc import Sequence

    from hunter_core.domain.market import NormalizedOrderBook, NormalizedTrade
    from hunter_core.execution.entries import MarketEntryOrder
    from hunter_core.execution.intents import ExitAttempt
    from hunter_core.execution.triggers import ProtectedPosition, TriggerEvaluation

__all__ = [
    "EntryWithoutApproval",
    "ExecutionAdapter",
    "ExecutionJournal",
    "ExecutionModel",
    "ExecutionReport",
    "FeeCharge",
    "FeeSchedule",
    "LevelFill",
    "LiveTradingDisabled",
    "MarketOrderVerdict",
    "Residual",
    "SpotFilters",
]


class LiveTradingDisabled(RuntimeError):
    """Raised by :class:`~hunter_core.execution.live.LiveExecutionAdapter`, always."""


class EntryWithoutApproval(RuntimeError):
    """An entry order was built from something other than an approved decision."""


class ExecutionModel(RiskModel):
    """Frozen, closed and float-free — the Risk Engine's own value-object base.

    Reused rather than re-declared: an execution report is money, and
    ``Decimal("0.1") != Decimal(0.1)`` is the same trap here as there.
    """


class LevelFill(ExecutionModel):
    """One book level actually consumed. The evidence behind a filled quantity."""

    price: Decimal = Field(gt=0)
    qty: Decimal = Field(gt=0)


class FeeCharge(ExecutionModel):
    """The taker fee, in the asset it is really charged in.

    Binance spot charges the fee on the asset *received*: base on a buy, quote on
    a sell. ``quote_equivalent`` exists so a base-asset fee can be shown in USDT
    and is **informational only** — booking it as well would charge the trade
    twice (Astra, T3.4 protocol review, point 4).
    """

    asset: Literal["base", "quote"]
    qty: Decimal = Field(ge=0)
    rate: Decimal = Field(ge=0)
    source: str = ""
    quote_equivalent: Decimal | None = None


class Residual(ExecutionModel):
    """Quantity left that the exchange will not let us sell — visible, not settled."""

    qty: Decimal = Field(ge=0)
    reason: str
    """``below_min_qty`` or ``below_min_notional``: which floor blocks it."""
    value_quote: Decimal | None = None
    """``None`` **with** a valuation source saying why, never a zero."""
    valuation_price: Decimal | None = None
    valuation_source: str = ""


ReportStatus = Literal["filled", "partially_filled", "rejected", "pending_degraded", "recorded"]
"""``pending_degraded``: nothing usable to fill against, so no fill and an alert.
``recorded``: shadow saw the attempt and, by construction, filled nothing."""


class ExecutionReport(ExecutionModel):
    """Everything one attempt produced, including the attempts that produced nothing."""

    kind: Literal["entry", "exit"]
    status: ReportStatus
    mode: ExecutionMode
    execution_key: str = Field(min_length=1)
    """Idempotency of the *execution* (``fills.execution_key``): ``entry:{proposal_id}``
    or ``exit:{attempt_id}``. A redelivered event finds this key already written."""
    client_order_id: str = Field(min_length=1)
    attempt_id: uuid.UUID | None = None
    proposal_id: uuid.UUID | None = None
    intent_id: uuid.UUID | None = None
    position_id: uuid.UUID | None = None
    side: OrderSide

    requested_qty: Decimal = Field(ge=0)
    submitted_qty: Decimal | None = None
    """What the caller asked for, **before** the market's filters rounded it —
    the quantity a replay of this key has to match (see
    :func:`hunter_core.execution.idempotency.guard_replay`). ``requested_qty``
    is post-filter and cannot serve: a step-size round-down would read as a
    different order."""
    decision_fingerprint: str = ""
    """The identity of the ``RiskDecision`` that authorised an entry. Same key,
    different decision means the proposal was re-decided, not redelivered."""
    filled_qty: Decimal = Field(default=Decimal(0), ge=0)
    unfilled_qty: Decimal = Field(default=Decimal(0), ge=0)
    levels: tuple[LevelFill, ...] = ()
    gross_quote: Decimal = Field(default=Decimal(0), ge=0)
    vwap: Decimal | None = None
    vwap_before_adjustment: Decimal | None = None
    model_adjustment_bps: Decimal = Decimal(0)
    """The declared extra slippage, published apart from what the book itself did."""

    fee: FeeCharge | None = None
    net_base_delta: Decimal = Decimal(0)
    net_quote_delta: Decimal = Decimal(0)
    """The two deltas the ledger applies. A base-asset fee is already inside
    ``net_base_delta`` and is **not** repeated in ``net_quote_delta``."""

    remaining_cancelled: bool = False
    depth_exhausted: bool = False
    residual: Residual | None = None

    book_sequence: int | None = None
    book_received_at: datetime | None = None
    decision_at: datetime | None = None
    eligible_at: datetime | None = None
    executed_at: datetime | None = None
    latency_ms: int = 0

    marking_policy_version: str = ""
    book_policy_version: str = ""
    execution_policy_version: str = ""

    planned_price: Decimal | None = None
    slippage_vs_plan_quote: Decimal | None = None
    slippage_vs_plan_bps: Decimal | None = None
    """Positive is **adverse**. Published, never corrected: a gap that fills below
    the planned stop is the real result (directive, "sem fabricar proteção perfeita")."""

    trigger_trade_id: str | None = None
    """The trade that **fired** the protection, when one did."""
    trigger_trade_price: Decimal | None = None
    triggered_at: datetime | None = None
    trigger_received_at: datetime | None = None
    trigger_evaluated_at: datetime | None = None
    """Event time, receipt and evaluation of the firing trade: a late receipt and
    an instant trigger are different facts about how fast we could act."""
    observed_trade_id: str | None = None
    """The trade seen at attempt time. Never conflated with the one above: a
    protection that retries minutes later observes a different tape."""
    degraded: bool = False
    alert: bool = False
    reason: str = ""
    filter_reference_price: Decimal | None = None
    filter_reference_source: str = ""
    """The price the ``NOTIONAL`` filter was actually judged against, and where it
    came from (the exchange average, or a spot trade that passed the validity
    rules). Computed here and nowhere else, so a replay can tell a verdict made
    with a live reference from one made with none."""

    @model_validator(mode="after")
    def _cannot_fabricate(self) -> ExecutionReport:
        walked = sum((level.qty for level in self.levels), Decimal(0))
        if self.filled_qty != walked:
            raise ValueError(
                "a filled quantity must equal the book levels consumed "
                f"({self.filled_qty} vs {walked}): no fill is ever fabricated"
            )
        if self.filled_qty > 0 and self.status in ("rejected", "pending_degraded", "recorded"):
            raise ValueError(f"status {self.status!r} cannot carry a fill")
        if self.status == "pending_degraded" and not (self.degraded and self.alert):
            raise ValueError("a degraded exit is marked degraded and raises an alert")
        if (
            self.kind == "entry"
            and self.status in ("filled", "partially_filled", "rejected")
            and self.unfilled_qty > 0
            and not self.remaining_cancelled
        ):
            raise ValueError("an entry is one attempt: the remainder is cancelled for good")
        if self.kind == "exit" and self.remaining_cancelled:
            raise ValueError(
                "a protection attempt never cancels the remainder: the intention survives it"
            )
        return self

    @property
    def filled(self) -> bool:
        return self.filled_qty > 0


@runtime_checkable
class MarketOrderVerdict(Protocol):
    """Structural twin of ``binance_spot.filters.MarketOrderCheck``."""

    @property
    def ok(self) -> bool: ...
    @property
    def qty(self) -> Decimal: ...
    @property
    def notional(self) -> Decimal | None: ...
    @property
    def reason(self) -> str | None: ...


@runtime_checkable
class SpotFilters(Protocol):
    """The market's MARKET-order rules, structurally.

    ``hunter_core`` may not import ``hunter_exchanges`` (the distribution
    dependency runs the other way, and inverting it would make the domain
    package depend on an exchange client). So the adapter is typed against the
    *shape* of ``SpotMarketFilters``; that the real class satisfies it is a test.
    """

    @property
    def effective_min_qty(self) -> Decimal: ...
    @property
    def effective_step_size(self) -> Decimal: ...
    def round_qty_down(self, qty: Decimal) -> Decimal: ...
    # ``PERCENT_PRICE_BY_SIDE``: on Binance it bounds a **limit** price and never
    # rejects a MARKET order, so here it is our own sanity band for a simulated
    # fill that walked the book (T3.0a §5), applied in ``execution.pricing``.
    def price_band(self, side: OrderSide, *, avg_price: Decimal) -> tuple[Decimal, Decimal]: ...

    def check_market_order(
        self,
        qty: Decimal,
        *,
        avg_price: Decimal | None = None,
        last_price: Decimal | None = None,
    ) -> MarketOrderVerdict: ...


@runtime_checkable
class FeeSchedule(Protocol):
    """Structural twin of ``binance_spot.fees.SpotFeeSchedule``."""

    @property
    def taker_rate(self) -> Decimal: ...
    @property
    def source(self) -> str: ...


class ExecutionJournal(Protocol):
    """Where an already-executed attempt is looked up by its execution key.

    The adapter is pure, so "idempotent" means: the same key returns the report
    that was recorded, and the book is never walked a second time. In production
    this is ``fills.execution_key`` (``docs/DATABASE.md`` §18.3); in tests it is
    a dictionary.
    """

    def get(self, execution_key: str) -> ExecutionReport | None: ...
    def record(self, report: ExecutionReport) -> None: ...


class ExecutionAdapter(Protocol):
    """The three things every mode answers, and the only three.

    The keyword arguments are part of the contract, not an implementation
    detail: ``already_consumed`` and ``previous_book_sequence`` are how a caller
    stops one snapshot from being spent twice, and ``last_accepted_trade_id`` is
    the trigger watermark that stops one crossing being reported twice.
    """

    mode: ExecutionMode

    def submit_market_entry(
        self,
        order: MarketEntryOrder,
        book: NormalizedOrderBook | None,
        last_trade: NormalizedTrade | None,
        filters: SpotFilters,
        fees: FeeSchedule,
        now: datetime,
        *,
        avg_price: Decimal | None = None,
        already_consumed: Sequence[LevelFill] = (),
        previous_book_sequence: int | None = None,
    ) -> ExecutionReport: ...

    def submit_protection_exit(
        self,
        attempt: ExitAttempt,
        position_qty: Decimal,
        book: NormalizedOrderBook | None,
        last_trade: NormalizedTrade | None,
        filters: SpotFilters,
        fees: FeeSchedule,
        now: datetime,
        *,
        avg_price: Decimal | None = None,
        already_consumed: Sequence[LevelFill] = (),
        previous_book_sequence: int | None = None,
    ) -> ExecutionReport: ...

    def check_triggers(
        self,
        position: ProtectedPosition,
        trades: Sequence[NormalizedTrade],
        now: datetime,
        *,
        tape_gap: bool = False,
        last_accepted_trade_id: int | None = None,
    ) -> TriggerEvaluation: ...
