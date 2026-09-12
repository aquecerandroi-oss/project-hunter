"""Value objects of the Lab loop's bet side: a snapshot, a quote, a wallet state
and the shape a closed bet is written in.

Split from :mod:`hunter_meme_worker.lab_models` in T4.10 for the 350-line
budget (that module re-exports every name here, so callers did not move).
Everything monetary is ``Decimal``, every timestamp is timezone-aware UTC, and
no dataclass here reads a clock, opens a session or knows a table name — the
repo (``lab_repo*.py``) builds them from rows and the engine
(``paper_engine.py``/``paper_fill.py``) moves between them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from hunter_indicators.meme.curve import CurveReserves

__all__ = [
    "LEGS",
    "BetExit",
    "Snapshot",
    "SolUsd",
    "WalletState",
    "money_str",
    "optional_money_str",
]

LEGS: tuple[str, ...] = ("probe", "scale", "single")
"""``meme_paper_bets.leg`` (``0026``, T4.10): the brief's "semi-comprado (sonda)"
(``probe``), "escalado (perna 2)" (``scale``, which names its ``parent_bet_id``)
and the one-leg bet every other rule set opens (``single``)."""


def money_str(value: Decimal) -> str:
    """A ``Decimal`` as plain digits — never ``0E-10`` or ``5E+1`` and never the
    28-digit tail of the arithmetic context: ``format(v, "f")`` writes every
    digit, trailing zeros after the point are dropped (the ``decimal_plain``
    rule of the API schemas, applied at write time so a row reads as it was
    meant)."""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def optional_money_str(value: Decimal | None) -> str | None:
    return None if value is None else money_str(value)


@dataclass(frozen=True, slots=True)
class Snapshot:
    """One ``meme_curve_snapshots`` row as the engine prices against it."""

    mint: str
    observed_at: datetime
    source: str
    reserves: CurveReserves
    real_sol_reserves: Decimal
    total_supply: Decimal
    complete: bool
    mcap_sol: Decimal | None = None

    def as_json(self) -> dict[str, Any]:
        return {
            "observed_at": self.observed_at.isoformat(),
            "source": self.source,
            "virtual_sol_reserves": money_str(self.reserves.virtual_sol_reserves),
            "virtual_token_reserves": money_str(self.reserves.virtual_token_reserves),
            "real_sol_reserves": money_str(self.real_sol_reserves),
            "real_token_reserves": optional_money_str(self.reserves.real_token_reserves),
            "complete": self.complete,
            "mcap_sol": optional_money_str(self.mcap_sol),
        }


@dataclass(frozen=True, slots=True)
class SolUsd:
    """An observed SOL/USD quote — source and instants travel with the number."""

    price_usd: Decimal
    source: str
    as_of: datetime
    observed_at: datetime
    stale: bool

    def as_json(self) -> dict[str, Any]:
        return {
            "price_usd": money_str(self.price_usd),
            "source": self.source,
            "as_of": self.as_of.isoformat(),
            "observed_at": self.observed_at.isoformat(),
            "stale": self.stale,
        }


@dataclass(frozen=True, slots=True)
class WalletState:
    """The paper wallet of one rule set, derived from ``meme_paper_bets`` alone."""

    balance_sol: Decimal
    """``wallet_max_sol + Σ closed pnl − Σ open sol_spent``: a restart is not a reset."""
    open_positions: int
    """Open bets that occupy a slot of ``max_open_positions``: every leg but
    ``scale`` — a second leg rides on its probe's slot, because the brief's
    ceiling ("máximo 5 sondas abertas") is a ceiling on probes."""
    realized_today_sol: Decimal
    """Closed PnL of the Brasília day — what ``daily_loss_cap_sol`` measures."""
    exposure_by_mint: Mapping[str, Decimal] = field(default_factory=dict[str, Decimal])


@dataclass(frozen=True, slots=True)
class BetExit:
    """Everything a sale (or a rug without a snapshot) writes when closing."""

    exit_at: datetime
    exit: dict[str, Any]
    pnl_sol: Decimal
    r_multiple: Decimal
    sol_usd_at_exit: Decimal | None
