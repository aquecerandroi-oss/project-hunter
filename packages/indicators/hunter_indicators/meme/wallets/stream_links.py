"""The survey's cross-mint evidence (wave 1c-bis), split out of :mod:`.stream` (CPU plan step 3).

- same-slot co-buys per mint → the weak links that reach 3 mints (with the carried evidence);
- the fills of multi-mint transactions → where each (owner, signature)'s tx fee is NOT due.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from itertools import combinations

from hunter_indicators.meme.wallets.carry import Carry, Evidence, canonical_order, merge_evidence
from hunter_indicators.meme.wallets.entities import Link
from hunter_indicators.meme.wallets.tape import Fill, event_order

__all__ = ["Pairs", "Seeds", "absorb", "cobuys", "fee_seeds", "weak_links"]

Pairs = dict[tuple[str, str], dict[str, datetime]]
Seeds = dict[str, set[tuple[str, str]]]


def cobuys(buys: Iterable[Fill]) -> dict[tuple[str, str], datetime]:
    """One mint's same-slot buyer pairs → the earliest instant the coincidence was knowable."""
    groups: dict[int, dict[str, datetime]] = {}
    for f in buys:
        seen = groups.setdefault(f.slot, {})
        seen[f.wallet] = min(seen.get(f.wallet, f.received_at), f.received_at)
    out: dict[tuple[str, str], datetime] = {}
    for buyers in groups.values():
        for a, b in combinations(sorted(buyers), 2):
            known = max(buyers[a], buyers[b])
            out[(a, b)] = min(out.get((a, b), known), known)
    return out


def absorb(pairs: Pairs, mint: str, found: Mapping[tuple[str, str], datetime]) -> None:
    for pair, known in found.items():
        pairs.setdefault(pair, {})[mint] = known


def _link(pair: tuple[str, str], evidence: Evidence) -> Link:
    return Link(pair[0], pair[1], "weak", evidence[-1][0], ",".join(m for _, m in evidence))


def weak_links(carry: Carry, pairs: Pairs) -> tuple[list[Link], dict[tuple[str, str], Evidence]]:
    """Links reaching 3 mints once ``pairs`` join the carry's evidence, and the pairs still pending."""
    done = {(link.a, link.b) for link in carry.weak_links}
    links, pending = list(carry.weak_links), dict[tuple[str, str], Evidence]()
    for pair, per_mint in pairs.items():
        if pair in done:
            continue
        merged = merge_evidence(carry.pending.get(pair, ()), per_mint)
        if len(merged) >= 3:
            links.append(_link(pair, merged))
        else:
            pending[pair] = merged
    return links, pending


def fee_seeds(shared: list[tuple[Fill, str]]) -> Seeds:
    """(owner, signature) → the mints where its fee is NOT due: the owner's first event of the
    transaction (event order, then input order) carries it."""
    first: dict[
        tuple[str, str], tuple[tuple[int, str, int], tuple[datetime, int, str, int, str], str]
    ]
    first = {}
    touched: dict[tuple[str, str], set[str]] = {}
    for f, owner in shared:
        key = (owner, f.signature)
        rank = (event_order(f), canonical_order(f), f.mint)
        if key not in first or rank[:2] < first[key][:2]:
            first[key] = rank
        touched.setdefault(key, set()).add(f.mint)
    seeds: Seeds = {}
    for key, mints in touched.items():
        for mint in mints - {first[key][2]}:
            seeds.setdefault(mint, set()).add(key)
    return seeds
