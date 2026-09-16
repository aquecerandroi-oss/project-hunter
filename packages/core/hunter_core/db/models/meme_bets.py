"""``meme_paper_bets`` — split out of ``meme_lab.py`` (T4.26) for the 350-line
budget, the same cut ``meme_lab_commands.py`` took for ``MemeOperatorCommand``.
Re-exported from ``meme_lab.py``, so every caller still imports from there.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import PERCENT

BET_EXIT_REASONS = (
    "target",
    "trailing",
    "time_stop",
    "migrated",
    "creator_dump",
    "sell_now",
    "rug_no_snapshot",
    "max_loss",
    "line_broken",
    "dead",
)
"""The contract's seven plus ``max_loss`` (Emendas 1): EXP-M1 pre-registered a
50 % loss floor as an exit rule, and a floor that closed a bet under another name
would be a lie in the diary. Plus ``line_broken`` (``0026``, T4.10): the market
cap closed below the support line for two snapshots in a row — EXP-M2's own
invalidation, named as such. Plus ``dead`` (``0029``, T4.11): the pool's tape
silent for 15 min with the mark at or below half the cost — the market gone,
for a bet that held through the migration."""

BET_LEGS = ("probe", "scale", "single")
"""``meme_paper_bets.leg`` (``0026``): the hype probe ("semi-comprado (sonda)"),
the second leg that scales it ("escalado (perna 2)", which names its
``parent_bet_id``) and the one-leg bet of every other rule set."""

MARK_SOURCES = ("curve", "pool_tape")
"""``meme_paper_bets.mark_source`` (``0029``): what priced the last mark — the
curve's snapshot, or the PumpSwap pool's last trade after the migration."""

OUTCOME_QUALITIES = ("measured", "indeterminate")
"""``meme_paper_bets.outcome_quality`` (``0030``, T4.16): ``measured`` is a
result the simulator priced on an observation; ``indeterminate`` is a close
the instrument could not price (``rug_no_snapshot``: no photo to sell into
inside the window — the coin did not die, the radar blinked). The row keeps
its numbers (``pnl_sol = −stake``, the CHECK demands them); the scoreboard,
the desk, the wallet of the loop and the daily close **exclude** it from
every sum of R/PnL and count it apart ("indeterminado (sem fotografia)")."""


class MemePaperBet(Base, UUIDPrimaryKeyMixin):
    """One paper position, from its fill to its exit. Never a real order."""

    __tablename__ = "meme_paper_bets"
    __table_args__ = (
        UniqueConstraint("proposal_id", name="uq_meme_paper_bets_proposal_id"),
        Index("ix_meme_paper_bets_status_entry_at", "status", "entry_at"),
        Index("ix_meme_paper_bets_rule_set_id_entry_at", "rule_set_id", "entry_at"),
        Index("ix_meme_paper_bets_mint", "mint"),
        CheckConstraint("mode = 'paper'", name="every_bet_is_paper"),
        CheckConstraint("status IN ('open', 'closed')", name="status_is_a_known_label"),
        CheckConstraint(
            "(status = 'closed') = (exit_at IS NOT NULL)", name="a_closed_bet_says_when"
        ),
        CheckConstraint(
            "(exit_at IS NULL) = (exit IS NULL) AND (exit_at IS NULL) = (pnl_sol IS NULL) "
            "AND (exit_at IS NULL) = (r_multiple IS NULL)",
            name="an_exit_carries_its_numbers",
        ),
        CheckConstraint("exit_at IS NULL OR exit_at > entry_at", name="an_exit_is_after_the_entry"),
        CheckConstraint("(mark_sol IS NULL) = (mark_at IS NULL)", name="a_mark_says_when"),
        CheckConstraint("initial_risk_sol > 0", name="the_risk_is_what_was_spent"),
        CheckConstraint("char_length(mint) > 0", name="mint_is_not_empty"),
        # 0026 — probe and scale legs (T4.10).
        Index(
            "ix_meme_paper_bets_parent_bet_id",
            "parent_bet_id",
            postgresql_where=text("parent_bet_id IS NOT NULL"),
        ),
        CheckConstraint("leg IN ('probe', 'scale', 'single')", name="leg_is_a_known_label"),
        CheckConstraint(
            "(leg = 'scale') = (parent_bet_id IS NOT NULL)", name="a_scale_leg_names_its_probe"
        ),
        # 0029 — the mark's source and its staleness (T4.11).
        CheckConstraint(
            "mark_source IS NULL OR mark_source IN ('curve', 'pool_tape')",
            name="mark_source_is_a_known_label",
        ),
        CheckConstraint(
            "(mark_sol IS NULL) = (mark_source IS NULL)", name="a_mark_names_its_source"
        ),
        CheckConstraint(
            "mark_stale_s IS NULL OR mark_stale_s >= 0", name="mark_stale_s_is_not_negative"
        ),
        # 0030 — the quality of the outcome (T4.16).
        CheckConstraint(
            "outcome_quality IN ('measured', 'indeterminate')",
            name="outcome_quality_is_a_known_label",
        ),
        CheckConstraint(
            "outcome_quality = 'measured' OR status = 'closed'",
            name="an_indeterminate_bet_is_closed",
        ),
        CheckConstraint(
            "(outcome_quality = 'indeterminate') = (outcome_quality_reason IS NOT NULL) "
            "AND (outcome_quality = 'indeterminate') = (outcome_quality_at IS NOT NULL)",
            name="an_indeterminate_outcome_names_its_reason",
        ),
        # T4.2h (0036).
        CheckConstraint(
            "creator_sold_fraction IS NULL OR (creator_sold_fraction > 0 AND creator_sold_fraction <= 1)",
            name="creator_sold_fraction_is_a_fraction",
        ),
        CheckConstraint(
            "(creator_sold_seen_at IS NULL) = (creator_sold_fraction IS NULL)",
            name="a_creator_sale_has_its_fraction",
        ),
        CheckConstraint(
            "creator_balance_reason IS NULL OR creator_balance_reason IN ('creator_ata_missing')",
            name="creator_balance_reason_is_a_known_label",
        ),
    )

    proposal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meme_proposals.id"))
    rule_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meme_rule_sets.id"))
    mint: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(Text, server_default=text("'paper'"))
    status: Mapped[str] = mapped_column(Text, server_default=text("'open'"))
    entry_at: Mapped[datetime]
    """``observed_at`` of the fill snapshot — strictly after the decision."""

    entry: Mapped[dict[str, Any]] = mapped_column(JSONB)
    initial_risk_sol: Mapped[Decimal]
    """``= sol_spent`` (RISK_ENGINE_MEME §5): on a curve the risk is everything
    paid, never a stop distance."""

    params: Mapped[dict[str, Any]] = mapped_column(JSONB)
    exit_intent: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    exit_at: Mapped[datetime | None]
    exit_: Mapped[dict[str, Any] | None] = mapped_column("exit", JSONB)
    pnl_sol: Mapped[Decimal | None]
    r_multiple: Mapped[Decimal | None]
    mark_sol: Mapped[Decimal | None]
    """What a full sell would net **now**, fees included — never marginal price
    times quantity (RISK_ENGINE_MEME §6)."""

    mark_at: Mapped[datetime | None]
    high_water_x: Mapped[Decimal | None]
    sol_usd_at_entry: Mapped[Decimal | None]
    sol_usd_at_exit: Mapped[Decimal | None]

    # --- 0026: probe and scale legs (T4.10) -------------------------------------
    parent_bet_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("meme_paper_bets.id"))
    """The probe a ``scale`` leg rides on — set exactly when ``leg = 'scale'``."""

    leg: Mapped[str] = mapped_column(Text, server_default=text("'single'"))
    """``probe`` | ``scale`` | ``single`` (:data:`BET_LEGS`); every bet written
    before ``0026`` is ``single`` by default, which is what it was."""

    # --- 0029: the mark's source and staleness (T4.11) --------------------------
    mark_source: Mapped[str | None] = mapped_column(Text)
    """``curve`` | ``pool_tape`` (:data:`MARK_SOURCES`) — set exactly when
    ``mark_sol`` is; every mark written before ``0029`` was the curve's."""

    mark_stale_s: Mapped[int | None]
    """Seconds the pool's tape had been silent when the mark was refreshed
    (the desk's "marca envelhecida há Ns"); the ``dead`` rule reads it."""

    # --- 0030: the quality of the outcome (T4.16) --------------------------------
    outcome_quality: Mapped[str] = mapped_column(Text, server_default=text("'measured'"))
    """``measured`` | ``indeterminate`` (:data:`OUTCOME_QUALITIES`); every bet
    written before ``0030`` is ``measured`` by default — the audited script
    ``infra/scripts/meme_reclassify_indeterminate.py`` is the only way a past
    ``rug_no_snapshot`` becomes ``indeterminate``, with its reason and instant."""

    outcome_quality_reason: Mapped[str | None] = mapped_column(Text)
    outcome_quality_at: Mapped[datetime | None]
    creator_sold_seen_at: Mapped[datetime | None]
    creator_sold_fraction: Mapped[Decimal | None] = mapped_column(PERCENT)
    creator_balance_reason: Mapped[str | None] = mapped_column(Text)
    """T4.2h (``0036``): the creator's sale seen on the chain, or why the watch could not measure."""


__all__ = [
    "BET_EXIT_REASONS",
    "BET_LEGS",
    "MARK_SOURCES",
    "OUTCOME_QUALITIES",
    "MemePaperBet",
]
