"""The continuous paper Lab on the pump.fun curve — rule sets, proposals, bets,
operator commands (DATABASE.md §34, revision ``0022_meme_lab``).

**Global tables** (§1.1), the shape of ``meme_tokens``: a paper bet on an
on-chain curve belongs to the Lab, not to an organization — no
``organization_id``, therefore no RLS. The schema is the contract
``.claude/state/contrato-T4.6-T4.7-mesa-meme.md`` froze so the operator desk
(T4.7) and the loop (T4.6) could be built in parallel; every departure from it
is a line under that file's "Emendas".

Three decisions live here rather than in prose:

- **``mode`` is locked to ``'paper'`` by CHECK.** The column exists so T4.8 can
  add ``'live'`` with its own revision behind ``ENABLE_MEME_LIVE_TRADING``; until
  then no role, owner included, can write a row claiming to be real.
- **A proposal's states carry their own evidence.** ``filled`` ⟺ ``bet_id``,
  ``unfilled`` ⟺ ``refusal``, and every decided state names who decided and
  when. A quiet desk is then explained by rows, never by absence of rows.
- **A bet's exit is all-or-nothing.** ``exit_at``, ``exit``, ``pnl_sol`` and
  ``r_multiple`` are null together or set together, so a half-closed bet cannot
  exist; ``exit_intent`` (Emendas 4) is the rule that fired while the sale waits
  for the *next* snapshot — the same non-anticipation the fill obeys.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import JSONB_EMPTY, JSONB_EMPTY_LIST

RULE_SET_KINDS = ("research_only", "operator")
"""``research_only``: the loop approves its own proposals (paper, EXP-M*).
``operator``: the loop proposes and waits for the desk's approval."""

PROPOSAL_STATUSES = ("proposed", "approved", "rejected", "expired", "filled", "unfilled")
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
)
"""The contract's seven plus ``max_loss`` (Emendas 1): EXP-M1 pre-registered a
50 % loss floor as an exit rule, and a floor that closed a bet under another name
would be a lie in the diary. Plus ``line_broken`` (``0026``, T4.10): the market
cap closed below the support line for two snapshots in a row — EXP-M2's own
invalidation, named as such."""

BET_LEGS = ("probe", "scale", "single")
"""``meme_paper_bets.leg`` (``0026``): the hype probe ("semi-comprado (sonda)"),
the second leg that scales it ("escalado (perna 2)", which names its
``parent_bet_id``) and the one-leg bet of every other rule set."""

OPERATOR_COMMANDS = ("sell_now", "cancel")


class MemeRuleSet(Base, UUIDPrimaryKeyMixin):
    """One frozen set of rules: gate, exits, size and the paper ceilings."""

    __tablename__ = "meme_rule_sets"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_meme_rule_sets_name_version"),
        CheckConstraint("kind IN ('research_only', 'operator')", name="kind_is_a_known_label"),
        CheckConstraint("status IN ('active', 'retired')", name="status_is_a_known_label"),
        CheckConstraint(
            "(status = 'retired') = (retired_at IS NOT NULL)", name="a_retired_set_says_when"
        ),
        CheckConstraint(
            "kind = 'operator' OR exp_ref IS NOT NULL", name="research_names_its_experiment"
        ),
        CheckConstraint(
            "char_length(name) > 0 AND char_length(version) > 0 AND char_length(code_ref) > 0",
            name="identity_is_not_empty",
        ),
    )

    name: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    """Frozen at pre-registration. Decimals are JSON **strings** (``"0.05"``)
    so ``Decimal`` reads them exactly; seconds and counts are integers."""

    code_ref: Mapped[str] = mapped_column(Text)
    exp_ref: Mapped[str | None] = mapped_column(Text)
    """``EXP-M1`` etc.; ``NULL`` only for ``kind = 'operator'`` (CHECK)."""

    status: Mapped[str] = mapped_column(Text, server_default=text("'active'"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    retired_at: Mapped[datetime | None]


class MemeProposal(Base, UUIDPrimaryKeyMixin):
    """One intention to buy, from the loop (``rules``) or the desk (``operator``)."""

    __tablename__ = "meme_proposals"
    __table_args__ = (
        Index("ix_meme_proposals_status_proposed_at", "status", "proposed_at"),
        Index("ix_meme_proposals_mint_proposed_at", "mint", "proposed_at"),
        Index(
            "uq_meme_proposals_one_per_rule_set_mint_minute",
            "rule_set_id",
            "mint",
            "features_end_time",
            unique=True,
            postgresql_where=text("origin = 'rules'"),
        ),
        CheckConstraint("origin IN ('rules', 'operator')", name="origin_is_a_known_label"),
        CheckConstraint(
            "status IN ('proposed', 'approved', 'rejected', 'expired', 'filled', 'unfilled')",
            name="status_is_a_known_label",
        ),
        CheckConstraint("expires_at > proposed_at", name="expiry_is_after_proposal"),
        CheckConstraint(
            "origin = 'operator' OR features_end_time IS NOT NULL",
            name="a_rules_proposal_names_its_minute",
        ),
        CheckConstraint(
            "(decided_at IS NULL) = (decided_by IS NULL)", name="a_decision_names_who_and_when"
        ),
        CheckConstraint(
            "status IN ('proposed', 'expired') OR decided_at IS NOT NULL",
            name="a_decided_status_carries_a_decision",
        ),
        CheckConstraint("(status = 'filled') = (bet_id IS NOT NULL)", name="a_fill_names_its_bet"),
        CheckConstraint(
            "(status = 'unfilled') = (refusal IS NOT NULL)",
            name="an_unfilled_proposal_names_its_refusal",
        ),
        CheckConstraint("char_length(mint) > 0", name="mint_is_not_empty"),
    )

    mint: Mapped[str] = mapped_column(Text)
    rule_set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meme_rule_sets.id"))
    origin: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'proposed'"))
    proposed_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime]
    features_end_time: Mapped[datetime | None]
    """The closed minute that motivated a ``rules`` proposal — the
    non-anticipation stamp. ``NULL`` only for a manual (``operator``) one."""

    quote: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    reasons: Mapped[list[Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY_LIST)
    suggested: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    decision: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    """Written by the API on approval (the operator may change any of the four
    numbers) or by the loop for ``research_only`` (``decision = suggested``).
    The loop applies the rule set's ceilings on top, refusing by name."""

    decided_by: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None]
    bet_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "meme_paper_bets.id",
            use_alter=True,
            name="fk_meme_proposals_bet_id_meme_paper_bets",
        )
    )
    """Closes the cycle proposals -> bets -> proposals; ``use_alter`` because a
    cycle cannot be sorted, and the DDL adds it with ``ALTER TABLE`` after both
    tables exist (``ddl/meme_lab.py``)."""
    refusal: Mapped[str | None] = mapped_column(Text)


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


class MemeOperatorCommand(Base, UUIDPrimaryKeyMixin):
    """An operator's order over an open bet (``sell_now``) or a pending
    proposal (``cancel``). Written by the API, applied by the loop."""

    __tablename__ = "meme_operator_commands"
    __table_args__ = (
        Index(
            "ix_meme_operator_commands_pending",
            "issued_at",
            postgresql_where=text("applied_at IS NULL"),
        ),
        CheckConstraint("command IN ('sell_now', 'cancel')", name="command_is_a_known_label"),
        CheckConstraint("(bet_id IS NULL) <> (proposal_id IS NULL)", name="exactly_one_target"),
        CheckConstraint("command <> 'sell_now' OR bet_id IS NOT NULL", name="a_sale_targets_a_bet"),
        CheckConstraint(
            "command <> 'cancel' OR proposal_id IS NOT NULL", name="a_cancel_targets_a_proposal"
        ),
        CheckConstraint(
            "(applied_at IS NULL) = (result IS NULL)", name="an_application_says_what_happened"
        ),
        CheckConstraint("char_length(issued_by) > 0", name="issuer_is_not_empty"),
    )

    bet_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "meme_paper_bets.id",
            use_alter=True,
            name="fk_meme_proposals_bet_id_meme_paper_bets",
        )
    )
    """Closes the cycle proposals -> bets -> proposals; ``use_alter`` because a
    cycle cannot be sorted, and the DDL adds it with ``ALTER TABLE`` after both
    tables exist (``ddl/meme_lab.py``)."""
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("meme_proposals.id"))
    command: Mapped[str] = mapped_column(Text)
    issued_by: Mapped[str] = mapped_column(Text)
    issued_at: Mapped[datetime] = mapped_column(server_default=func.now())
    applied_at: Mapped[datetime | None]
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


__all__ = [
    "BET_EXIT_REASONS",
    "OPERATOR_COMMANDS",
    "PROPOSAL_STATUSES",
    "RULE_SET_KINDS",
    "MemeOperatorCommand",
    "MemePaperBet",
    "MemeProposal",
    "MemeRuleSet",
]
