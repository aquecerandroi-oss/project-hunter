"""The lessons of one day of the meme Lab — pure: closed bets in, lessons out.

Each lesson is the same shape the study of 2026-09-12 wrote by hand
(``obsidian/03-TRADING/Meme/Estudo-2026-09-12-21-apostas.md``), measured
instead of read: exits by reason (and which exit cost the most R), age and
progress at entry in bands, snipers/top-10/dev at entry in terciles, the same
slot, the serial creator and the symbol clones. The pieces — cells, the
ruler, the verdict sentence — are ``meme_close_lesson_kit.py``'s.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from meme_close_lesson_kit import (
    Cell,
    ClosedBet,
    Lesson,
    TopOut,
    banded,
    cells,
    ci_text,
    grouped,
    hour_block,
    leave_top_out,
    lesson_flag,
    sample,
    verdict,
)
from meme_close_stats import block_contrast, fmt, tercile_edges, tercile_label

__all__ = [
    "AGE_BANDS",
    "EXIT_HINTS",
    "PROGRESS_BANDS",
    "SERIAL_CREATOR_MIN",
    "SYMBOL_CLONE_MIN",
    "Cell",
    "ClosedBet",
    "Lesson",
    "TopOut",
    "day_lessons",
    "hour_block",
    "leave_top_out",
    "lesson_age",
    "lesson_exits",
    "lesson_flag",
    "lesson_progress",
    "lesson_tercile",
]

SERIAL_CREATOR_MIN = 2
"""≥ 2 mints of the same creator in the hour before — the study's marker."""
SYMBOL_CLONE_MIN = 3
"""≥ 3 mints with the same symbol in the 24 h before — the study's marker."""

EXIT_HINTS: dict[str, str] = {
    "time_stop": "`max_hold_s`",
    "trailing": "`trailing_pct`",
    "max_loss": "`max_loss_pct`",
    "target": "`target_x`",
    "creator_dump": "a porta `creator_net_seller` (E2, exclusões de pedigree)",
    "rug_no_snapshot": "o instrumento (cobertura de fotografias), não uma regra",
    "dead": "`dead_stale_s`/`dead_mark_pct`",
    "line_broken": "`line_break_snapshots`",
    "migrated": "`exit_on_migration`",
    "sell_now": "nada (saída do operador, fora de regra)",
}


def lesson_exits(bets: Sequence[ClosedBet]) -> Lesson:
    """Fraction and R by exit reason per rule set; which exit cost the most R."""
    title, feature = "Saídas por motivo", "exit.reason"
    per_set: dict[str, list[ClosedBet]] = {}
    for bet in bets:
        per_set.setdefault(bet.rule_set, []).append(bet)
    table = tuple(
        cell
        for rule_set, rows in sorted(per_set.items())
        for cell in cells(grouped(rows, lambda b: b.exit_reason), group=rule_set)
    )
    pooled = grouped(bets, lambda b: b.exit_reason)
    if not pooled:
        change, _, _ = verdict(title=title, feature=feature, n=0, contrast=None, label=None)
        return Lesson("saidas", title, feature, 0, table, "Nenhuma saída no dia.", change)
    reason = min(pooled, key=lambda r: (sum((b.r_multiple for b in pooled[r]), Decimal(0)), r))
    total = sum((b.r_multiple for b in pooled[reason]), Decimal(0))
    share = Decimal(len(pooled[reason]) * 100) / len(bets)
    note = (
        f"Qual saída custou mais R: `{reason}` ({fmt(total)} R somados em {len(pooled[reason])} "
        f"saídas, {fmt(share, places=1)} % das saídas fechadas do dia)."
    )
    label = f"saída `{reason}`"
    contrast = block_contrast(
        sample(pooled[reason]), sample([b for b in bets if b.exit_reason != reason])
    )
    change, measured, proposal = verdict(
        title=title, feature=feature, n=len(bets), contrast=contrast, label=label
    )
    if measured is not None:
        hint = EXIT_HINTS.get(reason, "o parâmetro dessa saída")
        change = (
            f"amanhã o lote propõe um braço irmão com {hint} revisto — `{reason}` custou "
            f"{fmt(total)} R em {len(pooled[reason])} saídas (Δ {fmt(contrast.delta)} R contra as "
            f"outras saídas, {ci_text(contrast)}); os conjuntos vivos não mudam"
        )
        proposal = (
            f"braço irmão com {hint} revisto (saída `{reason}`); previsão `descartar`; régua "
            "≥ 100 apostas e 30 dias, IC 95 % por blocos de dia, leave-top-out; controle = o "
            "conjunto de hoje no mesmo período"
        )
    return Lesson(
        "saidas",
        title,
        feature,
        len(bets),
        table,
        note,
        change,
        contrast,
        label,
        measured,
        proposal,
    )


AGE_BANDS = ("< 30 s", "30–60 s", "1–2 min", "2–5 min", "5–10 min", "> 10 min", "desconhecida")
_AGE_EDGES = (
    (30, "< 30 s"),
    (60, "30–60 s"),
    (120, "1–2 min"),
    (300, "2–5 min"),
    (600, "5–10 min"),
)


def _age_band(bet: ClosedBet) -> str:
    age = bet.age_at_entry_s
    if age is None:
        return "desconhecida"
    return next((label for edge, label in _AGE_EDGES if age < edge), "> 10 min")


PROGRESS_BANDS = ("< 5 %", "5–10 %", "10–30 %", "≥ 30 %", "desconhecido")
_PROGRESS_EDGES = ((Decimal(5), "< 5 %"), (Decimal(10), "5–10 %"), (Decimal(30), "10–30 %"))


def _progress_band(bet: ClosedBet) -> str:
    progress = bet.progress_pct
    if progress is None:
        return "desconhecido"
    return next((label for edge, label in _PROGRESS_EDGES if progress < edge), "≥ 30 %")


def lesson_age(bets: Sequence[ClosedBet]) -> Lesson:
    return banded(
        bets,
        key="idade",
        title="Idade na entrada × R",
        feature="age_at_entry_s",
        label_of=_age_band,
        order=AGE_BANDS,
        note="Idade = `entry_at − meme_tokens.created_at` (o fill, não a proposta).",
    )


def lesson_progress(bets: Sequence[ClosedBet]) -> Lesson:
    return banded(
        bets,
        key="progresso",
        title="Progresso na entrada × R",
        feature="curve_progress_pct",
        label_of=_progress_band,
        order=PROGRESS_BANDS,
        note="Progresso da curva na fotografia da proposta (`meme_proposals.quote`), em %.",
    )


def lesson_tercile(bets: Sequence[ClosedBet], *, key: str, title: str, feature: str) -> Lesson:
    """Snipers, top-10 or dev share at the last closed minute before the entry, in terciles."""
    values = [getattr(b, feature) for b in bets]
    known = [Decimal(v) for v in values if v is not None]
    edges = tercile_edges(known)

    def label_of(bet: ClosedBet) -> str:
        value = getattr(bet, feature)
        return tercile_label(None if value is None else Decimal(value), edges)

    edge_text = "—" if edges is None else f"{fmt(edges[0])} / {fmt(edges[1])}"
    return banded(
        bets,
        key=key,
        title=title,
        feature=feature,
        label_of=label_of,
        order=(),
        note=f"Tercis de `{feature}` entre as apostas do dia com valor conhecido "
        f"({len(known)} de {len(bets)}); cortes {edge_text}.",
    )


def _serial(bet: ClosedBet) -> bool | None:
    return None if bet.creator_prior_1h is None else bet.creator_prior_1h >= SERIAL_CREATOR_MIN


def _clone(bet: ClosedBet) -> bool | None:
    return None if bet.symbol_dup_24h is None else bet.symbol_dup_24h >= SYMBOL_CLONE_MIN


def day_lessons(bets: Sequence[ClosedBet]) -> list[Lesson]:
    """The nine rule-facing lessons, in the diary's order."""
    return [
        lesson_exits(bets),
        lesson_age(bets),
        lesson_progress(bets),
        lesson_tercile(bets, key="snipers", title="Snipers na entrada × R", feature="snipers"),
        lesson_tercile(bets, key="top10", title="Top-10 na entrada × R", feature="top10_share"),
        lesson_tercile(bets, key="dev", title="Dev na entrada × R", feature="dev_share"),
        lesson_flag(
            bets,
            key="mesmo_slot",
            title="Mesmo slot × R",
            feature="same_slot",
            flag=lambda b: b.same_slot,
            yes="mesmo slot (pool ≤ 1 s após a criação)",
            no="demais",
        ),
        lesson_flag(
            bets,
            key="criador_em_serie",
            title="Criador em série × R",
            feature="creator_prior_mints_1h",
            flag=_serial,
            yes=f"criador em série (≥ {SERIAL_CREATOR_MIN} moedas na hora anterior)",
            no="criador sem outra moeda observada na hora anterior",
        ),
        lesson_flag(
            bets,
            key="clones",
            title="Clones de símbolo × R",
            feature="symbol_dup_24h",
            flag=_clone,
            yes=f"clone de símbolo (≥ {SYMBOL_CLONE_MIN} iguais em 24 h)",
            no="símbolo sem clones observados em 24 h",
        ),
    ]
