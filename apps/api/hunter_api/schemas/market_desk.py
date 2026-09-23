"""``GET /api/v1/orgs/{org_id}/markets/{exchange}/{symbol}/desk`` — the
``spot/1`` desk's trail on one market (T4.82, design §7a item 3).

Every money column is a ``DecimalStr``: ``NUMERIC(28,10)`` out of Postgres and
a **string** in JSON, never a float, so the value the screen prints is the
value the wallet moved. Every instant is tz-aware UTC.

The payload carries the permanent **REAL** label, like ``meme_live``'s: these
rows are transactions signed on the owner's Solana wallet. The API neither
signs nor asks for anything here — this route is a read, and the confluence
screen has no POST at all (design §6).

One shape is deliberately *absent*: there is no price level anywhere in
``positions``. The ``spot/1`` desk buys and evaluates its stop against the
**Jupiter quote of our lot in SOL** (``spot_exit_rules.py``), not against the
Binance price the chart draws; a stop triggered by SOL appreciating, plotted on
the Binance axis, would make a correct execution look like a mistake. The
execution is a **mark in time** (design §3, overlay 3) — which is why what
comes back is ``entry_at``/``exit_at``/``pnl_sol``/``r_multiple`` and never an
entry or stop price for the chart's axis.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from hunter_api.schemas.lab_common import DecimalStr

if TYPE_CHECKING:
    from hunter_core.db.models.spot_desk import SpotDeskMarket, SpotOrder, SpotPosition

__all__ = [
    "SPOT1_DESK_LABEL",
    "DeskMarketOut",
    "DeskOrderOut",
    "DeskOut",
    "DeskPositionOut",
]

SPOT1_DESK_LABEL = (
    "REAL — mesa spot/1: transações assinadas na carteira Solana dedicada; a chave vive só no "
    "meme-executor, a API nunca assina"
)


class DeskMarketOut(BaseModel):
    """The executable map row — ``null`` at the caller means the desk does not
    operate this market (design §5, "fora do mapa, ou desligado"), which is an
    answer, not an absence of data."""

    enabled: bool
    tier: str
    kind: str
    mint: str
    round_trip_cost_pct_at_seed: DecimalStr
    """A fraction (``0.00193`` = 0,193 %), as stored."""
    note: str | None

    @classmethod
    def from_row(cls, row: SpotDeskMarket) -> DeskMarketOut:
        return cls(
            enabled=row.enabled,
            tier=row.tier,
            kind=row.kind,
            mint=row.mint,
            round_trip_cost_pct_at_seed=row.round_trip_cost_pct_at_seed,
            note=row.note,
        )


class DeskOrderOut(BaseModel):
    """One attempt of the lane. A ``refused`` row is the point, not noise: the
    design's most valuable line (§4A) is "olhamos e recusamos", and it is built
    from ``status``/``reason`` plus the ``admission`` decomposition."""

    id: uuid.UUID
    signal_id: uuid.UUID
    side: str
    status: str
    reason: str | None
    """Named refusal or failure; ``NULL`` only when the status is neither
    (the table's own CHECK guarantees it)."""
    attempt: int
    admission: dict[str, Any]
    """The checks, the values, the ceiling and ``sizing.binding_constraint``
    as they were at decision time — what the screen hides behind "detalhes"."""
    quote: dict[str, Any] | None
    """The Jupiter quote that produced the transaction — never the fill."""
    tx_signature: str | None
    received_at: datetime
    admitted_at: datetime | None
    settled_at: datetime | None

    @classmethod
    def from_row(cls, row: SpotOrder) -> DeskOrderOut:
        return cls(
            id=row.id,
            signal_id=row.signal_id,
            side=row.side,
            status=row.status,
            reason=row.reason,
            attempt=row.attempt,
            admission=dict(row.admission or {}),
            quote=None if row.quote is None else dict(row.quote),
            tx_signature=row.tx_signature,
            received_at=row.received_at,
            admitted_at=row.admitted_at,
            settled_at=row.settled_at,
        )


class DeskPositionOut(BaseModel):
    """One real position whose life overlaps the requested window."""

    id: uuid.UUID
    signal_id: uuid.UUID
    status: str
    entry_at: datetime
    entry: dict[str, Any]
    params: dict[str, Any]
    """The geometry written at entry: ``ref``, ``stop_frac``, ``target_frac``,
    ``horizon_s``, ``entry_sol_per_atom``, ``r_unit_sol`` and the three
    prices."""
    sol_spent_lamports: int
    """Integer atoms of SOL, not money in the ``Decimal`` sense — a lamport is
    indivisible, so this is an ``int`` and stays one."""
    initial_risk_sol: DecimalStr
    """``r_unit_sol = ticket × stop_frac`` — the signal's R in SOL, not the spend."""
    mark_sol: DecimalStr | None
    mark_at: datetime | None
    """**The latest mark, not a historical one** (Astra's review of T4.82).
    ``spot_positions`` keeps one mark per position, overwritten each pass, so
    ``mark_at`` can be *after* the cursor the screen is asking about. The
    screen must honour ``mark_at`` and say "estado da mesa naquele instante
    não reconstruível" (design §5) rather than print this R as the R at the
    cursor."""

    high_water_sol: DecimalStr | None
    exit_at: datetime | None
    exit: dict[str, Any] | None
    pnl_sol: DecimalStr | None
    r_multiple: DecimalStr | None
    """Both ``null`` while the position is open — never a provisional zero."""

    @classmethod
    def from_row(cls, row: SpotPosition) -> DeskPositionOut:
        return cls(
            id=row.id,
            signal_id=row.signal_id,
            status=row.status,
            entry_at=row.entry_at,
            entry=dict(row.entry or {}),
            params=dict(row.params or {}),
            sol_spent_lamports=row.sol_spent_lamports,
            initial_risk_sol=row.initial_risk_sol,
            mark_sol=row.mark_sol,
            mark_at=row.mark_at,
            high_water_sol=row.high_water_sol,
            exit_at=row.exit_at,
            exit=None if row.exit_ is None else dict(row.exit_),
            pnl_sol=row.pnl_sol,
            r_multiple=row.r_multiple,
        )


class DeskOut(BaseModel):
    label: str = SPOT1_DESK_LABEL
    as_of: datetime
    since: datetime
    until: datetime
    """The window the server actually applied, echoed back: both bounds are
    defaulted when the caller omits them, and a screen that does not know which
    period it received cannot honestly say "nada aconteceu neste período"."""

    desk_market: DeskMarketOut | None

    orders: list[DeskOrderOut]
    """Newest first. Orders are cut on ``received_at`` inside the window."""
    orders_truncated: bool
    """``true`` when the server's row cap bit and older attempts were dropped.
    There is no cursor here by design (a bounded window, the ``meme_live``
    shape), so the remedy is a narrower window — and the screen must not read
    a capped list as "foi só isto que aconteceu"."""

    positions: list[DeskPositionOut]
    """Newest entry first. Positions are selected by **interval
    intersection**, so one opened at 10:00 and still open is here at 11:45.

    Note the window is not the cursor: this list also contains positions that
    opened *after* the instant the screen is asking about. Filtering down to
    "vigente às 11:45" is the client's job (``confluence-window.ts``), and the
    predicate is the same one ``position_intersects_window`` implements."""
    positions_truncated: bool
    """Same contract as ``orders_truncated``, and the reason the flag exists:
    ordered newest-first, the row a cap drops is the *oldest* — which is
    exactly the long-open position block A of §4 wants to show."""
