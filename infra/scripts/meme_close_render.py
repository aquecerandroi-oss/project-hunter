"""Section 6 of the diary — "O que o Lab aprendeu" — rendered from the day's
lessons. Pure: no database, no clock, no file.

The section replaces the stub ``meme_diary_render`` leaves for the archivist,
lesson by lesson, in the order the brief fixed (T4.15): exits by reason, age,
progress, snipers, top-10, dev, same slot, serial creator, symbol clones,
coverage, operator, real trades against the Lab's verdict, leave-top-out and
the comparison with the frozen pre-registration
(``meme_close_render_ops.py``). Every lesson ends with one sentence — "o que
muda amanhã" — and a number nobody measured is "—" with the reason, never zero.
"""

from __future__ import annotations

from meme_close_inputs import (
    CloseInputs,
    Coverage,
    ExpAllTime,
    OperatorDay,
    brt,
    ci_pair,
    pct,
)
from meme_close_lessons import Lesson
from meme_close_render_ops import (
    coverage_section,
    operator_section,
    prereg_section,
    reals_section,
    top_out_section,
)
from meme_close_stats import Contrast, Interval, fmt

__all__ = [
    "DIARY_STUB",
    "SECTION_SIX",
    "CloseInputs",
    "Coverage",
    "ExpAllTime",
    "OperatorDay",
    "brt",
    "fill_section_six",
    "pct",
    "render_lessons_section",
]

DIARY_STUB = "(a preencher pelo arquivista — Sexta-feira)"
SECTION_SIX = "## 6. O que o Lab aprendeu"


def _ci(interval: Interval) -> str:
    if interval.ci95 is None:
        return f"— ({interval.blocks} bloco{'s' if interval.blocks != 1 else ''})"
    return ci_pair(interval.ci95, missing="—")


def _contrast_line(label: str | None, contrast: Contrast | None) -> list[str]:
    if label is None or contrast is None:
        return []
    return [
        f"Contraste: «{label}» (n = {contrast.n_a}, R médio {fmt(contrast.mean_a)}) contra as demais "
        f"(n = {contrast.n_b}, R médio {fmt(contrast.mean_b)}): Δ {fmt(contrast.delta)} R, "
        f"IC 95 % por blocos de hora {ci_pair(contrast.ci95, missing='— (sem blocos suficientes)')} "
        f"({contrast.blocks} blocos).",
        "",
    ]


def _lesson(index: int, lesson: Lesson) -> list[str]:
    lines = [f"### 6.{index} {lesson.title}", "", lesson.note, ""]
    if lesson.cells:
        lines += [
            "| conjunto | célula | n | fração | R médio | R somado | IC 95 % (blocos de hora) |",
            "|---|---|---|---|---|---|---|",
        ]
        for cell in lesson.cells:
            group = f"`{cell.group}`" if cell.group else "todos"
            i = cell.interval
            lines.append(
                f"| {group} | {cell.label} | {i.n} | {pct(i.n, lesson.n)} | {fmt(i.mean)} | "
                f"{fmt(i.total)} | {_ci(i)} |"
            )
        lines.append("")
    else:
        lines += ["Nenhuma aposta fechada no dia (n = 0).", ""]
    lines += _contrast_line(lesson.contrast_label, lesson.contrast)
    lines += [f"**O que muda amanhã:** {lesson.change}.", ""]
    return lines


def render_lessons_section(inputs: CloseInputs) -> str:
    """The body that replaces the archivist's stub under ``## 6.``."""
    generated = brt(inputs.generated_at, "%Y-%m-%d %H:%M")
    lines = [
        f"Gerado por `infra/scripts/meme_close_day.py --day {inputs.day.isoformat()}` em {generated} BRT. "
        "Régua: cada lição traz n, IC 95 % por blocos de hora (bootstrap por blocos, semente 20260912, "
        "2 000 reamostragens); n < 30 = insuficiente; uma lição só vira linha `M-L` na fila quando o "
        "contraste passa a régua (n ≥ 30, ≥ 3 blocos, células ≥ 10, IC fora de zero); nenhuma vira "
        f"regra viva sem pré-registro (KB-0092). Apostas fechadas do dia: n = {len(inputs.bets)}.",
        "",
    ]
    for index, lesson in enumerate(inputs.lessons, start=1):
        lines += _lesson(index, lesson)
    lines += coverage_section(inputs.coverage)
    lines += operator_section(inputs.operator)
    lines += reals_section(inputs.reals)
    lines += top_out_section(inputs.top_out)
    lines += prereg_section(inputs)
    lines += [
        "### 6.15 Nota do arquivista",
        "",
        "(a acrescentar pela Sexta-feira, se houver — os números acima não se editam à mão)",
        "",
    ]
    return "\n".join(lines)


def fill_section_six(note: str, body: str) -> str | None:
    """Replace the archivist's stub with ``body``; ``None`` when section 6 is
    missing or was already written (a datelined record is never rewritten)."""
    at = note.find(SECTION_SIX)
    if at < 0:
        return None
    head = at + len(SECTION_SIX)
    if note[head:].strip() != DIARY_STUB:
        return None
    return note[:head] + "\n\n" + body
