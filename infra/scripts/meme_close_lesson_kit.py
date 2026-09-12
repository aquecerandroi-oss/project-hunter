"""The kit every lesson of the daily close is built from — pure.

A lesson is cells (n, R mean, R sum, IC 95 % by hour blocks), one contrast
(a cell against the rest), a one-sentence "o que muda amanhã" and — only when
:func:`meme_close_stats.passes_ruler` says so — the claim an ``M-L`` row may
carry and the arm the next batch may propose. Below 30 closed bets every
lesson says "nada muda (n insuficiente)"; nothing here edits a rule set.
``meme_close_lessons.py`` composes the concrete lessons from these pieces.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from meme_close_stats import (
    MIN_CELL_N,
    MIN_N,
    Contrast,
    Interval,
    Sample,
    block_ci,
    block_contrast,
    fmt,
    passes_ruler,
)

SAO_PAULO = ZoneInfo("America/Sao_Paulo")
UNKNOWN = frozenset({"desconhecido", "desconhecida"})


@dataclass(frozen=True, slots=True)
class ClosedBet:
    mint: str
    rule_set: str
    exp_ref: str | None
    kind: str
    entry_at: datetime
    exit_at: datetime
    exit_reason: str
    r_multiple: Decimal
    pnl_sol: Decimal
    initial_risk_sol: Decimal
    age_at_entry_s: int | None
    progress_pct: Decimal | None
    """Curve progress in percent at the proposal's snapshot; ``None`` unknown."""
    snipers: int | None
    top10_share: Decimal | None
    dev_share: Decimal | None
    same_slot: bool | None
    """``pool_created_at − created_at ≤ 1 s``; ``None`` without a creation time."""
    creator_prior_1h: int | None
    symbol_dup_24h: int | None


@dataclass(frozen=True, slots=True)
class Cell:
    label: str
    interval: Interval
    group: str = ""
    """The rule set, for the exits table; empty when the cell pools every set."""


@dataclass(frozen=True, slots=True)
class Lesson:
    key: str
    title: str
    feature: str
    n: int
    cells: tuple[Cell, ...]
    note: str
    change: str
    contrast: Contrast | None = None
    contrast_label: str | None = None
    measured: str | None = None
    """The claim an ``M-L`` row carries — only when the ruler passed."""
    proposal: str | None = None
    """The arm the next batch proposes — only when the ruler passed."""

    @property
    def sufficient(self) -> bool:
        return self.n >= MIN_N


@dataclass(frozen=True, slots=True)
class TopOut:
    rule_set: str
    n: int
    total: Decimal
    best_mint: str
    best_r: Decimal
    without_best: Decimal


def hour_block(at: datetime) -> str:
    return at.astimezone(SAO_PAULO).strftime("%H")


def sample(bets: Iterable[ClosedBet]) -> Sample:
    rows = list(bets)
    return Sample(
        blocks=tuple(hour_block(b.entry_at) for b in rows),
        values=tuple(b.r_multiple for b in rows),
    )


def cells(groups: dict[str, list[ClosedBet]], *, group: str = "") -> tuple[Cell, ...]:
    return tuple(Cell(label, block_ci(sample(rows)), group) for label, rows in groups.items())


def ci_text(contrast: Contrast) -> str:
    if contrast.ci95 is None:
        return "IC 95 % — (sem blocos suficientes)"
    return f"IC 95 % [{fmt(contrast.ci95[0])}, {fmt(contrast.ci95[1])}]"


def verdict(
    *, title: str, feature: str, n: int, contrast: Contrast | None, label: str | None
) -> tuple[str, str | None, str | None]:
    """``(change, measured, proposal)`` — the last two only past the ruler."""
    if n < MIN_N:
        return f"nada muda (n insuficiente: {n} < {MIN_N})", None, None
    if contrast is None or label is None or contrast.delta is None:
        return f"nada muda (nenhuma célula com n ≥ {MIN_CELL_N} para contrastar)", None, None
    if not passes_ruler(contrast, total_n=n):
        return (
            f"nada muda (o contraste «{label}» não passa a régua: Δ {fmt(contrast.delta)} R, "
            f"{ci_text(contrast)})",
            None,
            None,
        )
    negative = contrast.delta < 0
    verb = "exclui" if negative else "se restringe a"
    change = (
        f"amanhã o lote propõe um braço irmão que {verb} {label} (Δ {fmt(contrast.delta)} R, "
        f"{ci_text(contrast)}); os conjuntos vivos não mudam"
    )
    measured = (
        f"{title}: {label} rendeu R médio {fmt(contrast.mean_a)} (n = {contrast.n_a}) contra "
        f"{fmt(contrast.mean_b)} nas demais (n = {contrast.n_b}) — Δ {fmt(contrast.delta)} R, "
        f"{ci_text(contrast).replace('IC 95 %', 'IC 95 % por blocos de hora')} "
        f"({contrast.blocks} blocos), n = {n} apostas fechadas no dia"
    )
    rule = f"`{feature}` {'∈' if negative else '∉'} {label} → recusa nomeada"
    proposal = (
        f"braço irmão de cada conjunto vivo com {rule}; previsão `descartar`; régua ≥ 100 "
        "apostas e 30 dias, IC 95 % por blocos de dia, leave-top-out; controle = o conjunto sem "
        "o filtro no mesmo período"
    )
    return change, measured, proposal


def deviant(groups: dict[str, list[ClosedBet]], everything: Sequence[ClosedBet]) -> str | None:
    """The known cell with n ≥ 10 whose mean R sits farthest from the day's."""
    if not everything:
        return None
    overall = sum((b.r_multiple for b in everything), Decimal(0)) / len(everything)
    candidates = [
        (abs(sum((b.r_multiple for b in rows), Decimal(0)) / len(rows) - overall), label)
        for label, rows in groups.items()
        if len(rows) >= MIN_CELL_N and label not in UNKNOWN
    ]
    return max(candidates)[1] if candidates else None


def contrast_of(
    groups: dict[str, list[ClosedBet]], label: str | None, everything: Sequence[ClosedBet]
) -> Contrast | None:
    if label is None:
        return None
    inside = groups[label]
    outside = [b for b in everything if b not in inside]
    return block_contrast(sample(inside), sample(outside))


def grouped(
    bets: Sequence[ClosedBet], label_of: Callable[[ClosedBet], str], order: Sequence[str] = ()
) -> dict[str, list[ClosedBet]]:
    groups: dict[str, list[ClosedBet]] = {label: [] for label in order}
    for bet in bets:
        groups.setdefault(label_of(bet), []).append(bet)
    return {label: rows for label, rows in groups.items() if rows}


def banded(
    bets: Sequence[ClosedBet],
    *,
    key: str,
    title: str,
    feature: str,
    label_of: Callable[[ClosedBet], str],
    order: Sequence[str],
    note: str,
) -> Lesson:
    """Cells by ``label_of``; the contrast is the most deviant cell against the rest."""
    groups = grouped(bets, label_of, order)
    label = deviant(groups, bets)
    contrast = contrast_of(groups, label, bets)
    change, measured, proposal = verdict(
        title=title, feature=feature, n=len(bets), contrast=contrast, label=label
    )
    return Lesson(
        key,
        title,
        feature,
        len(bets),
        cells(groups),
        note,
        change,
        contrast,
        label,
        measured,
        proposal,
    )


def lesson_flag(
    bets: Sequence[ClosedBet],
    *,
    key: str,
    title: str,
    feature: str,
    flag: Callable[[ClosedBet], bool | None],
    yes: str,
    no: str,
) -> Lesson:
    """Two cells — the flag and the rest — with the unknown apart."""

    def label_of(bet: ClosedBet) -> str:
        value = flag(bet)
        return "desconhecido" if value is None else (yes if value else no)

    groups = grouped(bets, label_of, (yes, no, "desconhecido"))
    label = yes if groups.get(yes) else None
    contrast = contrast_of(groups, label, bets)
    change, measured, proposal = verdict(
        title=title, feature=feature, n=len(bets), contrast=contrast, label=label
    )
    known = sum(len(rows) for name, rows in groups.items() if name not in UNKNOWN)
    note = f"`{feature}` conhecido em {known} de {len(bets)} apostas."
    return Lesson(
        key,
        title,
        feature,
        len(bets),
        cells(groups),
        note,
        change,
        contrast,
        label,
        measured,
        proposal,
    )


def leave_top_out(bets: Sequence[ClosedBet]) -> tuple[TopOut, ...]:
    """R summed without the best bet, per rule set — a balance that flips sign is a ticket."""
    per_set: dict[str, list[ClosedBet]] = {}
    for bet in bets:
        per_set.setdefault(bet.rule_set, []).append(bet)
    out: list[TopOut] = []
    for rule_set, rows in sorted(per_set.items()):
        best = max(rows, key=lambda b: b.r_multiple)
        total = sum((b.r_multiple for b in rows), Decimal(0))
        out.append(
            TopOut(rule_set, len(rows), total, best.mint, best.r_multiple, total - best.r_multiple)
        )
    return tuple(out)
