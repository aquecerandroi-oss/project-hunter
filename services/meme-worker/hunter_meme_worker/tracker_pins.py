"""The pinned set (T4.16b): every mint the tracker's cap and window must not
touch right now — from the durable rows, never from memory, so a restart
rebuilds exactly the same set (``lab.py``'s reload every tick, ``main.py``'s
reload at boot).

Five ``hype_probe_v0`` paper bets closed ``rug_no_snapshot`` on 12/09 with a
last photo 13 minutes before the exit and no coin actually dead
(``docs/RISK_ENGINE_MEME.md`` §10): the tracker's cap evicted them at roughly
one discovery every few seconds, and the chain loop stopped photographing a
mint the instant it left the tracked set. The three facts below are the
brief's own definition of "not optional inventory": an open paper bet, an
open live position (T4.14, ``meme_live_positions`` — read-only here, the
executor owns the writes) and a proposal still waiting on a decision that has
not expired. A ``rejected``/``expired``/``filled``/``unfilled`` proposal
carries no urgency of its own — whatever it produced (a bet, a position) is
already pinned by its own row.

**T4.91 (EXP-M24): ``recuo_v1/1``'s open bets pin nothing.** A pinned mint
stays tracked past the cap, so ``fold.fold_minute`` keeps writing its
``meme_features_1m`` rows — ``creator_sold`` among them, the source of
``lab_repo_fast._PEDIGREE``'s ``creator_prior_dump_count`` that no rule set id
can subtract — and every pinned mint narrows everyone else's cap. The arm's
bet enters up to 60 s after the desk's decision on the same mint and would
outlive the desk's own pin (its shadow bet, its proposal) by that much, or
entirely when the desk never took the mint: exactly the window in which it
could change what ``operator/5`` reads. The price, declared: under cap
pressure an arm bet may lose its photos in that tail and close through
``lab_point_read`` or ``indeterminate`` — the arm's measurement pays, never
the desk.

**T4.95 (EXP-M25): ``recuo_ctrl_v1/1`` pins nothing either.** The arm's
immediate-entry control enters on every arming — 122 of R79's 171 on mints
the desk refused, where no desk row pins anything — so its pin would keep
folding exactly the ``creator_sold`` rows above for mints only an experiment
holds. Unpinned, the pair is also measured under the same tracker.

**H-037 (EXP-M28): the copy lane's sets (``params.clock = 'copy'``) pin nothing.** The lane prices
from its own chain reads. Up to 2 x 100 copy mints held for up to 3 600 s would keep
``fold_minute`` writing ``creator_sold`` (the tape source of the pedigree's dump count) and narrow
everyone's cap; excluded by the clock, not by id, because the seed is a later task.

**I2 (EXP-M26, design §1.6): a second, separate pin.** :func:`pinned_mints`
now also excludes every EXP-M26 rule set's own bets/proposals — they move to
:func:`pinned_mints_exp_m26` instead, which :meth:`MintTracker.prune` never
lets narrow the young cap. Fixed there: an open bet or re-entry, and an
``approved`` proposal with no bet yet, until it decides (a bet, a refusal, an
expiry) or :data:`APPROVED_PIN_TERMINAL_S` after ``decided_at``, whichever
comes first — the design's own failure scenario is a research proposal born
``approved`` (``research_only`` sets never sit in ``proposed``) whose mint
leaves the top-K before the fill's photo ever lands.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_meme_worker.entry_pullback import PULLBACK_ARM_RULE_SET_ID, PULLBACK_CONTROL_RULE_SET_ID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["APPROVED_PIN_TERMINAL_S", "EXP_M26", "pinned_mints", "pinned_mints_exp_m26"]

EXP_M26 = "EXP-M26"
APPROVED_PIN_TERMINAL_S = 180
"""How long an ``approved``-without-bet EXP-M26 proposal stays pinned past
``decided_at`` (design §1.6) — the desk's own ``lab_proposal_ttl_s`` is a
different clock (``proposed_at``), and this one is not it."""

_ORDINARY_PINNED_MINTS = text(
    "SELECT b.mint FROM meme_paper_bets b JOIN meme_rule_sets rs ON rs.id = b.rule_set_id "
    "WHERE b.status = 'open' "
    "  AND b.rule_set_id <> CAST(:pullback_rule_set_id AS uuid) "
    "  AND b.rule_set_id <> CAST(:pullback_control_rule_set_id AS uuid) "
    "  AND COALESCE(rs.exp_ref, '') <> :exp_m26 "
    "  AND COALESCE(rs.params ->> 'clock', '') <> 'copy' "
    "UNION SELECT mint FROM meme_live_positions WHERE status = 'open' "
    "UNION SELECT p.mint FROM meme_proposals p JOIN meme_rule_sets rs ON rs.id = p.rule_set_id "
    "WHERE p.status = 'proposed' AND p.expires_at > :now AND COALESCE(rs.exp_ref, '') <> :exp_m26 "
    "  AND COALESCE(rs.params ->> 'clock', '') <> 'copy'"
)

_EXP_M26_PINNED_MINTS = text(
    "SELECT b.mint FROM meme_paper_bets b JOIN meme_rule_sets rs ON rs.id = b.rule_set_id "
    "WHERE b.status = 'open' AND rs.exp_ref = :exp_m26 "
    "UNION SELECT p.mint FROM meme_proposals p JOIN meme_rule_sets rs ON rs.id = p.rule_set_id "
    "WHERE p.status = 'approved' AND p.bet_id IS NULL AND rs.exp_ref = :exp_m26 "
    "  AND p.decided_at > :approved_cutoff "
    "UNION SELECT p.mint FROM meme_proposals p JOIN meme_rule_sets rs ON rs.id = p.rule_set_id "
    "WHERE p.status = 'proposed' AND p.expires_at > :now AND rs.exp_ref = :exp_m26"
)


async def pinned_mints(session: AsyncSession, *, now: datetime) -> frozenset[str]:
    """Every *ordinary* mint the tracker's cap and window may not evict right
    now — an EXP-M26 rule set's own bets/proposals are :func:`pinned_mints_exp_m26`
    instead."""
    rows = await session.execute(
        _ORDINARY_PINNED_MINTS,
        {
            "now": now,
            "pullback_rule_set_id": PULLBACK_ARM_RULE_SET_ID,
            "pullback_control_rule_set_id": PULLBACK_CONTROL_RULE_SET_ID,
            "exp_m26": EXP_M26,
        },
    )
    return frozenset(str(m) for m in rows.scalars().all())


async def pinned_mints_exp_m26(session: AsyncSession, *, now: datetime) -> frozenset[str]:
    """Every mint fixed *only* for belonging to an EXP-M26 rule set — never
    narrows the tracker's young cap (:meth:`MintTracker.pin_exp_m26`)."""
    rows = await session.execute(
        _EXP_M26_PINNED_MINTS,
        {
            "now": now,
            "exp_m26": EXP_M26,
            "approved_cutoff": now - timedelta(seconds=APPROVED_PIN_TERMINAL_S),
        },
    )
    return frozenset(str(m) for m in rows.scalars().all())
