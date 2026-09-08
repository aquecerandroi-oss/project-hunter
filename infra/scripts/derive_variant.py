"""Derivar uma **variante de pesquisa** de uma versão congelada — auditado, e recusando na dúvida.

    uv run python infra/scripts/derive_variant.py momentum v2 \
        --set atr_pct_min=0.0089 --changelog "KB-0008: piso de custo" [--dry-run]

Terceira forma de derivar uma ``strategy_version``, ao lado de ``--supersede``
(mesmo conteúdo, código novo) e ``--paper-line`` (mesmo conteúdo, propósito
novo) de ``infra/scripts/activate_strategy_version.py``, e oposta às duas: **o
código é o mesmo e o conteúdo muda** — um ou mais parâmetros recebem um valor
explícito e o resto do conjunto congelado do pai é copiado byte a byte
(``docs/plans/SHADOW-LAB.md`` §1: "conteúdo diferente = versão nova"). A linha
nasce ``draft``, ``activated_at = NULL``, ``purpose = 'research_only'``, e **nada
é ativado aqui**: ativar é uma corrida separada e auditada de
``activate_strategy_version.py``, que reconhece a linha derivada pelo conteúdo
próprio dela e o preserva em vez de reescrevê-lo a partir do código de hoje.

O ``changelog`` congelado carrega a linhagem legível **e** analisável::

    variante de v2 | derived_from=v2 | overrides=atr_pct_min=0.0089
    | params_hash=<12 hex> | <o motivo que o operador escreveu>

``derived_from=v<n>`` é o que ``infra/scripts/obsidian_strategy_pages.py``
(``parse_parent_version``) lê para ligar a página da variante à do pai, como já
lê ``succeeds v<n>`` e ``paper line of v<n>`` (``notes-T3.20.md``).

Recusas, todas antes de qualquer escrita e nenhuma um aviso: migração ausente,
pai inexistente, pai nunca ativado (uma variante deriva de uma coorte
**congelada**), pai que não é ``research_only``, ``code_ref`` que este build não
reproduz, parâmetro que o schema congelado não declara, valor que não valida
contra ele, valor fora da faixa que a estratégia declara
(``hunter_core.strategies.constraints``, T3.26c/A2: sinal invertido em relação ao
pai, piso acima do teto, objeto tipado que não instancia), e um conjunto que já
existe (mesmo ``params_hash`` no mesmo ``code_ref``) — que seria o mesmo
experimento contado duas vezes.

Conecta com ``DATABASE_URL_MIGRATIONS`` (direto, nunca pelo pooler), como
``activate_strategy_version.py``: a ``0011`` revogou ``INSERT`` em
``strategy_versions`` de todo papel de aplicação e ``purpose`` só o dono escreve
(DATABASE.md §24.5).

**Roda dentro da imagem publicada** (``docker exec -i hunter-api-1 python - ...
< derive_variant.py``), então importa só o pacote instalado. A partir da T3.26c
isso inclui ``hunter_core.strategies.constraints``: a imagem precisa ser **deste
commit ou posterior** — ``docs/ACTIVATION.md`` §7 diz como conferir.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from hunter_core.strategies.base import Strategy
from hunter_core.strategies.canonical import canonical_json, params_hash
from hunter_core.strategies.constraints import check_ranges
from hunter_core.strategies.registry import DEFAULT_REGISTRY, StrategyRegistry
from hunter_strategy_worker.activation import validate_parameters
from hunter_strategy_worker.activation_db import (
    PURPOSE_RESEARCH_ONLY,
    Refused,
    load_row,
    migration_applied,
    migration_url,
    next_free_version,
    purpose_column_present,
    record_event,
    record_failure,
)
from hunter_strategy_worker.catalogue import resolve_strategy
from hunter_strategy_worker.code_ref import strategy_module, version_code_ref

__all__ = ["Refused", "build_parameters", "derive_variant", "lineage_of", "main", "parse_overrides"]

NUMERIC = re.compile(r"^-?[0-9]+(\.[0-9]+)?$")
"""O que ``hunter_core.strategies.schema`` aceita como número: forma posicional,
sem expoente. Um valor que casa isto **e** cujo schema declara ``number``/
``integer`` entra como número canônico; o resto entra como a string que veio,
para o validador recusá-lo com a mensagem do próprio schema."""

LINEAGE_RE = re.compile(
    r"^variante de v\d+ \| derived_from=v\d+ \| overrides=[^|]* \| params_hash=[0-9a-f]{12}"
)
"""O prefixo de linhagem que a ativação preserva. É formato congelado: mudá-lo
tornaria ilegíveis as variantes já gravadas, então uma mudança é um formato
novo — nunca uma edição deste."""


def parse_overrides(pairs: list[str]) -> dict[str, str]:
    """``["atr_pct_min=0.0089"] -> {"atr_pct_min": "0.0089"}``, cru e sem juízo."""
    overrides: dict[str, str] = {}
    for pair in pairs:
        name, separator, raw = pair.partition("=")
        name, raw = name.strip(), raw.strip()
        if not separator or not name:
            raise Refused(f"--set {pair!r} não tem a forma parametro=valor")
        if name in overrides:
            raise Refused(f"--set {name} aparece duas vezes: qual dos dois valeria?")
        if "|" in raw or "\n" in raw:
            raise Refused(f"--set {name}: o valor não pode conter '|' nem quebra de linha")
        overrides[name] = raw
    return overrides


def _coerce(name: str, raw: str, rule: dict[str, Any]) -> Any:
    """O valor na forma que o schema congelado espera, nunca numa forma nova."""
    declared = rule.get("type")
    allowed = {declared} if isinstance(declared, str) else set(declared or ())
    if not allowed & {"number", "integer"} or NUMERIC.fullmatch(raw) is None:
        return raw
    try:
        return Decimal(raw)
    except InvalidOperation as exc:  # pragma: no cover - NUMERIC já garante
        raise Refused(f"--set {name}={raw!r} não é um número finito") from exc


def build_parameters(
    schema: dict[str, Any],
    parent: dict[str, Any],
    overrides: dict[str, str],
    strategy: Strategy,
) -> tuple[dict[str, Any], list[tuple[str, str, str]]]:
    """O conjunto da variante e o que nele se moveu, na forma canônica.

    Canonizar **antes** de comparar e de validar é o que faz ``0.00890`` e
    ``0.0089`` serem o mesmo parâmetro (e não duas variantes com hashes
    diferentes), e é a mesma passagem que ``activate()`` faz antes de congelar.

    ``strategy`` é obrigatória, e não um argumento opcional, porque a checagem de
    faixa que ela habilita (:func:`check_ranges`) é a única que olha o *conteúdo*
    do número: uma trava que se pode esquecer de ligar não é uma trava.
    """
    properties: dict[str, Any] = schema.get("properties") or {}
    if not overrides:
        raise Refused("uma variante sem --set é o próprio pai: nada seria derivado")
    merged = dict(parent)
    for name, raw in overrides.items():
        if name not in properties:
            raise Refused(f"--set {name}: o schema congelado do pai não declara esse parâmetro")
        if name not in parent:
            raise Refused(f"--set {name}: o pai não tem esse parâmetro em default_parameters")
        merged[name] = _coerce(name, raw, properties[name])
    canonical: dict[str, Any] = json.loads(canonical_json(merged))
    before: dict[str, Any] = json.loads(canonical_json(parent))
    report = validate_parameters(schema, canonical)
    if not report.ok:
        raise Refused(
            "os parâmetros da variante não validam contra o schema congelado do pai: "
            + "; ".join(report.errors)
        )
    if problems := check_ranges(strategy, before, canonical):
        raise Refused("a variante sai da faixa declarada: " + "; ".join(problems))
    changes = [
        (name, str(before[name]), str(canonical[name]))
        for name in sorted(overrides)
        if before[name] != canonical[name]
    ]
    if not changes:
        raise Refused(
            "nenhum parâmetro se moveu: a variante teria o mesmo params_hash do pai e seria "
            "o mesmo experimento com outro nome"
        )
    return canonical, changes


def lineage_of(changelog: str | None) -> str:
    """O prefixo de linhagem de um ``changelog`` congelado, ou ``""``."""
    match = LINEAGE_RE.match(changelog or "")
    return match.group(0) if match else ""


def variant_changelog(
    version: str, changes: list[tuple[str, str, str]], digest: str, note: str
) -> str:
    """A linhagem primeiro — é por ela que a variante é encontrada e ligada."""
    moved = ",".join(f"{name}={after}" for name, _, after in changes)
    return (
        f"variante de {version} | derived_from={version} | overrides={moved} "
        f"| params_hash={digest[:12]} | {note}"
    )


async def _collision(conn: AsyncConnection, strategy_id: Any, code_ref: str, digest: str) -> Any:
    """A versão que já roda esse mesmo código com esses mesmos parâmetros, se houver."""
    rows = await conn.execute(
        text(
            "SELECT version, default_parameters, code_ref FROM strategy_versions "
            "WHERE strategy_id = :strategy_id"
        ),
        {"strategy_id": strategy_id},
    )
    for row in rows:
        if row.code_ref == code_ref and params_hash(dict(row.default_parameters or {})) == digest:
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
    registry: StrategyRegistry = DEFAULT_REGISTRY,
) -> str:
    """Deriva a variante de ``(key, version)``. Devolve o resumo da corrida."""
    if not await migration_applied(conn):
        raise Refused("0002_shadow_lab não está aplicada: aplique a migração antes de derivar")
    if not await purpose_column_present(conn):
        raise Refused("0010_strategy_purpose não está aplicada: aplique a migração antes")
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
    params, changes = build_parameters(schema, parent, overrides, strategy)
    digest = params_hash(params)
    twin = await _collision(conn, row.strategy_id, code_ref, digest)
    if twin is not None:
        raise Refused(
            f"{key} {twin} já tem exatamente esses parâmetros neste code_ref "
            f"(params_hash {digest[:12]}): seria o mesmo experimento contado duas vezes"
        )
    successor = await next_free_version(conn, row.strategy_id)
    moved = ", ".join(f"{name} {before} -> {after}" for name, before, after in changes)
    if dry_run:
        return (
            f"derivaria {key} {successor} de {version} (purpose {PURPOSE_RESEARCH_ONLY}, draft, "
            f"nada ativado) em code_ref {code_ref}: {moved} [params_hash {digest[:12]}]"
        )
    await conn.execute(
        text(
            "INSERT INTO strategy_versions (id, strategy_id, version, status, "
            "parameters_schema, default_parameters, code_ref, params_format, changelog, "
            "activated_at, purpose) VALUES (gen_random_uuid(), :strategy_id, :version, 'draft', "
            "CAST(:schema AS jsonb), CAST(:params AS jsonb), :code_ref, :params_format, "
            ":changelog, NULL, :purpose)"
        ),
        {
            "strategy_id": row.strategy_id,
            "version": successor,
            "schema": json.dumps(schema, separators=(",", ":"), sort_keys=True),
            "params": canonical_json(params).decode("utf-8"),
            "code_ref": code_ref,
            "params_format": row.params_format,
            "changelog": variant_changelog(version, changes, digest, changelog),
            "purpose": PURPOSE_RESEARCH_ONLY,
        },
    )
    await record_event(
        conn,
        "info",
        "strategy_version_variant_derived",
        f"{key} {successor} derived from {version} (variante, purpose {PURPOSE_RESEARCH_ONLY}) "
        f"code_ref={code_ref} params_hash={digest} overrides: {moved}; draft, "
        f"não ativada: {changelog}",
    )
    return (
        f"derivada {key} {successor} de {version} (purpose {PURPOSE_RESEARCH_ONLY}, draft, "
        f"nada ativado) em code_ref {code_ref}: {moved} [params_hash {digest[:12]}]"
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
    parser.add_argument("--changelog", required=True, help="por que esta variante existe")
    parser.add_argument("--dry-run", action="store_true", help="roda tudo e não escreve nada")
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
