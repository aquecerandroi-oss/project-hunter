"""SQLAlchemy Core metadata for the operator desk (T4.7): the four tables of
the frozen contract ``.claude/state/contrato-T4.6-T4.7-mesa-meme.md``
(``meme_rule_sets``, ``meme_proposals``, ``meme_operator_commands``,
``meme_paper_bets``), declared on T4.3's private ``MEME_METADATA`` so the desk
can join them to ``meme_tokens``/``meme_curve_snapshots``/``meme_features_1m``
(``repositories/meme_tables.py``). Every column below is copied from the
contract's tables verbatim; the migration ``0022_meme_lab`` is T4.6's
(``infra/migrations/**`` is outside this task), which is why these are
declared here instead of imported from ``hunter_core.db.models`` — the same
reason ``meme_tables.py`` did it for ``0021`` (``notes-T4.3.md``).

The API writes **only** ``meme_proposals`` (``status``/``decision``/
``decided_by``/``decided_at`` on approve/reject; an ``INSERT`` for a manual
proposal) and ``INSERT``s into ``meme_operator_commands`` — never
``meme_paper_bets`` (contract §Papéis: the loop, as ``hunter_worker``, is the
only writer of bets).
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Numeric, Table, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from hunter_api.repositories.meme_tables import MEME_METADATA

__all__ = [
    "meme_operator_commands",
    "meme_paper_bets",
    "meme_proposals",
    "meme_rule_sets",
]

meme_rule_sets = Table(
    "meme_rule_sets",
    MEME_METADATA,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("name", Text, nullable=False),
    Column("version", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("params", JSONB(none_as_null=True), nullable=False),
    Column("code_ref", Text),
    Column("exp_ref", Text),
    Column("status", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("retired_at", DateTime(timezone=True)),
)

meme_proposals = Table(
    "meme_proposals",
    MEME_METADATA,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("mint", Text, nullable=False),
    Column("rule_set_id", UUID(as_uuid=True), nullable=False),
    Column("origin", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("proposed_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("features_end_time", DateTime(timezone=True)),
    Column("quote", JSONB(none_as_null=True)),
    Column("reasons", JSONB(none_as_null=True)),
    Column("suggested", JSONB(none_as_null=True)),
    Column("decision", JSONB(none_as_null=True)),
    Column("decided_by", Text),
    Column("decided_at", DateTime(timezone=True)),
    Column("bet_id", UUID(as_uuid=True)),
    Column("refusal", Text),
    # 0028 (T4.14): ``paper`` | ``live``.
    Column("mode", Text, nullable=False, server_default="paper"),
)

meme_operator_commands = Table(
    "meme_operator_commands",
    MEME_METADATA,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("bet_id", UUID(as_uuid=True)),
    Column("command", Text, nullable=False),
    Column("proposal_id", UUID(as_uuid=True)),
    Column("issued_by", Text, nullable=False),
    Column("issued_at", DateTime(timezone=True), nullable=False),
    Column("applied_at", DateTime(timezone=True)),
    Column("result", JSONB(none_as_null=True)),
)

meme_paper_bets = Table(
    "meme_paper_bets",
    MEME_METADATA,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("proposal_id", UUID(as_uuid=True), nullable=False),
    Column("rule_set_id", UUID(as_uuid=True), nullable=False),
    Column("mint", Text, nullable=False),
    Column("mode", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("entry_at", DateTime(timezone=True), nullable=False),
    Column("entry", JSONB(none_as_null=True), nullable=False),
    Column("initial_risk_sol", Numeric(), nullable=False),
    Column("params", JSONB(none_as_null=True), nullable=False),
    Column("exit_at", DateTime(timezone=True)),
    Column("exit", JSONB(none_as_null=True)),
    Column("pnl_sol", Numeric()),
    Column("r_multiple", Numeric()),
    Column("mark_sol", Numeric()),
    Column("mark_at", DateTime(timezone=True)),
    Column("high_water_x", Numeric()),
    Column("sol_usd_at_entry", Numeric()),
    Column("sol_usd_at_exit", Numeric()),
    # 0026 (T4.10) — probe and scale legs.
    Column("parent_bet_id", UUID(as_uuid=True)),
    Column("leg", Text, nullable=False),
    # 0029 (T4.11) — ``mark_source``/``mark_stale_s`` are deliberately NOT here:
    # ``select(meme_paper_bets)`` must keep working on a database still at
    # ``0028``; they are read tolerantly by ``repositories/meme_desk_marks.py``.
)
