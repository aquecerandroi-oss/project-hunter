"""The executor's admission step: rows + chain reads → the engine's inputs →
``evaluate_meme_entry`` — pure in the middle, effects on both sides.

What each input is built from, so the provenance is one place:

- the **proposal** from the desk's ``decision`` (``size_sol``, ``target_x``,
  ``trailing_pct``, ``max_hold_s``) and the executor's own fee policy;
- the **curve** from the chain, this second, ``confirmed`` (never a snapshot the
  radar wrote a minute ago — that one is the *fallback mark* for exits, not an
  admission input);
- the **context** from ``meme_tokens`` (age with provenance, denominator,
  migration) and the newest ``meme_features_1m`` row of the mint (organic 1 m
  volume, creator flow, top-10) plus the ``/in-memory-coin`` reads of
  ``meme_risk_snapshots`` (bundled share, dev share). What the radar does not
  measure arrives as ``None`` and refuses by name — today that is
  ``bundled_share`` and, on most mints, the volume and the creator flow (§4's
  declared consequence). The **dev share** is the one input that can undo a
  refusal instead of causing one (T4.28h, :func:`dev_share_input`), and only
  when the owner turned ``creator_unknown_allowed_if_dev_measured`` on;
- the **wallet** from the chain's balance, the open positions' honest marks, the
  pending attempts' reservations and the **persisted** day anchor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from hunter_exchanges.pumpfun.curve import TOKEN_SUBUNITS_PER_TOKEN
from hunter_meme_executor.repo import (
    DEV_SHARE_MAX_AGE_S,
    Candidate,
    OpenPosition,
    PendingAttempt,
    TokenContext,
)
from hunter_risk_meme import (
    CurveState,
    MemeContext,
    MemeDecision,
    MemeEntryProposal,
    MemeKillSwitchInputs,
    MemeLimits,
    MemeWalletState,
    OpenMemePosition,
    PendingMemeIntent,
    evaluate_meme_entry,
)

if TYPE_CHECKING:
    from hunter_meme_executor.chain import CurveRead, TokenAccountRead, WalletRead
    from hunter_meme_executor.kill_switch import DayAnchor

__all__ = ["AdmissionInputs", "admit", "day_start_utc", "proposal_from", "wallet_from"]

SAO_PAULO = ZoneInfo("America/Sao_Paulo")
LAMPORTS = Decimal(1_000_000_000)
_ZERO = Decimal(0)


def day_start_utc(now: datetime) -> datetime:
    local = now.astimezone(SAO_PAULO)
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def _decimal(value: Any, default: Decimal | None = None) -> Decimal | None:
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except ArithmeticError:
        return default


def proposal_from(
    candidate: Candidate,
    *,
    wallet_id: str,
    limits: MemeLimits,
    priority_fee_sol: Decimal,
    requested_cap_sol: Decimal | None = None,
) -> MemeEntryProposal:
    """``requested_cap_sol`` (T4.28) is what the written scope still allows: the
    request is clamped to it so ``max_total_sol`` is never overshot by the last buy."""
    decision = candidate.decision
    requested = _decimal(decision.get("size_sol"), _ZERO) or _ZERO
    if requested_cap_sol is not None:
        requested = min(requested, requested_cap_sol)
    return MemeEntryProposal(
        proposal_id=candidate.id,
        wallet_id=wallet_id,
        mint=candidate.mint,
        requested_sol=requested,
        max_slippage_pct=limits.max_slippage_pct,
        priority_fee_sol=priority_fee_sol,
        mode="live",
        agent_id=candidate.decided_by,
    )


def curve_from(read: CurveRead) -> CurveState:
    a = read.account
    return CurveState(
        mint=read.mint,
        virtual_sol_reserves=a.virtual_sol_reserves,
        virtual_token_reserves=a.virtual_token_reserves,
        real_sol_reserves=a.real_sol_reserves,
        real_token_reserves=a.real_token_reserves,
        total_supply=a.token_total_supply,
        complete=a.complete,
        creator=a.creator,
        is_mayhem_mode=a.is_mayhem_mode,
        slot=read.slot,
        commitment="confirmed",
        observed_at=read.observed_at,
        source="solana_rpc",
    )


def denominator_subunits(tokens: int | Decimal | None) -> int | None:
    """``meme_tokens.initial_real_token_reserves`` → the curve's unit.

    The radar stores the launch denominator in **tokens** (793,1 M on a stock
    curve; 100 654 rows on 16/09/2026, none above 1e12), while the bonding-curve
    account the executor reads by RPC counts **sub-units** (6 decimals,
    ``TOKEN_SUBUNITS_PER_TOKEN``). ``curve_progress_check`` divides one by the
    other, so the conversion happens here, once, on the way into
    :class:`MemeContext`. T4.28e, 16/09/2026 11:46–11:48 BRT: with the raw value
    the first four auto-approved buys of stage 1 were refused
    ``progress_below_window`` with ``progress ≈ −541 546`` — every coin would
    have been. A missing or non-positive value stays ``None`` and refuses by name
    (``progress_denominator_missing``), as before.
    """
    if tokens is None or tokens <= 0:
        return None
    return int((Decimal(tokens) * TOKEN_SUBUNITS_PER_TOKEN).to_integral_value())


def dev_share_input(
    token: TokenContext, now: datetime
) -> tuple[Decimal | None, str | None, datetime | None]:
    """T4.28h — the dev share only reaches the engine dated and inside its window.

    ``None`` on three cases, all fail-closed: no reading, a reading with no
    instant (``0023`` stamps the holders read only when ``holders`` was read), and
    a reading older than :data:`DEV_SHARE_MAX_AGE_S`. A stamp **in the future** is
    two clocks disagreeing, not a fresh reading, and is dropped too — the same
    doctrine ``state_freshness`` applies to the curve (§8.2). What this returns is
    the only thing that may vouch for an unknown creator, so "stale is absent"
    matters here more than anywhere: a ten-minute-old 5 % says nothing about a dev
    who dumped two minutes ago.
    """
    stamp = token.dev_share_observed_at
    if token.dev_share is None or stamp is None:
        return None, None, None
    age = now - stamp
    if age < timedelta(0) or age > timedelta(seconds=DEV_SHARE_MAX_AGE_S):
        return None, None, None
    return token.dev_share, token.dev_share_source, stamp


def context_from(
    mint: str, token: TokenContext, *, participation_used_sol: Decimal, now: datetime
) -> MemeContext:
    volume_fresh = (
        token.features_end_time is not None
        and now - token.features_end_time <= timedelta(seconds=120)
    )
    dev_share, dev_source, dev_at = dev_share_input(token, now)
    return MemeContext(
        mint=mint,
        token_created_at=token.created_at,
        token_age_source=None if token.created_at is None else "meme_tokens.created_at",
        initial_real_token_reserves=denominator_subunits(token.initial_real_token_reserves),
        organic_volume_1m_sol=token.curve_volume_1m_sol if volume_fresh else None,
        volume_ts=token.features_end_time if volume_fresh else None,
        volume_window_complete=True
        if volume_fresh and token.curve_volume_1m_sol is not None
        else None,
        participation_used_sol=participation_used_sol,
        bundled_share_pct=token.bundled_share,
        top10_share_pct=token.top10_share,
        holder_denominator_valid=None if token.top10_share is None else True,
        creator_net_sol=None
        if token.creator_sold is None
        else (Decimal(-1) if token.creator_sold else Decimal(1)),
        dev_share_pct=dev_share,
        dev_share_source=dev_source,
        dev_share_ts=dev_at,
    )


def wallet_from(
    *,
    wallet_id: str,
    now: datetime,
    balance: WalletRead,
    positions: list[OpenPosition],
    pending: list[PendingAttempt],
    anchor: DayAnchor,
    limits: MemeLimits,
    unrecognized: tuple[str, ...] = (),
) -> MemeWalletState:
    return MemeWalletState(
        wallet_id=wallet_id,
        as_of=now,
        sol_balance=Decimal(balance.lamports) / LAMPORTS,
        unrecognized_holdings=unrecognized,
        positions=tuple(
            OpenMemePosition(
                position_id=p.id,
                mint=p.mint,
                sol_spent=Decimal(p.sol_spent_lamports) / LAMPORTS,
                token_amount=max(1, p.tokens),
                mark_sol=p.mark_sol,
                migrated=p.migrated,
            )
            for p in positions
        ),
        pending_intents=tuple(
            PendingMemeIntent(proposal_id=i.proposal_id, mint=i.mint, reserved_sol=i.reserved_sol)
            for i in pending
        ),
        day_start_sol_equity=anchor.day_start_sol_equity,
        peak_sol_equity=max(anchor.peak_sol_equity, anchor.day_start_sol_equity),
        day_start_utc=anchor.day_start_utc,
        marks_complete=all(p.mark_sol is not None for p in positions),
        is_active=True,
        rent_reserved_sol=limits.ata_rent_sol,
    )


@dataclass(frozen=True, slots=True)
class AdmissionInputs:
    proposal: MemeEntryProposal
    wallet: MemeWalletState
    curve: CurveState
    context: MemeContext
    kill_switch: MemeKillSwitchInputs
    creates_ata: bool
    curve_fee_pct: Decimal


def admit(inputs: AdmissionInputs, limits: MemeLimits, *, live_enabled: bool) -> MemeDecision:
    return evaluate_meme_entry(
        inputs.proposal,
        inputs.wallet,
        limits,
        inputs.curve,
        inputs.context,
        inputs.kill_switch,
        live_enabled=live_enabled,
        curve_fee_pct=inputs.curve_fee_pct,
        creates_ata=inputs.creates_ata,
    )


def creates_ata(token_account: TokenAccountRead) -> bool:
    return not token_account.exists
