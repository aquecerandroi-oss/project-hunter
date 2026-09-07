"""paper geometry: what was asked, and what is only dust

Ninth revision. Two columns, one CHECK each, one partial index and three
refusals added to the request guard. Described in DATABASE.md section 21; it
closes one blocking gap and one "must fix" that three tasks reached from three
directions.

1. **``trade_proposals.request_payload jsonb NULL``** - the geometry of a filed
   request. ``trade_proposals`` stored the *identity* of a request (key and
   digest) and none of its inputs, so a row filed by the API could be recognised
   and never decided: ``notes-T3.5.md`` section 5.1 records the execution worker
   logging ``pending_request_without_geometry`` once per second, for ever,
   because ``entry_ref``, ``stop``, ``assumed_costs`` and the ceiling exist
   nowhere in the schema. The column carries them as canonical JSON - money as
   strings - and a CHECK makes a malformed payload unrepresentable.
2. **``positions.is_residual boolean NOT NULL DEFAULT false``** - the dust a spot
   exit leaves behind, below the venue's minimum quantity and unsellable at any
   price. Until now it sat in ``status = 'closing'`` with ``qty > 0`` and every
   reader of "live positions" counted it: a slot held for ever, exposure that is
   not exposure and a second order in that coin refused as a duplicate
   (``review-T3.5.md`` item 3, reproduced four hours after a stop). ``CHECK (NOT
   is_residual OR status = 'closing')`` keeps the flag on the one state that can
   hold dust, and ``ix_positions_org_portfolio_live`` is the index the readers
   need once their predicate grows a term.
3. **the request guard gains two refusals** (S1 of
   ``.claude/state/review-T3.1c-security.md``): a request filed by the API must
   carry its ``request_payload``, and may **not** carry a ``request_digest`` or a
   ``kill_switch_snapshot``. A digest chosen by the caller is a proof chosen by
   the party it exists to bind, and the engine read it back with
   ``coalesce(request_digest, ...)``; it now recomputes it from the payload.

**``trade_proposals.signal_id`` is deliberately not added**: it has existed since
``0001_initial_schema`` (section 7), nullable, with its ``agent_signals`` foreign
key and its index. The T3.14 bridge writes the column that is already there.

**There is no upgrade guard, and that is an assertion.** ``request_payload`` is
nullable and every stored row is honestly null; ``is_residual`` defaults to
``false`` and every stored position honestly is not dust; the CHECK on the
payload only speaks about non-null values and the widened trigger fires on
``INSERT`` only, so no existing row becomes unrepresentable. ``0002``/``0003``/
``0006`` stop where they stop because they create invariants over data that
exists; this one creates none - the same statement ``0007`` (section 19.5) and
``0008`` (section 20.5) make.

**The downgrade refuses twice**, in the section 17.7 boundary - reversing is
allowed, losing an obligation or a distinction is not: a proposal that carries a
payload (dropping it makes every pending request undecidable for ever) and a
position marked residual (dropping it makes dust a live position again). The
guard names them and counts them; it never deletes anything.

Nothing here depends on session state: two columns, two constraints, one partial
index and a trigger that reads only ``NEW`` and ``pg_has_role``. No
session-level prepared statement, no ``LISTEN``/``NOTIFY``, no session advisory
lock.

**Named ``0009_paper_geometry`` (19 characters)** - ``alembic_version.version_num``
is ``VARCHAR(32)`` (section 17.6).

Revision ID: 0009_paper_geometry
Revises: 0008_paper_roles_2
Create Date: 2026-09-07
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.paper_geometry import (
    add_columns,
    create_request_guard_0009,
    drop_columns,
    refuse_a_downgrade_that_would_lose_a_request_or_hide_dust,
)
from ddl.paper_roles import create_request_guard, drop_request_guard

revision: str = "0009_paper_geometry"
down_revision: str | None = "0008_paper_roles_2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    add_columns()
    create_request_guard_0009()


def downgrade() -> None:
    """Refuse first, then put ``0007``'s own guard back and drop the columns.

    The guard is restored by calling ``ddl.paper_roles.create_request_guard``
    rather than by writing ``0007``'s body out again: reverting to ``0008`` means
    having the guard ``0007`` describes, and ``ddl/paper_roles.py`` is that
    description - the same direction ``0008``'s downgrade takes back to
    ``0006`` (section 20.3). It has to happen **before** the column goes, since
    ``0007``'s body does not mention ``request_payload`` and ``0009``'s does.
    """
    refuse_a_downgrade_that_would_lose_a_request_or_hide_dust()
    drop_request_guard()
    create_request_guard()
    drop_columns()
