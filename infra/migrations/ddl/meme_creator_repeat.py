"""``0039_meme_creator_repeat`` — the creator's repeat dump, EXP-M6's second
arm (T4.24).

**Measured in the VPS database (15/09/2026, 176 apostas de papel medidas até
20:4x BRT, ``infra/scripts/sql/research/2026-09-15-t424-reincidencia.sql``):**
89 apostas tinham criador com moeda anterior no nosso banco; em **31** o
criador **já tinha vendido** numa moeda anterior
(``meme_features_1m.creator_sold = true`` antes da criação da moeda apostada).
Essas 31: R médio −0,168 (contra −0,140 nas outras 145), **26 das 85 saídas
``creator_dump``** e só 4 ganhas (13 %, contra 19 %). Sinal real, modesto —
não é bala de prata (a maioria dos golpes é de criador **novo**) — mas é o
filtro mais barato que ainda não existia.

**A feature (``hunter_indicators.meme.pedigree``, T4.24):**
``creator_prior_dump_count`` conta, em **qualquer janela** até a criação da
moeda julgada, moedas anteriores do mesmo criador em que (a) o dev vendeu na
fita (``meme_features_1m.creator_sold``), (b) a vigilância da cadeia viu a
venda (``meme_paper_bets.creator_sold_seen_at``, T4.2h) ou (c) uma aposta
nossa saiu por ``creator_dump``. ``evaluate_repeat_dumper`` recusa
``creator_repeat_dumper`` quando o contador é ≥ 1 e o conjunto liga
``params.pedigree_repeat_dumper`` (desligado por padrão nos conjuntos
congelados — desconhecido já recusa por ``creator_unknown``, da E2 v1).
``creator_prior_dead_count`` (moedas anteriores que morreram, < 20 % do topo
em 30 min) é gravado ao lado, diagnóstico, nunca uma recusa.

**A semente planta dois conjuntos e aposenta um.** ``flow_v2/5`` (``…0010``,
``research_only``, EXP-M6) é ``flow_v2/2`` (o braço 2 da porta E1) mais
``pedigree_repeat_dumper: true``; ``operator/5`` (``…0011``, ``kind =
operator``) é ``operator/4`` mais o mesmo — a mesa passa a usar o filtro.
``flow_v2/1`` e ``flow_v2/2`` continuam ativos, a comparação é o ponto.
``operator/4`` → ``retired`` **antes** do insert, como as aposentadorias
anteriores (``operator/2`` → ``operator/3`` → ``operator/4``); a invariante
de um ``operator`` ativo é verificada nos dois sentidos. Downgrade recusa
com proposta ou aposta referenciando qualquer um dos dois conjuntos (§17.7)
e revive ``operator/4``.

Previsão registrada na página do EXP-M6 (braço 2): ``descartar``.
"""

from __future__ import annotations

from alembic import op

from ddl.meme_gate_e1_arm2 import (
    ARM2_OVERRIDES,
    OPERATOR_4_OVERRIDES,
    OPERATOR_4_RULE_SET_ID,
)
from ddl.meme_gate_v2_seed import FLOW_V2_PARAMS

FLOW_V2_ARM5_RULE_SET_ID = "01994d00-6c1a-7000-8000-000000000010"
OPERATOR_5_RULE_SET_ID = "01994d00-6c1a-7000-8000-000000000011"

REPEAT_DUMPER_OVERRIDES = ARM2_OVERRIDES + ', "pedigree_repeat_dumper": true'
"""Arm 2 plus the one new switch: ``test_0039`` proves
``flow_v2/5.params − 'pedigree_repeat_dumper' = flow_v2/2.params`` byte for byte."""

OPERATOR_5_OVERRIDES = OPERATOR_4_OVERRIDES + ', "pedigree_repeat_dumper": true'
"""``operator/4``'s numbers, restated, plus the same switch: the desk starts
using the filter."""

_CODE_REF = "hunter_indicators.meme.rules:evaluate_entry+evaluate_exit"

_RETIRE_OPERATOR_4 = (
    "UPDATE meme_rule_sets SET status = 'retired', retired_at = now() "  # noqa: S608
    f"WHERE id = '{OPERATOR_4_RULE_SET_ID}' AND status = 'active'"
)
_REVIVE_OPERATOR_4 = (
    "UPDATE meme_rule_sets SET status = 'active', retired_at = NULL "  # noqa: S608
    f"WHERE id = '{OPERATOR_4_RULE_SET_ID}'"
)
_SEED = f"""
INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref, status)
VALUES
  ('{FLOW_V2_ARM5_RULE_SET_ID}', 'flow_v2', '5', 'research_only',
   '{{{FLOW_V2_PARAMS}}}'::jsonb || '{{{REPEAT_DUMPER_OVERRIDES}}}'::jsonb,
   '{_CODE_REF}', 'EXP-M6', 'active'),
  ('{OPERATOR_5_RULE_SET_ID}', 'operator', '5', 'operator',
   '{{{FLOW_V2_PARAMS}}}'::jsonb || '{{{OPERATOR_5_OVERRIDES}}}'::jsonb,
   '{_CODE_REF}', NULL, 'active')
ON CONFLICT (name, version) DO NOTHING
"""  # noqa: S608 - the only interpolation is this module's own frozen constants
_UNSEED = (
    "DELETE FROM meme_rule_sets "  # noqa: S608 - this module's own frozen ids
    f"WHERE id IN ('{FLOW_V2_ARM5_RULE_SET_ID}', '{OPERATOR_5_RULE_SET_ID}')"
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
"""The desk's invariant (``0033``), asserted after the hand-over in both directions."""


def seed_creator_repeat() -> None:
    """``operator/4`` retired first, then the two repeat-dumper sets planted;
    then the invariant. Idempotent on a database already at ``0039``."""
    op.execute(_RETIRE_OPERATOR_4)
    op.execute(_SEED)
    op.execute(_ASSERT_ONE_ACTIVE_OPERATOR)


def unseed_creator_repeat() -> None:
    op.execute(_UNSEED)
    op.execute(_REVIVE_OPERATOR_4)
    op.execute(_ASSERT_ONE_ACTIVE_OPERATOR)


_GUARDED: tuple[tuple[str, str], ...] = (
    (
        "meme_proposals",
        "proposals reference the seeded flow_v2/5 or operator/5 set - the seed cannot be removed "
        "under them",
    ),
    (
        "meme_paper_bets",
        "bets reference the seeded flow_v2/5 or operator/5 set - the seed cannot be removed "
        "under them",
    ),
)


def refuse_a_downgrade_that_would_orphan_a_repeat_dumper_row() -> None:
    """§17.7: reversing is allowed, losing evidence is not — count, name, stop."""
    predicate = f"WHERE rule_set_id IN ('{FLOW_V2_ARM5_RULE_SET_ID}', '{OPERATOR_5_RULE_SET_ID}')"
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
