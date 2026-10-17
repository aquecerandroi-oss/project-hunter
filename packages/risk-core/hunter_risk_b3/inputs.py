"""Inputs read from the proposal and the broker (docs/RISK_ENGINE_B3.md §8.1).

Every snapshot that can fail to be read carries ``read_ok``. When ``read_ok`` is true the
fields the checks need **must** be present — a model that accepted ``read_ok=True`` with a
missing equity would let an absent number turn into a passing check ("o número que esconde
perda é o zero", §8.3). When ``read_ok`` is false the fields may be absent and the checks
that need them come out ``unavailable``.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pydantic import Field, model_validator

from hunter_risk_b3.base import B3Model, UtcDatetime
from hunter_risk_b3.enums import Side, TradeMode

__all__ = [
    "AccountSnapshot",
    "B3EntryProposal",
    "BrokerOrder",
    "BrokerPosition",
    "BrokerSnapshot",
    "QuoteSnapshot",
    "TerminalState",
]


class B3EntryProposal(B3Model):
    """A persisted entry proposal. ``limit_price`` is **not** here: it is derived (§8.3)."""

    proposal_id: uuid.UUID
    organization_id: uuid.UUID
    instance_id: uuid.UUID
    strategy_key: str = Field(min_length=1)
    strategy_version: int = Field(ge=1)
    params_hash: str = Field(min_length=1)
    session_date: date
    window_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    side: Side
    requested_contracts: int
    """Validated by check 12 (``requested_contracts_invalid``), not by the model."""
    ref_price: Decimal = Field(gt=0)
    stop_price: Decimal | None = Field(default=None, gt=0)
    target_price: Decimal | None = Field(default=None, gt=0)
    exit_at_utc: UtcDatetime | None = None
    signal_published_at: UtcDatetime
    signal_deadline_utc: UtcDatetime
    entry_window_start_utc: UtcDatetime
    entry_window_end_utc: UtcDatetime
    created_at: UtcDatetime


class BrokerPosition(B3Model):
    position_id: int
    position_ticket: int
    symbol: str
    side: Side
    volume: Decimal = Field(gt=0)
    price_open: Decimal
    sl: Decimal = Field(ge=0)
    tp: Decimal = Field(ge=0)
    magic: int
    time_msc: int


class BrokerOrder(B3Model):
    ticket: int
    symbol: str
    type: str
    volume_current: Decimal = Field(ge=0)
    price: Decimal
    magic: int
    comment: str


class TerminalState(B3Model):
    connected: bool
    trade_allowed: bool
    """K2 — "Algo Trading" on the terminal."""
    tradeapi_disabled: bool
    version: str | None
    read_ok: bool


class BrokerSnapshot(B3Model):
    as_of: UtcDatetime
    """The engine's only notion of "now" (§8.1: no clock inside the engine)."""
    positions: tuple[BrokerPosition, ...]
    orders: tuple[BrokerOrder, ...]
    positions_ok: bool
    orders_ok: bool
    terminal: TerminalState


class AccountSnapshot(B3Model):
    account_hash: str | None
    trade_mode: TradeMode | None
    currency: str | None
    margin_mode: str | None
    equity: Decimal | None
    balance: Decimal | None
    margin_free: Decimal | None
    read_ok: bool

    @model_validator(mode="after")
    def _complete_when_read(self) -> AccountSnapshot:
        if self.read_ok:
            missing = [
                name
                for name in ("account_hash", "trade_mode", "currency", "margin_mode", "equity",
                             "balance", "margin_free")
                if getattr(self, name) is None
            ]  # fmt: skip
            if missing:
                raise ValueError(f"account read_ok=True without {missing}")
        return self


class QuoteSnapshot(B3Model):
    bid: Decimal | None
    ask: Decimal | None
    last: Decimal | None
    time_utc: UtcDatetime | None
    """Server stamp converted by the measured clock offset."""
    read_ok: bool

    @model_validator(mode="after")
    def _complete_when_read(self) -> QuoteSnapshot:
        if self.read_ok and (self.bid is None or self.ask is None or self.time_utc is None):
            raise ValueError("quote read_ok=True without bid, ask or time_utc")
        return self
