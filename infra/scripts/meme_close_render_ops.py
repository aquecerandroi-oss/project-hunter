"""Section 6's operational subsections — coverage, operator, real trades against
the Lab's verdict, leave-top-out and the comparison with the pre-registration.
Pure text; a number nobody measured is "—" with the reason, never zero."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from meme_close_inputs import CloseInputs, Coverage, OperatorDay, brt, ci_pair, pct
from meme_close_lessons import TopOut
from meme_close_stats import fmt
from meme_diary_render import WalletTradeLine


def coverage_section(c: Coverage) -> list[str]:
    lines = ["### 6.10 Cobertura do dia", ""]
    if c.rows:
        lines.append(
            f"- Linhas do portão (`meme_features_1m`, versão mais alta do dia): {c.rows} em "
            f"{c.minutes} minutos × {c.mints} mints; com progresso {c.with_progress}/{c.rows} "
            f"({pct(c.with_progress, c.rows)}), com fita {c.with_tape}/{c.rows} "
            f"({pct(c.with_tape, c.rows)}), com linha {c.with_line}/{c.rows} "
            f"({pct(c.with_line, c.rows)}), com hype {c.with_hype}/{c.rows} ({pct(c.with_hype, c.rows)})."
        )
    else:
        lines.append(
            "- Linhas do portão: nenhuma linha de `meme_features_1m` no dia (coletor parado?)."
        )
    if c.ticks:
        lines.append(
            f"- Laço (`meme_lab_ticks`): {c.ticks} ticks entre {brt(c.first_tick)} e {brt(c.last_tick)} "
            f"BRT, {c.gaps} buraco{'s' if c.gaps != 1 else ''} > 3 min, {c.rows_evaluated} linhas "
            "avaliadas pelo portão."
        )
    else:
        lines.append(
            "- Laço: **sem ticks gravados** em `meme_lab_ticks` (laço parado, ou anterior à migração "
            "0031) — a cobertura do portão não é reconstruível para este dia."
        )
    if c.refusals:
        for rule_set, reasons in sorted(c.refusals.items()):
            listed = ", ".join(
                f"`{reason}`: {count}"
                for reason, count in sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0]))
            )
            lines.append(f"- Recusas de `{rule_set}` (soma dos ticks): {listed or '—'}.")
    elif c.ticks:
        lines.append("- Recusas por motivo: nenhuma recusa registrada nos ticks do dia.")
    else:
        lines.append("- Recusas por motivo: — (sem ticks gravados).")
    change = "nada muda nas regras (cobertura é instrumento — T4.2*/T4.16 —, não porta)"
    if not c.ticks:
        change += "; verificar `hb:meme:radar` e a migração 0031 antes do próximo fechamento"
    lines += ["", f"**O que muda amanhã:** {change}.", ""]
    return lines


def _quantile(values: Sequence[int], p: float) -> int:
    ordered = sorted(values)
    position = p * (len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return round(ordered[low] + (ordered[high] - ordered[low]) * (position - low))


def operator_section(o: OperatorDay) -> list[str]:
    lines = [
        "### 6.11 Operador",
        "",
        f"- Operador: propostas pelo laço {o.proposed} (conjunto `operator`): aprovadas {o.approved}, "
        f"rejeitadas {o.rejected}, expiradas sem aval {o.expired}; preenchidas {o.filled}, não "
        f"preenchidas {o.unfilled}; manuais {o.manual}.",
    ]
    if o.latency_s:
        lines.append(
            f"- Latência até o aval (aprovadas/rejeitadas): mediana {_quantile(o.latency_s, 0.5)} s, "
            f"p90 {_quantile(o.latency_s, 0.9)} s, máx {max(o.latency_s)} s (n = {len(o.latency_s)})."
        )
    else:
        lines.append("- Latência até o aval: — (nenhuma proposta decidida pela mesa).")
    if o.r_approved:
        total = sum(o.r_approved, Decimal(0))
        lines.append(
            f"- R das aprovadas fechadas: n = {len(o.r_approved)}, R somado {fmt(total)}, "
            f"R médio {fmt(total / len(o.r_approved))}."
        )
    else:
        lines.append("- R das aprovadas fechadas: — (nenhuma aposta aprovada fechou).")
    lines += [
        "",
        "**O que muda amanhã:** nada muda (o operador não é regra; a latência é do humano, não do laço).",
        "",
    ]
    return lines


def reals_section(reals: Sequence[WalletTradeLine]) -> list[str]:
    lines = ["### 6.12 Operações reais × veredito do Lab", ""]
    if not reals:
        lines += ["Nenhuma operação real observada neste dia.", ""]
    else:
        wallets: dict[str, dict[str, int]] = {}
        positions: dict[tuple[str, str | None], Decimal | None] = {}
        for t in reals:
            w = wallets.setdefault(t.wallet, {"buy": 0, "sell": 0})
            if t.side in w:
                w[t.side] += 1
            positions[(t.wallet, t.mint)] = t.realized_pnl_sol
        lines += [
            "| carteira | compras | vendas | PnL realizado (SOL, FIFO) |",
            "|---|---|---|---|",
        ]
        for wallet, counts in sorted(wallets.items()):
            pnl = [v for (w, _m), v in positions.items() if w == wallet and v is not None]
            realized = fmt(sum(pnl, Decimal(0))) if pnl else "—"
            lines.append(f"| `{wallet[:8]}` | {counts['buy']} | {counts['sell']} | {realized} |")
        lines.append("")
        buys = [t for t in reals if t.side == "buy"]
        labels = sorted({label for t in buys for label in t.lab_verdicts})
        for label in labels:
            accepted = [t for t in buys if t.lab_verdicts.get(label) == "aceito"]
            refused = [
                t.lab_verdicts[label]
                for t in buys
                if t.lab_verdicts.get(label) not in (None, "aceito")
            ]
            r_values = [t.r_multiple for t in accepted if t.r_multiple is not None]
            r_text = (
                f"R das posições {fmt(sum(r_values, Decimal(0)))}"
                if r_values
                else "R — (posições sem marca)"
            )
            why = f" — recusas: {', '.join(sorted(set(refused)))}" if refused else ""
            lines.append(
                f"- `{label}` aceitaria {len(accepted)} de {len(buys)} compras reais ({r_text}){why}."
            )
        if not labels:
            lines.append(
                "- O Lab não tinha veredito gravado (`lab_context`) para nenhuma compra real."
            )
        lines.append("")
    lines += [
        "**O que muda amanhã:** nada muda nas regras; a diferença Lab × real fica registrada aqui e no lote.",
        "",
    ]
    return lines


def top_out_section(rows: Sequence[TopOut]) -> list[str]:
    lines = ["### 6.13 Leave-top-out", ""]
    if not rows:
        lines += ["Nenhuma aposta fechada no dia.", ""]
    else:
        lines += [
            "| conjunto | n | R somado | melhor aposta | R sem a melhor | leitura |",
            "|---|---|---|---|---|---|",
        ]
        for r in rows:
            if r.total > 0 and r.without_best <= 0:
                reading = "o saldo positivo é um bilhete (vira ≤ 0 sem a melhor)"
            elif r.total > 0:
                reading = "positivo com e sem a melhor"
            else:
                reading = "negativo com ou sem a melhor"
            lines.append(
                f"| `{r.rule_set}` | {r.n} | {fmt(r.total)} | `{r.best_mint}` ({fmt(r.best_r)}) | "
                f"{fmt(r.without_best)} | {reading} |"
            )
        lines.append("")
    lines += [
        "**O que muda amanhã:** nada muda hoje; o lote de amanhã carrega o sinal do leave-top-out por conjunto.",
        "",
    ]
    return lines


def prereg_section(inputs: CloseInputs) -> list[str]:
    lines = ["### 6.14 Comparação com o pré-registro", ""]
    exps = [e for e in inputs.all_time if e.exp_ref]
    if not exps:
        lines += ["Nenhum conjunto ativo com `exp_ref`.", ""]
    for e in exps:
        prediction = inputs.predictions.get(e.exp_ref or "")
        quoted = f"«{prediction}»" if prediction else "— (previsão não localizada na página)"
        lines += [
            f"- **{e.exp_ref}** (`{e.rule_set}`): hoje n = {e.today_n}, R somado {fmt(e.today_total)}; "
            f"acumulado n = {e.n}, dias distintos = {e.days}, R médio {fmt(e.mean)}, IC 95 % por blocos "
            f"de dia {ci_pair(e.ci95, missing='— (< 2 dias)')}, alvo em {fmt(e.target_share, places=1)} %, "
            f"`dead`/`time_stop` em {fmt(e.dead_or_time_share, places=1)} %, R sem a melhor "
            f"{fmt(e.without_best)}. A previsão congelada dizia: {quoted}. Veredito: régua não atingida "
            f"(n {e.n}/100, dias {e.days}/30) — `result` da página não muda."
        ]
    lines += [
        "",
        "**O que muda amanhã:** nada muda (avaliação datada acrescentada à página de cada EXP com aposta hoje; "
        "o veredito é do orquestrador).",
        "",
    ]
    return lines
