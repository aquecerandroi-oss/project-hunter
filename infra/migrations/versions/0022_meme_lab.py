"""meme lab: rule sets, proposals, paper bets, operator commands and two views

Twenty-second revision. **Four tables**, seven indexes, two views, a seed of two
rule sets and grants by subtraction. No enum, no RLS policy, no partition, no
column added anywhere else, and nothing touched in ``0021``.

T4.6, on the storage T4.2 committed (``0021_meme_radar``), the paper simulator
T4.5 committed (``hunter_indicators.meme``) and the contract
``.claude/state/contrato-T4.6-T4.7-mesa-meme.md`` froze on 2026-09-12 04:25 BRT
so the operator desk (T4.7) could be built in parallel. The slice is **paper
only**: ``meme_paper_bets.mode`` is ``CHECK``-locked to ``'paper'``, nothing here
is reachable by ``packages/risk-core`` or the execution path, and no key and no
live flag exist in the process that writes these rows.

**Global, RLS-free** (DATABASE.md §1.1), like the five tables of ``0021``: a
paper bet on an on-chain curve belongs to the Lab, not to an organization. No
``organization_id``, therefore no policy — and the absence is asserted by the
``LIKE 'meme%'`` tests ``0021`` already runs.

**Who writes what is a privilege here, not a promise.** The loop
(``hunter_worker``) proposes, fills, marks and closes; the API (``hunter_app``)
may insert a manual proposal or an operator command and may update exactly the
four decision columns of a proposal. Nobody has ``DELETE`` on any of the four:
a bet is evidence and an unfilled proposal is the refusal that explains a quiet
desk.

**The seed is in the revision** (``ddl/meme_lab_views.py``): ``meme_paper_v0/1``
(``research_only``, EXP-M1, the parameters of ``docs/RISK_ENGINE_MEME.md`` §3.1)
and ``operator/1`` (``operator``: the same gate, but it only proposes and waits
for the operator's approval). Both are paper ceilings; the live numbers are
Everton's (§14 there).

**No upgrade guard, and that is an assertion**: the revision creates tables that
did not exist. **The downgrade refuses** while a proposal, a bet or a command
exists, counting them and naming the ``COPY`` (§17.7); the seed alone reverses,
so the round trip runs on every database of today.

**Nothing here depends on session state**: four ``CREATE TABLE``, one ``ALTER
TABLE`` (the proposal → bet backlink), seven ``CREATE INDEX``, two ``CREATE
VIEW``, one ``INSERT`` and the grants. ``CREATE TABLE`` takes no lock on a
relation that does not yet exist and the grants lock only the catalogue: this
revision **opens no maintenance window**.

**Named ``0022_meme_lab`` (13 characters)** — ``alembic_version.version_num`` is
``VARCHAR(32)`` (§17.6). Described in ``docs/DATABASE.md`` §34.

Revision ID: 0022_meme_lab
Revises: 0021_meme_radar
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_lab import create_meme_lab_tables, drop_meme_lab_tables, grant_meme_lab_privileges
from ddl.meme_lab_views import (
    create_meme_lab_views,
    drop_meme_lab_views,
    refuse_a_downgrade_that_would_lose_meme_lab_rows,
    seed_meme_lab_rule_sets,
)

revision: str = "0022_meme_lab"
down_revision: str | None = "0021_meme_radar"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    create_meme_lab_tables()
    create_meme_lab_views()
    seed_meme_lab_rule_sets()
    grant_meme_lab_privileges()


def downgrade() -> None:
    """Refuse first, then unwind in the exact reverse order of ``upgrade``."""
    refuse_a_downgrade_that_would_lose_meme_lab_rows()
    drop_meme_lab_views()
    drop_meme_lab_tables()
