"""TEST FIXTURES ONLY — a synthetic B3 scenario in which all 25 checks pass.

Nothing here is market data: the numbers are chosen so the arithmetic is easy to follow
(WIN ≈ 207 000 points, tick 5, R$ 1,00 per tick, H-038-like window [C−30, C−25] on
2026-10-20 with the pre-03/11 grid 10:00–17:00 BRT). Each table case mutates one input of
this scenario with :func:`dataclasses.replace` / ``model_copy`` and states which check
must move and with which ``reason``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from hunter_core.domain.enums import KillSwitchState
from hunter_risk_b3 import (
    AccountSnapshot,
    ArmedStrategy,
    AuditPath,
    AuthorityPhase,
    AuthorityView,
    B3EntryProposal,
    BrokerSnapshot,
    CalendarB3,
    ClockCheck,
    CurrentContract,
    DayPnl,
    FeeSchedule,
    KillSwitchB3,
    LastReconcile,
    MarginInputs,
    OrderCheckResult,
    QuoteSnapshot,
    RiskDecision,
    RiskLimitsB3,
    RobotOpsState,
    SessionContext,
    Side,
    SpecInputs,
    SpecNow,
    SpecPin,
    SpecStatus,
    TerminalState,
    TradeMode,
    evaluate,
    initial_limits,
)

NOW = datetime(2026, 10, 20, 19, 31, tzinfo=UTC)  # 16:31 BRT, inside [C−30, C−25]
INSTANCE = uuid.UUID("01900000-0000-7000-8000-000000000001")
ORG = uuid.UUID("01900000-0000-7000-8000-0000000000aa")
PROPOSAL = uuid.UUID("01900000-0000-7000-8000-0000000000b1")
ACCOUNT_HASH = "a" * 64
MAGIC = 7001


def s(seconds: float) -> timedelta:
    return timedelta(seconds=seconds)


def limits(**update: Any) -> RiskLimitsB3:
    base = initial_limits("test-v1").model_copy(
        update={"flatten_at_local": time(16, 50), "rico_flatten_local": time(17, 10)}
    )
    return base.model_copy(update=update)


def proposal(**update: Any) -> B3EntryProposal:
    base = B3EntryProposal(
        proposal_id=PROPOSAL,
        organization_id=ORG,
        instance_id=INSTANCE,
        strategy_key="h038_intraday_momentum",
        strategy_version=1,
        params_hash="p" * 64,
        session_date=date(2026, 10, 20),
        window_id="C-30",
        symbol="WINZ26",
        side=Side.BUY,
        requested_contracts=1,
        ref_price=Decimal("207005"),
        stop_price=Decimal("205975"),
        target_price=None,
        exit_at_utc=datetime(2026, 10, 20, 20, 0, tzinfo=UTC),
        signal_published_at=datetime(2026, 10, 20, 14, 29, tzinfo=UTC),
        signal_deadline_utc=datetime(2026, 10, 20, 14, 30, tzinfo=UTC),
        entry_window_start_utc=datetime(2026, 10, 20, 19, 30, tzinfo=UTC),
        entry_window_end_utc=datetime(2026, 10, 20, 19, 35, tzinfo=UTC),
        created_at=NOW - s(2),
    )
    return base.model_copy(update=update)


def broker(**update: Any) -> BrokerSnapshot:
    base = BrokerSnapshot(
        as_of=NOW,
        positions=(),
        orders=(),
        positions_ok=True,
        orders_ok=True,
        terminal=TerminalState(
            connected=True,
            trade_allowed=True,
            tradeapi_disabled=False,
            version="5.0.5000",
            read_ok=True,
        ),
    )
    return base.model_copy(update=update)


def account(**update: Any) -> AccountSnapshot:
    base = AccountSnapshot(
        account_hash=ACCOUNT_HASH,
        trade_mode=TradeMode.DEMO,
        currency="BRL",
        margin_mode="RETAIL_NETTING",
        equity=Decimal("10000"),
        balance=Decimal("10000"),
        margin_free=Decimal("10000"),
        read_ok=True,
    )
    return base.model_copy(update=update)


def session(**update: Any) -> SessionContext:
    base = SessionContext(
        session_date=date(2026, 10, 20),
        open_utc=datetime(2026, 10, 20, 13, 0, tzinfo=UTC),
        close_utc=datetime(2026, 10, 20, 20, 0, tzinfo=UTC),
        flatten_at_utc=datetime(2026, 10, 20, 19, 50, tzinfo=UTC),
        rico_flatten_utc=datetime(2026, 10, 20, 20, 10, tzinfo=UTC),
        session_end_utc=datetime(2026, 10, 20, 21, 30, tzinfo=UTC),
        entry_cutoff_utc=None,
        grid_version="grid-2026-10-13",
        clock=ClockCheck(offset_ms=100, measured_at=NOW - s(60), ok=True),
    )
    return base.model_copy(update=update)


def calendar(**update: Any) -> CalendarB3:
    base = CalendarB3(
        is_holiday=False,
        is_shortened=False,
        has_grid=True,
        current_contract=CurrentContract(
            symbol="WINZ26", root="WIN", expiry_date=date(2026, 12, 16)
        ),
        is_expiry_day=False,
        read_ok=True,
    )
    return base.model_copy(update=update)


def quote(**update: Any) -> QuoteSnapshot:
    base = QuoteSnapshot(
        bid=Decimal("207000"),
        ask=Decimal("207005"),
        last=Decimal("207005"),
        time_utc=NOW - s(1),
        read_ok=True,
    )
    return base.model_copy(update=update)


def kill(**update: Any) -> KillSwitchB3:
    base = KillSwitchB3(
        system=KillSwitchState.ACTIVE,
        organization=KillSwitchState.ACTIVE,
        robot=KillSwitchState.ACTIVE,
        authority=AuthorityView(
            phase=AuthorityPhase.ENTRIES,
            instance_id=INSTANCE,
            authority_expires_at=datetime(2026, 10, 20, 21, 30, tzinfo=UTC),
        ),
        registered_account_hash=ACCOUNT_HASH,
        k1_present=False,
        armed_strategy=ArmedStrategy(key="h038_intraday_momentum", version=1, params_hash="p" * 64),
    )
    return base.model_copy(update=update)


SPEC_FIELDS: dict[str, Any] = {
    "trade_tick_size": Decimal("5"),
    "trade_tick_value": Decimal("1"),
    "point": Decimal("1"),
    "digits": 0,
    "volume_min": Decimal("1"),
    "volume_step": Decimal("1"),
    "volume_max": Decimal("100"),
    "trade_mode": "SYMBOL_TRADE_MODE_FULL",
    "filling_mode": "SYMBOL_FILLING_RETURN",
    "expiration_mode": "SYMBOL_EXPIRATION_DAY",
    "account_margin_mode": "RETAIL_NETTING",
    "terminal_version": "5.0.5000",
    "package_version": "5.0.5",
    "order_lifecycle_proven": True,
    "comment_preserved": True,
    "stale_ticket_rejection_proven": True,
}


def spec(pin: dict[str, Any] | None = None, now: dict[str, Any] | None = None) -> SpecInputs:
    pin_fields: dict[str, Any] = {"spec_pin_id": "pin-1", **SPEC_FIELDS, **(pin or {})}
    now_fields: dict[str, Any] = {**SPEC_FIELDS, "status": SpecStatus.OK, **(now or {})}
    return SpecInputs(
        pin=SpecPin.model_validate(pin_fields), now=SpecNow.model_validate(now_fields)
    )


def margin(**update: Any) -> MarginInputs:
    base = MarginInputs(
        per_volume={v: Decimal("100") * v for v in range(1, 6)},
        order_check={v: OrderCheckResult(ok=True) for v in range(1, 6)},
        read_ok=True,
    )
    return base.model_copy(update=update)


def day(**update: Any) -> DayPnl:
    base = DayPnl(
        anchor_equity=Decimal("10000"),
        anchor_at=datetime(2026, 10, 20, 12, 55, tzinfo=UTC),
        cash_flows_brl=Decimal("0"),
        history_complete=True,
        realized_gross_brl=Decimal("0"),
        costs_positive_brl=Decimal("0"),
        open_mtm_gross_brl=Decimal("0"),
        open_exit_fee_brl=Decimal("0"),
        mark_time=NOW - s(1),
        equity_delta_brl=Decimal("0"),
    )
    return base.model_copy(update=update)


def ops(**update: Any) -> RobotOpsState:
    base = RobotOpsState(
        entries_today=0,
        open_entry_intents=0,
        unknown_intents=0,
        orphan_sltp_unknown=frozenset(),
        entry_rejects=(),
        breaker_latched=False,
        last_reconcile=LastReconcile(at=NOW - s(3), clean=True, consistent_passes=2),
        audit=AuditPath(api_last_ok_at=NOW - s(2), buffer_len=0, buffer_writable=True),
        day=day(),
        fee_schedule=FeeSchedule(
            per_leg_brl=Decimal("0.256"), source="B3 RLP (test fixture)", valid=True
        ),
        robot_magics=frozenset({MAGIC}),
    )
    return base.model_copy(update=update)


@dataclass(frozen=True)
class Scenario:
    proposal: B3EntryProposal
    broker: BrokerSnapshot
    account: AccountSnapshot
    limits: RiskLimitsB3
    session: SessionContext
    calendar: CalendarB3
    quote: QuoteSnapshot
    kill_switch: KillSwitchB3
    spec: SpecInputs
    margin: MarginInputs
    ops: RobotOpsState

    def with_(self, **update: Any) -> Scenario:
        return replace(self, **update)

    def evaluate(self) -> RiskDecision:
        return evaluate(
            self.proposal,
            self.broker,
            self.account,
            self.limits,
            self.session,
            self.calendar,
            self.quote,
            self.kill_switch,
            spec=self.spec,
            margin=self.margin,
            ops=self.ops,
        )


def scenario() -> Scenario:
    return Scenario(
        proposal=proposal(),
        broker=broker(),
        account=account(),
        limits=limits(),
        session=session(),
        calendar=calendar(),
        quote=quote(),
        kill_switch=kill(),
        spec=spec(),
        margin=margin(),
        ops=ops(),
    )
