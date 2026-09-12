"""meme lab ticks: one durable row per tick of the Lab loop, with the gate's refusals

Thirty-first revision. **One table** (``meme_lab_ticks``) and grants by
subtraction. No column on an existing table, no view, no enum, no RLS policy;
nothing touched in ``0022``–``0030``.

T4.15, the daily close of the meme Lab (``infra/scripts/meme_close_day.py``,
Everton's directive of 12/09/2026: "ele vai se auto aprimorando a cada leitura,
a cada compra e venda"): the close writes the day's lessons from rows alone,
and the lesson "how much of the day did the gate see, and why did it refuse?"
had no row to read — the heartbeat's ``lab_gate_refusals`` is overwritten
every minute. From this revision the loop writes one row per tick
(``ddl/meme_lab_ticks.py``), the same counters and the same refusal
dictionary the heartbeat publishes, frozen.

**Upgrade guard: none, and that is an assertion** — the table is new.
**The downgrade refuses** while a row exists (``ddl/meme_lab_ticks.py``).

**Lock and pooler.** ``CREATE TABLE`` on a relation that does not exist takes
no lock anyone waits on. Nothing depends on session state.
**Named ``0031_meme_lab_ticks`` (19 characters)** — ``VARCHAR(32)`` (§17.6).
Described in ``docs/DATABASE.md`` §42.

**Chain.** Written in parallel with ``0030_meme_gate_v2`` (T4.16); it revises
``0030`` because that was the head on disk when the two trees were joined
(``.claude/state/notes-T4.15.md``), so the chain stays linear.

Revision ID: 0031_meme_lab_ticks
Revises: 0030_meme_gate_v2
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_lab_ticks import (
    create_meme_lab_ticks,
    drop_meme_lab_ticks,
    grant_meme_lab_ticks_privileges,
    refuse_a_downgrade_that_would_lose_the_ticks,
)

revision: str = "0031_meme_lab_ticks"
down_revision: str | None = "0030_meme_gate_v2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    create_meme_lab_ticks()
    grant_meme_lab_ticks_privileges()


def downgrade() -> None:
    """Refuse first, then unwind."""
    refuse_a_downgrade_that_would_lose_the_ticks()
    drop_meme_lab_ticks()
