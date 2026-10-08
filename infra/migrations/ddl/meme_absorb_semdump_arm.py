"""``0069_meme_absorb_semdump_arm`` — the twin of ``absorb_v0/2`` without the
``creator_dump`` exit (H-031b, EXP-M27,
``obsidian/05-EXPERIMENTS/EXP-M27-gemeo-sem-creator-dump.md``).

**Why it exists.** H-031 (R88, KB-0188) found the largest net buyer's share of
the curve's SOL does not separate the paper return, while the ``creator_dump``
exit fired 2,11x more often in the concentrated arm. The Defensor's route (2):
the exit may be what hides the difference, and only the same bet **without**
that exit can say so. Everton approved it on 07/10/2026 ("Ligar o gêmeo").

**What it is — and what it is not.** One arm, ``absorb_semdump_v0/1``
(``…0022``), ``research_only`` under ``exp_ref = 'EXP-M27'``: ``absorb_v0/2``'s
**live** document **plus** ``"exit_on_creator_dump": false`` and nothing else —
the same gate, ticket, ceilings and every other exit (trailing 10 % armed at the
entry, ``line_broken``, ``max_loss`` 50 %, 300 s). Both are ``15s`` sets judged
on the same evaluation of the event lane, so every ``absorb_v0/2`` proposal has
a twin proposal with the same ``(mint, features_end_time)`` beside it.

**Copied from the LIVE ``absorb_v0/2`` row, in the same statement** (``0065``'s
reason): a ``--set-param`` after ``0058`` lives in no constant of this tree.
``test_migration_0069`` proves ``twin - exit_on_creator_dump == original``, key
by key. The upgrade **refuses** when ``absorb_v0/2`` is missing or not active,
when it is not on the ``15s`` clock (the event lane reads only ``15s`` sets),
when the original already has the exit off (the twin would be a copy), and when
anything but this exact copy sits under the frozen name afterwards.

**The switch must be read.** ``RuleSetSpec.from_params`` reads
``exit_on_creator_dump`` (a bare JSON boolean) and every bet records it
(``EffectiveParams.as_json``); a worker without that code would run this set as
a plain copy of ``absorb_v0/2`` — ``test_migration_0069`` loads the row the way
the worker does and fails then.

**Paper by construction, not by flag** — ``kind = 'research_only'``:
``hunter_meme_executor.auto_approve`` selects only ``rs.kind = 'operator'``. The
twin's bets are subtracted from the desk's ``creator_prior_dump_count`` by id
(``lab_repo_pedigree.ABSORB_SEMDUMP_RULE_SET_ID``); it pins mints like any set
(without photos its tail after the original's ``creator_dump`` would vanish).
Nothing is retired and the desk is not touched.

**Downgrade (§17.7)** refuses while a proposal, a bet, a param-history row, a
sampled refusal or an opportunity record references the twin. The slug is 28
characters (``VARCHAR(32)``).
"""

from __future__ import annotations

from alembic import op

from ddl.meme_gate_absorb_arm import ABSORB_V0_2_RULE_SET_ID

ABSORB_SEMDUMP_RULE_SET_ID = "01994d00-6c1a-7000-8000-000000000022"
SEEDED_RULE_SET_IDS_0069: tuple[str, ...] = (ABSORB_SEMDUMP_RULE_SET_ID,)

TWIN_OVERRIDE = '{"exit_on_creator_dump": false}'
"""The only key the twin adds; every other key is ``absorb_v0/2``'s, live."""

_CODE_REF = (
    "hunter_indicators.meme.rules:evaluate_entry+evaluate_exit"
    "+hunter_meme_worker.absorb_rules:absorb_refusals"
)
"""``0058``'s own ``code_ref`` — the same evaluation, by construction."""

_SOURCE = (
    f"a.id = '{ABSORB_V0_2_RULE_SET_ID}' AND a.name = 'absorb_v0' AND a.version = '2' "
    "AND a.status = 'active'"
)
"""The one row the twin is copied from — the guards, the ``INSERT … SELECT`` and
the post-check read the same predicate, so they can never disagree."""
_VALID = (
    f"{_SOURCE} AND a.params ->> 'clock' = '15s' "
    "AND (NOT a.params ? 'exit_on_creator_dump' "
    "OR a.params -> 'exit_on_creator_dump' = 'true'::jsonb)"
)
"""The source as the guards accept it: the copy and the post-check read this, so a
document that changed between the guard and the copy is copied by nothing and
refused by the post-check, never seeded."""
_LOCK = (
    "SELECT 1 FROM meme_rule_sets "  # noqa: S608 - this module's own frozen id
    f"WHERE id = '{ABSORB_V0_2_RULE_SET_ID}' FOR NO KEY UPDATE"
)
"""Astra (H-031b-diff, must-fix 2): the original row is locked for the whole
migration transaction — a ``--set-param`` racing the deploy waits, it does not
slip between the guard and the copy. ``FOR NO KEY UPDATE``, not ``FOR UPDATE``
(database-architect review, 07/10/2026): it still conflicts with the
``UPDATE``/``DELETE`` of ``meme_rule_set.py`` (``--set-param``, ``--deprecate``),
but not with the ``FOR KEY SHARE`` every foreign-key check takes, so the
worker's inserts of ``absorb_v0/2`` proposals, bets and refusals neither wait
for the migration nor make it wait (``test_migration_0069_guards``)."""

_REFUSE_WITHOUT_THE_ORIGINAL = (
    "DO $$ BEGIN "  # noqa: S608 - this module's own frozen ids
    f"IF NOT EXISTS (SELECT 1 FROM meme_rule_sets a WHERE {_SOURCE}) THEN "
    "RAISE EXCEPTION USING MESSAGE = 'PROJECT HUNTER: absorb_v0/2 is missing or not active - "
    "absorb_semdump_v0/1 is its twin without the creator_dump exit and has nothing to pair with', "
    "HINT = 'H-031b pairs every absorb_v0/2 bet; seed the twin beside a running original'; "
    "END IF; "
    f"IF NOT EXISTS (SELECT 1 FROM meme_rule_sets a WHERE {_SOURCE} "
    "AND a.params ->> 'clock' = '15s') THEN "
    "RAISE EXCEPTION USING MESSAGE = 'PROJECT HUNTER: absorb_v0/2 is not on the 15s clock - "
    "the twin would copy a clock the event lane never reads, so no proposal would have its pair', "
    "HINT = 'the pair is judged on the event lane: seed it against a 15s original'; "
    "END IF; "
    f"IF EXISTS (SELECT 1 FROM meme_rule_sets a WHERE {_SOURCE} "
    "AND a.params -> 'exit_on_creator_dump' IS DISTINCT FROM 'true'::jsonb "
    "AND a.params ? 'exit_on_creator_dump') THEN "
    "RAISE EXCEPTION USING MESSAGE = 'PROJECT HUNTER: absorb_v0/2 does not plainly sell on "
    "the creator dump - the twin would be a copy of it, not its counterfactual', "
    "HINT = 'H-031b needs the original with the exit on: the key absent, or true'; "
    "END IF; END $$;"
)
_SEED = f"""
INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref, status)
SELECT '{ABSORB_SEMDUMP_RULE_SET_ID}', 'absorb_semdump_v0', '1', 'research_only',
       a.params || '{TWIN_OVERRIDE}'::jsonb,
       '{_CODE_REF}', 'EXP-M27', 'active'
FROM meme_rule_sets a WHERE {_VALID}
ON CONFLICT (name, version) DO NOTHING
"""  # noqa: S608 - the only interpolation is this module's own frozen constants
_REFUSE_A_STRANGER = (
    "DO $$ BEGIN "  # noqa: S608 - this module's own frozen ids
    "IF NOT EXISTS (SELECT 1 FROM meme_rule_sets t, meme_rule_sets a "
    f"WHERE {_VALID} AND t.id = '{ABSORB_SEMDUMP_RULE_SET_ID}' "
    "AND t.name = 'absorb_semdump_v0' AND t.version = '1' AND t.kind = 'research_only' "
    f"AND t.exp_ref = 'EXP-M27' AND t.status = 'active' AND t.code_ref = '{_CODE_REF}' "
    f"AND t.params = a.params || '{TWIN_OVERRIDE}'::jsonb) THEN "
    "RAISE EXCEPTION USING MESSAGE = 'PROJECT HUNTER: absorb_semdump_v0/1 exists but is not "
    "absorb_v0/2 plus exit_on_creator_dump=false under the frozen id - refusing to pair "
    "H-031b against a stranger', "
    "HINT = 'inspect meme_rule_sets WHERE name = ''absorb_semdump_v0'' before upgrading'; "
    "END IF; END $$;"
)
_UNSEED = (
    "DELETE FROM meme_rule_sets "  # noqa: S608 - this module's own frozen id
    f"WHERE id = '{ABSORB_SEMDUMP_RULE_SET_ID}'"
)


def seed_absorb_semdump() -> None:
    """Refuses without an active ``absorb_v0/2`` on ``15s`` with the exit on, and
    under a stranger; nothing is retired and the desk is not touched."""
    op.execute(_LOCK)
    op.execute(_REFUSE_WITHOUT_THE_ORIGINAL)
    op.execute(_SEED)
    op.execute(_REFUSE_A_STRANGER)


def unseed_absorb_semdump() -> None:
    op.execute(_UNSEED)


_GUARDED: tuple[tuple[str, str], ...] = (
    (
        "meme_proposals",
        "proposals reference the seeded absorb_semdump_v0 set - they are H-031b's "
        "pairs and cannot be removed under them",
    ),
    (
        "meme_paper_bets",
        "bets reference the seeded absorb_semdump_v0 set - the seed cannot be removed under them",
    ),
    (
        "meme_rule_set_param_history",
        "param history rows reference the seeded absorb_semdump_v0 set - "
        "the seed cannot be removed under them",
    ),
    (
        "meme_gate_refusals_by_mint",
        "refusal rows reference the seeded absorb_semdump_v0 set - "
        "the seed cannot be removed under them",
    ),
    (
        "meme_mature_opportunities",
        "opportunity records reference the seeded absorb_semdump_v0 set - "
        "the seed cannot be removed under them",
    ),
)
"""Every table with a ``rule_set_id`` foreign key to ``meme_rule_sets``:
``0065``'s four plus ``0066``'s opportunity record (the minute lane writes it
for minute-clock sets only, so the twin should never have one — but the guard
names it instead of leaving a bare foreign-key error)."""


def refuse_a_downgrade_that_would_orphan_a_twin_row() -> None:
    """§17.7: reversing is allowed, losing evidence is not — count, name, stop."""
    predicate = f"WHERE rule_set_id = '{ABSORB_SEMDUMP_RULE_SET_ID}'"
    safe_predicate = predicate.replace("'", "''")
    for table, why in _GUARDED:
        safe_why = why.replace("'", "''")
        op.execute(
            f"DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
            f"SELECT count(*) INTO offenders FROM {table} {predicate}; "
            f"IF offenders > 0 THEN RAISE EXCEPTION USING "
            f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' {table} rows exist - {safe_why}', "
            f"HINT = 'COPY (SELECT * FROM {table} {safe_predicate}) TO ... before reversing'; "
            f"END IF; END $$;"
        )
