"""Renders the daily ficha (T4.92) as Portuguese Markdown — pure, no IO, no
clock (``generated_at``/``git_sha`` come in already resolved).

Every number comes from :mod:`meme_daily_ficha_queries`; a value this ficha
could not prove is written as "—" with the reason, never as zero — the same
discipline ``meme_diary_render.py``/``meme_close_render.py`` already use.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from meme_daily_ficha_classify import LossClassInputs, classify_loss, rose_after_buy
from meme_daily_ficha_queries import SAO_PAULO, TICKET_SOL
from meme_daily_ficha_types import DayFicha, PaperArm, RealPosition, SpotPosition

__all__ = ["Ficha", "render_day", "render_week"]


@dataclass(frozen=True, slots=True)
class Ficha:
    """A ``DayFicha`` plus the two things only the CLI knows: when this run
    happened and which commit produced it."""

    data: DayFicha
    generated_at: datetime
    git_sha: str


def _n(value: Decimal | int | None, *, places: int = 4, reason: str = "sem leitura") -> str:
    if value is None:
        return f"— ({reason})"
    if isinstance(value, int):
        return str(value)
    return f"{value:.{places}f}"


def _pct(value: Decimal | None, *, reason: str = "sem leitura") -> str:
    return f"— ({reason})" if value is None else f"{value:.1f} %"


def _brt(at: datetime | None) -> str:
    return "—" if at is None else at.astimezone(SAO_PAULO).strftime("%H:%M:%S")


def _duration(entry_at: datetime, exit_at: datetime | None) -> str:
    if exit_at is None:
        return "— (posição ainda aberta)"
    return f"{int((exit_at - entry_at).total_seconds())} s"


_SHORT_MINT_THRESHOLD = 10


def _short_mint(mint: str) -> str:
    return mint if len(mint) <= _SHORT_MINT_THRESHOLD else f"{mint[:4]}…{mint[-4:]}"


def _solscan(mint: str) -> str:
    return f"[{_short_mint(mint)}](https://solscan.io/token/{mint})"


def _label(position: RealPosition) -> str:
    symbol = position.symbol or "?"
    return f"`{symbol}` {_solscan(position.mint)}"


def _pnl_pct(position: RealPosition) -> Decimal | None:
    if position.pnl_sol is None or position.cost_sol == 0:
        return None
    return position.pnl_sol / position.cost_sol * 100


def _peak_pct(position: RealPosition) -> Decimal | None:
    if position.high_water_sol is None or position.cost_sol == 0:
        return None
    return position.high_water_sol / position.cost_sol * 100


def _loss_class(position: RealPosition) -> str | None:
    if position.pnl_sol is None:
        return None  # open position: not a closed loss, nothing to classify yet
    return classify_loss(
        LossClassInputs(
            pnl_sol=position.pnl_sol,
            cost_sol=position.cost_sol,
            high_water_sol=position.high_water_sol,
            exit_reason=position.exit_reason,
            distinct_sellers_one_slot=position.distinct_sellers_one_slot,
            since_prior_exit=position.since_prior_exit,
            round_trip_cost_sol=position.round_trip_cost_sol,
        )
    )


def _frontmatter(ficha: Ficha) -> list[str]:
    day = ficha.data.day.isoformat()
    return [
        "---",
        "tags: [trading, meme, mesa-real, ficha-diaria, automatica]",
        f"data: {day}",
        "owner: sexta-feira",
        f"generated_by: infra/scripts/meme_daily_ficha.py@{ficha.git_sha}",
        f"generated_at: {ficha.generated_at.astimezone(SAO_PAULO).strftime('%Y-%m-%d %H:%M BRT')}",
        f"updated: {day}",
        "---",
        "",
        f"# Ficha do dia — {ficha.data.day.strftime('%d/%m/%Y')} · mesa real de memes (automática)",
        "",
    ]


def _summary(data: DayFicha) -> list[str]:
    closed = [p for p in data.positions if p.pnl_sol is not None]
    wins = [p for p in closed if p.pnl_sol is not None and p.pnl_sol > 0]
    losses = [p for p in closed if p.pnl_sol is not None and p.pnl_sol <= 0]
    net = sum((p.pnl_sol for p in closed if p.pnl_sol is not None), Decimal(0))
    avg_win = (
        None if not wins else sum((p.pnl_sol for p in wins if p.pnl_sol), Decimal(0)) / len(wins)
    )
    avg_loss = (
        None
        if not losses
        else sum((p.pnl_sol for p in losses if p.pnl_sol), Decimal(0)) / len(losses)
    )
    best = max((p for p in closed), key=lambda p: p.pnl_sol or Decimal(0), default=None)
    worst = min((p for p in closed), key=lambda p: p.pnl_sol or Decimal(0), default=None)
    return [
        "## O placar",
        "",
        f"- **Operações:** {len(data.positions)} ({len(closed)} fechadas, "
        f"{len(data.positions) - len(closed)} ainda abertas)",
        f"- **Ganhos:** {len(wins)}/{len(closed)} "
        + ("—" if not closed else f"({len(wins) * 100 // len(closed)} %)"),
        f"- **Net SOL (fechadas):** {_n(net)}",
        f"- **Ganho médio:** {_n(avg_win, reason='nenhum ganho fechado')}",
        f"- **Perda média:** {_n(avg_loss, reason='nenhuma perda fechada')}",
        f"- **Melhor:** {'—' if best is None else f'{_label(best)} {_n(best.pnl_sol)}'}",
        f"- **Pior:** {'—' if worst is None else f'{_label(worst)} {_n(worst.pnl_sol)}'}",
        f"- **Acumulado (todo o histórico até o fim do dia):** "
        f"{_n(data.cumulative_pnl_sol, reason='nenhuma posição real fechada ainda')}",
        "",
    ]


def _positions_table(positions: Sequence[RealPosition]) -> list[str]:
    if not positions:
        return ["## As posições reais do dia", "", "Nenhuma posição real de meme neste dia.", ""]
    lines = [
        "## As posições reais do dia",
        "",
        "| # | moeda | operador | entrada | saída | duração | SOL in | SOL out | PnL SOL | PnL % | "
        "pico % | subiu depois? | motivo saída | tentativas venda | custo ida-e-volta | classe |",
        "|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|---:|---|",
    ]
    for i, p in enumerate(positions, start=1):
        rose = rose_after_buy(high_water_sol=p.high_water_sol, cost_sol=p.cost_sol)
        rose_text = "—" if rose is None else ("sim" if rose else "não")
        klass = _loss_class(p)
        klass_text = "ganho" if p.pnl_sol is not None and p.pnl_sol >= 0 else (klass or "—")
        lines.append(
            f"| {i} | {_label(p)} | `{p.operator}` | {_brt(p.entry_at)} | {_brt(p.exit_at)} | "
            f"{_duration(p.entry_at, p.exit_at)} | {_n(p.cost_sol)} | "
            f"{_n(p.sol_out, reason='sem venda confirmada')} | "
            f"{_n(p.pnl_sol, reason='posição aberta')} | {_pct(_pnl_pct(p), reason='posição aberta')} | "
            f"{_pct(_peak_pct(p), reason='sem marca registrada')} | {rose_text} | "
            f"{p.exit_reason or '—'} | {p.sell_attempts} | "
            f"{_n(p.round_trip_cost_sol, reason='fill incompleto')} | {klass_text} |"
        )
    lines.append("")
    return lines


def _features_table(positions: Sequence[RealPosition]) -> list[str]:
    if not positions:
        return []
    lines = [
        "## As métricas da decisão",
        "",
        "| moeda | progresso da curva | compras 1m | vendas 1m | compradores únicos | "
        "fluxo líquido (SOL/min) | snipers | dev share | bundle da criação (SOL/carteiras) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for p in positions:
        f = p.features
        bundle = (
            "—"
            if f.creation_bundle_sol is None and f.creation_bundle_wallets is None
            else f"{_n(f.creation_bundle_sol, places=2)} / {_n(f.creation_bundle_wallets, places=0)}"
        )
        lines.append(
            f"| {_label(p)} | {_pct(f.curve_progress_pct)} | {_n(f.buys_1m, places=0)} | "
            f"{_n(f.sells_1m, places=0)} | {_n(f.unique_buyers, places=0)} | "
            f"{_n(f.net_flow_sol, places=2, reason='sem fita de decisão registrada')} | "
            f"{_n(f.snipers, places=0)} | {_pct(f.dev_share_pct)} | {bundle} |"
        )
    lines.append("")
    return lines


def _loss_totals(positions: Sequence[RealPosition]) -> list[str]:
    by_class: dict[str, list[Decimal]] = {}
    for p in positions:
        klass = _loss_class(p)
        if klass is None:
            continue
        by_class.setdefault(klass, []).append(p.pnl_sol or Decimal(0))
    lines = ["## A classe de perda automática", ""]
    if not by_class:
        lines += ["Nenhuma perda fechada neste dia.", ""]
        return lines
    lines += ["| classe | n | SOL |", "|---|---:|---:|"]
    for klass in sorted(by_class, key=lambda k: sum(by_class[k])):
        values = by_class[klass]
        lines.append(f"| {klass} | {len(values)} | {_n(sum(values, Decimal(0)))} |")
    worst_class = min(by_class, key=lambda k: sum(by_class[k]))
    worst_total = sum(by_class[worst_class], Decimal(0))
    lines += [
        "",
        f"**Maior vazamento do dia:** `{worst_class}` ({len(by_class[worst_class])} operações, {_n(worst_total)} SOL)",
        "",
    ]
    return lines


def _spot_table(spot: Sequence[SpotPosition]) -> list[str]:
    lines = ["## `spot/1` — posições reais do dia", ""]
    if not spot:
        lines += ["Nenhuma posição real de `spot/1` neste dia.", ""]
        return lines
    lines += [
        "| mercado | entrada | preço entrada | alvo | stop | saída | PnL SOL |",
        "|---|---|---:|---:|---:|---|---:|",
    ]
    for s in spot:
        lines.append(
            f"| `{s.market_symbol}` | {_brt(s.entry_at)} | {_n(s.entry_price, places=2, reason='não registrado')} | "
            f"{_n(s.target_price, places=2, reason='não registrado')} | "
            f"{_n(s.stop_price, places=2, reason='não registrado')} | {_brt(s.exit_at)} | "
            f"{_n(s.pnl_sol, reason='posição aberta')} |"
        )
    lines.append("")
    return lines


def _paper_arms_table(arms: Sequence[PaperArm]) -> list[str]:
    lines = [f"## Braços de papel — últimas 24 h (normalizado a {TICKET_SOL} SOL/ficha)", ""]
    if not arms:
        lines += ["Nenhuma entrada de papel nas últimas 24 h.", ""]
        return lines
    lines += ["| braço | entradas | ganhos | SOL | avg % por ficha |", "|---|---:|---:|---:|---:|"]
    for arm in arms:
        lines.append(
            f"| `{arm.rule_set}` | {arm.entries} | {arm.wins} | {_n(arm.pnl_sol)} | "
            f"{_pct(arm.avg_pct_per_ticket, reason='nenhuma fechada ainda')} |"
        )
    lines.append("")
    return lines


def render_day(ficha: Ficha) -> str:
    lines: list[str] = []
    lines += _frontmatter(ficha)
    lines += _summary(ficha.data)
    lines += _positions_table(ficha.data.positions)
    lines += _features_table(ficha.data.positions)
    lines += _loss_totals(ficha.data.positions)
    lines += _spot_table(ficha.data.spot)
    lines += _paper_arms_table(ficha.data.paper_arms)
    lines += [
        "## Relacionado",
        "",
        f"[[Fila de Hipoteses]] · [[KB-0149-o-que-a-mesa-real-ensinou]] · "
        f"[[09-OPERATIONS/Diario/{ficha.data.day.isoformat()}|{ficha.data.day.isoformat()}]]",
    ]
    return "\n".join(lines) + "\n"


def render_week(
    by_day: dict[str, list[RealPosition]], *, generated_at: datetime, git_sha: str
) -> str:
    """The last 7 days by loss class, for the weekly review."""
    totals: dict[str, list[Decimal]] = {}
    positions_n = 0
    for positions in by_day.values():
        for p in positions:
            positions_n += 1
            klass = _loss_class(p)
            if klass is not None:
                totals.setdefault(klass, []).append(p.pnl_sol or Decimal(0))
    days = sorted(by_day)
    lines = [
        "---",
        "tags: [trading, meme, mesa-real, ficha-semanal, automatica]",
        f"generated_by: infra/scripts/meme_daily_ficha.py@{git_sha}",
        f"generated_at: {generated_at.astimezone(SAO_PAULO).strftime('%Y-%m-%d %H:%M BRT')}",
        "---",
        "",
        f"# Ficha semanal — {days[0] if days else '—'} a {days[-1] if days else '—'} · classe de perda",
        "",
        f"**Operações reais na semana:** {positions_n}",
        "",
    ]
    if not totals:
        lines += ["Nenhuma perda fechada na semana.", ""]
    else:
        lines += ["| classe | n | SOL |", "|---|---:|---:|"]
        for klass in sorted(totals, key=lambda k: sum(totals[k])):
            values = totals[klass]
            lines.append(f"| {klass} | {len(values)} | {_n(sum(values, Decimal(0)))} |")
        worst_class = min(totals, key=lambda k: sum(totals[k]))
        worst_total = sum(totals[worst_class], Decimal(0))
        lines += [
            "",
            f"**Maior vazamento da semana:** `{worst_class}` "
            f"({len(totals[worst_class])} operações, {_n(worst_total)} SOL)",
            "",
        ]
    lines += ["## Relacionado", "", "[[Fila de Hipoteses]] · [[KB-0149-o-que-a-mesa-real-ensinou]]"]
    return "\n".join(lines) + "\n"
