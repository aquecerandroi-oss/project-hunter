"""``0060_meme_refused_probe_arm`` — the empty square of the 2×2, seeded
(T4.85, EXP-M23, ``obsidian/05-EXPERIMENTS/EXP-M23-desfecho-das-recusadas.md``
and its Emenda 1 of 23/09/2026).

**The measurement, as data.** R69 closed on the one thing none of R58–R69
measured: 41 905 refusals recorded in ``meme_gate_refusals_by_mint`` since
17/09 (3 593 mints) and **zero outcomes**. While that square is empty, a gate
that SELECTS and a gate that merely bets LESS OFTEN are indistinguishable in
our data. This arm opens a paper bet on a random, known-probability sample of
the mints the desk refused, under the desk's **own** exit policy, so the
square gets filled.

**One arm, no control to seed.** The control the pre-registration asks for —
"as apostas admitidas com os mesmos parâmetros, em paralelo e no mesmo
período" — already exists and is ``operator/6`` (``0055``): every approved
proposal of the desk also becomes a ``meme_paper_bets`` row through the same
``lab_bets.fill_approved`` (``lab_repo.load_approved_proposals`` does not
filter by ``kind``), at 0,07 SOL, alvo 1,15×, ``max_hold`` 300 s, trailing
10 % armed at the entry and ``exit_on_line_break``. Seeding a second mirror
would add a second population, not a second control.

**Same exits, same costs, different ceilings — and the difference is
declared.** :data:`REFUSED_PROBE_OVERRIDES` changes exactly six keys of
``operator/6``:

- ``clock`` → ``refused``, this arm's own (``lab_models.CLOCKS``). No existing
  step selects it (``lab._gate_step`` takes ``1m``, ``lab_fast`` and
  ``event_gate_caches`` take ``15s``, ``launch_lane_repo`` refuses anything
  that is not ``event``), and ``lab_repo.load_active_rule_sets`` still loads
  it — so the fill, the marks and the exits are the Lab's own. That sameness
  is EXP-M23's "simetria obrigatória".
- ``gate_key``/``gate_version`` → ``recusadas_da_mesa/1``: the population is
  what the desk rejected, not a criterion this set evaluates. The criteria
  keys stay at ``operator/6``'s values so the proposal's decomposition lists
  the same feature blocks the desk read — they are never evaluated here.
- ``max_open_positions`` 2 → 25, ``daily_loss_cap_sol`` 0,20 → 10,0 and
  ``wallet_max_sol`` 2,0 → 100,0. **These are not the desk's, on purpose.**
  Emenda 1 expects ~79 mints/day; at the desk's ceilings the arm would latch
  shut after three losing paper bets and the sample would be a measurement of
  its own bankroll instead of the market. The exit policy — which is what the
  pre-registration froze — is untouched, and the ceilings are paper.

Everything about money stays a **string** (the Lab refuses a bare float), the
seed and the four sampling rates live in ``hunter_meme_worker.refused_probe``
and **not** in the params — moving one is a new arm, never an edit of a live
row, exactly as ``0058`` froze the absorption thresholds in code.

The downgrade refuses while any row references the seeded set (§17.7), the
same four tables ``0049``–``0058`` guard.
"""

from __future__ import annotations

from alembic import op

from ddl.meme_gate_v2_seed import FLOW_V2_PARAMS
from ddl.meme_operator_6 import OPERATOR_6_OVERRIDES

REFUSED_PROBE_RULE_SET_ID = "01994d00-6c1a-7000-8000-00000000001c"
SEEDED_RULE_SET_IDS_0060: tuple[str, ...] = (REFUSED_PROBE_RULE_SET_ID,)

REFUSED_PROBE_OVERRIDES = (
    '"clock": "refused", '
    '"gate_key": "recusadas_da_mesa", "gate_version": 1, '
    '"max_open_positions": 25, "daily_loss_cap_sol": "10.0", "wallet_max_sol": "100.0"'
)
"""The six keys this arm does not share with ``operator/6``; every other key —
and in particular every exit and cost key — comes from the desk's own row by
construction, because the seed below is literally ``operator/6``'s expression."""

REFUSED_PROBE_ARM_KEYS: tuple[str, ...] = (
    "clock",
    "gate_key",
    "gate_version",
    "max_open_positions",
    "daily_loss_cap_sol",
    "wallet_max_sol",
)
"""Frozen beside the overrides so ``test_migration_0060`` can subtract them
from both rows and prove what is left is ``operator/6``, byte for byte."""

DESK_EXIT_KEYS: tuple[str, ...] = (
    "exit_key",
    "exit_version",
    "size_sol",
    "target_x",
    "trailing_pct",
    "trailing_arm_x",
    "max_hold_s",
    "max_loss_pct",
    "exit_on_line_break",
    "line_break_snapshots",
    "fee_pct",
    "priority_fee_sol",
    "max_sol_per_bet",
    "max_exposure_per_mint_sol",
)
"""What "os parâmetros de saída são os da mesa real" means as a list of keys:
the test asserts this arm and ``operator/6`` agree on every one of them."""

_CODE_REF = (
    "hunter_meme_worker.refused_probe:pick_probes+hunter_indicators.meme.rules:evaluate_exit"
)

_SEED = f"""
INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref, status)
VALUES
  ('{REFUSED_PROBE_RULE_SET_ID}', 'refused_probe_v0', '1', 'research_only',
   '{{{FLOW_V2_PARAMS}}}'::jsonb || '{{{OPERATOR_6_OVERRIDES}}}'::jsonb
     || '{{{REFUSED_PROBE_OVERRIDES}}}'::jsonb,
   '{_CODE_REF}', 'EXP-M23', 'active')
ON CONFLICT (name, version) DO NOTHING
"""  # noqa: S608 - the only interpolation is this module's own frozen constants
_UNSEED = (
    "DELETE FROM meme_rule_sets "  # noqa: S608 - this module's own frozen id
    f"WHERE id = '{REFUSED_PROBE_RULE_SET_ID}'"
)


def seed_refused_probe_arm() -> None:
    """Idempotent on a database already at ``0060``; nothing is retired, and
    the desk is not touched (this arm is paper only, by ``kind``)."""
    op.execute(_SEED)


def unseed_refused_probe_arm() -> None:
    op.execute(_UNSEED)


_GUARDED: tuple[tuple[str, str], ...] = (
    (
        "meme_proposals",
        "proposals reference the seeded refused_probe_v0 set - "
        "they carry EXP-M23's inclusion probabilities and cannot be removed under them",
    ),
    (
        "meme_paper_bets",
        "bets reference the seeded refused_probe_v0 set - the seed cannot be removed under them",
    ),
    (
        "meme_rule_set_param_history",
        "param history rows reference the seeded refused_probe_v0 set - "
        "the seed cannot be removed under them",
    ),
    (
        "meme_gate_refusals_by_mint",
        "refusal rows reference the seeded refused_probe_v0 set - "
        "the seed cannot be removed under them",
    ),
)
"""``0049``–``0058``'s four: every table with a ``rule_set_id`` foreign key to
``meme_rule_sets``. The first one matters more here than in any previous arm —
a probe proposal's ``reasons`` is the **only** copy of that mint's refusal
reasons, its stratum and its inclusion probability."""


def refuse_a_downgrade_that_would_orphan_a_probe_row() -> None:
    """§17.7: reversing is allowed, losing evidence is not — count, name, stop."""
    predicate = f"WHERE rule_set_id = '{REFUSED_PROBE_RULE_SET_ID}'"
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
