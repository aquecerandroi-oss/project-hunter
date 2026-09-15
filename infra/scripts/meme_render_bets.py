#!/usr/bin/env python3
"""T4.25 — toda aposta meme fechada vira gráfico traçado no Obsidian.

Três subcomandos, o mesmo desenho do render de operações (T3.50): exportar na
VPS (somente leitura), desenhar no laptop (matplotlib fora do lock), embutir no
vault.

    # 1. exportar (na VPS, dentro da imagem publicada, como `hunter_app`)
    ./compose.sh ops python infra/scripts/meme_render_bets.py export \\
        --day 2026-09-14 > /tmp/meme-bets-2026-09-14.jsonl

    # 2. desenhar (local; matplotlib NAO esta no pyproject desta arvore)
    uv run --with matplotlib python infra/scripts/meme_render_bets.py render \\
        /tmp/meme-bets-2026-09-14.jsonl --max 200

    # 3. escrever a pagina de cada conjunto e a secao 7 do diario do dia
    uv run python infra/scripts/meme_render_bets.py notes /tmp/meme-bets-2026-09-14.jsonl

**Idempotencia.** ``render`` pula o PNG que ja existe (``--force`` redesenha) e
``--max`` limita o lote; ``notes`` substitui o bloco do proprio dia e nunca toca
no bloco de outro dia. Rodar duas vezes nao muda um byte.

**O que a exportacao le:** so aposta **fechada** (``status = 'closed'``) do dia
Brasilia, com a serie de 15 s, a de 1 min com as colunas de linha da
``meme_features_v3`` e as fotografias da curva, de 10 min antes da entrada a
10 min depois da saida. As indeterminadas (T4.16) ficam de fora por padrao e
entram rotuladas com ``--include-indeterminate``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path

from meme_render_bets_model import Bet, load_bets
from meme_render_bets_notes import attachments_dir, write_notes
from meme_render_bets_query import gather_day, write_jsonl

MAX_PNG_BYTES = 200 * 1024
"""Teto do brief T4.25 por imagem (dpi 110)."""


def export(args: argparse.Namespace) -> int:
    day = date.fromisoformat(args.day)
    records = asyncio.run(
        gather_day(day, rule_set=args.set, with_indeterminate=args.include_indeterminate)
    )
    if args.out:
        write_jsonl(records, Path(args.out))
        print(f"{day}: {len(records)} aposta(s) -> {args.out}")
        return 0
    for record in records:
        sys.stdout.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"{day}: {len(records)} aposta(s) no stdout", file=sys.stderr)
    return 0


def _destination(bet: Bet, root: Path | None) -> Path:
    if root is None:
        return attachments_dir(bet.day, bet.rule_set)
    return root / bet.day.isoformat() / bet.rule_set.replace("/", "-")


def render(args: argparse.Namespace) -> int:
    from meme_render_bets_draw import render as draw_one

    bets = load_bets(Path(args.jsonl))
    if not bets:
        print(f"{args.jsonl}: nenhuma aposta — nada a desenhar")
        return 0
    root = Path(args.out) if args.out else None
    seen: dict[str, str] = {}
    for bet in bets:
        key = str(_destination(bet, root) / bet.filename())
        other = seen.setdefault(key, bet.bet_id)
        if other != bet.bet_id:
            raise SystemExit(f"colisão de nome de arquivo: {key} ({other} e {bet.bet_id})")
    written = skipped = heavy = 0
    for bet in bets:
        if written >= args.max:
            break
        path, did = draw_one(bet, _destination(bet, root), force=args.force)
        written += int(did)
        skipped += int(not did)
        size = path.stat().st_size
        heavy += int(size > MAX_PNG_BYTES)
        if did:
            print(f"{path.name:34s} {size / 1024:6.1f} KB  {bet.rule_set}")
    print(
        f"{len(bets)} aposta(s): {written} desenhada(s), {skipped} já existia(m)"
        + (f"; ATENÇÃO {heavy} acima de {MAX_PNG_BYTES // 1024} KB" if heavy else "")
    )
    return 0


def notes(args: argparse.Namespace) -> int:
    bets = load_bets(Path(args.jsonl))
    if not bets:
        print(f"{args.jsonl}: nenhuma aposta — nenhuma nota escrita")
        return 0
    days = {bet.day for bet in bets}
    if len(days) != 1:
        raise SystemExit(f"o JSONL mistura {len(days)} dias: {sorted(d.isoformat() for d in days)}")
    for path in write_notes(bets):
        print(path)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    exp = sub.add_parser("export", help="exporta as apostas fechadas do dia (somente leitura)")
    exp.add_argument("--day", required=True, help="dia em Brasília, AAAA-MM-DD")
    exp.add_argument("--set", default=None, help="um conjunto só, no formato nome/versão")
    exp.add_argument("--include-indeterminate", action="store_true")
    exp.add_argument("--out", default=None, help="padrão: JSONL no stdout")
    exp.set_defaults(func=export)

    ren = sub.add_parser("render", help="desenha um PNG por aposta")
    ren.add_argument("jsonl")
    ren.add_argument("--out", default=None, help="raiz alternativa (padrão: obsidian/attachments)")
    ren.add_argument("--force", action="store_true")
    ren.add_argument("--max", type=int, default=200, help="teto de PNGs por invocação")
    ren.set_defaults(func=render)

    nte = sub.add_parser("notes", help="escreve a página do conjunto e a seção 7 do diário")
    nte.add_argument("jsonl")
    nte.set_defaults(func=notes)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
