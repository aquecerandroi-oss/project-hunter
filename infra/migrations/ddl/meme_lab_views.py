"""The two read models of ``0022_meme_lab``, its seed and its downgrade guard.

Split from ``ddl/meme_lab.py`` for the 350-line budget, the cut
``meme_radar_guards.py`` took: the *shape* of the schema is there, what the API
reads and what the revision plants are here.

**The seed is part of the revision, not of a script.** The two rule sets the
contract names are the Lab's first pre-registered arms, and a Lab that started
with an empty ``meme_rule_sets`` would be a loop that runs and proposes nothing
while looking alive — the "silent zero" the contract forbids. Their parameters
are the ``meme_paper_v0`` profile of ``docs/RISK_ENGINE_MEME.md`` §3.1 exactly as
EXP-M1 froze them (``obsidian/05-EXPERIMENTS/EXP-M1-comprar-cedo-na-curva.md``):
every decimal is a JSON **string** so ``Decimal`` reads it byte for byte, and the
values are paper ceilings — the live ones are Everton's to write (§14 there).

**Every scoreboard number is derived from ``meme_paper_bets`` alone**, never from
memory of a process: a restart of the worker changes nothing on the board.
"""

from __future__ import annotations

from alembic import op

from hunter_core.db.models import APP_ROLE, WORKER_ROLE

MEME_LAB_SCOREBOARD_VIEW = "meme_lab_scoreboard_v1"
MEME_LAB_DESK_VIEW = "meme_desk_v1"
MEME_LAB_VIEWS_0022: tuple[str, ...] = (MEME_LAB_SCOREBOARD_VIEW, MEME_LAB_DESK_VIEW)

RESEARCH_RULE_SET_ID = "01994d00-6c1a-7000-8000-000000000001"
OPERATOR_RULE_SET_ID = "01994d00-6c1a-7000-8000-000000000002"
"""Fixed so two databases migrated on different days agree on the id the desk
and the diary name — the ``seed_reference.py`` argument."""

_GATE_V0 = (
    '"gate_key": "comprar_cedo_na_curva", "gate_version": 1, '
    '"exit_key": "alvo_2x_trailing_30_tempo_15m", "exit_version": 1, '
    '"min_age_s": 30, "max_age_s": 600, "min_progress_pct": "2", "max_progress_pct": "50", '
    '"max_participation_pct": "1", "require_creator_not_net_seller": true, '
    '"size_sol": "0.05", "target_x": "2", "trailing_pct": "30", "max_hold_s": 900, '
    '"max_loss_pct": "50", "wallet_max_sol": "2.0", "max_sol_per_bet": "0.05", '
    '"daily_loss_cap_sol": "0.20", "max_open_positions": 3, "max_exposure_per_mint_sol": "0.05", '
    '"fee_pct": "1.75", "priority_fee_sol": "0", "day_timezone": "America/Sao_Paulo"'
)
"""The gate, the exits and the ceilings of ``meme_paper_v0`` (T4.4 §3.1, T4.5).
``fee_pct`` 1,75 % is 1,25 % of the curve plus 0,5 % of the local path —
RISK_ENGINE_MEME §10.2, the paper never simulates a cheaper path than the live
one will use. ``priority_fee_sol`` is ``0`` because no priority fee has been
observed by this project yet; EXP-M1 declares every number an optimistic
ceiling for exactly that reason."""

_SEED = f"""
INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref, status)
VALUES
  ('{RESEARCH_RULE_SET_ID}', 'meme_paper_v0', '1', 'research_only',
   '{{{_GATE_V0}}}'::jsonb,
   'hunter_indicators.meme.rules:evaluate_entry+evaluate_exit', 'EXP-M1', 'active'),
  ('{OPERATOR_RULE_SET_ID}', 'operator', '1', 'operator',
   '{{{_GATE_V0}}}'::jsonb,
   'hunter_indicators.meme.rules:evaluate_entry+evaluate_exit', NULL, 'active')
ON CONFLICT (name, version) DO NOTHING
"""  # noqa: S608 - the only interpolation is this module's own frozen constants

_SCOREBOARD = f"""
CREATE VIEW {MEME_LAB_SCOREBOARD_VIEW} AS
WITH bets AS (
    SELECT b.rule_set_id,
           (b.entry_at AT TIME ZONE 'America/Sao_Paulo')::date AS day_brt,
           b.id, b.status, b.pnl_sol, b.r_multiple, b.exit_at, b.sol_usd_at_exit,
           b.exit ->> 'reason' AS exit_reason
    FROM meme_paper_bets b
), curve AS (
    SELECT rule_set_id, day_brt, exit_at, id,
           sum(pnl_sol) OVER (PARTITION BY rule_set_id, day_brt ORDER BY exit_at, id) AS cum_pnl
    FROM bets WHERE status = 'closed'
), excursions AS (
    SELECT rule_set_id, day_brt,
           cum_pnl - GREATEST(0, max(cum_pnl) OVER
               (PARTITION BY rule_set_id, day_brt ORDER BY exit_at, id)) AS drawdown
    FROM curve
), drawdowns AS (
    SELECT rule_set_id, day_brt, -min(drawdown) AS max_drawdown_sol
    FROM excursions GROUP BY rule_set_id, day_brt
)
SELECT r.id AS rule_set_id, r.name, r.version, r.kind, r.exp_ref, r.status AS rule_set_status,
       b.day_brt,
       count(*) AS bets,
       count(*) FILTER (WHERE b.status = 'closed') AS closed,
       count(*) FILTER (WHERE b.status = 'closed' AND b.pnl_sol > 0) AS wins,
       sum(b.pnl_sol) FILTER (WHERE b.status = 'closed') AS pnl_sol,
       sum(b.pnl_sol * b.sol_usd_at_exit)
           FILTER (WHERE b.status = 'closed' AND b.sol_usd_at_exit IS NOT NULL) AS pnl_usd,
       count(*) FILTER (WHERE b.status = 'closed' AND b.sol_usd_at_exit IS NULL) AS unpriced_usd,
       sum(b.r_multiple) FILTER (WHERE b.status = 'closed') AS r_sum,
       d.max_drawdown_sol,
       count(*) FILTER (WHERE b.exit_reason = 'rug_no_snapshot') AS rugs
FROM bets b
JOIN meme_rule_sets r ON r.id = b.rule_set_id
LEFT JOIN drawdowns d ON d.rule_set_id = b.rule_set_id AND d.day_brt = b.day_brt
GROUP BY r.id, r.name, r.version, r.kind, r.exp_ref, r.status, b.day_brt, d.max_drawdown_sol
"""  # noqa: S608
"""Per rule set per Brasília day of **entry**. ``max_drawdown_sol`` is the deepest
fall of the day's cumulative closed PnL (ordered by ``exit_at``) below its running
high, floored at zero so a first losing bet counts — a magnitude, ``NULL`` when
nothing closed. ``pnl_usd`` only sums bets that carry an observed SOL/USD quote at
exit and ``unpriced_usd`` says how many did not: a day is never priced in dollars
by a rate nobody observed."""

_DESK = f"""
CREATE VIEW {MEME_LAB_DESK_VIEW} AS
SELECT p.id AS proposal_id, p.mint, p.rule_set_id, r.name AS rule_set_name,
       r.version AS rule_set_version, r.kind AS rule_set_kind,
       p.origin, p.status, p.proposed_at, p.expires_at, p.features_end_time, p.quote, p.reasons,
       p.suggested, p.decision, p.decided_by, p.decided_at, p.bet_id, p.refusal,
       t.name, t.symbol, t.creator, t.created_at AS token_created_at,
       t.mayhem_enabled, t.mayhem_mode, t.mayhem_state, t.completed_at, t.migrated_at,
       b.status AS bet_status, b.mode AS bet_mode, b.entry_at, b.entry, b.params AS bet_params,
       b.initial_risk_sol, b.exit_intent, b.mark_sol, b.mark_at, b.high_water_x,
       b.exit_at, b.exit, b.pnl_sol, b.r_multiple, b.sol_usd_at_entry, b.sol_usd_at_exit
FROM meme_proposals p
JOIN meme_rule_sets r ON r.id = p.rule_set_id
LEFT JOIN meme_tokens t ON t.mint = p.mint
LEFT JOIN meme_paper_bets b ON b.id = p.bet_id
"""  # noqa: S608
"""The desk's row. ``meme_tokens`` is a ``LEFT JOIN`` on purpose (Emendas 2 of the
contract): retention prunes the dimension after 90 days and a proposal must not
vanish from the desk because its token aged out."""


def create_meme_lab_views() -> None:
    op.execute(_SCOREBOARD)
    op.execute(_DESK)
    for view in MEME_LAB_VIEWS_0022:
        op.execute(f"GRANT SELECT ON {view} TO {APP_ROLE}, {WORKER_ROLE}")


def seed_meme_lab_rule_sets() -> None:
    """The two arms the contract names. Idempotent on ``(name, version)``."""
    op.execute(_SEED)


def drop_meme_lab_views() -> None:
    for view in reversed(MEME_LAB_VIEWS_0022):
        op.execute(f"DROP VIEW IF EXISTS {view}")


_GUARDED: tuple[tuple[str, str], ...] = (
    (
        "meme_paper_bets",
        "paper bets - the Lab's only ledger, and the day blocks EXP-M1 is judged on",
    ),
    (
        "meme_proposals",
        "proposals with their quotes and refusals - the record of what the gate saw and "
        "what the operator decided",
    ),
    ("meme_operator_commands", "operator orders and what the loop did with them"),
)
"""``meme_rule_sets`` is deliberately not guarded: the seed alone must reverse,
or the round trip an operator runs to roll a deploy back would refuse on every
database this revision ever touched."""


def refuse_a_downgrade_that_would_lose_meme_lab_rows() -> None:
    """§17.7: reversing is allowed, losing evidence is not — count, name, stop."""
    for table, why in _GUARDED:
        safe_why = why.replace("'", "''")
        op.execute(
            f"DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
            f"SELECT count(*) INTO offenders FROM {table}; "
            f"IF offenders > 0 THEN RAISE EXCEPTION USING "
            f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' {table} rows exist - {safe_why}', "
            f"HINT = 'COPY (SELECT * FROM {table}) TO ... before reversing, and understand "
            f"that the meme Lab restarts with no history'; END IF; END $$;"
        )
