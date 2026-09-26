"""T4.67b — the inputs of the launch profile (``hunter_risk_meme.profile``),
built from what exists one second after a ``create``: the proposal's own
create stamp, a ``processed`` curve read, the wallet's balance, the rows that
are cheap (open positions, pending attempts, the 60 s participation window)
and — when the radar already wrote it — the ``meme_tokens`` row.

Pure in the middle (:func:`launch_context`, :func:`launch_position_params`,
:func:`launch_proposal`): no I/O, so the table of cases in
``test_launch_admission.py`` runs without a database. What this module does
**not** do, by design and recorded in ``admission.launch.skipped``: the
on-demand risk read, the creator ATA read, the buyer's ATA read (a mint that
is seconds old cannot be held by this wallet: ``creates_ata = True``), the
conviction read. Each is named there next to the engine's own ``skipped``
checks, so the row alone says what was not measured.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final, cast

from hunter_meme_executor.admission import denominator_subunits
from hunter_meme_executor.launch_config import LAUNCH_SERIES, LaunchConfig
from hunter_meme_executor.launch_repo import LaunchCandidate, created_at_of
from hunter_risk_meme import LAUNCH_LANE, LAUNCH_SKIPPED_CHECKS, MemeContext, MemeEntryProposal

if TYPE_CHECKING:
    from hunter_exchanges.pumpfun.global_state import GlobalAccount
    from hunter_meme_executor.chain import CurveRead
    from hunter_meme_executor.repo import TokenContext
    from hunter_risk_meme import MemeLimits

__all__ = [
    "DEFAULT_DRAWDOWN_PCT",
    "DEFAULT_TIME_STOP_S",
    "LAUNCH_READS_SKIPPED",
    "launch_context",
    "launch_position_params",
    "launch_proposal",
    "launch_requested_sol",
]

LAMPORTS = Decimal(1_000_000_000)
DEFAULT_TIME_STOP_S: Final = 6
DEFAULT_DRAWDOWN_PCT: Final = Decimal(20)
DEFAULT_THIRD_PARTY_SELL: Final = True

LAUNCH_READS_SKIPPED: Final[dict[str, str]] = {
    "risk_snapshot_on_demand": "no /in-memory-coin row can exist at t+1s (T4.45 read not made)",
    "creator_ata": "no creator flow at t+1s (T4.45 chain read not made)",
    "buyer_ata": "a mint seconds old is not held by this wallet: creates_ata assumed true",
    "conviction_read": "no curve photos / features row at t+1s (T4.61c read not made)",
    "token_context": "read if present; absent is not a refusal (the proposal carries the stamp)",
}
"""The reads the launch path does not make, written to ``admission.launch.skipped_reads``."""


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except ArithmeticError:
        return None
    return parsed if parsed.is_finite() else None


def _first(*sources: dict[str, Any], key: str) -> Any:
    for source in sources:
        if key in source and source[key] is not None:
            return source[key]
    return None


def _int_or(raw: Any, default: int) -> int:
    if isinstance(raw, bool) or raw is None:
        return default
    try:
        return int(str(raw).strip())
    except ValueError:
        return default


def str_list(raw: Any) -> list[str]:
    """The strings of a JSON list; anything else is an empty list."""
    if not isinstance(raw, list):
        return []
    return [x for x in cast(list[Any], raw) if isinstance(x, str) and x]


def launch_context(
    candidate: LaunchCandidate,
    token: TokenContext | None,
    curve: CurveRead,
    global_account: GlobalAccount,
    *,
    participation_used_sol: Decimal,
    now: datetime,
) -> tuple[MemeContext, dict[str, Any]]:
    """The :class:`MemeContext` of a launch and the provenance of every field
    that had to come from somewhere other than the radar's tables."""
    created_at, age_source = created_at_of(candidate)
    if created_at is None and token is not None and token.created_at is not None:
        created_at, age_source = token.created_at, "meme_tokens.created_at"
    if created_at is None:
        created_at = candidate.candidate.proposed_at
        age_source = "meme_proposals.proposed_at(lower_bound_on_age)"
    denominator: int | None = None
    denominator_source = "none"
    first = candidate.reasons[0] if candidate.reasons else {}
    lane_denominator = _decimal(first.get("initial_real_token_reserves"))
    if token is not None and token.initial_real_token_reserves:
        denominator = denominator_subunits(token.initial_real_token_reserves)
        denominator_source = "meme_tokens.initial_real_token_reserves"
    elif lane_denominator is not None and lane_denominator > 0:
        # T4.67a reconstructs it from the create frame (tokens, like ``meme_tokens``).
        denominator = denominator_subunits(lane_denominator)
        denominator_source = "meme_proposals.reasons[0].initial_real_token_reserves"
    elif (
        not curve.account.is_mayhem_mode
        and curve.account.token_total_supply == global_account.token_total_supply
    ):
        denominator = int(global_account.initial_real_token_reserves)
        denominator_source = "pump_global.initial_real_token_reserves(stock_curve)"
    volume = Decimal(curve.account.real_sol_reserves) / LAMPORTS
    context = MemeContext(
        mint=candidate.mint,
        token_created_at=created_at,
        token_age_source=age_source,
        initial_real_token_reserves=denominator,
        organic_volume_1m_sol=volume,
        volume_ts=curve.observed_at,
        volume_window_complete=True,
        participation_used_sol=participation_used_sol,
        bundled_share_pct=None,
        top10_share_pct=None,
        holder_denominator_valid=None,
        creator_net_sol=None,
    )
    extras: dict[str, Any] = {
        "profile": LAUNCH_LANE,
        "series": candidate.series,
        "rule_set": f"launch_v0/{candidate.rule_set_version}",
        "token_age_source": age_source,
        "token_age_s": str((now - created_at).total_seconds()),
        "denominator_source": denominator_source,
        "volume_source": "curve.real_sol_reserves(whole_life)",
        "quote_commitment": curve.commitment,
        "quote_slot": curve.slot,
        "skipped_checks": dict(LAUNCH_SKIPPED_CHECKS),
        "skipped_reads": dict(LAUNCH_READS_SKIPPED),
        "token_row_present": token is not None and token.created_at is not None,
    }
    return context, extras


def launch_requested_sol(
    candidate: LaunchCandidate, limits: MemeLimits, launch: LaunchConfig
) -> Decimal:
    """The set's ``size_sol``, or the ticket when the set says nothing."""
    requested = _decimal(candidate.candidate.decision.get("size_sol")) or launch.ticket(limits)
    return requested if requested > 0 else launch.ticket(limits)


def launch_proposal(
    candidate: LaunchCandidate,
    *,
    wallet_id: str,
    limits: MemeLimits,
    launch: LaunchConfig,
    priority_fee_sol: Decimal,
    requested_cap_sol: Decimal | None = None,
) -> MemeEntryProposal:
    """The request (:func:`launch_requested_sol`), always ``live``; the engine
    caps it by ``launch_ticket`` and ``trade_cap`` — never above either.
    ``requested_cap_sol`` (T4.96) is what the written scope still allows, applied
    **after** the ticket fallback so a zero cap can never bring the ticket back."""
    requested = launch_requested_sol(candidate, limits, launch)
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
        agent_id=f"launch:{candidate.candidate.decided_by}",
    )


def launch_position_params(candidate: LaunchCandidate, curve: CurveRead) -> dict[str, Any]:
    """What the position row carries for the exits (``exit_common.exit_params``
    and the event path's third-party rule): the set's numbers — the decision,
    then ``suggested``, then the rule set's ``params`` — with EXP-M18's defaults
    (6 s, 20 %, first third-party sell) where the set is silent."""
    decision, suggested, params = (
        candidate.candidate.decision,
        candidate.suggested,
        candidate.rule_set_params,
    )
    time_stop = _first(decision, suggested, params, key="time_stop_s")
    if time_stop is None:
        time_stop = _first(decision, suggested, params, key="max_hold_s")
    time_stop_s = _int_or(time_stop, DEFAULT_TIME_STOP_S)
    drawdown = _decimal(_first(decision, suggested, params, key="max_drawdown_from_peak_pct"))
    if drawdown is None:
        drawdown = _decimal(_first(decision, suggested, params, key="trailing_pct"))
    drawdown_pct = drawdown if drawdown is not None and 0 < drawdown < 100 else DEFAULT_DRAWDOWN_PCT
    third_party = _first(decision, suggested, params, key="exit_on_first_third_party_sell")
    third_party_on = DEFAULT_THIRD_PARTY_SELL if third_party is None else bool(third_party)
    target = _decimal(_first(decision, suggested, params, key="target_x"))
    first = candidate.reasons[0] if candidate.reasons else {}
    known_buyers = str_list(first.get("known_buyers") or first.get("bundled_buyers"))
    creation_slot = _int_or(first.get("creation_slot") or first.get("slot"), -1)
    out: dict[str, Any] = {
        "lane": LAUNCH_LANE,
        "series": LAUNCH_SERIES,
        "rule_set": f"launch_v0/{candidate.rule_set_version}",
        "size_sol": str(_decimal(decision.get("size_sol")) or ""),
        "time_stop_s": max(1, time_stop_s),
        "max_hold_s": max(1, time_stop_s),
        "max_drawdown_from_peak_pct": str(drawdown_pct),
        "trailing_pct": str(drawdown_pct),
        "exit_on_first_third_party_sell": third_party_on,
        "creator": curve.account.creator,
        "creation_slot": None if creation_slot < 0 else creation_slot,
        "known_buyers": known_buyers,
        "decided_by": candidate.candidate.decided_by,
    }
    if target is not None and target > 1:
        out["target_x"] = str(target)
    return out
