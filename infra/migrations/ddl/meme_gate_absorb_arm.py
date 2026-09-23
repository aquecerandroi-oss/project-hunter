"""``0058_meme_gate_absorb_arm`` — "sell absorption" as a pre-registered
research family with its own control (T4.79, EXP-M22,
``obsidian/05-EXPERIMENTS/EXP-M22-absorcao-de-venda.md``).

**The hypothesis, as data.** Astra (20/09/2026, item 4 of the strategy
review over R62/R64): a sell ≥ 5 % of the curve's real SOL is the trigger
that precedes the dumps (KB-0143), but alone it does not tell a dump from a
shake-out — **who absorbs it does**. So the treatment enters only after the
price is back at the pre-sell level within 30 s and stays there 10 s; the
control enters right after the same sell. Frozen thresholds, no grid.

**Two arms, one difference.** Both are ``research_only`` under
``exp_ref = 'EXP-M22'`` on the **15-second clock** (``clock = "15s"``: the
event lane reads its sets from the same cache as the fast lane —
``event_gate_caches.refresh_event_gate_caches`` keeps ``clock == "15s"`` —
exactly as ``flow_v2/8``–``/10`` are read; ``clock = "event"`` is the
**launch lane's** marker (``0053``), whose loader would refuse these params):

- ``absorb_v0/1`` (``…001a``) = :data:`ABSORB_BASE` + ``require_absorb_confirmed: true``;
- ``absorb_v0/2`` (``…001b``) = :data:`ABSORB_BASE` + ``require_absorb_sell_seen: true``.

``test_migration_0058`` proves ``/1.params − require_absorb_confirmed ==
/2.params − require_absorb_sell_seen`` byte for byte. The two switches are
read by ``RuleSetSpec.from_params`` (``lab_models``, T4.79) and judged by
``hunter_meme_worker.absorb_rules`` beside ``require_event``; the readings
come from ``hunter_meme_worker.absorb.AbsorbTracker`` inside the event lane's
``MintEventState`` — **only the event lane** fills them, so on the 15-second
lane both sets refuse every row ``absorb_unknown`` (fail closed, by name),
as ``flow_v2/10`` does for the crowd.

**The base gate is the pre-registration's universe, not ``flow_v2``'s.** Age
30–300 s, curve not migrated (``evaluate_entry``'s own ``migrated``), not
Mayhem (``exclude_mayhem``), participation ≤ 1 % of the minute's volume (the
desk's own ceiling; the tape needs 60 s of coverage, so the useful age is
60–300 s on both arms alike), the pedigree exclusions every set carries. No
progress window (``require_progress: false``), **no** creator criterion (the
creator's sell may be the trigger itself — FЕРЕ in R62), no flow/holders/
snipers keys: the family tests the absorption sequence, not one more
threshold of the flow gate. Ticket and exit are the desk's (``operator/6``,
``0055``): 0,07 SOL, target 1,15×, trailing 10 % armed at the entry, 300 s,
``line_broken``, ``max_loss`` 50 %; ``fee_pct "1.25"`` (the fee R62/R64
measured, the pre-registration's own cost); ``max_open_positions 3``;
``ttl_s 180``. Decimals are **strings** (the Lab refuses a bare float).

**Paper by construction, not by flag** — ``kind = 'research_only'`` and
``hunter_meme_executor.auto_approve`` only ever opens proposals of a ``kind =
'operator'`` set. Nothing is retired, the desk is not touched. The slug is
25 characters (``alembic_version.version_num`` is ``VARCHAR(32)``).
"""

from __future__ import annotations

from alembic import op

ABSORB_V0_1_RULE_SET_ID = "01994d00-6c1a-7000-8000-00000000001a"
ABSORB_V0_2_RULE_SET_ID = "01994d00-6c1a-7000-8000-00000000001b"
SEEDED_RULE_SET_IDS_0058: tuple[str, ...] = (ABSORB_V0_1_RULE_SET_ID, ABSORB_V0_2_RULE_SET_ID)

ABSORB_BASE = (
    '"gate_key": "absorcao_de_venda", "gate_version": 1, '
    '"exit_key": "alvo_1_15x_trailing_10_tempo_5m", "exit_version": 1, '
    '"clock": "15s", "pedigree_exclusions": true, "exclude_mayhem": true, '
    '"min_age_s": 30, "max_age_s": 300, "min_progress_pct": "0", "max_progress_pct": "100", '
    '"require_progress": false, "require_creator_not_net_seller": false, '
    '"max_participation_pct": "1", '
    '"size_sol": "0.07", "target_x": "1.15", "trailing_pct": "10", "trailing_arm_x": null, '
    '"max_hold_s": 300, "max_loss_pct": "50", '
    '"exit_on_line_break": true, "line_break_snapshots": 2, '
    '"wallet_max_sol": "2.0", "max_sol_per_bet": "0.07", "daily_loss_cap_sol": "0.20", '
    '"max_open_positions": 3, "max_exposure_per_mint_sol": "0.07", '
    '"fee_pct": "1.25", "priority_fee_sol": "0", "ttl_s": 180, '
    '"day_timezone": "America/Sao_Paulo"'
)
"""Everything the two arms share; the absorption thresholds (5 %, 30 s, 10 s,
60 s) are **not** params — frozen in ``hunter_meme_worker.absorb`` — so moving
one is a new feature version, never an edit of a live row."""

TREATMENT_OVERRIDE = '"require_absorb_confirmed": true'
CONTROL_OVERRIDE = '"require_absorb_sell_seen": true'

_CODE_REF = (
    "hunter_indicators.meme.rules:evaluate_entry+evaluate_exit"
    "+hunter_meme_worker.absorb_rules:absorb_refusals"
)

_SEED = f"""
INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref, status)
VALUES
  ('{ABSORB_V0_1_RULE_SET_ID}', 'absorb_v0', '1', 'research_only',
   '{{{ABSORB_BASE}}}'::jsonb || '{{{TREATMENT_OVERRIDE}}}'::jsonb,
   '{_CODE_REF}', 'EXP-M22', 'active'),
  ('{ABSORB_V0_2_RULE_SET_ID}', 'absorb_v0', '2', 'research_only',
   '{{{ABSORB_BASE}}}'::jsonb || '{{{CONTROL_OVERRIDE}}}'::jsonb,
   '{_CODE_REF}', 'EXP-M22', 'active')
ON CONFLICT (name, version) DO NOTHING
"""  # noqa: S608 - the only interpolation is this module's own frozen constants
_UNSEED = (
    "DELETE FROM meme_rule_sets "  # noqa: S608 - this module's own frozen ids
    f"WHERE id IN ('{ABSORB_V0_1_RULE_SET_ID}', '{ABSORB_V0_2_RULE_SET_ID}')"
)


def seed_absorb_arms() -> None:
    """Idempotent on a database already at ``0058``; nothing is retired, and
    the desk is not touched (both arms are paper only)."""
    op.execute(_SEED)


def unseed_absorb_arms() -> None:
    op.execute(_UNSEED)


_GUARDED: tuple[tuple[str, str], ...] = (
    (
        "meme_proposals",
        "proposals reference a seeded absorb_v0 set - the seed cannot be removed under them",
    ),
    (
        "meme_paper_bets",
        "bets reference a seeded absorb_v0 set - the seed cannot be removed under them",
    ),
    (
        "meme_rule_set_param_history",
        "param history rows reference a seeded absorb_v0 set - "
        "the seed cannot be removed under them",
    ),
    (
        "meme_gate_refusals_by_mint",
        "refusal rows reference a seeded absorb_v0 set - the seed cannot be removed under them",
    ),
)
"""``0049``–``0054``'s four: every table with a ``rule_set_id`` foreign key to
``meme_rule_sets``, named so the ``DELETE`` fails with the §17.7 sentence
that says what was about to be lost and how to copy it out first."""


def refuse_a_downgrade_that_would_orphan_an_absorb_row() -> None:
    """§17.7: reversing is allowed, losing evidence is not — count, name, stop."""
    predicate = f"WHERE rule_set_id IN ('{ABSORB_V0_1_RULE_SET_ID}', '{ABSORB_V0_2_RULE_SET_ID}')"
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
