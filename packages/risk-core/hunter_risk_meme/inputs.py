"""Inputs of the meme engine — pure, stamped, no clock of their own (§2).

Every value here is handed to :func:`hunter_risk_meme.evaluate.evaluate_meme_entry`
by the process that read it; the engine measures every age against
``wallet.as_of`` and never calls a clock. Money is ``Decimal`` SOL; reserves are
the chain's integers (lamports / token subunits), because the curve's arithmetic
is integer arithmetic (``hunter_exchanges.pumpfun.quote``) and a rounded reserve
is a wrong quote. A missing input is ``None`` **with** its reason elsewhere, and
``None`` makes the check that needs it ``unavailable`` — never a zero.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, model_validator

from hunter_core.domain.enums import KillSwitchState
from hunter_risk_meme.base import MemeModel

__all__ = [
    "PUMP_PROGRAM",
    "PUMPSWAP_PROGRAM",
    "CurveState",
    "MemeContext",
    "MemeEntryProposal",
    "MemeExitProposal",
    "MemeKillSwitchInputs",
    "MemeWalletState",
    "OpenMemePosition",
    "PendingMemeIntent",
]

PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PUMPSWAP_PROGRAM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
_ZERO = Decimal(0)
_SAO_PAULO = ZoneInfo("America/Sao_Paulo")


class MemeEntryProposal(MemeModel):
    """One intention to buy on the curve. ``requested_sol`` is a ceiling, never a target."""

    proposal_id: str = Field(min_length=1)
    wallet_id: str = Field(min_length=1)
    mint: str = Field(min_length=32)
    program: str = PUMP_PROGRAM
    quote: str = "SOL"
    action: Literal["buy"] = "buy"
    requested_sol: Decimal = Field(gt=0)
    max_slippage_pct: Decimal = Field(ge=0)
    priority_fee_sol: Decimal = Field(ge=0)
    jito_tip_sol: Decimal = Field(ge=0, default=_ZERO)
    signal_valid: bool = True
    agent_enabled: bool = True
    mode: Literal["paper", "live"] = "paper"
    agent_id: str | None = None


class MemeExitProposal(MemeModel):
    proposal_id: str = Field(min_length=1)
    wallet_id: str = Field(min_length=1)
    position_id: str = Field(min_length=1)
    mint: str = Field(min_length=32)
    token_amount: int = Field(gt=0)
    reason: str = Field(min_length=1)


class CurveState(MemeModel):
    """The bonding curve as read from the chain, with slot and commitment (§8.2)."""

    mint: str = Field(min_length=32)
    virtual_sol_reserves: int = Field(ge=0)
    virtual_token_reserves: int = Field(ge=0)
    real_sol_reserves: int = Field(ge=0)
    real_token_reserves: int = Field(ge=0)
    total_supply: int = Field(ge=0)
    complete: bool
    creator: str = Field(min_length=32)
    is_mayhem_mode: bool
    slot: int = Field(ge=0)
    commitment: Literal["processed", "confirmed", "finalized"]
    observed_at: datetime | None
    source: str = Field(min_length=1)


class MemeContext(MemeModel):
    """Everything about the coin that is not the curve itself — one stamp per field."""

    mint: str = Field(min_length=32)
    token_created_at: datetime | None = None
    token_age_source: str | None = None
    initial_real_token_reserves: int | None = None
    organic_volume_1m_sol: Decimal | None = None
    volume_ts: datetime | None = None
    volume_window_complete: bool | None = None
    participation_used_sol: Decimal = Field(ge=0, default=_ZERO)
    """SOL this wallet already spent on this mint in the moving 60 s window."""
    unique_buyers_1m: int | None = None
    bundled_share_pct: Decimal | None = None
    top10_share_pct: Decimal | None = None
    holder_denominator_valid: bool | None = None
    creator_net_sol: Decimal | None = None
    """Creator's net SOL flow since creation; negative = net seller. ``None`` = unknown."""
    mayhem_agent_state_known: bool = False
    mayhem_policy_approved: bool = False
    rug_signals: tuple[str, ...] = ()
    mint_rugged: bool = False
    rug_cooldown_until: datetime | None = None
    program_allowlist: tuple[str, ...] = (PUMP_PROGRAM, PUMPSWAP_PROGRAM)


class OpenMemePosition(MemeModel):
    position_id: str = Field(min_length=1)
    mint: str = Field(min_length=32)
    sol_spent: Decimal = Field(gt=0)
    token_amount: int = Field(gt=0)
    mark_sol: Decimal | None = None
    """What a full sell would net now, fees included (§6); ``None`` = unmarked."""
    migrated: bool = False


class PendingMemeIntent(MemeModel):
    proposal_id: str = Field(min_length=1)
    mint: str = Field(min_length=32)
    reserved_sol: Decimal = Field(gt=0)


class MemeWalletState(MemeModel):
    """The wallet at ``as_of``. Every aggregate is derived here, never received ready."""

    wallet_id: str = Field(min_length=1)
    as_of: datetime
    sol_balance: Decimal = Field(ge=0)
    unrecognized_holdings: tuple[str, ...] = ()
    positions: tuple[OpenMemePosition, ...] = ()
    pending_intents: tuple[PendingMemeIntent, ...] = ()
    day_start_sol_equity: Decimal = Field(ge=0)
    peak_sol_equity: Decimal = Field(ge=0)
    day_start_utc: datetime
    marks_complete: bool = True
    is_active: bool = True
    rent_reserved_sol: Decimal = Field(ge=0, default=_ZERO)

    @model_validator(mode="after")
    def _anchored_to_the_sao_paulo_day(self) -> MemeWalletState:
        if self.as_of.tzinfo is None or self.day_start_utc.tzinfo is None:
            raise ValueError("as_of and day_start_utc must be timezone-aware")
        local = self.as_of.astimezone(_SAO_PAULO)
        midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
        if self.day_start_utc != midnight:
            raise ValueError(
                "day_start_utc is not the America/Sao_Paulo midnight of as_of "
                f"({midnight.isoformat()})"
            )
        if self.peak_sol_equity < self.day_start_sol_equity:
            raise ValueError("peak_sol_equity cannot be below day_start_sol_equity")
        return self

    def age_s(self, stamp: datetime) -> Decimal:
        """Seconds between ``stamp`` and ``as_of`` (negative = stamp in the future)."""
        return Decimal((self.as_of - stamp) / timedelta(seconds=1))

    @property
    def equity_sol(self) -> Decimal:
        """Cash plus the **honest** mark of every position; an unmarked position counts
        as worth nothing (the doctrine's plausible outcome of a curve position, §5)."""
        return self.sol_balance + sum((p.mark_sol or _ZERO for p in self.positions), _ZERO)

    @property
    def reserved_sol(self) -> Decimal:
        return sum((i.reserved_sol for i in self.pending_intents), _ZERO)

    @property
    def available_sol(self) -> Decimal:
        return max(_ZERO, self.sol_balance - self.reserved_sol - self.rent_reserved_sol)

    @property
    def exposure_total_sol(self) -> Decimal:
        """SOL at risk: what open positions cost plus what pending intents reserve."""
        return sum((p.sol_spent for p in self.positions), _ZERO) + self.reserved_sol

    def exposure_for_mint(self, mint: str) -> Decimal:
        return sum((p.sol_spent for p in self.positions if p.mint == mint), _ZERO) + sum(
            (i.reserved_sol for i in self.pending_intents if i.mint == mint), _ZERO
        )

    @property
    def slots_used(self) -> int:
        return len(self.positions) + len(self.pending_intents)

    @property
    def daily_loss_sol(self) -> Decimal:
        return max(_ZERO, self.day_start_sol_equity - self.equity_sol)

    @property
    def drawdown_pct(self) -> Decimal:
        if self.peak_sol_equity == 0:
            return _ZERO
        return max(_ZERO, 1 - self.equity_sol / self.peak_sol_equity)


class MemeKillSwitchInputs(MemeModel):
    """The persisted scopes (§7) plus the durable daily latch the caller stores."""

    system: KillSwitchState = KillSwitchState.ACTIVE
    organization: KillSwitchState = KillSwitchState.ACTIVE
    wallet: KillSwitchState = KillSwitchState.ACTIVE
    daily_loss_latched: bool = False
