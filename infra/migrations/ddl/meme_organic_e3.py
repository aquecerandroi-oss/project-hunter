"""``0035_meme_organic_e3`` — the "slow organic" arm, E3 of the study of the 21 bets (T4.22, EXP-M7).

**Why (measured 12/09/2026):** 35 measured paper closes at −9,4 R; in 31 of 35 the
coin never traded above the entry (``high_water_x ≤ 1,0``); the creator dumped in
22. Every live set buys 30–300 s after creation — the top of the bots' pump. E3
enters **later**, on the closed minute, when the curve crosses 10–30 % with holders
≥ 20 and rising, the top-10 share ≤ 30 % (read ≥ 3 min after creation, M-D5),
snipers ≤ 2, dev ≤ 10 %, the creator not a net seller, the E2 exclusions — and
**holds through completion and migration** (``exit_on_migration = false``, marked on
the pool's tape, T4.11): target 5×, trailing 40 % armed after 2×, 60 min, floor 50 %.
The hypothesis is Kamat's tail (plantão run 12): the slow, organically bought cell
is where the payers live. Prediction on the EXP-M7 page: ``descartar``.

**The seed plants one set** — ``organic_v0/1`` (``…000d``, ``research_only``,
EXP-M7, ``clock = 1m``) — as ``FLOW_V2_PARAMS`` composed in SQL with E3's numbers
written over it; nothing retires. The downgrade refuses while a proposal or a bet
references it (§17.7).
"""

from __future__ import annotations

from alembic import op

from ddl.meme_gate_v2_seed import FLOW_V2_PARAMS

ORGANIC_V0_RULE_SET_ID = "01994d00-6c1a-7000-8000-00000000000d"

ORGANIC_OVERRIDES = (
    '"gate_key": "organica_lenta", "gate_version": 1, '
    '"exit_key": "alvo_5x_trailing_40_apos_2x_tempo_60m_segura_migracao", "exit_version": 1, '
    '"clock": "1m", "pedigree_exclusions": true, '
    '"min_age_s": 180, "max_age_s": 1800, "min_progress_pct": "10", "max_progress_pct": "30", '
    '"require_progress": true, "require_progress_rising": true, '
    '"require_positive_flow": true, "min_unique_buyers": 5, "max_sells_to_buys": "0.8", '
    '"min_holders": 20, "require_holders_rising": true, "holders_rising_or_flat": false, '
    '"max_top10_share": "0.30", "max_snipers": 2, '
    '"max_dev_share": "0.10", "dev_share_unknown_allowed": false, '
    '"creator_unknown_allowed_if_dev_measured": false, "progress_or_mcap_rising": false, '
    '"require_creator_not_net_seller": true, "max_participation_pct": "1", '
    '"size_sol": "0.05", "target_x": "5", "trailing_pct": "40", "trailing_arm_x": "2", '
    '"max_hold_s": 3600, "max_loss_pct": "50", "exit_on_migration": false, '
    '"exit_on_line_break": false, '
    '"max_open_positions": 3, "max_sol_per_bet": "0.05", "max_exposure_per_mint_sol": "0.05"'
)
"""E3 as the study wrote it; every number restated so the seed says what it plants."""

_CODE_REF = "hunter_indicators.meme.rules:evaluate_entry+evaluate_exit"

_SEED = f"""
INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref, status)
VALUES
  ('{ORGANIC_V0_RULE_SET_ID}', 'organic_v0', '1', 'research_only',
   '{{{FLOW_V2_PARAMS}}}'::jsonb || '{{{ORGANIC_OVERRIDES}}}'::jsonb,
   '{_CODE_REF}', 'EXP-M7', 'active')
ON CONFLICT (name, version) DO NOTHING
"""  # noqa: S608 - the only interpolation is this module's own frozen constants
_UNSEED = (
    "DELETE FROM meme_rule_sets "  # noqa: S608 - this module's own frozen id
    f"WHERE id = '{ORGANIC_V0_RULE_SET_ID}'"
)


def seed_organic_e3() -> None:
    """Idempotent on a database already at ``0035``."""
    op.execute(_SEED)


def unseed_organic_e3() -> None:
    op.execute(_UNSEED)


_GUARDED: tuple[tuple[str, str], ...] = (
    (
        "meme_proposals",
        "proposals reference the seeded organic_v0/1 set - the seed cannot be removed under them",
    ),
    (
        "meme_paper_bets",
        "bets reference the seeded organic_v0/1 set - the seed cannot be removed under them",
    ),
)


def refuse_a_downgrade_that_would_orphan_an_organic_row() -> None:
    """§17.7: reversing is allowed, losing evidence is not — count, name, stop."""
    predicate = f"WHERE rule_set_id = '{ORGANIC_V0_RULE_SET_ID}'"
    safe_predicate = predicate.replace("'", "''")
    for table, why in _GUARDED:
        op.execute(
            f"DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
            f"SELECT count(*) INTO offenders FROM {table} {predicate}; "
            f"IF offenders > 0 THEN RAISE EXCEPTION USING "
            f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' {table} rows exist - {why}', "
            f"HINT = 'COPY (SELECT * FROM {table} {safe_predicate}) TO ... before reversing'; "
            f"END IF; END $$;"
        )
