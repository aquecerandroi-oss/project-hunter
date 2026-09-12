"""meme activity: the tape by batch — one table, three columns on each feature series

Thirty-second revision. **One table** (``meme_market_activity_1m``, monthly
``RANGE`` on ``end_time``, four initial months, grants by subtraction) and
**three nullable columns** on ``meme_features_1m`` and ``meme_features_15s``
(``tape_source``, ``tape_window_s``, ``tape_as_of``) with three CHECKs each
and no backfill. No enum, no view, no RLS policy; nothing touched in
``0022``–``0031``.

T4.2g, on the tape of ``0023`` and the 15-second series of ``0030``: the
per-mint tape is capped by Cloudflare at ~20 requests per 60 s per IP
(T4.2f, measured), so it covered ~40 % of the gate's rows a minute and the
flow gate refused ~100 of ~110 young coins a tick for want of a tape.
``POST /v1/coins/market-activity/batch`` counts 50 coins per request
(``ddl/meme_activity.py``): three requests a minute cover the tracked set,
and every feature row now names where its tape came from.

**Upgrade guard: none, and that is an assertion** — a new table, nullable
columns, no backfill. **The downgrade refuses** while the activity table holds
a row or a feature row names the batch as its tape (``ddl/meme_activity.py``).

**Lock and pooler.** ``CREATE TABLE`` on a relation that does not exist takes
no lock anyone waits on; ``ADD COLUMN`` of nullable columns without a default
is catalogue-only on PG 16; ``ADD CONSTRAINT CHECK`` scans the two series once
(the predicates hold trivially on rows where the columns are ``NULL``).
Nothing depends on session state. **Named ``0032_meme_activity`` (18
characters)** — ``VARCHAR(32)`` (§17.6). Described in ``docs/DATABASE.md`` §44.

Revision ID: 0032_meme_activity
Revises: 0031_meme_lab_ticks
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_activity import (
    add_tape_source_columns,
    create_meme_market_activity,
    drop_meme_market_activity,
    drop_tape_source_columns,
    refuse_a_downgrade_that_would_lose_the_activity,
)

revision: str = "0032_meme_activity"
down_revision: str | None = "0031_meme_lab_ticks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    create_meme_market_activity()
    add_tape_source_columns()


def downgrade() -> None:
    """Refuse first, then unwind in the exact reverse order of ``upgrade``."""
    refuse_a_downgrade_that_would_lose_the_activity()
    drop_tape_source_columns()
    drop_meme_market_activity()
