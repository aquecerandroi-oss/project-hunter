"""``0033_meme_operator_3`` — the desk proposes through the E1 gate (T4.19).

**The seed plants ``operator/3`` and retires ``operator/2``.** ``operator/2``
(``0029``) inherited EXP-M1's gate ``comprar_cedo_na_curva/1`` — reproved by
the study of the 21 bets (9/9 negative). The gate that study chose is E1
(``flow_v2/1``, EXP-M5) with the E2 exclusions (``pedigree.py``, EXP-M6),
both ``research_only`` until now: their signals never reached the desk.
``operator/3`` (``…000a``, ``kind = operator``, ``clock = 15s``) carries
**the same gate and the same exclusions** — ``FLOW_V2_PARAMS`` is the base,
composed in SQL (``jsonb ||``), never copied by hand — with the numbers the
brief fixes for a buy by hand written over it: ``ttl_s = 180`` (the operator
proposal waits 180 s instead of the loop's 120: a hand needs the extra minute)
and ``max_open_positions = 2``; the rest of the brief's list (0,05 SOL, target
3×, trailing 35 % armed after 1,5×, ``max_hold_s = 1800``, ``max_loss`` 50 %,
``line_broken`` when a line exists; ``creator_dump`` is every set's) is
**restated** in the override so the seed says what it plants even if the base
moves. ``operator/2`` → ``retired`` with ``retired_at`` — retired **before**
the insert, so the desk never sees two active ``operator`` sets; the
``downgrade`` deletes ``operator/3`` and brings ``operator/2`` back
``active``, exactly as ``0029`` did with ``operator/1``.

**Upgrade guard: one, after the seed** — exactly one ``operator`` set active
(the desk's invariant; a hand-planted active set or a pre-existing retired
``operator/3`` is refused, not repaired). **The downgrade refuses** while a
proposal or a bet references ``operator/3`` (a proposal the desk saw, a bet it
filled, are evidence — §17.7) and asserts the same invariant after reviving
``operator/2``. Ids continue ``0030``'s sequence, fixed so two databases agree.
"""

from __future__ import annotations

from alembic import op

from ddl.meme_gate_v2_seed import FLOW_V2_PARAMS
from ddl.meme_moonshot import OPERATOR_2_RULE_SET_ID

OPERATOR_3_RULE_SET_ID = "01994d00-6c1a-7000-8000-00000000000a"

OPERATOR_3_OVERRIDES = (
    '"ttl_s": 180, "max_open_positions": 2, '
    '"size_sol": "0.05", "max_sol_per_bet": "0.05", "max_exposure_per_mint_sol": "0.05", '
    '"target_x": "3", "trailing_pct": "35", "trailing_arm_x": "1.5", '
    '"max_hold_s": 1800, "max_loss_pct": "50", "exit_on_line_break": true'
)
"""What the brief fixes for the hand-executed test, laid over ``FLOW_V2_PARAMS``.
Only ``ttl_s`` and ``max_open_positions`` differ from the base today; the
others restate it on purpose (``test_0033`` proves ``params − ttl_s −
max_open_positions = flow_v2/1.params``)."""

_CODE_REF = "hunter_indicators.meme.rules:evaluate_entry+evaluate_exit"

_RETIRE_OPERATOR_2 = (
    "UPDATE meme_rule_sets SET status = 'retired', retired_at = now() "  # noqa: S608
    f"WHERE id = '{OPERATOR_2_RULE_SET_ID}' AND status = 'active'"
)
_REVIVE_OPERATOR_2 = (
    "UPDATE meme_rule_sets SET status = 'active', retired_at = NULL "  # noqa: S608
    f"WHERE id = '{OPERATOR_2_RULE_SET_ID}'"
)
_SEED = f"""
INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref, status)
VALUES
  ('{OPERATOR_3_RULE_SET_ID}', 'operator', '3', 'operator',
   '{{{FLOW_V2_PARAMS}}}'::jsonb || '{{{OPERATOR_3_OVERRIDES}}}'::jsonb,
   '{_CODE_REF}', NULL, 'active')
ON CONFLICT (name, version) DO NOTHING
"""  # noqa: S608 - the only interpolation is this module's own frozen constants
_UNSEED = (
    "DELETE FROM meme_rule_sets "  # noqa: S608 - this module's own frozen id
    f"WHERE id = '{OPERATOR_3_RULE_SET_ID}'"
)


_ASSERT_ONE_ACTIVE_OPERATOR = (
    "DO $$ DECLARE active_operators bigint; BEGIN "
    "SELECT count(*) INTO active_operators FROM meme_rule_sets "
    "WHERE kind = 'operator' AND status = 'active'; "
    "IF active_operators <> 1 THEN RAISE EXCEPTION USING "
    "MESSAGE = 'PROJECT HUNTER: ' || active_operators || ' operator sets are active - the desk "
    "files manual buys under exactly one', "
    "HINT = 'retire the extra set (infra/scripts/meme_rule_set.py --deprecate) or restore the "
    "missing one before migrating'; "
    "END IF; END $$;"
)
"""The desk's invariant, asserted after the hand-over in both directions: a
set someone planted by hand, or an ``operator/3`` that already existed
retired (``ON CONFLICT DO NOTHING`` would keep it so), leaves the desk with
two or none — refused, never repaired in a migration."""


def seed_operator_3() -> None:
    """``operator/2`` retired first, then ``operator/3`` planted; then the
    invariant. Idempotent on a database already at ``0033``."""
    op.execute(_RETIRE_OPERATOR_2)
    op.execute(_SEED)
    op.execute(_ASSERT_ONE_ACTIVE_OPERATOR)


def unseed_operator_3() -> None:
    op.execute(_UNSEED)
    op.execute(_REVIVE_OPERATOR_2)
    op.execute(_ASSERT_ONE_ACTIVE_OPERATOR)


_GUARDED: tuple[tuple[str, str], ...] = (
    (
        "meme_proposals",
        "proposals reference the seeded operator/3 set - the seed cannot be removed under them",
    ),
    (
        "meme_paper_bets",
        "bets reference the seeded operator/3 set - the seed cannot be removed under them",
    ),
)


def refuse_a_downgrade_that_would_orphan_an_operator_3_row() -> None:
    """§17.7: reversing is allowed, losing evidence is not — count, name, stop."""
    predicate = f"WHERE rule_set_id = '{OPERATOR_3_RULE_SET_ID}'"
    # The predicate is quoted twice: bare in the COUNT, and inside the HINT's
    # string literal — where its own quotes must double.
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
