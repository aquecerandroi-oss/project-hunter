"""``0065_meme_pullback_control_arm`` — the immediate-entry control of the
pullback arm (T4.95, EXP-M25, ``obsidian/05-EXPERIMENTS/EXP-M25-controle-do-recuo.md``).

**Why it exists.** H-017 (EXP-M24) pairs every ``recuo_v1/1`` arming at ``t0``
with ``operator/5``'s paper shadow of the same decision. R79
(``.claude/state/notes-R79.md`` §4) found that shadow is born only when the real
desk **accepts** the proposal: of 171 armings, 39 had it; 122 were refused by
``auto_stage1`` (the desk's own checks, which a ``research_only`` arm never
passes through), 9 expired. The control was missing by construction, not by
chance, and ``39 < 150`` pairs is a data limit that the desk's own mood sets.

**What it is — and what it is not.** One arm, ``recuo_ctrl_v1/1`` (``…001e``),
``research_only`` under ``exp_ref = 'EXP-M25'``: ``recuo_v1/1``'s own document
**minus** ``entry_pullback_pct`` / ``entry_pullback_window_s`` and nothing else —
the same gate, the same exit, the same size and paper ceilings; the entry is
immediate at ``t0`` (a set without ``entry_pullback_pct`` proposes as every set
always did, ``hunter_meme_worker.entry_pullback``). Both are ``15s`` sets judged
on the same evaluation of the same row, so every arming has a same-gate
immediate-entry proposal with ``features_end_time = t0`` beside it.

**Copied from the LIVE ``recuo_v1/1`` row, in the same statement** — ``0063``'s
reason, one step further: ``recuo_v1/1`` is itself a copy of ``operator/5``'s
live row on the day of its deploy, carried by no constant in this tree. The
seed is ``recuo_v1/1.params - PULLBACK_KEYS``, read by the same predicate the
guard checks, and ``test_migration_0065`` proves ``control = arm - the two
keys``, byte for byte. A later edit of either row splits the EXP-M25 cohort; the
control does not follow it. The upgrade **refuses** when ``recuo_v1/1`` is
missing or not active (nothing to pair with is not a control), and when its
``clock`` is anything but ``15s`` (absent/``null`` included): the event lane
reads only ``15s`` sets, and the arm arms only there.

**Paper by construction, not by flag** — ``kind = 'research_only'``:
``hunter_meme_executor.auto_approve._OPERATOR_PROPOSED`` selects only ``rs.kind
= 'operator'`` (``test_migration_0065`` runs that query against a proposal of
this arm). Its bets are subtracted from the desk's pedigree read and pin no
mint in the tracker (``lab_repo_fast._PEDIGREE``, ``tracker_pins``), exactly
like the arm's (T4.91). Nothing is retired and the desk is not touched.

**Downgrade (§17.7)** refuses while a proposal, a bet, a param-history row or a
sampled refusal references the control — ``0063``'s four. The slug is 30
characters (``VARCHAR(32)``).
"""

from __future__ import annotations

from alembic import op

from ddl.meme_pullback_entry_arm import PULLBACK_ARM_RULE_SET_ID

PULLBACK_CONTROL_RULE_SET_ID = "01994d00-6c1a-7000-8000-00000000001e"
SEEDED_RULE_SET_IDS_0065: tuple[str, ...] = (PULLBACK_CONTROL_RULE_SET_ID,)

PULLBACK_KEYS: tuple[str, ...] = ("entry_pullback_pct", "entry_pullback_window_s")
"""The only keys the control drops; every other key is ``recuo_v1/1``'s."""

_CODE_REF = "hunter_indicators.meme.rules:evaluate_entry+evaluate_exit"

_SOURCE = f"a.id = '{PULLBACK_ARM_RULE_SET_ID}' AND a.status = 'active'"
"""The one row the control is copied from — the guard and the ``INSERT …
SELECT`` read the same predicate, so the check and the copy can never disagree."""
_REFUSE_WITHOUT_THE_ARM = (
    "DO $$ BEGIN "  # noqa: S608 - this module's own frozen id
    f"IF NOT EXISTS (SELECT 1 FROM meme_rule_sets a WHERE {_SOURCE}) THEN "
    "RAISE EXCEPTION USING MESSAGE = 'PROJECT HUNTER: recuo_v1/1 is missing or not active - "
    "recuo_ctrl_v1/1 is its immediate-entry control and has nothing to pair with', "
    "HINT = 'EXP-M25 pairs every recuo_v1 arming; seed the control beside a running arm'; "
    "END IF; "
    f"IF NOT EXISTS (SELECT 1 FROM meme_rule_sets a WHERE {_SOURCE} "
    "AND a.params ->> 'clock' = '15s') THEN "
    "RAISE EXCEPTION USING MESSAGE = 'PROJECT HUNTER: recuo_v1/1 is not on the 15s clock - "
    "recuo_ctrl_v1/1 would copy a clock the event lane never reads, so no arming would "
    "have its pair', "
    "HINT = 'the pair is judged on the event lane: seed it against a 15s arm'; "
    "END IF; END $$;"
)
_DROPPED = ", ".join(f"'{key}'" for key in PULLBACK_KEYS)
_SEED = f"""
INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref, status)
SELECT '{PULLBACK_CONTROL_RULE_SET_ID}', 'recuo_ctrl_v1', '1', 'research_only',
       a.params - ARRAY[{_DROPPED}]::text[],
       '{_CODE_REF}', 'EXP-M25', 'active'
FROM meme_rule_sets a WHERE {_SOURCE}
ON CONFLICT (name, version) DO NOTHING
"""  # noqa: S608 - the only interpolation is this module's own frozen constants
_UNSEED = (
    "DELETE FROM meme_rule_sets "  # noqa: S608 - this module's own frozen id
    f"WHERE id = '{PULLBACK_CONTROL_RULE_SET_ID}'"
)


def seed_pullback_control() -> None:
    """Refuses without an active ``recuo_v1/1`` on ``15s``; idempotent on a
    database already at ``0065``; nothing is retired and the desk is not touched."""
    op.execute(_REFUSE_WITHOUT_THE_ARM)
    op.execute(_SEED)


def unseed_pullback_control() -> None:
    op.execute(_UNSEED)


_GUARDED: tuple[tuple[str, str], ...] = (
    (
        "meme_proposals",
        "proposals reference the seeded recuo_ctrl_v1 set - they are EXP-M25's "
        "immediate-entry pairs and cannot be removed under them",
    ),
    (
        "meme_paper_bets",
        "bets reference the seeded recuo_ctrl_v1 set - the seed cannot be removed under them",
    ),
    (
        "meme_rule_set_param_history",
        "param history rows reference the seeded recuo_ctrl_v1 set - "
        "the seed cannot be removed under them",
    ),
    (
        "meme_gate_refusals_by_mint",
        "refusal rows reference the seeded recuo_ctrl_v1 set - "
        "the seed cannot be removed under them",
    ),
)
"""``0063``'s four: every table with a ``rule_set_id`` foreign key to
``meme_rule_sets``."""


def refuse_a_downgrade_that_would_orphan_a_control_row() -> None:
    """§17.7: reversing is allowed, losing evidence is not — count, name, stop."""
    predicate = f"WHERE rule_set_id = '{PULLBACK_CONTROL_RULE_SET_ID}'"
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
