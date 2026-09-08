"""Replicar uma ``strategy_version`` promissora — auditado, e recusando na dúvida.

    uv run python infra/scripts/replicate_strategy_version.py momentum v1 \
        --siblings 10 --seed 20260908 --dry-run
    uv run python infra/scripts/replicate_strategy_version.py momentum v1 \
        --siblings 10 --seed 20260908 --changelog "T3.19: replicação do momentum"
    uv run python infra/scripts/replicate_strategy_version.py momentum v1 --report
    uv run python infra/scripts/replicate_strategy_version.py momentum v1 \
        --siblings 10 --seed 7 --force-research "experimento manual do Everton"

Protocolo completo em ``docs/plans/REPLICATION.md``. Em uma frase: uma versão
promissora (o placar disse ``validada`` uma vez) só é considerada **real**
quando quatro repetições independentes concordam — fora da amostra no tempo,
dez irmãs de parâmetro, as duas metades de mercado e o bootstrap.

O que este script faz: deriva N irmãs ``research_only`` do pai, com cada
parâmetro numérico deslocado em ±15 % por um RNG semeado, numa única transação,
com auditoria em ``system_events``. Do pai ele move **uma** coluna, e é a razão
da ``0012_replication``: ``promising_at`` (com ``promising_by``), uma vez, por
``mark_promising`` — nunca de novo e nunca para trás. **O que ele nunca faz:**
ativar uma linha ``paper``, depreciar uma versão, mudar risco, mexer nos
parâmetros do pai ou chegar perto da carteira. Uma irmã nasce com
``purpose = research_only``, que a ponte de execução recusa pelo nome, com a
coorte ``replication:<pai>:<k>`` (que a ponte recusa de novo, ``cohort_not_live``)
e sem nenhuma linha em ``agents`` que a autorize numa carteira.

``--report`` e ``--dry-run`` não escrevem nada. ``--force-research "<motivo>"``
existe só para os experimentos manuais do Everton: ele dispensa a exigência de o
pai estar ``validada``, exige um motivo escrito, é auditado como ``warning`` e
**não** grava ``promising_at`` (um pai forçado não é um pai promissor).

Conecta com ``DATABASE_URL_MIGRATIONS`` (direto, nunca pelo pooler), como
``infra/scripts/activate_strategy_version.py``: ``0011`` revogou ``INSERT`` em
``strategy_versions`` de todo papel de aplicação, e ``purpose``, ``promising_at``
e a linhagem só o dono escreve (DATABASE.md §24.5). Exige a ``0012_replication``
aplicada e recusa sem ela. A lógica mora em :mod:`hunter_strategy_worker.replication` e
:mod:`hunter_strategy_worker.replication_stats`; aqui só a linha de comando.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from hunter_core.settings import Settings
from hunter_indicators.replication import SIBLINGS_N
from hunter_strategy_worker.activation_db import Refused, load_row
from hunter_strategy_worker.replication import (
    COMPONENT,
    record_replication_event,
    replicate,
)
from hunter_strategy_worker.replication_stats import build_report, summarise

__all__ = ["Refused", "main", "replicate"]


def migration_url() -> str:
    """``DATABASE_URL_MIGRATIONS`` no driver asyncpg (como ``seed.py`` faz)."""
    secret = Settings().database_url_migrations
    if secret is None or not secret.get_secret_value():
        raise SystemExit("DATABASE_URL_MIGRATIONS não está configurada")
    url = secret.get_secret_value()
    if url.startswith("postgresql+"):
        return url
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


async def report(conn: AsyncConnection, key: str, version: str, *, seed: int) -> str:
    """O relatório dos quatro blocos, sem escrever nada."""
    row = await load_row(conn, key, version)
    if row is None:
        raise Refused(f"não existe strategy_version para {key} {version}")
    result = await build_report(conn, row.id, seed=seed)
    return f"{key} {version} — {COMPONENT}\n{summarise(result)}"


async def _record_failure(engine: AsyncEngine, level: str, event: str, message: str) -> None:
    """Conexão nova para a linha de auditoria: a que falhou pode estar abortada
    (o mesmo cuidado de ``activation_db.record_failure``, T3.15c)."""
    async with engine.connect() as conn, conn.begin():
        await record_replication_event(conn, level, event, message, {"failed": True})


async def _run(args: argparse.Namespace) -> int:
    engine = create_async_engine(migration_url(), connect_args={"statement_cache_size": 0})
    try:
        try:
            async with engine.connect() as conn, conn.begin():
                if args.report:
                    message = await report(conn, args.strategy, args.version, seed=args.seed)
                else:
                    message = await replicate(
                        conn,
                        args.strategy,
                        args.version,
                        args.changelog,
                        dry_run=args.dry_run,
                        siblings=args.siblings,
                        seed=args.seed,
                        force_research=args.force_research,
                    )
        except Refused as refusal:
            await _record_failure(
                engine, "warning", "strategy_version_replication_refused", str(refusal)
            )
            print(f"RECUSADO: {refusal}", file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"ERRO: {exc}", file=sys.stderr)
            await _record_failure(engine, "error", "strategy_version_replication_error", str(exc))
            raise SystemExit(2) from exc
        print(message)
    finally:
        await engine.dispose()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("strategy", help="strategies.key, ex.: momentum")
    parser.add_argument("version", help="strategy_versions.version do pai, ex.: v1")
    parser.add_argument(
        "--siblings", type=int, default=SIBLINGS_N, help=f"quantas irmãs (padrão {SIBLINGS_N})"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20260908,
        help="semente do jitter; fica registrada na auditoria e reproduz as irmãs",
    )
    parser.add_argument(
        "--changelog",
        default="replicação do protocolo T3.19 (docs/plans/REPLICATION.md)",
        help="por que esta replicação está sendo feita",
    )
    parser.add_argument("--dry-run", action="store_true", help="roda tudo e não escreve nada")
    parser.add_argument(
        "--report", action="store_true", help="só imprime os quatro blocos do pai; não escreve nada"
    )
    parser.add_argument(
        "--force-research",
        metavar="MOTIVO",
        help="dispensa a exigência de o pai estar validada (experimento manual, auditado)",
    )
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
