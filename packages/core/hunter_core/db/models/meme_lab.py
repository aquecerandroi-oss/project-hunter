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
  add ``'live'`` with its own revision behind ``ENABLE_MEME_LIVE_TRADING``.
- **A proposal's states carry their own evidence.** ``filled`` ⟺ ``bet_id``,
  ``unfilled`` ⟺ ``refusal``; a quiet desk is explained by rows, never absence.
- **A bet's exit is all-or-nothing.** ``exit_at``, ``exit``, ``pnl_sol`` and
  ``r_multiple`` are null together or set together; ``exit_intent`` (Emendas 4)
  is the rule that fired while the sale waits for the *next* snapshot.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import JSONB_EMPTY, JSONB_EMPTY_LIST
from hunter_core.db.models.meme_bets import (
    BET_EXIT_REASONS,
    BET_LEGS,
    MARK_SOURCES,
    OUTCOME_QUALITIES,
    MemePaperBet,
)
from hunter_core.db.models.meme_lab_commands import MemeOperatorCommand

RULE_SET_KINDS = ("research_only", "operator")
"""``research_only``: the loop approves its own proposals (paper, EXP-M*).
``operator``: the loop proposes and waits for the desk's approval."""

PROPOSAL_STATUSES = ("proposed", "approved", "rejected", "expired", "filled", "unfilled")
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
        # 0028 — the live mode (T4.14).
        CheckConstraint("mode IN ('paper', 'live')", name="mode_is_a_known_label"),
        Index(
            "ix_meme_proposals_live_decided_at",
            "decided_at",
            postgresql_where=text("mode = 'live'"),
        ),
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

    # --- 0028: the live mode (T4.14) ---------------------------------------------
    mode: Mapped[str] = mapped_column(Text, server_default=text("'paper'"))
    """``paper`` | ``live``. The desk writes ``live`` on approval only while the
    API's ``ENABLE_MEME_LIVE_TRADING`` is on; the executor (``services/meme-executor``)
    reads ``live`` rows and the paper loop keeps filling them in shadow."""

    # --- 0041: the event a proposal is tied to (T4.26) --------------------------
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("meme_events.id"))
    """Set by the per-minute matching job (``ddl/meme_events.py``) when a
    ``meme_events`` row named this mint (by handle or symbol) in the 60 minutes
    before the mint was created. ``NULL`` for every proposal born without a
    matching event — the overwhelming majority."""


__all__ = [
    "BET_EXIT_REASONS",
    "BET_LEGS",
    "MARK_SOURCES",
    "OPERATOR_COMMANDS",
    "OUTCOME_QUALITIES",
    "PROPOSAL_STATUSES",
    "RULE_SET_KINDS",
    "MemeOperatorCommand",
    "MemePaperBet",
    "MemeProposal",
    "MemeRuleSet",
]
