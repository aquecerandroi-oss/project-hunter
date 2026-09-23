"""market_events: what happened around a non-meme market, read by the confluence screen

Fifty-ninth revision. **One table** (``market_events``), three indexes, grants
by subtraction, **no seed**. No enum, no view, no partition, no trigger, no RLS
policy; nothing touched in ``0022``–``0058``.

T4.82, on Everton's decision of 23/09/2026 12:3x BRT, for §7a item 4 of
``docs/design/tela-confluencia-mercado.md``: the "Notícias" lane of the
confluence screen needs somewhere to put a listing, an incident or a macro
headline, dated and attributed. Until now the plantão read baha.com and wrote
in the vault, so none of it reached the database and therefore none of it
reached a screen.

**A new table rather than a ``kind`` on ``meme_events``**, with a failure and
not a preference behind it: ``meme_events.mint`` is an FK to
``meme_tokens.mint`` and the per-minute matching job
(``services/meme-worker/hunter_meme_worker/events_repo.py``) scans by
``observed_at`` **without filtering ``mint IS NULL``**, pairing an event with a
coin through ``symbol_hint``. A Zcash headline filed as ``symbol_hint = 'ZEC'``
would find a homonymous meme minted in the same window and start
contextualising that meme's proposals. A new ``kind`` plus a partial index does
not fix it: an index does not change the matcher's ``SELECT``.

**Global, no ``organization_id``, no RLS** (DATABASE.md §1.1) — the shape of
``0041``'s ``meme_events`` and of ``0028``'s ``meme_live_*``. Who may read it
is the API's gate: the two T4.82 endpoints sit under
``/api/v1/orgs/{org_id}/markets/...`` behind ``require_org(VIEWER)``, the same
door the ``meme_live`` router uses.

**Upgrade guard: none, and that is an assertion** — the table is new and there
is nothing to seed. **The downgrade refuses** while any row exists
(``ddl/market_events.py``, §17.7): the rows were read off a page by a human and
typed in, and the database holds no second copy of them.

**Lock and pooler.** One ``CREATE TABLE`` on a table that did not exist, three
``CREATE INDEX`` on it, two ``GRANT``s on the catalogue. Nothing depends on
session state. **Named ``0059_market_events`` (19 characters)** —
``VARCHAR(32)`` (§17.6).

``down_revision`` is ``0058_meme_gate_absorb_arm`` (T4.79), which was still
uncommitted in the shared working tree when this revision was written: chaining
onto it keeps a single linear head and leaves another task's file untouched.

Revision ID: 0059_market_events
Revises: 0058_meme_gate_absorb_arm
Create Date: 2026-09-23
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.market_events import (
    create_market_events,
    drop_market_events,
    grant_market_events_privileges,
    refuse_a_downgrade_that_would_lose_a_recorded_event,
)

revision: str = "0059_market_events"
down_revision: str | None = "0058_meme_gate_absorb_arm"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    create_market_events()
    grant_market_events_privileges()


def downgrade() -> None:
    """Refuse first, then unwind in the exact reverse order of ``upgrade``."""
    refuse_a_downgrade_that_would_lose_a_recorded_event()
    drop_market_events()
