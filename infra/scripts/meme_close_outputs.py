"""The close's other outputs — pure text: the ``M-L`` rows for the hypotheses
queue, the next batch's proposal, the dated evaluation appended to an EXP-M*
page, and the diary folder's index line.

Every write these feed is **append-only** and idempotent by a marker that
names the day; the ``obsidian_lint.py`` rule ``exp_reescrita`` is what keeps
an evaluation from ever being rewritten, so nothing here edits an existing
section.
"""

from __future__ import annotations

import re
from datetime import timedelta

from meme_close_render import CloseInputs, ExpAllTime, brt
from meme_close_stats import fmt

INBOX_MARKER = "fechamento diário T4.15, dia {day}"
EVALUATION_HEADING = "### Avaliação de {day} — fechamento diário (T4.15)"
_INBOX_NUMBER = re.compile(r"\*\*M-L(\d+)\*\*")
_VERDICT = "Veredito previsto"


def next_inbox_number(inbox_text: str) -> int:
    numbers = [int(n) for n in _INBOX_NUMBER.findall(inbox_text)]
    return (max(numbers) + 1) if numbers else 1


def inbox_rows(inputs: CloseInputs, *, first_number: int) -> list[str]:
    """One ``nova`` row per lesson that passed the ruler — none otherwise."""
    day = inputs.day.isoformat()
    rows: list[str] = []
    number = first_number
    for lesson in inputs.lessons:
        if lesson.measured is None or lesson.proposal is None:
            continue
        rows.append(
            f"| {day} | **M-L{number}** (lição medida; {INBOX_MARKER.format(day=day)}) — "
            f"{lesson.measured} | `infra/scripts/meme_close_day.py --day {day}` sobre "
            "`meme_paper_bets`, `meme_proposals`, `meme_tokens` e `meme_features_1m`; diário "
            f"[[09-OPERATIONS/Diario-Meme/{day}]] | {lesson.proposal} | nova |"
        )
        number += 1
    return rows


def _retire_or_keep(e: ExpAllTime) -> str:
    ruler = e.n >= 100 and e.days >= 30
    below_zero = e.ci95 is not None and e.ci95[1] < 0
    if ruler and below_zero and e.without_best is not None and e.without_best < 0:
        return "aposentar (proposta: régua atingida e IC inteiramente < 0)"
    return f"manter (n {e.n}/100, dias {e.days}/30)"


def render_lote(inputs: CloseInputs) -> str:
    day = inputs.day.isoformat()
    tomorrow = (inputs.day + timedelta(days=1)).isoformat()
    generated = brt(inputs.generated_at, "%Y-%m-%d %H:%M")
    lines = [
        f"# Lote meme — proposta para {tomorrow}",
        "",
        f"Gerado por `infra/scripts/meme_close_day.py --day {day}` em {generated} BRT a partir do "
        f"fechamento de {day} (`obsidian/09-OPERATIONS/Diario-Meme/{day}.md`). **Proposta, não ação**: "
        "o orquestrador pré-registra (página EXP-M* nova antes de qualquer corrida) e o Everton decide "
        "o que pesa dinheiro; nada aqui altera `meme_rule_sets`.",
        "",
        "## 1. Conjuntos vivos — manter ou aposentar (proposta)",
        "",
        "| conjunto | exp | n acumulado | dias | R médio | IC 95 % (blocos de dia) | R sem a melhor | proposta |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for e in inputs.all_time:
        ci = "— (< 2 dias)" if e.ci95 is None else f"[{fmt(e.ci95[0])}, {fmt(e.ci95[1])}]"
        lines.append(
            f"| `{e.rule_set}` | {e.exp_ref or '—'} | {e.n} | {e.days} | {fmt(e.mean)} | {ci} | "
            f"{fmt(e.without_best)} | {_retire_or_keep(e)} |"
        )
    lines += [
        "",
        'Regra: "aposentar" só com n ≥ 100 **e** ≥ 30 dias **e** IC 95 % por blocos de dia inteiramente '
        "abaixo de zero **e** leave-top-out negativo (a régua de sucesso do pré-registro ao contrário); "
        'até lá "manter", com a contagem.',
        "",
        "## 2. Braços a pré-registrar (lições que passaram a régua hoje)",
        "",
    ]
    passed = [lesson for lesson in inputs.lessons if lesson.proposal]
    if not passed:
        lines.append(
            "Nenhuma lição passou a régua hoje — nenhum braço novo; o que roda amanhã é o que rodou hoje."
        )
    for lesson in passed:
        lines += [
            f"- **{lesson.title}** — {lesson.proposal}.",
            f"  Evidência: {lesson.measured}. Parâmetros: os do conjunto-base byte a byte mais o filtro; "
            "tamanho o do base; nome sugerido `<base>_ml/1`; página `EXP-M<n>` nova com a previsão "
            "`descartar` escrita antes da primeira corrida.",
        ]
    lines += [
        "",
        "## 3. O que não fazer",
        "",
        "- Ajustar limiar de conjunto vivo olhando as apostas de um dia (KB-0092: o modelo que morreu no holdout).",
        "- Ligar dinheiro real em regra que não passou a régua de sucesso do pré-registro.",
        "- Aposentar por um dia ruim: a régua da seção 1 exige n e dias, não humor.",
        "",
    ]
    return "\n".join(lines)


def frozen_prediction(page: str) -> str | None:
    """The bullet of "Previsões congeladas" that carries the predicted verdict,
    quoted flat (bold stripped); ``None`` when the page has none."""
    lines = page.splitlines()
    end = next((i for i, line in enumerate(lines) if _VERDICT in line), None)
    if end is None:
        return None
    start = end
    while start > 0 and not lines[start].lstrip().startswith("- "):
        start -= 1
    text = " ".join(line.strip() for line in lines[start : end + 1])
    text = text.removeprefix("- ").replace("**", "")
    return re.sub(r"\s+", " ", text).strip()


def exp_evaluation(inputs: CloseInputs, exp: ExpAllTime, prediction: str | None) -> str:
    day = inputs.day.isoformat()
    ci = "— (< 2 dias)" if exp.ci95 is None else f"[{fmt(exp.ci95[0])}, {fmt(exp.ci95[1])}]"
    reasons = ", ".join(
        f"`{reason}` {count}"
        for reason, count in sorted(exp.today_reasons.items(), key=lambda kv: (-kv[1], kv[0]))
    )
    quoted = (
        f"«{prediction}»" if prediction else "— (não localizada na seção de previsões da página)"
    )
    return "\n".join(
        [
            EVALUATION_HEADING.format(day=day),
            "",
            f"Escrita por `infra/scripts/meme_close_day.py --day {day}` em "
            f"{brt(inputs.generated_at, '%Y-%m-%d %H:%M')} BRT (`meme_paper_bets`, conjunto "
            f"`{exp.rule_set}`, coorte prospectiva). Nada acima desta linha foi editado.",
            "",
            f"- **Hoje ({day})**: n = {exp.today_n}, R somado {fmt(exp.today_total)}; saídas: "
            f"{reasons or '—'}.",
            f"- **Acumulado até {day} 23:59 BRT**: n = {exp.n}, dias distintos = {exp.days}, R médio "
            f"{fmt(exp.mean)}, IC 95 % por blocos de dia {ci}, alvo em {fmt(exp.target_share, places=1)} % "
            f"das saídas, `dead`/`time_stop` em {fmt(exp.dead_or_time_share, places=1)} %, "
            f"leave-top-out (R somado sem a melhor) {fmt(exp.without_best)}.",
            f"- **A previsão congelada dizia:** {quoted}",
            f"- **Veredito:** régua não atingida (n {exp.n}/100, dias {exp.days}/30) — `result` da "
            "frontmatter não muda; quem escreve `validada`/`reprovada` é o orquestrador, com a régua "
            "completa (2 de 3 janelas, controle, censura).",
            "",
        ]
    )


def append_evaluation(page: str, block: str) -> str | None:
    """Insert ``block`` at the end of "Avaliações" (before "Variantes tentadas");
    ``None`` when this day's evaluation is already on the page."""
    heading = block.splitlines()[0]
    if heading in page:
        return None
    body = page if page.endswith("\n") else page + "\n"
    for anchor in ("## Variantes tentadas", "## Relacionadas"):
        at = body.find(anchor)
        if at >= 0:
            return body[:at].rstrip("\n") + "\n\n" + block + "\n" + body[at:]
    return body + "\n" + block


def diary_index_line(inputs: CloseInputs) -> str:
    day = inputs.day.isoformat()
    total = sum((b.r_multiple for b in inputs.bets), start=__import__("decimal").Decimal(0))
    return (
        f"- [[09-OPERATIONS/Diario-Meme/{day}|{day}]] — {len(inputs.bets)} apostas fechadas, "
        f"R somado {fmt(total)}"
    )
