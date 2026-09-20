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

from collections.abc import Mapping
from datetime import timedelta
from typing import TYPE_CHECKING, Final

from sqlalchemy import text

from hunter_core.execution.meme.approval import AUTO_STAGE1_DECIDED_BY
from hunter_risk_meme import MINT_COOLDOWN_AFTER_LOSS
from hunter_risk_meme.limits_env import DEFAULT_MINT_COOLDOWN_AFTER_LOSS_S

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "DETERMINISTIC_REFUSALS",
    "SHORT_COOLDOWNS",
    "cooling_mints_by_window",
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
        "creator_net_seller",
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

``creator_net_seller`` joined on T4.56 (COVER, 17/09/2026 — R56 §3.2): the chain
read refused the mint at 19:46:56 BRT, the desk re-proposed it 23 s later, and
the 1-minute fold's lagging ``creator_sold = false`` let it through. A creator
who sold his allocation does not un-sell in 120 s, whichever source saw it — the
chain's ATA read, this process's memory of one, or the tape itself. Its sibling
``creator_flow_unknown`` stays **out**: that is data availability (the fold's
row or T4.45's chain read can answer on the next tick), and cooling it would
sit on a coin whose creator still holds everything.

Names checked against §4 and **dropped** because no such refusal exists:
``creator_serial``, ``symbol_clone``, ``mayhem_curve``, ``mayhem_unknown`` — those
are the *radar gate*'s refusals (``hunter_meme_worker.rules_criteria``), never
written to ``meme_live_orders.reason``; a mint refused by the gate never reaches
the executor at all."""

SHORT_COOLDOWNS: Final[Mapping[str, float]] = {
    "entry_after_drop": 30.0,
    MINT_COOLDOWN_AFTER_LOSS: float(DEFAULT_MINT_COOLDOWN_AFTER_LOSS_S),
}
"""T4.61c — refusals the **clock** clears, but not on the next tick: each cools
its mint for its own window, never longer than the owner's cooldown.

``mint_cooldown_after_loss`` (T4.78, check 28; the row's reason carries the
seconds left, ``mint_cooldown_after_loss:240``, matched by its **base** name):
the mint's last live close lost and the engine refuses it for up to 300 s. The
desk re-proposes every ~20 s; without this entry each re-proposal would be
opened, cost three RPC reads and be refused with a smaller number — the same
"cost without information" of T4.28f. The wait is the **announced remainder**
(``:10`` cools 10 s, never the 300 s ceiling — Astra, review T4.78: a fixed
window restarted at ``t = 290`` would hold the mint past ``t = 410`` while the
engine had freed it at 300), capped by the owner's cooldown like every short
one; a reason without a readable remainder uses the ceiling.

``entry_after_drop`` (check 26, §17): the real SOL fell ≥ 50 % from the peak of
the last 60 s. The desk re-proposes in ~20 s and every retry costs three RPC
reads, the creator's ATA and the series read for the same answer, because the
peak only leaves the window as it ages — 30 s is short enough to stay under
KB-0118's 60 s (the fall that has *stopped*, +0,566 R at 60–180 s, is never
skipped by it) and long enough to skip one useless retry. Its sibling
``entry_after_drop_unknown`` is **not** here: the next photo can answer it."""

_COOLING_REFUSALS = text(
    "SELECT p.mint, o.reason, o.received_at FROM meme_live_orders o "
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


def cooling_mints_by_window(
    rows: Iterable[tuple[str, str, datetime]], *, now: datetime, cooldown_s: float
) -> frozenset[str]:
    """Pure: the deterministic refusals inside the owner's window, plus the
    short-cooldown ones (:data:`SHORT_COOLDOWNS`) inside their own — each capped
    by ``cooldown_s``, so the owner's number is always the longest wait."""
    out: set[str] = set()
    for mint, reason, refused_at in rows:
        base, _, remainder = reason.partition(":")  # T4.78: ``mint_cooldown_after_loss:<left>``
        short = SHORT_COOLDOWNS.get(base)
        if short is not None and base == MINT_COOLDOWN_AFTER_LOSS and remainder.isdigit():
            short = min(short, float(remainder))
        window = cooldown_s if base in DETERMINISTIC_REFUSALS else short
        if window is None:
            continue
        if refused_at >= now - timedelta(seconds=min(window, cooldown_s)):
            out.add(mint)
    return frozenset(out)


async def refusal_cooling_mints(
    session: AsyncSession, *, now: datetime, cooldown_s: float
) -> frozenset[str]:
    """One query per pass: the mints this executor must not re-open yet."""
    since = refusal_window_start(now, cooldown_s)
    if since is None:
        return frozenset()
    rows = await session.execute(_COOLING_REFUSALS, {"by": AUTO_STAGE1_DECIDED_BY, "since": since})
    return cooling_mints_by_window(
        ((str(row[0]), str(row[1]), row[2]) for row in rows), now=now, cooldown_s=cooldown_s
    )
