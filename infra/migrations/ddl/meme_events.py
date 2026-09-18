"""``meme_events`` — the "may pump" event, and the gate that judges only a mint
tied to one (T4.26, same revision as ``ddl/meme_social.py``).

**The table.** ``id``, ``observed_at``, ``source`` (``plantao`` | ``baha`` |
``indexer_boost`` | ``dexscreener_profile`` | ``manual``), ``kind``
(``public_figure_launch`` | ``exchange_listing`` | ``viral_post`` |
``brand_launch`` | ``narrative`` | ``incident``), ``title``, ``url``, ``mint``
(nullable — the event usually precedes the coin), ``symbol_hint``,
``handle_hint``, ``confidence`` (``confirmed`` | ``reported`` | ``rumor``),
``notes`` jsonb, ``recorded_by``. Global, no RLS (§1.1), the ``meme_tokens``
shape. Written by ``hunter_worker`` (a future automated source) and by the
audited script ``infra/scripts/meme_event.py add`` (the owner connection).

**The seed: ``event_v0/1``** (``research_only``, EXP-M8, prediction
``descartar``). Only proposes a mint whose matched event is ``confirmed`` and
one of ``public_figure_launch``/``exchange_listing``/``brand_launch``
(``require_event``, T4.26's own switch, read by the worker beside
``pedigree_exclusions``/``pedigree_repeat_dumper`` — same wiring, no change to
the frozen ``evaluate_entry``). E2 exclusions on, ``dev_share ≤ 10 %``
(unknown refuses), ``snipers ≤ 25`` (deliberately wide — the bum attracts
snipers, that is not disqualifying here), no flow floor (the flow comes
*after* the announcement, ``require_positive_flow = false``); 0,05 SOL;
moonshot exits (target 10×, trailing 50 % armed after 3×, 2 h,
``exit_on_migration = false`` — hold through the migration, EXP-M4's shape).
``max_participation_pct = 20`` is this revision's own number, not in the
brief: the base gate's participation check (``rules._participation_refusals``)
is unconditional for every set, so a cap had to be chosen; 20 % is generous
next to EXP-M1's 1 %, declared rather than hidden.
"""

from __future__ import annotations

from alembic import op

from hunter_core.db.models import APP_ROLE, WORKER_ROLE

MEME_EVENTS_TABLE = "meme_events"

MEME_EVENTS_APP_READ_ONLY_TABLES: tuple[str, ...] = (MEME_EVENTS_TABLE,)
"""The desk reads the event and never records one (T4.53).

The only writer that runs as a service is the matching job, as
``hunter_worker``; a manual event is written by ``infra/scripts/meme_event.py
add`` over the owner connection. ``hunter_app`` gets ``SELECT`` and nothing
else — the ``meme_rule_sets`` shape (§52.2). Declared here, as ``0041``'s own
list, because ``ddl/tables.py``'s four classes are frozen as of ``0001``;
``test_schema_privileges.py`` unions it so every table stays in exactly one
class.
"""

MEME_EVENTS_WORKER_UPSERT_TABLES: tuple[str, ...] = (MEME_EVENTS_TABLE,)
"""``SELECT``/``INSERT``/``UPDATE``, never ``DELETE``: the job appends an event
and moves ``mint``/``matched_at``/``last_scanned_created_at`` (``0043``) on it,
and nobody erases one (§17.7 — the downgrade refuses while a row exists).
"""
EVENT_SOURCES = ("plantao", "baha", "indexer_boost", "dexscreener_profile", "manual")
EVENT_KINDS = (
    "public_figure_launch",
    "exchange_listing",
    "viral_post",
    "brand_launch",
    "narrative",
    "incident",
)
EVENT_CONFIDENCES = ("confirmed", "reported", "rumor")

EVENT_V0_RULE_SET_ID = "01994d00-6c1a-7000-8000-000000000012"
_CODE_REF = "hunter_indicators.meme.rules:evaluate_entry+evaluate_exit"

EVENT_V0_PARAMS = (
    '"gate_key": "evento_pode_dar_bum", "gate_version": 1, '
    '"exit_key": "moonshot_10x_trailing_50_apos_3x_2h_segura_migracao", "exit_version": 1, '
    '"clock": "1m", "pedigree_exclusions": true, "require_event": true, '
    '"min_age_s": 0, "max_age_s": 3600, "min_progress_pct": "0", "max_progress_pct": "100", '
    '"require_progress": false, "require_creator_not_net_seller": true, '
    '"max_participation_pct": "20", '
    '"max_dev_share": "0.10", "dev_share_unknown_allowed": false, "max_snipers": 25, '
    '"require_positive_flow": false, '
    '"size_sol": "0.05", "target_x": "10", "trailing_pct": "50", "trailing_arm_x": "3", '
    '"max_hold_s": 7200, "max_loss_pct": "50", "exit_on_migration": false, '
    '"wallet_max_sol": "2.0", "max_sol_per_bet": "0.05", "daily_loss_cap_sol": "0.20", '
    '"max_open_positions": 5, "max_exposure_per_mint_sol": "0.05", '
    '"fee_pct": "1.75", "priority_fee_sol": "0", "day_timezone": "America/Sao_Paulo"'
)

_TABLE = f"""
CREATE TABLE {MEME_EVENTS_TABLE} (
    id uuid NOT NULL,
    observed_at timestamptz NOT NULL,
    source text NOT NULL,
    kind text NOT NULL,
    title text NOT NULL,
    url text,
    mint text,
    symbol_hint text,
    handle_hint text,
    confidence text NOT NULL,
    notes jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    recorded_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    matched_at timestamptz,
    CONSTRAINT pk_meme_events PRIMARY KEY (id),
    CONSTRAINT fk_meme_events_mint_meme_tokens FOREIGN KEY (mint) REFERENCES meme_tokens (mint),
    CONSTRAINT ck_meme_events_source_is_a_known_label
        CHECK (source IN {EVENT_SOURCES!r}),
    CONSTRAINT ck_meme_events_kind_is_a_known_label CHECK (kind IN {EVENT_KINDS!r}),
    CONSTRAINT ck_meme_events_confidence_is_a_known_label
        CHECK (confidence IN {EVENT_CONFIDENCES!r}),
    CONSTRAINT ck_meme_events_title_is_not_empty CHECK (char_length(title) > 0),
    CONSTRAINT ck_meme_events_a_matched_mint_is_not_empty
        CHECK (mint IS NULL OR char_length(mint) > 0),
    CONSTRAINT ck_meme_events_a_handle_hint_is_not_empty
        CHECK (handle_hint IS NULL OR char_length(handle_hint) > 0),
    CONSTRAINT ck_meme_events_a_symbol_hint_is_not_empty
        CHECK (symbol_hint IS NULL OR char_length(symbol_hint) > 0),
    CONSTRAINT ck_meme_events_recorded_by_is_not_empty CHECK (char_length(recorded_by) > 0),
    CONSTRAINT ck_meme_events_a_match_says_when CHECK ((mint IS NULL) = (matched_at IS NULL))
)
"""

_INDEXES = (
    f"CREATE INDEX ix_meme_events_observed_at ON {MEME_EVENTS_TABLE} (observed_at)",
    f"CREATE INDEX ix_meme_events_unmatched ON {MEME_EVENTS_TABLE} (observed_at) "
    "WHERE mint IS NULL",
    f"CREATE INDEX ix_meme_events_mint ON {MEME_EVENTS_TABLE} (mint) WHERE mint IS NOT NULL",
)

_EVENT_ID_COLUMN = (
    "ALTER TABLE meme_proposals ADD COLUMN event_id uuid "
    "CONSTRAINT fk_meme_proposals_event_id_meme_events REFERENCES meme_events (id)"
)
_DROP_EVENT_ID_COLUMN = "ALTER TABLE meme_proposals DROP COLUMN IF EXISTS event_id"

_SEED = f"""
INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref, status)
VALUES ('{EVENT_V0_RULE_SET_ID}', 'event_v0', '1', 'research_only',
        '{{{EVENT_V0_PARAMS}}}'::jsonb, '{_CODE_REF}', 'EXP-M8', 'active')
ON CONFLICT (name, version) DO NOTHING
"""  # noqa: S608 - the only interpolation is this module's own frozen constants
_UNSEED = f"DELETE FROM meme_rule_sets WHERE id = '{EVENT_V0_RULE_SET_ID}'"  # noqa: S608


def create_meme_events_table() -> None:
    op.execute(_TABLE)
    for statement in _INDEXES:
        op.execute(statement)
    op.execute(_EVENT_ID_COLUMN)


def grant_meme_events_privileges() -> None:
    for table in MEME_EVENTS_APP_READ_ONLY_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {APP_ROLE}")
    for table in MEME_EVENTS_WORKER_UPSERT_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {WORKER_ROLE}")


def seed_event_v0() -> None:
    op.execute(_SEED)


def unseed_event_v0() -> None:
    op.execute(_UNSEED)


def drop_meme_events_table() -> None:
    op.execute(_DROP_EVENT_ID_COLUMN)
    op.execute(f"DROP TABLE IF EXISTS {MEME_EVENTS_TABLE}")


def refuse_a_downgrade_that_would_lose_an_event() -> None:
    """§17.7: an event is discovery history — count, name, stop. On every
    database of today it counts zero."""
    op.execute(
        "DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
        f"SELECT count(*) INTO offenders FROM {MEME_EVENTS_TABLE}; "
        "IF offenders > 0 THEN RAISE EXCEPTION USING "
        "MESSAGE = 'PROJECT HUNTER: ' || offenders || ' meme_events rows exist - an "
        "announcement nobody re-observes cannot be dropped under them', "
        f"HINT = 'COPY (SELECT * FROM {MEME_EVENTS_TABLE}) TO ... before reversing'; "
        "END IF; END $$;"
    )


def refuse_a_downgrade_that_would_orphan_an_event_v0_row() -> None:
    """§17.7: a proposal referencing ``event_v0/1`` is evidence — count, name, stop."""
    op.execute(
        "DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
        f"SELECT count(*) INTO offenders FROM meme_proposals WHERE rule_set_id = "
        f"'{EVENT_V0_RULE_SET_ID}'; "
        "IF offenders > 0 THEN RAISE EXCEPTION USING "
        "MESSAGE = 'PROJECT HUNTER: ' || offenders || ' meme_proposals rows reference the "
        "seeded event_v0/1 set - the seed cannot be removed under them', "
        "HINT = 'COPY (SELECT * FROM meme_proposals WHERE rule_set_id = "
        f"''{EVENT_V0_RULE_SET_ID}'') TO ... before reversing'; "
        "END IF; END $$;"
    )
