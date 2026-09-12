"""Renders one day of the meme Lab as the Obsidian diary note — pure, no IO.

``infra/scripts/meme_diary.py`` reads the rows and calls :func:`render_diary`;
this module turns them into the Markdown of
``obsidian/09-OPERATIONS/Diario-Meme/<AAAA-MM-DD>.md`` in the format the folder's
README fixed before the generator existed (six sections, in that order). Every
number comes from a row; the only free text is the archivist's section, left
as a stub on purpose. A number nobody observed is written as "—" with the
reason, never as zero.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

SAO_PAULO = ZoneInfo("America/Sao_Paulo")
GOAL_TARGET_USD = Decimal(7_000_000)
GOAL_HORIZON_DAYS = 30
PAPER_LABEL = "PAPEL — nenhuma transação real; a chave e a flag ao vivo não existem neste processo"


@dataclass(frozen=True, slots=True)
class RuleSetDay:
    name: str
    version: str
    kind: str
    exp_ref: str | None
    wallet_max_sol: Decimal
    balance_start_sol: Decimal
    balance_end_sol: Decimal
    realized_day_sol: Decimal
    realized_total_sol: Decimal
    r_day: Decimal | None
    r_total: Decimal | None
    drawdown_day_sol: Decimal | None
    drawdown_total_sol: Decimal | None
    bets_day: int
    closed_day: int
    wins_day: int
    rugs_day: int
    open_at_end: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])


@dataclass(frozen=True, slots=True)
class BetLine:
    mint: str
    rule_set: str
    exp_ref: str | None
    entry_at: datetime
    exit_at: datetime | None
    exit_reason: str | None
    r_multiple: Decimal | None
    pnl_sol: Decimal | None
    pnl_usd: Decimal | None
    sol_usd_source: str | None
    sol_usd_observed_at: str | None
    initial_risk_sol: Decimal


@dataclass(frozen=True, slots=True)
class DiaryInputs:
    day: date
    generated_at: datetime
    rule_sets: Sequence[RuleSetDay]
    bets: Sequence[BetLine]
    unfilled_by_refusal: Mapping[str, int]
    expired_proposals: int
    gaps_by_stream_reason: Mapping[str, int]
    sol_usd: Decimal | None
    sol_usd_source: str | None
    sol_usd_observed_at: str | None
    clock_start: date | None
    lab_last_tick_at: datetime | None


def _n(value: Decimal | None, *, places: int = 6, reason: str = "sem leitura") -> str:
    if value is None:
        return f"— ({reason})"
    text = f"{value:.{places}f}".rstrip("0").rstrip(".")
    return text or "0"


def _brt(ts: datetime | None) -> str:
    return "—" if ts is None else ts.astimezone(SAO_PAULO).strftime("%H:%M:%S")


def required_daily_return(capital_usd: Decimal, days_remaining: int) -> Decimal | None:
    """``(7 000 000 / capital) ^ (1 / d) − 1`` — the decision note's formula, the
    same one ``GET /meme/lab`` publishes; undefined without capital or days."""
    if capital_usd <= 0 or days_remaining <= 0:
        return None
    return (GOAL_TARGET_USD / capital_usd).ln().__truediv__(Decimal(days_remaining)).exp() - 1


def _frontmatter(day: date) -> str:
    return (
        "---\n"
        "tags: [operacoes, diario, meme, m4]\n"
        "status: registro\n"
        "owner: sexta-feira\n"
        f"updated: {day.isoformat()}\n"
        "---\n"
    )


def _wallets(inputs: DiaryInputs) -> list[str]:
    lines = [
        "## 1. Estado da carteira paper",
        "",
        "| conjunto | tipo | teto (SOL) | saldo início | saldo fim | PnL do dia | PnL acumulado | abertas ao fechar |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in inputs.rule_sets:
        label = f"`{r.name}/{r.version}`" + (f" ({r.exp_ref})" if r.exp_ref else "")
        lines.append(
            f"| {label} | {r.kind} | {_n(r.wallet_max_sol)} | {_n(r.balance_start_sol)} | "
            f"{_n(r.balance_end_sol)} | {_n(r.realized_day_sol)} | {_n(r.realized_total_sol)} | "
            f"{len(r.open_at_end)} |"
        )
    for r in inputs.rule_sets:
        for position in r.open_at_end:
            lines.append(
                f"- `{r.name}/{r.version}` aberta: `{position['mint']}` — custo "
                f"{_n(position['cost_sol'])} SOL, marca (venda cheia agora) "
                f"{_n(position.get('mark_sol'), reason='sem marca')} SOL"
            )
    return lines


def _bets(inputs: DiaryInputs) -> list[str]:
    lines = ["## 2. Apostas do dia", ""]
    if not inputs.bets:
        lines.append("Nenhuma aposta aberta neste dia (o laço propõe só quando o portão libera).")
        return lines
    lines += [
        "| mint | conjunto | entrada (BRT) | saída (BRT) | motivo | R (SOL) | PnL SOL | PnL USD | cotação |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for b in inputs.bets:
        quote = (
            f"{b.sol_usd_source} @ {b.sol_usd_observed_at}"
            if b.sol_usd_source and b.sol_usd_observed_at
            else "—"
        )
        rule = f"`{b.rule_set}`" + (f" ({b.exp_ref})" if b.exp_ref else "")
        lines.append(
            f"| `{b.mint}` | {rule} | {_brt(b.entry_at)} | {_brt(b.exit_at)} | "
            f"{b.exit_reason or 'aberta'} | {_n(b.r_multiple, places=4, reason='aberta')} | "
            f"{_n(b.pnl_sol, reason='aberta')} | {_n(b.pnl_usd, places=2, reason='sem cotação')} | {quote} |"
        )
    return lines


def _r_section(inputs: DiaryInputs) -> list[str]:
    lines = ["## 3. R em SOL do dia e acumulado", ""]
    lines += [
        "| conjunto | apostas | fechadas | acertos | R do dia | R acumulado | drawdown do dia (SOL) | drawdown acumulado (SOL) | rugs |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in inputs.rule_sets:
        lines.append(
            f"| `{r.name}/{r.version}` | {r.bets_day} | {r.closed_day} | {r.wins_day} | "
            f"{_n(r.r_day, places=4, reason='sem fechada')} | {_n(r.r_total, places=4, reason='sem fechada')} | "
            f"{_n(r.drawdown_day_sol, reason='sem fechada')} | {_n(r.drawdown_total_sol, reason='sem fechada')} | "
            f"{r.rugs_day} |"
        )
    return lines


def _goal(inputs: DiaryInputs) -> list[str]:
    capital_sol = sum((r.balance_end_sol for r in inputs.rule_sets), start=Decimal(0))
    lines = ["## 4. Distância à meta", ""]
    lines.append(
        "> [!alerta] Conta sobre o alvo declarado (US$ 7 M em 30 dias), nunca previsão de retorno."
    )
    lines.append("")
    if inputs.sol_usd is None:
        capital_usd_text = "— (sem cotação SOL/USD observada)"
        required_text = "— (sem cotação SOL/USD observada)"
    else:
        capital_usd = capital_sol * inputs.sol_usd
        capital_usd_text = f"US$ {_n(capital_usd, places=2)} (SOL/USD {_n(inputs.sol_usd, places=4)}, {inputs.sol_usd_source} @ {inputs.sol_usd_observed_at})"
        days_elapsed = (
            0 if inputs.clock_start is None else max((inputs.day - inputs.clock_start).days, 0)
        )
        remaining = max(GOAL_HORIZON_DAYS - days_elapsed, 0)
        rate = required_daily_return(capital_usd, remaining)
        required_text = (
            f"{_n(rate * 100, places=2)} %/dia com {remaining} dias restantes"
            if rate is not None
            else "— (horizonte esgotado ou capital não positivo)"
        )
    realized_day = sum((r.realized_day_sol for r in inputs.rule_sets), start=Decimal(0))
    opening = capital_sol - realized_day
    measured = (
        f"{_n(realized_day / opening * 100, places=2)} %/dia"
        if opening > 0 and any(r.closed_day for r in inputs.rule_sets)
        else "— (nenhuma aposta fechada no dia)"
    )
    clock = (
        f"{inputs.clock_start.isoformat()} (primeiro conjunto ativo; seed da migração 0022)"
        if inputs.clock_start
        else "— (nenhum conjunto de regras)"
    )
    lines += [
        f"- Capital (paper, soma dos conjuntos ativos ao fechar o dia): {_n(capital_sol)} SOL = {capital_usd_text}",
        f"- Retorno diário exigido: {required_text}",
        f"- Retorno diário medido: {measured}",
        f"- Início do relógio: {clock}",
    ]
    return lines


def _incidents(inputs: DiaryInputs) -> list[str]:
    lines = ["## 5. Incidentes", ""]
    rugs = [b for b in inputs.bets if b.exit_reason == "rug_no_snapshot"]
    if rugs:
        lines.append(
            f"- Rug sem fotografia durante aposta aberta: {len(rugs)} ({', '.join('`' + b.mint + '`' for b in rugs)})"
        )
    for refusal, count in sorted(inputs.unfilled_by_refusal.items()):
        lines.append(f"- Propostas não preenchidas — `{refusal}`: {count}")
    if inputs.expired_proposals:
        lines.append(f"- Propostas expiradas sem aval: {inputs.expired_proposals}")
    for key, count in sorted(inputs.gaps_by_stream_reason.items()):
        lines.append(f"- Lacuna de coleta `{key}`: {count}")
    if inputs.lab_last_tick_at is None:
        lines.append(
            "- Laço: sem heartbeat lido (`hb:meme:radar` sem `lab_last_tick_at`) — laço parado ou nunca rodou"
        )
    else:
        lines.append(
            f"- Laço: último tick às {inputs.lab_last_tick_at.astimezone(SAO_PAULO).strftime('%Y-%m-%d %H:%M:%S')} BRT"
        )
    if len(lines) == 2:
        lines.append("Nenhum incidente registrado nas tabelas do dia.")
    return lines


def render_diary(inputs: DiaryInputs) -> str:
    """The whole note, frontmatter included."""
    generated = inputs.generated_at.astimezone(SAO_PAULO).strftime("%Y-%m-%d %H:%M BRT")
    header = [
        f"# Diário Meme — {inputs.day.isoformat()}",
        "",
        f"Gerado por `infra/scripts/meme_diary.py` em {generated} a partir de `meme_paper_bets`, "
        f"`meme_proposals`, `meme_rule_sets` e `meme_ingest_gaps`. **{PAPER_LABEL}.** "
        "Nenhum número financeiro abaixo foi digitado à mão; só a seção 6 é do arquivista.",
        "",
    ]
    body = (
        header
        + _wallets(inputs)
        + [""]
        + _bets(inputs)
        + [""]
        + _r_section(inputs)
        + [""]
        + _goal(inputs)
        + [""]
        + _incidents(inputs)
        + ["", "## 6. O que o Lab aprendeu", "", "(a preencher pelo arquivista — Sexta-feira)", ""]
    )
    return _frontmatter(inputs.day) + "\n" + "\n".join(body)
