"""strategy_versions.eligibility_policy: the context a version may decide in

Seventeenth revision. T3.52 — the hourly regime series the T3.43 job writes
(``market_regimes``, ``scope = 'btc'``, ``classifier_version =
'regime_hourly_v1'``) is read by research SQL and by nothing that decides. A
version that should only decide in one regime has nowhere to say so: not
``default_parameters`` (the frozen ``parameters_schema`` does not declare it and
the strategy code never reads it), not ``changelog`` (prose nothing enforces).
``eligibility_policy jsonb NULL`` is where it says so, and the first-activation
trigger freezes it like ``code_ref``, ``default_parameters`` and ``purpose``.

Described in DATABASE.md section 29.

**One column, one trigger swap. Nothing else**: no enum, no index, no CHECK (the
shape is validated by the reader that fails closed,
``hunter_strategy_worker.regime_gate``, not by a constraint that would freeze a
JSON grammar into DDL), no ``GRANT`` (a column added after ``0010``'s
column-level re-grant is writable by the owner connection alone — see
``ddl/eligibility_policy.py``), no RLS (``strategy_versions`` is a global
catalogue table, §1.1).

**There is no upgrade guard, and that is an assertion**: every existing row gets
``NULL``, which is exactly what every existing row already is — a version with
no gate, deciding in every regime. No invariant is created over data that
already violates it.

**The downgrade refuses** (§17.7) when any row carries a policy: dropping the
column would let a version built to decide only in ``SIDEWAYS`` start deciding
in every regime, silently, and nothing that remains could say which regime it
had been gated to.

**Named ``0017_eligibility_policy`` (23 characters)** — ``alembic_version.version_num``
is ``VARCHAR(32)`` (section 17.6).

Revision ID: 0017_eligibility_policy
Revises: 0016_exchange_status_planned
Create Date: 2026-09-09
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.eligibility_policy import (
    add_policy_column,
    drop_policy_column,
    refuse_a_downgrade_that_would_lose_a_policy,
    replace_strategy_version_freeze,
    restore_replication_freeze,
)

revision: str = "0017_eligibility_policy"
down_revision: str | None = "0016_exchange_status_planned"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    add_policy_column()
    replace_strategy_version_freeze()


def downgrade() -> None:
    """Refuse first, then unwind in the exact reverse order of ``upgrade``."""
    refuse_a_downgrade_that_would_lose_a_policy()
    restore_replication_freeze()
    drop_policy_column()
