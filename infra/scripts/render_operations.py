#!/usr/bin/env python3
"""T3.50 — toda operação concluída do Lab vira gráfico traçado no Obsidian.

Três subcomandos, cada um com uma responsabilidade e nenhuma sobreposição:

    # 1. exportar (SOMENTE LEITURA na VPS; nada é escrito lá, nada em disco de lá)
    uv run python infra/scripts/render_operations.py export \\
        --version momentum v6 --cohort all --out /tmp/momentum-v6.jsonl

    # 2. desenhar (matplotlib NÃO está no pyproject — `uv run --with matplotlib`)
    uv run --with matplotlib python infra/scripts/render_operations.py render \\
        /tmp/momentum-v6.jsonl --out obsidian/attachments/operacoes/momentum-v6 --max 200

    # 3. escrever a nota da versão e reconstruir o índice
    uv run python infra/scripts/render_operations.py note /tmp/momentum-v6.jsonl

**Idempotência.** ``render`` pula o PNG que já existe (``--force`` redesenha), e
``--max`` limita o lote — rodar duas vezes com ``--max 200`` completa uma versão
de 212 operações sem redesenhar as 200 primeiras. ``note`` reescreve a nota
inteira a partir do JSONL: a nota é derivada, nunca editada à mão.

**O que a exportação lê e o que ela não lê.** Só desfecho `terminal` com
`r_multiple` conhecido — uma operação que entrou, saiu e teve o R apurado. A
consulta inteira, com o argumento do corte da barra de decisão, está em
``infra/scripts/sql/research/2026-09-09-t350-02-export.sql``.
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from render_operations_chart import Operation, geometry, load_operations

REPO = Path(__file__).resolve().parents[2]
SQL = REPO / "infra" / "scripts" / "sql" / "research" / "2026-09-09-t350-02-export.sql"
NOTES_DIR = REPO / "obsidian" / "03-TRADING" / "Operacoes-tracadas"
ATTACH_DIR = REPO / "obsidian" / "attachments" / "operacoes"
DEFAULT_HOST = "hunter-vps"
PSQL = "docker exec -i hunter-postgres-1 psql -U hunter -d hunter -X -q -A -t -v ON_ERROR_STOP=1"

RESULT_PT = {
    "target": "alvo",
    "stop": "stop",
    "expired": "horizonte",
    "invalidated": "invalidação",
}

EXPERIMENT = {
    "momentum-v6": "[[EXP-0013-momentum-alvo-3-atr]]",
    "session_orb-v1": "[[EXP-0010-session-orb-faixa-de-abertura]]",
    "mean_reversion-v2": "[[EXP-0009-mean-reversion-pullback-em-tendencia]] (contrato da mãe v1)",
    "mean_reversion-v3": "[[EXP-0009-mean-reversion-pullback-em-tendencia]] (contrato da mãe v1)",
    "trendline_breakout-v1": (
        "`EXP-0016-trendline-breakout` — ainda **rascunho** em "
        "`.claude/state/exp-drafts/`, por isso sem link de nota"
    ),
    "trendline_bounce-v1": (
        "`EXP-0022-trendline-bounce` — ainda **rascunho** em "
        "`.claude/state/exp-drafts/`, por isso sem link de nota"
    ),
    "momentum-v7": (
        "`EXP-0018-stop-largo` (T3.47 V1, stop ×1,5 sobre a `momentum v6`) — "
        "em redação por outra tarefa, ainda sem nota no vault"
    ),
    "momentum-v8": (
        "`EXP-0018-stop-largo` (T3.47 V2, stop ×2 sobre a `momentum v6`) — "
        "em redação por outra tarefa, ainda sem nota no vault"
    ),
}
"""Contrato de cada versão. Só entra `[[wikilink]]` de nota que **existe** no
vault: um link para um EXP que ainda é rascunho seria achado de link morto no
`obsidian_lint.py`, e a nota diria uma falsidade sobre onde o contrato está."""

LEAD = """As linhas de tendência destes gráficos são traçadas pelo **mesmo código congelado**
que decide (`hunter_core.strategies.tl_scan`, parâmetros de
`trendline_breakout_v1.default_parameters`), cortado na barra da decisão: nenhuma
vela posterior à decisão participa do traçado. Para toda versão fora da família
`trendline_*`, elas são **contexto calculado depois** — a estratégia não leu linha
nenhuma para decidir. Ver [[Operacoes-tracadas/README]] e [[KB-0076-por-que-perdemos-2026-09-08]]."""


def _slug(strategy: str, version: str) -> str:
    return f"{strategy}-{version}"


def export(args: argparse.Namespace) -> int:
    strategy, version = args.version
    # Every value is quoted for the REMOTE shell: `ssh host <string>` hands
    # the string to the VPS shell, and an unquoted `--since "x; rm …"` would
    # run there as the operator (review of T3.50, CRITICAL). psql's `-v`
    # substitution (`:'var'`) already protects the SQL side.
    remote = (
        f"{PSQL} -v strategy={shlex.quote(strategy)} -v ver={shlex.quote(version)} "
        f"-v coorte={shlex.quote(args.cohort)} -v since={shlex.quote(args.since)} -f -"
    )
    with SQL.open("rb") as sql:
        done = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", args.host, remote],
            stdin=sql,
            capture_output=True,
            timeout=args.timeout,
            check=False,
        )
    if done.returncode != 0:
        sys.stderr.write(done.stderr.decode("utf-8", "replace"))
        return done.returncode
    lines = [line for line in done.stdout.decode("utf-8").splitlines() if line.startswith("{")]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    print(f"{strategy} {version} coorte={args.cohort}: {len(lines)} operação(ões) -> {out}")
    return 0


def render(args: argparse.Namespace) -> int:
    from render_operations_draw import render as draw_one

    ops = load_operations(Path(args.jsonl))
    if not ops:
        print(f"{args.jsonl}: nenhuma operação — nada a desenhar")
        return 0
    out_dir = Path(args.out) if args.out else ATTACH_DIR / _slug(ops[0].strategy, ops[0].version)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Two operations of the same version mapping to one file name (same
    # market, decision bar and outcome -- possible across cohorts) would make
    # the second one vanish silently behind the first PNG; fail loud instead
    # (review of T3.50).
    seen: dict[str, str] = {}
    for op in ops:
        other = seen.setdefault(op.filename(), op.signal_id)
        if other != op.signal_id:
            raise SystemExit(
                f"colisão de nome de arquivo: {op.filename()} ({other} e {op.signal_id})"
            )
    written = skipped = 0
    for op in ops:
        if written >= args.max:
            break
        path, did = draw_one(op, out_dir, force=args.force)
        written += int(did)
        skipped += int(not did)
        if did:
            print(f"{path.name:44s} {path.stat().st_size / 1024:6.1f} KB")
    total = sum(p.stat().st_size for p in out_dir.glob("*.png"))
    print(
        f"{len(ops)} operação(ões): {written} desenhada(s), {skipped} já existia(m); "
        f"{len(list(out_dir.glob('*.png')))} PNG em {out_dir} ({total / 1024 / 1024:.1f} MB)"
    )
    return 0


def table_row(index: int, op: Operation, slug: str) -> str:
    scan, _ = geometry(op)
    lines = "—" if scan is None else str(len(scan.lines))
    used = op.used_line_id or "—"
    target = f"{op.targets[0]:f}" if op.targets else "—"
    r = "—" if op.r_multiple is None else f"{op.r_multiple:+.2f}"
    return (
        f"| {index:03d} | {op.brt:%d/%m %H:%M} | {op.decision_bar_close:%H:%M}Z | {op.symbol} "
        f"| {op.coorte} | {op.entry:f} | {op.stop:f} | {target} "
        f"| {RESULT_PT.get(op.result, op.result)} | {r} | {lines} | `{used}` "
        f"| [{op.filename()}](../../attachments/operacoes/{slug}/{op.filename()}) |"
    )


def build_note(ops: list[Operation], slug: str, as_of: datetime) -> str:
    first = ops[0]
    rs = [op.r_multiple for op in ops if op.r_multiple is not None]
    # Decimal all the way: a float mean rebuilt as Decimal can differ in the
    # 4th place that the note publishes (review of T3.50).
    expectancy = (sum(rs, Decimal(0)) / len(rs)).quantize(Decimal("0.0001")) if rs else Decimal(0)
    cohorts = ", ".join(sorted({op.coorte for op in ops}))
    reads_lines = first.strategy in {"trendline_breakout", "trendline_bounce"}
    head = [
        "---",
        f"tags: [operacoes, {first.strategy.replace('_', '-')}, shadow-lab, graficos]",
        "status: em-andamento",
        "owner: quant-engineer",
        f"updated: {as_of:%Y-%m-%d}",
        f"strategy: {first.strategy}",
        f"version: {first.version}",
        f"code_ref: {first.code_ref}",
        f"cohort: {cohorts}",
        f"as_of: {as_of:%Y-%m-%dT%H:%M:%SZ}",
        f"n: {len(ops)}",
        f"expectancy: {expectancy}",
        "---",
        "",
        f"# {first.label} — operações traçadas",
        "",
        f"**{len(ops)} operação(ões) concluída(s)**, coorte(s) {cohorts}, expectância "
        f"**{expectancy:+} R** por operação (média simples de `signal_outcomes.r_multiple`, "
        "líquida de custos e funding). Corte da leitura: "
        f"{as_of.astimezone(first.brt.tzinfo):%d/%m/%Y %H:%M} BRT ({as_of:%H:%M}Z).",
        "",
        LEAD,
        "",
        f"> [!info] Esta versão {'**lê**' if reads_lines else '**não lê**'} linhas de tendência "
        f"para decidir.{'' if reads_lines else ' As linhas abaixo são contexto, nunca entrada da decisão.'}",
        "",
        f"**Contrato da hipótese:** {EXPERIMENT.get(slug, '(sem experimento registrado)')}.",
        "",
        "## Tabela",
        "",
        "| # | Decisão (BRT) | UTC | Mercado | Coorte | Entrada | Stop | Alvo | Saída | R "
        "| Linhas no corte | `line_id` usado | Gráfico |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    head += [table_row(i, op, slug) for i, op in enumerate(ops, start=1)]
    head += ["", "## Gráficos", ""]
    for i, op in enumerate(ops, start=1):
        r = "—" if op.r_multiple is None else f"{op.r_multiple:+.2f} R"
        head += [
            f"### {i:03d} — {op.symbol} · {op.brt:%d/%m/%Y %H:%M} BRT · {r}",
            "",
            f"![{op.symbol} {op.label} {op.brt:%d/%m %H:%M} BRT]"
            f"(../../attachments/operacoes/{slug}/{op.filename()})",
            "",
            f"> {op.reason}" if op.reason else "> (a versão não gravou frase de decisão)",
            "",
        ]
    return "\n".join(head)


def build_index(as_of: datetime) -> str:
    versions = sorted(p.stem for p in NOTES_DIR.glob("*.md") if p.stem != "README")
    rows = [f"- [[Operacoes-tracadas/{name}]]" for name in versions]
    return "\n".join(
        [
            "---",
            "tags: [operacoes, shadow-lab, graficos]",
            "status: em-andamento",
            "owner: quant-engineer",
            f"updated: {as_of:%Y-%m-%d}",
            "---",
            "",
            "# Operações traçadas — índice",
            "",
            "Uma nota por versão, uma linha e um gráfico por operação **concluída** "
            "(entrou, saiu, R apurado). Reproduzir: `docs/PIPELINE.md` §9b.",
            "",
            *rows,
            "",
            "## O que as linhas significam",
            "",
            "**Lê linhas para decidir:** apenas `trendline_breakout_v1` — nela a linha é a "
            "regra (rompimento de resistência descendente ou repique em suporte ascendente) e a "
            "invalidação estrutural. O `line_id` da tabela é o que a decisão usou, gravado no "
            "envelope pelo próprio worker.",
            "",
            "**Não lê linhas:** `momentum`, `mean_reversion`, `session_orb`, `volume_anomaly`, "
            "`breakout`, `sweep_reclaim`. As linhas desenhadas nos gráficos dessas versões são "
            "**contexto calculado depois**, pelo mesmo scanner congelado e cortado na barra da "
            "decisão — servem para olhar a operação, nunca foram entrada dela. Confundir as duas "
            "coisas é a forma mais barata de inventar uma explicação retrospectiva.",
            "",
            "Ver [[KB-0077-linhas-de-tendencia]] (as regras de detecção e os seis pontos em que "
            "um humano traçaria diferente) e [[KB-0076-por-que-perdemos-2026-09-08]].",
            "",
        ]
    )


def note(args: argparse.Namespace) -> int:
    ops = load_operations(Path(args.jsonl))
    if not ops:
        print(f"{args.jsonl}: nenhuma operação — nota não escrita")
        return 0
    as_of = datetime.now(UTC)
    slug = _slug(ops[0].strategy, ops[0].version)
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    path = NOTES_DIR / f"{slug}.md"
    path.write_text(build_note(ops, slug, as_of), encoding="utf-8")
    readme = NOTES_DIR / "README.md"
    readme.write_text(build_index(as_of), encoding="utf-8")
    print(f"{path} ({len(ops)} operações) + {readme}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    exp = sub.add_parser("export", help="exporta operações concluídas (somente leitura)")
    exp.add_argument("--version", nargs=2, metavar=("STRATEGY", "VERSION"), required=True)
    exp.add_argument("--cohort", default="all", choices=("all", "replay", "prospective"))
    exp.add_argument("--since", default="-infinity")
    exp.add_argument("--out", required=True)
    exp.add_argument("--host", default=DEFAULT_HOST)
    exp.add_argument("--timeout", type=int, default=280)
    exp.set_defaults(func=export)

    ren = sub.add_parser("render", help="desenha um PNG por operação")
    ren.add_argument("jsonl")
    ren.add_argument("--out", default=None, help="padrão: obsidian/attachments/operacoes/<slug>")
    ren.add_argument("--force", action="store_true")
    ren.add_argument("--max", type=int, default=200, help="teto de PNGs por invocação")
    ren.set_defaults(func=render)

    nte = sub.add_parser("note", help="escreve a nota da versão e o índice no Obsidian")
    nte.add_argument("jsonl")
    nte.set_defaults(func=note)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
