"""T4.28f — a mint the admission just refused for a deterministic reason is not
re-opened by stage 1 for a couple of minutes (``auto_approve``'s
``recently_refused`` skip).

Measured on 16/09/2026, 11:46–11:48 BRT (first day of ``MEME_LIVE=1``): the desk
re-proposes the same mint every ~20 s, ``auto_approve_once`` opened one coin five
times and the admission refused it five times with the same
``progress_below_window``. T4.28e had already stopped a refusal from spending an
hourly slot; what was left was cost without information — one RPC read of the
curve, one ``refused`` order row and one ``rejected`` proposal per re-proposal.

The whole module is one decision: **which refusals are worth waiting on**. Nothing
here creates or blocks an order — a cooling mint simply has no proposal opened for
it, so the row stays ``proposed`` for the human's click and the admission is never
reached. The cooldown is a delay, never a ban.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Final

from sqlalchemy import text

from hunter_core.execution.meme.approval import AUTO_STAGE1_DECIDED_BY

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "DETERMINISTIC_REFUSALS",
    "cooling_mints_of",
    "refusal_cooling_mints",
    "refusal_window_start",
]

DETERMINISTIC_REFUSALS: Final[frozenset[str]] = frozenset(
    {
        "progress_above_window",
        "token_too_old",
        "token_age_unknown",
        "program_not_allowed",
        "unsupported_quote",
        "progress_denominator_missing",
    }
)
"""T4.28f — the admission refusals that cool their mint (skip ``recently_refused``).

Every name here is a real refusal of ``hunter_risk_meme.checks.REFUSAL_NAMES``
(proved by ``test_every_cooling_reason_is_a_real_admission_refusal``), and the
line that decides who is in is: **a refusal the clock alone will clear is never
here**. ``token_too_young`` is the counter-example that decided the rule — the
window opens at ``token_age_min_s`` (30 s in ``MEME_PAPER_V0``), so a 120 s
cooldown would sit on a coin that became admissible 90 s earlier. The same for
``curve_state_stale``, ``volume_unavailable``, ``marks_incomplete`` and
``wallet_over_max_sol``: a fresh read, a finished sale or a released lamport
clears them on the next tick, and the retry is worth its RPC call.

What is here needs the **market or the database** to change, not the clock:
progress outside the 2–50 % window, a coin already past the age ceiling, a
``created_at`` with no provenance, a program that is not the allowed one, a quote
that is not SOL, a missing denominator. Retrying those every ~20 s (the desk's
re-proposal cadence) only writes one ``refused`` order and one ``rejected``
proposal per pass — measured 16/09/2026 11:46–11:48 BRT, five times on one mint.

Names checked against §4 and **dropped** because no such refusal exists:
``creator_serial``, ``symbol_clone``, ``mayhem_curve``, ``mayhem_unknown`` — those
are the *radar gate*'s refusals (``hunter_meme_worker.rules_criteria``), never
written to ``meme_live_orders.reason``; a mint refused by the gate never reaches
the executor at all."""

_COOLING_REFUSALS = text(
    "SELECT p.mint, o.reason FROM meme_live_orders o "
    "JOIN meme_proposals p ON p.id = o.proposal_id "
    "WHERE p.decided_by = :by AND o.side = 'buy' AND o.status = 'refused' "
    "  AND o.received_at >= :since"
)
"""T4.28f — the buys this executor opened and the admission refused inside the
cooldown, with the reason. Same shape (and same index,
``ix_meme_live_orders_status_received_at``) as ``auto_approve``'s hourly count;
the reason is filtered in Python so :data:`DETERMINISTIC_REFUSALS` has exactly
one home. Rows are few by construction: two minutes of one wallet's refusals."""


def refusal_window_start(now: datetime, cooldown_s: float) -> datetime | None:
    """Pure: the oldest refusal that still cools its mint, or ``None`` when the
    cooldown is off (``0``/negative — then no query runs and nothing is skipped)."""
    if cooldown_s <= 0:
        return None
    return now - timedelta(seconds=cooldown_s)


def cooling_mints_of(rows: Iterable[tuple[str, str]]) -> frozenset[str]:
    """Pure: of the refusals inside the window, the mints whose reason cannot
    change in the next couple of minutes (:data:`DETERMINISTIC_REFUSALS`)."""
    return frozenset(mint for mint, reason in rows if reason in DETERMINISTIC_REFUSALS)


async def refusal_cooling_mints(
    session: AsyncSession, *, now: datetime, cooldown_s: float
) -> frozenset[str]:
    """One query per pass: the mints this executor must not re-open yet."""
    since = refusal_window_start(now, cooldown_s)
    if since is None:
        return frozenset()
    rows = await session.execute(_COOLING_REFUSALS, {"by": AUTO_STAGE1_DECIDED_BY, "since": since})
    return cooling_mints_of((str(row[0]), str(row[1])) for row in rows)
