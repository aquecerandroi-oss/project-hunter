"""``0059_market_events`` — the non-meme news row (T4.82, design
``docs/design/tela-confluencia-mercado.md`` §7a item 4).

**One table, three indexes, grants by subtraction, no seed.** Global and
RLS-free (DATABASE.md §1.1), the shape of ``meme_events``: a headline belongs
to the world, not to an organization. No enum, no partition, no view, no
trigger.

Why a new table and not a ``kind`` on ``meme_events`` is argued in the model's
own docstring (``hunter_core/db/models/market_events.py``) with the concrete
failure it prevents — the meme matcher scanning by ``observed_at`` without
filtering ``mint IS NULL`` and attaching a Zcash headline to a homonymous
meme.

**Who writes what.** ``hunter_app``: ``SELECT``, and nothing else — the
confluence screen is a pure read (design §6, "Sem POST"), and the one writer
today is the audited operator script ``infra/scripts/market_event.py``, which
connects as the owner through ``DATABASE_URL_MIGRATIONS``. ``hunter_worker``:
``SELECT, INSERT, UPDATE``, for the collector §8 says will eventually replace
the plantão's hand — granted here so that arrival is a deployment, not a
migration. ``DELETE`` to nobody: a headline that turns out to be wrong is
corrected through ``confidence``/``notes``, never erased.

**The downgrade refuses** (§17.7) while any row exists: these rows are read by
hand off baha.com by the shift, and no other copy of them is in the database.
"""

from __future__ import annotations

from alembic import op

from hunter_core.db.models import APP_ROLE, WORKER_ROLE

MARKET_EVENTS_TABLE_0059 = "market_events"

MARKET_EVENT_SOURCES_0059: tuple[str, ...] = ("baha", "manual", "plantao", "exchange_notice")
MARKET_EVENT_KINDS_0059: tuple[str, ...] = (
    "listing",
    "delisting",
    "upgrade",
    "incident",
    "macro",
    "company",
    "narrative",
)
MARKET_EVENT_CONFIDENCES_0059: tuple[str, ...] = ("confirmed", "reported", "rumor")


def _labels(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


CREATE_MARKET_EVENTS = f"""
CREATE TABLE market_events (
    id uuid NOT NULL,
    market_id uuid,
    exchange text,
    symbol text NOT NULL,
    source text NOT NULL,
    kind text NOT NULL,
    title text NOT NULL,
    url text,
    published_at timestamptz,
    observed_at timestamptz NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now(),
    confidence text NOT NULL,
    notes jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    recorded_by text NOT NULL,
    CONSTRAINT pk_market_events PRIMARY KEY (id),
    CONSTRAINT fk_market_events_market_id_markets
        FOREIGN KEY (market_id) REFERENCES markets (id),
    CONSTRAINT ck_market_events_source_is_a_known_label
        CHECK (source IN ({_labels(MARKET_EVENT_SOURCES_0059)})),
    CONSTRAINT ck_market_events_kind_is_a_known_label
        CHECK (kind IN ({_labels(MARKET_EVENT_KINDS_0059)})),
    CONSTRAINT ck_market_events_confidence_is_a_known_label
        CHECK (confidence IN ({_labels(MARKET_EVENT_CONFIDENCES_0059)})),
    CONSTRAINT ck_market_events_identity_is_not_empty
        CHECK (char_length(title) > 0 AND char_length(symbol) > 0
               AND char_length(recorded_by) > 0),
    CONSTRAINT ck_market_events_a_url_is_not_empty
        CHECK (url IS NULL OR char_length(url) > 0),
    CONSTRAINT ck_market_events_an_exchange_is_not_empty
        CHECK (exchange IS NULL OR char_length(exchange) > 0)
)
"""
"""``market_id`` nullable with an FK, ``symbol`` NOT NULL: a headline can be
filed before the pair joins the monitored universe (design §9). No
``organization_id``, therefore nothing for an RLS policy to key on."""

MARKET_EVENTS_INDEXES: tuple[str, ...] = (
    "CREATE INDEX ix_market_events_symbol_published_at ON market_events (symbol, published_at)",
    "CREATE INDEX ix_market_events_symbol_observed_at ON market_events (symbol, observed_at)",
    "CREATE UNIQUE INDEX uq_market_events_source_url_symbol "
    "ON market_events (source, url, symbol) WHERE url IS NOT NULL",
)
"""The screen reads by ``symbol`` and a time window. It orders on
``COALESCE(published_at, observed_at)``, which neither b-tree serves directly;
both are here because the selective half is the ``symbol`` equality prefix they
share, and because the two orderings are the two honest answers to "when" (an
item with no publication instant is placed by when we saw it).

Ascending, not ``DESC``: Postgres reads a b-tree backwards at no cost, and an
expression/ordered index is something ``alembic check`` cannot compare against
the model (§17.3) — the DESC would buy nothing and cost the guard that catches
drift between this DDL and ``models/market_events.py``. Astra's review of this
revision suggested going further, to a single expression index on
``(symbol, COALESCE(published_at, observed_at) DESC, id DESC)``, which is what
the read actually orders by; it is **not** taken here because it could not be
validated against a live Postgres in this task (no Docker) and an unverified
expression index is exactly the drift the paragraph above avoids. Left to the
``database-architect`` review, with an ``EXPLAIN (ANALYZE, BUFFERS)``.

The partial unique is ``(source, url, symbol)``, not ``(source, url)`` as the
design wrote it. Astra's review found the case: one Binance announcement can
name ZECUSDT *and* BTCUSDT, and on ``(source, url)`` the second filing is
swallowed as a duplicate, so the BTCUSDT screen never shows a headline that is
genuinely about it. With ``symbol`` the intended property survives — re-running
the same link for the same market writes one row — without the one nobody
asked for. Partial because a row with no url has nothing to be idempotent on:
several distinct headlines from one source legitimately carry no link."""


def create_market_events() -> None:
    op.execute(CREATE_MARKET_EVENTS)
    for statement in MARKET_EVENTS_INDEXES:
        op.execute(statement)


def grant_market_events_privileges() -> None:
    """``hunter_app`` reads; ``hunter_worker`` will write. Nobody deletes."""
    op.execute(f"GRANT SELECT ON {MARKET_EVENTS_TABLE_0059} TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON {MARKET_EVENTS_TABLE_0059} TO {WORKER_ROLE}")


def drop_market_events() -> None:
    op.execute(f"DROP TABLE IF EXISTS {MARKET_EVENTS_TABLE_0059}")


def refuse_a_downgrade_that_would_lose_a_recorded_event() -> None:
    """§17.7: reversing is allowed, losing the shift's reading is not — lock,
    count, name, stop.

    The lock comes first, for the reason ``ddl/spot_desk.py`` spells out:
    counting and then dropping leaves a window in which a row is written
    between the two. ``LOCK TABLE`` inside the migration's transaction is the
    lock the ``DROP`` takes anyway, only earlier.

    Any row counts, not just the ones with a url. Unlike an order, a headline
    has no second copy anywhere in the database: it was read off a page by a
    human and typed in. The hint names the ``COPY`` that makes the reversal
    safe.
    """
    op.execute(f"LOCK TABLE {MARKET_EVENTS_TABLE_0059} IN ACCESS EXCLUSIVE MODE")
    op.execute(
        "DO $$ DECLARE recorded bigint; BEGIN "
        "SELECT count(*) INTO recorded FROM market_events; "
        "IF recorded > 0 THEN RAISE EXCEPTION USING "
        "MESSAGE = 'PROJECT HUNTER: ' || recorded || ' market_events rows were recorded by hand "
        "off the sources (docs/design/tela-confluencia-mercado.md section 8); dropping the table "
        "loses the only copy of what the shift read', "
        "HINT = 'COPY (SELECT * FROM market_events) TO ... before reversing'; "
        "END IF; END $$;"
    )


__all__ = [
    "CREATE_MARKET_EVENTS",
    "MARKET_EVENTS_INDEXES",
    "MARKET_EVENTS_TABLE_0059",
    "MARKET_EVENT_CONFIDENCES_0059",
    "MARKET_EVENT_KINDS_0059",
    "MARKET_EVENT_SOURCES_0059",
    "create_market_events",
    "drop_market_events",
    "grant_market_events_privileges",
    "refuse_a_downgrade_that_would_lose_a_recorded_event",
]
