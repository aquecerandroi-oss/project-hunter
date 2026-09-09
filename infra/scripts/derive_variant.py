"""Derivar uma **variante de pesquisa** de uma versão congelada — auditado, e recusando na dúvida.

    uv run python infra/scripts/derive_variant.py momentum v2 \
        --set atr_pct_min=0.0089 --changelog "KB-0008: piso de custo" [--dry-run]

    uv run python infra/scripts/derive_variant.py mean_reversion v6 \
        --policy regime=btc:SIDEWAYS --changelog "T3.52: só decide em lateral" [--dry-run]

Terceira forma de derivar uma ``strategy_version``, ao lado de ``--supersede``
(mesmo conteúdo, código novo) e ``--paper-line`` (mesmo conteúdo, propósito
novo) de ``infra/scripts/activate_strategy_version.py``, e oposta às duas: **o
código é o mesmo e o conteúdo muda** — um ou mais parâmetros recebem um valor
explícito, ou o **portão de elegibilidade** muda, e o resto do conjunto
congelado do pai é copiado byte a byte (``docs/plans/SHADOW-LAB.md`` §1:
"conteúdo diferente = versão nova"). A linha nasce ``draft``,
``activated_at = NULL``, ``purpose = 'research_only'``, e **nada é ativado
aqui**: ativar é uma corrida separada e auditada de
``activate_strategy_version.py``, que reconhece a linha derivada pelo conteúdo
próprio dela e o preserva em vez de reescrevê-lo do código de hoje.

``--policy`` grava ``strategy_versions.eligibility_policy``
(``0017_eligibility_policy``), e **toda** regra declarada tem de passar:
``regime=<escopo>:<RÓTULO>[,<RÓTULO>…]`` (T3.52) e ``hours=<HH>-<HH>[+…]``,
meia-aberta e em UTC (T3.59) — juntas em ``regime=btc:BTC_BULL,hours=12-15``;
``<portão>=none`` tira uma regra, ``none`` sozinho tira todas. **Sem ``--policy``
a variante herda o portão do pai**, e um ``--policy`` que não mencione uma regra
do pai é recusado (largá-la calado faria a filha decidir em mais contexto que
ele). O ilegível — e o par ``(scope, classifier_version)`` sem série em
``market_regimes`` — é recusado aqui pelas **mesmas** funções que o worker usa
para ler a coluna (``gate_policy``, :func:`_refuse_a_gate_with_no_series`).

O ``changelog`` congelado carrega a linhagem legível **e** analisável::

    variante de v2 | derived_from=v2 | overrides=atr_pct_min=0.0089
    | params_hash=<12 hex> [| policy=btc:SIDEWAYS;hours=12-15] | <o motivo escrito>

``derived_from=v<n>`` é o que ``infra/scripts/obsidian_strategy_pages.py``
(``parse_parent_version``) lê para ligar a página da variante à do pai, como já
lê ``succeeds v<n>`` e ``paper line of v<n>`` (``notes-T3.20.md``).

Recusas, todas antes de qualquer escrita e nenhuma um aviso: migração ausente,
pai inexistente, pai nunca ativado (uma variante deriva de uma coorte
**congelada**), pai que não é ``research_only``, ``code_ref`` que este build não
reproduz, parâmetro que o schema congelado não declara, valor que não valida
contra ele, valor fora da faixa que a estratégia declara
(``hunter_core.strategies.constraints``, T3.26c/A2: sinal invertido em relação ao
pai, piso acima do teto, objeto tipado que não instancia), política ilegível,
portão sem série que o sustente, portão do pai largado em silêncio, e um conjunto
que já existe (mesmo ``params_hash`` **e** mesma política no mesmo ``code_ref``).

Conecta com ``DATABASE_URL_MIGRATIONS`` (direto, nunca pelo pooler), como
``activate_strategy_version.py``: a ``0011`` revogou ``INSERT`` em
``strategy_versions`` de todo papel, e ``purpose``/``eligibility_policy`` só o
dono escreve (DATABASE.md §24.5, §29). A metade pura — ``--set``, forma
canônica, linhagem — mora em ``hunter_strategy_worker.variant`` (orçamento de
350 linhas, T3.52) e é re-exportada aqui, então quem importava daqui não mudou.
**Roda dentro da imagem publicada** (``docker exec -i hunter-api-1 python - <
derive_variant.py``), então importa só o pacote instalado: desde a T3.26c isso
inclui ``hunter_core.strategies.constraints`` e, desde a T3.52,
``hunter_strategy_worker.variant``/``.gate_policy`` — a imagem precisa ser
**deste commit ou posterior** (``docs/ACTIVATION.md`` §7 diz como conferir).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from hunter_core.strategies.canonical import canonical_json, params_hash
from hunter_core.strategies.registry import DEFAULT_REGISTRY, StrategyRegistry
from hunter_strategy_worker.activation import validate_parameters
from hunter_strategy_worker.activation_db import (
    PURPOSE_RESEARCH_ONLY,
    Refused,
    load_row,
    migration_applied,
    migration_url,
    next_free_version,
    policy_column_present,
    purpose_column_present,
    record_event,
    record_failure,
)
from hunter_strategy_worker.catalogue import resolve_strategy
from hunter_strategy_worker.code_ref import strategy_module, version_code_ref
from hunter_strategy_worker.gate_policy import EligibilityPolicy, PolicyError, parse_policy
from hunter_strategy_worker.variant import (
    LINEAGE_RE,
    NUMERIC,
    build_parameters,
    canonical_policy,
    lineage_of,
    parse_overrides,
    policy_note,
    resolve_policy,
    stored_policy,
    variant_changelog,
)

__all__ = [
    "LINEAGE_RE",
    "NUMERIC",
    "Refused",
    "build_parameters",
    "derive_variant",
    "lineage_of",
    "main",
    "parse_overrides",
    "resolve_policy",
    "variant_changelog",
]


async def _parent_policy(conn: AsyncConnection, version_id: Any) -> dict[str, Any] | None:
    """``strategy_versions.eligibility_policy`` do pai — lido à parte de
    :func:`load_row` de propósito (ver ``activation_db.policy_column_present``)."""
    raw = await conn.scalar(
        text("SELECT eligibility_policy FROM strategy_versions WHERE id = :id"), {"id": version_id}
    )
    return None if raw is None else dict(raw)


async def _refuse_a_gate_with_no_series(conn: AsyncConnection, policy: EligibilityPolicy) -> None:
    """Recusa um ``--policy`` cujo par ``(scope, classifier_version)`` não tem
    **nenhuma** linha em ``market_regimes``: a gramática não fecha a lista de
    classificadores (o nome vem do produtor, T3.43), então quem fecha é o banco.
    Sem isto um par errado entra no roster e recusa **toda** barra por
    ``regime_gate:unknown``/``no_row`` — em silêncio. DATABASE.md §29.7.
    """
    seen = await conn.scalar(
        text(
            "SELECT 1 FROM market_regimes WHERE scope = CAST(:scope AS regime_scope) "
            "AND classifier_version = :classifier LIMIT 1"
        ),
        {"scope": policy.scope, "classifier": policy.classifier_version},
    )
    if seen is None:
        raise Refused(
            f"--policy: market_regimes não tem nenhuma linha para (scope={policy.scope}, "
            f"classifier_version={policy.classifier_version}): o portão recusaria toda "
            "barra por regime_gate:unknown/no_row, em silêncio"
        )


async def _collision(
    conn: AsyncConnection,
    strategy_id: Any,
    code_ref: str,
    digest: str,
    policy: dict[str, Any] | None,
) -> Any:
    """A versão que já roda esse código com esses parâmetros **e** esse portão.

    O portão entra na comparação porque ele é conteúdo: mesmo ``params_hash`` com
    portões diferentes são dois experimentos (é o que a T3.52 deriva).
    """
    rows = await conn.execute(
        text(
            "SELECT version, default_parameters, code_ref, eligibility_policy "
            "FROM strategy_versions WHERE strategy_id = :strategy_id"
        ),
        {"strategy_id": strategy_id},
    )
    wanted = canonical_policy(policy)
    for row in rows:
        same_content = (
            row.code_ref == code_ref and params_hash(dict(row.default_parameters or {})) == digest
        )
        if same_content and canonical_policy(row.eligibility_policy) == wanted:
            return row.version
    return None


async def derive_variant(
    conn: AsyncConnection,
    key: str,
    version: str,
    changelog: str,
    *,
    overrides: dict[str, str],
    dry_run: bool,
    policy: str | None = None,
    registry: StrategyRegistry = DEFAULT_REGISTRY,
) -> str:
    """Deriva a variante de ``(key, version)``. Devolve o resumo da corrida."""
    if not await migration_applied(conn):
        raise Refused("0002_shadow_lab não está aplicada: aplique a migração antes de derivar")
    if not await purpose_column_present(conn):
        raise Refused("0010_strategy_purpose não está aplicada: aplique a migração antes")
    if not await policy_column_present(conn):
        raise Refused("0017_eligibility_policy não está aplicada: aplique a migração antes")
    row = await load_row(conn, key, version)
    if row is None:
        raise Refused(f"não existe strategy_version para {key} {version}")
    if row.activated_at is None:
        raise Refused(
            f"{key} {version} nunca foi ativada: uma variante deriva de uma coorte congelada "
            "— ative a versão de pesquisa primeiro"
        )
    if row.purpose != PURPOSE_RESEARCH_ONLY:
        raise Refused(
            f"{key} {version} tem purpose {row.purpose!r}: só uma versão {PURPOSE_RESEARCH_ONLY!r} "
            "é variada — uma linha que pode tocar carteira nunca ganha parâmetros novos por aqui"
        )
    strategy = resolve_strategy(key, version, row.code_ref, registry)
    if strategy is None:
        raise Refused(
            f"este build não liga {key} {version} a código: nem o registry nem o code_ref "
            f"congelado ({row.code_ref}) nomeiam um módulo que ele carrega"
        )
    code_ref = version_code_ref(strategy_module(strategy))
    if row.code_ref != code_ref:
        raise Refused(
            f"{key} {version} está congelada em code_ref {row.code_ref} e este build é {code_ref}: "
            "uma variante roda exatamente o código que o pai rodou"
        )
    schema: dict[str, Any] = dict(row.parameters_schema or {})
    parent: dict[str, Any] = dict(row.default_parameters or {})
    if not parent:
        raise Refused(f"{key} {version} não tem default_parameters: nada a variar")
    parent_report = validate_parameters(schema, parent)
    if not parent_report.ok:
        raise Refused(
            f"os parâmetros congelados de {key} {version} não validam contra o próprio schema: "
            + "; ".join(parent_report.errors)
        )
    inherited = await _parent_policy(conn, row.id)
    chosen = resolve_policy(policy, inherited)
    moved = canonical_policy(chosen) != canonical_policy(inherited)
    try:
        parsed = parse_policy(chosen)
    except PolicyError as invalid:  # pragma: no cover - resolve_policy já validou o novo
        raise Refused(f"a política herdada de {key} {version} é ilegível: {invalid}") from invalid
    if policy is not None and parsed is not None and parsed.regime is not None:
        await _refuse_a_gate_with_no_series(conn, parsed.regime)
    params, changes = build_parameters(schema, parent, overrides, strategy, policy_moved=moved)
    digest = params_hash(params)
    twin = await _collision(conn, row.strategy_id, code_ref, digest, chosen)
    if twin is not None:
        raise Refused(
            f"{key} {twin} já tem exatamente esses parâmetros e esse portão neste code_ref "
            f"(params_hash {digest[:12]}, policy {policy_note(parsed)}): seria o mesmo "
            "experimento contado duas vezes"
        )
    successor = await next_free_version(conn, row.strategy_id)
    what = ", ".join(f"{name} {before} -> {after}" for name, before, after in changes)
    if moved:
        what = f"{what + ', ' if what else ''}policy -> {policy_note(parsed)}"
    if dry_run:
        return (
            f"derivaria {key} {successor} de {version} (purpose {PURPOSE_RESEARCH_ONLY}, draft, "
            f"nada ativado) em code_ref {code_ref}: {what} [params_hash {digest[:12]}]"
        )
    await conn.execute(
        text(
            "INSERT INTO strategy_versions (id, strategy_id, version, status, "
            "parameters_schema, default_parameters, code_ref, params_format, changelog, "
            "activated_at, purpose, eligibility_policy) VALUES (gen_random_uuid(), "
            ":strategy_id, :version, 'draft', "
            "CAST(:schema AS jsonb), CAST(:params AS jsonb), :code_ref, :params_format, "
            ":changelog, NULL, :purpose, CAST(:policy AS jsonb))"
        ),
        {
            "strategy_id": row.strategy_id,
            "version": successor,
            "schema": json.dumps(schema, separators=(",", ":"), sort_keys=True),
            "params": canonical_json(params).decode("utf-8"),
            "code_ref": code_ref,
            "params_format": row.params_format,
            "changelog": variant_changelog(
                version, changes, digest, changelog, policy=parsed, policy_moved=moved
            ),
            "purpose": PURPOSE_RESEARCH_ONLY,
            "policy": stored_policy(chosen),
        },
    )
    await record_event(
        conn,
        "info",
        "strategy_version_variant_derived",
        f"{key} {successor} derived from {version} (variante, purpose {PURPOSE_RESEARCH_ONLY}) "
        f"code_ref={code_ref} params_hash={digest} policy={policy_note(parsed)} changes: {what}; "
        f"draft, não ativada: {changelog}",
    )
    return (
        f"derivada {key} {successor} de {version} (purpose {PURPOSE_RESEARCH_ONLY}, draft, "
        f"nada ativado) em code_ref {code_ref}: {what} [params_hash {digest[:12]}]"
    )


async def _run(args: argparse.Namespace) -> int:
    engine = create_async_engine(migration_url(), connect_args={"statement_cache_size": 0})
    try:
        try:
            overrides = parse_overrides(list(args.set or []))
            async with engine.connect() as conn, conn.begin():
                message = await derive_variant(
                    conn,
                    args.strategy,
                    args.version,
                    args.changelog,
                    overrides=overrides,
                    dry_run=args.dry_run,
                    policy=args.policy,
                )
        except Refused as refusal:
            await record_failure(
                engine, "warning", "strategy_version_variant_refused", str(refusal)
            )
            print(f"RECUSADO: {refusal}", file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"ERRO: {exc}", file=sys.stderr)
            await record_failure(engine, "error", "strategy_version_variant_error", str(exc))
            raise SystemExit(2) from exc
        print(message)
    finally:
        await engine.dispose()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("strategy", help="strategies.key do pai, ex.: momentum")
    parser.add_argument("version", help="strategy_versions.version do pai, ex.: v2")
    parser.add_argument(
        "--set",
        action="append",
        metavar="PARAM=VALOR",
        help="sobrescreve um parâmetro do conjunto congelado (repetível)",
    )
    parser.add_argument(
        "--policy",
        metavar="regime=ESCOPO:RÓTULO[,RÓTULO][,hours=HH-HH]",
        help="portão(ões) da variante (ex.: regime=btc:SIDEWAYS,hours=12-15, hours=12-15, "
        "regime=none) ou 'none' para tirar todos; sem isto, herda o do pai",
    )
    parser.add_argument("--changelog", required=True, help="por que esta variante existe")
    parser.add_argument("--dry-run", action="store_true", help="roda tudo e não escreve nada")
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
