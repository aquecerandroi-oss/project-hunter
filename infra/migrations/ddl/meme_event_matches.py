"""``meme_event_matches`` — one event may now name many coins (T4.26b):
buy-kind coins genuinely swept up by an announcement, and avoid-kind clones
the event itself warns against (KB-0100, 16/09: the "aviso" event's own
union covered 35 clones the singleton ``meme_events.mint`` could never
record, because it only ever kept the earliest match). ``meme_events.mint``/
``matched_at`` (0041) stay as they were — legacy, no longer written by the
per-minute job, which records every pair here instead.

``last_scanned_created_at`` on ``meme_events`` is the per-event cursor
(T4.26b): the matching job reads only ``meme_tokens`` created after it, so a
tick never re-scans coins it already judged.
"""

from __future__ import annotations

from alembic import op

from hunter_core.db.models import APP_ROLE, WORKER_ROLE

MEME_EVENT_MATCHES_TABLE = "meme_event_matches"
MATCH_KINDS = ("buy", "avoid")

MEME_EVENT_MATCHES_APP_READ_ONLY_TABLES: tuple[str, ...] = (MEME_EVENT_MATCHES_TABLE,)
"""The desk reads which coins an event named; it names none itself (T4.53).

``meme_events``' shape one table over (§52.3): ``hunter_app`` gets ``SELECT``
only, because a pairing a request handler could write is not evidence that the
announcement swept the coin up — it is the handler saying so.
"""

MEME_EVENT_MATCHES_WORKER_APPEND_TABLES: tuple[str, ...] = (MEME_EVENT_MATCHES_TABLE,)
"""``SELECT``/``INSERT`` and nothing else: the job writes each pair once with
``ON CONFLICT DO NOTHING`` and never rewrites ``match_kind`` — "matched once
stays matched" is a privilege here, not a convention in the writer.
"""

_CURSOR_COLUMN = "ALTER TABLE meme_events ADD COLUMN last_scanned_created_at timestamptz"
_DROP_CURSOR_COLUMN = "ALTER TABLE meme_events DROP COLUMN IF EXISTS last_scanned_created_at"

_TABLE = f"""
CREATE TABLE {MEME_EVENT_MATCHES_TABLE} (
    event_id uuid NOT NULL,
    mint text NOT NULL,
    match_kind text NOT NULL,
    matched_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pk_meme_event_matches PRIMARY KEY (event_id, mint),
    CONSTRAINT fk_meme_event_matches_event_id_meme_events
        FOREIGN KEY (event_id) REFERENCES meme_events (id),
    CONSTRAINT fk_meme_event_matches_mint_meme_tokens
        FOREIGN KEY (mint) REFERENCES meme_tokens (mint),
    CONSTRAINT ck_meme_event_matches_match_kind_is_a_known_label
        CHECK (match_kind IN {MATCH_KINDS!r})
)
"""

_INDEXES = (f"CREATE INDEX ix_meme_event_matches_mint ON {MEME_EVENT_MATCHES_TABLE} (mint)",)


def add_scan_cursor_column() -> None:
    op.execute(_CURSOR_COLUMN)


def drop_scan_cursor_column() -> None:
    op.execute(_DROP_CURSOR_COLUMN)


def create_meme_event_matches_table() -> None:
    op.execute(_TABLE)
    for statement in _INDEXES:
        op.execute(statement)


def grant_meme_event_matches_privileges() -> None:
    for table in MEME_EVENT_MATCHES_APP_READ_ONLY_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {APP_ROLE}")
    for table in MEME_EVENT_MATCHES_WORKER_APPEND_TABLES:
        op.execute(f"GRANT SELECT, INSERT ON {table} TO {WORKER_ROLE}")


def drop_meme_event_matches_table() -> None:
    op.execute(f"DROP TABLE IF EXISTS {MEME_EVENT_MATCHES_TABLE}")


def refuse_a_downgrade_that_would_lose_a_match() -> None:
    """§17.7: which coin an event named is evidence — count, name, stop."""
    op.execute(
        "DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
        f"SELECT count(*) INTO offenders FROM {MEME_EVENT_MATCHES_TABLE}; "
        "IF offenders > 0 THEN RAISE EXCEPTION USING "
        "MESSAGE = 'PROJECT HUNTER: ' || offenders || ' meme_event_matches rows exist - a "
        "coin an event named cannot be forgotten under them', "
        f"HINT = 'COPY (SELECT * FROM {MEME_EVENT_MATCHES_TABLE}) TO ... before reversing'; "
        "END IF; END $$;"
    )
