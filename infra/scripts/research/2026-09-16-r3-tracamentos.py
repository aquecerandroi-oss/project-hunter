#!/usr/bin/env python3
"""R3 (16/09/2026) — leitura parcial dos traçamentos do dia a partir do JSONL exportado.

Só números do JSONL de ``meme_render_bets.py export`` (nenhum lido do banco ou digitado):

    uv run python infra/scripts/research/2026-09-16-r3-tracamentos.py \
        C:/Users/evert/AppData/Local/Temp/hunter-render/meme-bets-2026-09-16.jsonl

Imprime o bloco em Markdown que a página ``03-TRADING/Meme/Apostas-tracadas/Leitura-2026-09-16``
cola: R total e por conjunto (soma, mediana), motivos de saída, ``line_broken`` contra o resto,
3 melhores e 3 piores com o embed do PNG do dia. Idempotente e somente leitura.
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from statistics import mean, median

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meme_render_bets_model import Bet, load_bets, rule_set_slug  # noqa: E402


def _png(bet: Bet) -> str:
    """Embed markdown relativo à página em ``03-TRADING/Meme/Apostas-tracadas/`` (a mesma forma
    das páginas por conjunto; ``obsidian_lint`` não resolve ``![[...png]]``)."""
    name = bet.filename().replace("+", "%2B")
    return (
        f"![{bet.ticker} {bet.rule_set} {bet.entry_brt:%d/%m %H:%M}]"
        f"(../../../attachments/meme/{bet.day.isoformat()}/{rule_set_slug(bet.rule_set)}/{name})"
    )


def _line(bet: Bet) -> str:
    return (
        f"`{bet.rule_set}` · {bet.ticker} · {bet.entry_brt:%H:%M} BRT · **{bet.r_multiple:+.2f} R** · "
        f"saída `{bet.exit_reason}`"
    )


def _distinct(ranked: list[Bet], universe: list[Bet], limit: int = 3) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for b in ranked:
        if b.mint in seen:
            continue
        seen.add(b.mint)
        others = sorted(
            f"`{o.rule_set}` {o.r_multiple:+.2f}"
            for o in universe
            if o.mint == b.mint and o.bet_id != b.bet_id
        )
        tail = f" (também {', '.join(others)})" if others else ""
        out += [f"- {_line(b)}{tail}", "", _png(b), ""]
        if len(seen) == limit:
            break
    return out


def _sum(rows: list[Bet]) -> Decimal:
    return sum((b.r_multiple for b in rows), Decimal(0))


def _mean(rows: list[Bet]) -> float:
    return mean(float(b.r_multiple) for b in rows) if rows else float("nan")


def main(path: Path) -> int:
    bets = load_bets(path)
    measured = [b for b in bets if b.measured]
    latest = max(bets, key=lambda b: b.exit_at)
    out: list[str] = []
    out.append(
        f"{len(bets)} aposta(s) fechada(s) no JSONL ({len(measured)} medida(s), "
        f"{len(bets) - len(measured)} indeterminada(s)); última saída às "
        f"{latest.exit_brt:%H:%M} BRT; {len({b.mint for b in bets})} moedas distintas "
        f"(a mesma entrada cai em vários conjuntos). Soma de R: **{_sum(measured):+.2f}**; "
        f"mediana **{median(float(b.r_multiple) for b in measured):+.3f}**; "
        f"média {_mean(measured):+.3f}; {sum(b.r_multiple > 0 for b in measured)} positivas."
    )
    out.append("")
    without = [b for b in measured if b.mint != max(measured, key=lambda b: b.r_multiple).mint]
    top = max(measured, key=lambda b: b.r_multiple)
    out.append(
        f"Sem a moeda da maior aposta ({top.ticker}, todas as suas pernas): soma **{_sum(without):+.2f}** "
        f"em {len(without)} apostas."
    )
    out.append("")
    out.append("| conjunto | n | soma R | mediana R | média R | positivas | pior | melhor |")
    out.append("|---|---|---|---|---|---|---|---|")
    by_set: dict[str, list[Bet]] = defaultdict(list)
    for b in measured:
        by_set[b.rule_set].append(b)
    for rule_set, rows in sorted(by_set.items(), key=lambda kv: _sum(kv[1])):
        rs = [float(b.r_multiple) for b in rows]
        out.append(
            f"| `{rule_set}` | {len(rows)} | {_sum(rows):+.2f} | {median(rs):+.3f} | "
            f"{mean(rs):+.3f} | {sum(r > 0 for r in rs)} | {min(rs):+.2f} | {max(rs):+.2f} |"
        )
    out.append("")
    out.append("| motivo de saída | n | soma R | média R | mediana R |")
    out.append("|---|---|---|---|---|")
    reasons = Counter(b.exit_reason for b in measured)
    for reason, n in reasons.most_common():
        rows = [b for b in measured if b.exit_reason == reason]
        rs = [float(b.r_multiple) for b in rows]
        out.append(f"| `{reason}` | {n} | {_sum(rows):+.2f} | {mean(rs):+.3f} | {median(rs):+.3f} |")
    out.append("")
    broken = [b for b in measured if b.exit_reason == "line_broken"]
    rest = [b for b in measured if b.exit_reason != "line_broken"]
    out.append(
        f"`line_broken`: **{len(broken)}** de {len(measured)} ({100 * len(broken) / len(measured):.0f} %), "
        f"R médio **{_mean(broken):+.3f}** (mediana {median(float(b.r_multiple) for b in broken):+.3f}, "
        f"{sum(b.r_multiple > 0 for b in broken)} positivas) contra **{_mean(rest):+.3f}** das outras "
        f"{len(rest)} (mediana {median(float(b.r_multiple) for b in rest):+.3f}, "
        f"{sum(b.r_multiple > 0 for b in rest)} positivas)."
    )
    hw = [b for b in broken if b.high_water_x is not None]
    if hw:
        above = [b for b in hw if b.high_water_x >= Decimal("1.5")]
        out.append(
            f"Das `line_broken`, {len(above)} chegaram a ≥ 1,5× (arme do trailing) antes de sair; "
            f"high-water mediano {median(float(b.high_water_x) for b in hw):.2f}×."
        )
    out.append("")
    buckets = Counter(
        "≤ -0.50" if b.r_multiple <= Decimal("-0.5") else
        "-0.50 … -0.10" if b.r_multiple <= Decimal("-0.1") else
        "-0.10 … +0.10" if b.r_multiple < Decimal("0.1") else
        "+0.10 … +0.50" if b.r_multiple < Decimal("0.5") else "≥ +0.50"
        for b in broken
    )
    order = ["≤ -0.50", "-0.50 … -0.10", "-0.10 … +0.10", "+0.10 … +0.50", "≥ +0.50"]
    out.append("Faixas de R das `line_broken`: " + "; ".join(f"{k}: {buckets.get(k, 0)}" for k in order) + ".")
    out.append("")
    # Uma moeda por linha: a mesma aposta cai em vários conjuntos (mesma entrada, R quase igual).
    ranked = sorted(measured, key=lambda b: b.r_multiple)
    out.append("**3 melhores** (uma moeda por linha; os outros conjuntos que a levaram entre parênteses)")
    out.append("")
    out += _distinct(list(reversed(ranked)), measured)
    out.append("**3 piores**")
    out.append("")
    out += _distinct(ranked, measured)
    sys.stdout.write("\n".join(out) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
