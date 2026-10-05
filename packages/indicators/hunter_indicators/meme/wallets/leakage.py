"""Leak detectors for the wallet engine (design §2.1, KB-0149 §5 item 24).

- :func:`ranker_leaks` — the perturbation test: run a ranker on inputs that
  contain the future and on the same inputs stripped to what was knowable at
  ``T_D``; any difference in the snapshot is a leak. The honest
  :func:`.ranking.build_snapshot` passes; a ranker that peeks at day D's trades,
  or that ignores ``received_at``, is caught.
- :func:`snapshot_violations` — every bet must name a snapshot that existed,
  was published, and was cut and published **at or before** the decision.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import date, datetime, timedelta
from types import MappingProxyType

from hunter_indicators.meme.wallets.follow import ArmDecision
from hunter_indicators.meme.wallets.ranking import RankInputs, cut_of
from hunter_indicators.meme.wallets.snapshot import Snapshot

__all__ = ["fingerprint", "ranker_leaks", "snapshot_violations", "strip_future"]

Ranker = Callable[[RankInputs, date], Snapshot]


def strip_future(inputs: RankInputs, cut: datetime, *, window_days: int = 7) -> RankInputs:
    """Only what was knowable strictly before ``cut`` (order preserved); opening lots
    only if preserved before the window start (later ones are the window's own buys)."""
    start = cut - timedelta(days=window_days)
    return replace(
        inputs,
        fills=tuple(f for f in inputs.fills if f.block_time < cut and f.received_at < cut),
        creates=tuple(c for c in inputs.creates if c.received_at < cut and c.block_time < cut),
        links=tuple(link for link in inputs.links if link.known_at < cut),
        funders=MappingProxyType({w: v for w, v in inputs.funders.items() if v[1] < cut}),
        opening_lots=tuple(lot for lot in inputs.opening_lots if lot.opened_at < start),
    )


def fingerprint(snap: Snapshot) -> tuple[object, ...]:
    """Everything a decision could read from a snapshot, in a comparable form."""
    rows = tuple(
        (r.entity, r.reasons, r.rank, r.followed, r.c_pnl_lamports, r.metrics)
        for _, r in sorted(snap.rows.items())
    )
    return (snap.day, snap.entities.version, rows, tuple(sorted(snap.manifest.items())))


def ranker_leaks(ranker: Ranker, inputs: RankInputs, day: date) -> bool:
    """``True`` when the ranker's snapshot depends on anything at/after ``T_D``."""
    return fingerprint(ranker(inputs, day)) != fingerprint(
        ranker(strip_future(inputs, cut_of(day)), day)
    )


def snapshot_violations(
    decisions: Iterable[ArmDecision], snapshots: Iterable[Snapshot]
) -> tuple[str, ...]:
    """``<signature>:<why>`` for every bet that read a snapshot it could not have had."""
    by_id = {s.snapshot_id: s for s in snapshots}
    out: list[str] = []
    for d in decisions:
        if not d.bet:
            continue
        snap = by_id.get(d.snapshot_id or "")
        why: str | None = None
        if snap is None:
            why = "unknown_snapshot"
        elif snap.published_at is None:
            why = "unpublished"
        elif snap.published_at > d.decided_at:
            why = "published_after_decision"
        elif snap.cut > d.decided_at:
            why = "cut_after_decision"
        if why is not None:
            out.append(f"{d.fill.signature}:{why}")
    return tuple(out)
