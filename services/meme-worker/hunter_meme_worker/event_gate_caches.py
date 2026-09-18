"""What ``lab_fast.fast_gate_step`` refreshes every Lab tick (plan-T4.52b.md
§2) for :func:`hunter_meme_worker.event_gate.run_event_gate` to read without
ever opening a session of its own: the active 15-second rule sets, each
one's open mints, the pedigree/E2-b lineage already read this tick, the last
``GateRow`` per mint — and ``recently_proposed``, the in-memory guard both
lanes write to and read from so neither doubles the other (plan §4
"Sem dupla proposta"; the DB's own unique index is the last guard either way).

Everything here is at most ``lab_cycle_s`` (~15 s) old and reset wholesale on
every refresh **except** ``base_rows`` (merged — a row not repeated in a tick
with no new photo for that mint is still the last one known) and
``recently_proposed`` (its own TTL, independent of the tick clock).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from hunter_indicators.meme.pedigree import PedigreeFeatures
    from hunter_indicators.meme.pedigree_e2b import E2bFeatures
    from hunter_meme_worker.lab_models import RuleSetSpec
    from hunter_meme_worker.proposals import GateRow

__all__ = ["EventGateCaches", "prune_event_gate_caches", "refresh_event_gate_caches"]

MAX_CACHE_AGE_S = 600
"""F1 (review-T4.52b.md §4): a mint's ``base_rows``/``pedigree``/``e2b`` entry
older than this is evicted on the next sync even if still tracked — a lull,
not a leak."""


@dataclass(slots=True)
class EventGateCaches:
    """One instance lives on ``LabContext.caches``; ``run_event_gate`` only
    ever reads it (and calls :meth:`mark_proposed`) — it never opens a session."""

    specs: tuple[RuleSetSpec, ...] = ()
    """Active rule sets whose ``clock == "15s"`` — the only ones the event
    gate (or the fast lane) ever judges."""
    open_mints: dict[str, frozenset[str]] = field(default_factory=dict[str, "frozenset[str]"])
    """``rule_set_id -> mints already open`` — replaced wholesale every
    refresh (an open position can close between ticks; a stale ``True`` here
    would block a proposal forever)."""
    pedigree: dict[str, PedigreeFeatures] = field(default_factory=dict[str, "PedigreeFeatures"])
    e2b: dict[str, E2bFeatures] = field(default_factory=dict[str, "E2bFeatures"])
    """T4.31's lineage, keyed by mint alone here (the plan's own wording,
    §2): the event gate judges an instant the tick never read, so the exact
    ``(mint, end_time)`` key the minute/15-second lane uses cannot match — the
    last tick's reading is the best available and is what a set with
    ``pedigree_e2b`` reads, on approximation, until the datum is missing
    (``e2b_top_buyer_unknown``) rather than ever silently wrong-keyed."""
    base_rows: dict[str, GateRow] = field(default_factory=dict[str, "GateRow"])
    """The last 15-second ``GateRow`` per mint — merged tick over tick."""
    updated_at: dict[str, datetime] = field(default_factory=dict[str, "datetime"])
    """When ``base_rows``/``pedigree``/``e2b`` last learned about a mint — the
    F1 fix's own clock (``prune_event_gate_caches``): these three only grew
    before (review-T4.52b.md §4), unlike ``open_mints`` (replaced wholesale)
    and ``recently_proposed``/``shadow_marked_until`` (their own TTL)."""
    refreshed_at: datetime | None = None
    proposed_until: dict[tuple[str, str], datetime] = field(
        default_factory=dict[tuple[str, str], datetime]
    )
    """``(mint, rule_set_id) -> expires_at`` — written at insert time by
    *either* lane (``fast_gate_step`` and ``event_gate``'s own inserter), read
    by both as part of ``already_open`` (plan §4 (ii)/(iii))."""
    shadow_marked_until: dict[tuple[str, str], datetime] = field(
        default_factory=dict[tuple[str, str], datetime]
    )
    """``shadow`` mode's own dedupe guard (T4.52b-4 fix, metrics): never read
    by ``already_open`` — a shadow run must judge exactly as ``on`` would,
    this only dedupes ``shadow_proposals_total`` and the agree/only split."""

    def recently_proposed_mints(self, rule_set_id: str, *, now: datetime) -> frozenset[str]:
        return frozenset(
            mint
            for (mint, rs_id), expires in self.proposed_until.items()
            if rs_id == rule_set_id and expires > now
        )

    def mark_proposed(self, mint: str, rule_set_id: str, *, now: datetime, ttl_s: int) -> None:
        self.proposed_until[(mint, rule_set_id)] = now + timedelta(seconds=max(0, ttl_s))
        self.prune(now)

    def unmark_proposed(self, mint: str, rule_set_id: str) -> None:
        """The race fix's undo (T4.52b-4 F-race): a reservation whose insert
        found the row already there (0 rows — the other lane's) is released,
        not left blocking this mint for the rest of its TTL."""
        self.proposed_until.pop((mint, rule_set_id), None)

    def shadow_recently_marked(self, rule_set_id: str, mint: str, *, now: datetime) -> bool:
        expires = self.shadow_marked_until.get((mint, rule_set_id))
        return expires is not None and expires > now

    def mark_shadow(self, mint: str, rule_set_id: str, *, now: datetime, ttl_s: int) -> None:
        self.shadow_marked_until[(mint, rule_set_id)] = now + timedelta(seconds=max(0, ttl_s))
        self.prune(now)

    def prune(self, now: datetime) -> None:
        for table in (self.proposed_until, self.shadow_marked_until):
            expired = [key for key, expires in table.items() if expires <= now]
            for key in expired:
                del table[key]


def refresh_event_gate_caches(
    caches: EventGateCaches,
    *,
    specs: Sequence[RuleSetSpec],
    rows: Sequence[GateRow],
    open_mints: Mapping[str, frozenset[str]],
    pedigree: Mapping[str, PedigreeFeatures],
    e2b: Mapping[tuple[str, datetime], E2bFeatures] | None,
    now: datetime,
) -> None:
    """Called once per Lab tick from ``lab_fast.fast_gate_step``, after it has
    already paid for every read below — this never issues one of its own."""
    caches.specs = tuple(spec for spec in specs if spec.clock == "15s")
    caches.open_mints = {rule_set_id: frozenset(mints) for rule_set_id, mints in open_mints.items()}
    caches.pedigree.update(pedigree)
    for mint in pedigree:
        caches.updated_at[mint] = now
    if e2b:
        for (mint, _end_time), features in e2b.items():
            caches.e2b[mint] = features
            caches.updated_at[mint] = now
    for row in rows:
        caches.base_rows[row.mint] = row
        caches.updated_at[row.mint] = now
    caches.refreshed_at = now
    caches.prune(now)


def prune_event_gate_caches(
    caches: EventGateCaches, *, keep: frozenset[str], now: datetime, max_mints: int
) -> None:
    """F1 (review-T4.52b.md §4): called from ``sync_subscriptions`` every
    ``subscription_sync_s`` — evict a mint's ``base_rows``/``pedigree``/``e2b``
    once it is no longer tracked (``keep`` — ``fast_lane.young_mints``, the
    same set the subscriptions themselves follow) or its last refresh is
    older than :data:`MAX_CACHE_AGE_S`, then enforce ``max_mints * 2`` as a
    hard ceiling regardless (dropping the oldest first) — a shadow run left
    for a day must never grow past a small multiple of what it ever tracks."""
    horizon = now - timedelta(seconds=MAX_CACHE_AGE_S)
    stale = {mint for mint, at in caches.updated_at.items() if mint not in keep or at < horizon}
    _evict(caches, stale)
    cap = max(0, max_mints) * 2
    over = len(caches.updated_at) - cap
    if over > 0:
        oldest = sorted(caches.updated_at.items(), key=lambda kv: kv[1])[:over]
        _evict(caches, {mint for mint, _at in oldest})


def _evict(caches: EventGateCaches, mints: set[str]) -> None:
    for mint in mints:
        caches.base_rows.pop(mint, None)
        caches.pedigree.pop(mint, None)
        caches.e2b.pop(mint, None)
        caches.updated_at.pop(mint, None)
