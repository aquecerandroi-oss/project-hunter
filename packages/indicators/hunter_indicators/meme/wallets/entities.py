"""Entities (§1.2): wallets joined by union-find, versioned by what was known.

- **Strong link:** the same first funder, unless the funder is an exchange or
  app wallet (those fund thousands and link nobody) — the caller passes them in
  ``excluded``. ``known_at`` = when the later of the two resolutions arrived.
- **Weak link:** buys of the same mint in the same slot in ≥ 3 distinct mints.
  ``known_at`` = when the third coincidence became knowable (the later
  ``received_at`` of the pair's buys in that mint).

A link counts in a snapshot only when ``known_at < as_of`` (strict — "a
coincidence seen tomorrow merges nothing today"). The entity id is ``e:`` + the
smallest member address; a lone wallet is its own id.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from itertools import combinations
from typing import Literal

from hunter_indicators.meme.wallets.tape import Fill, event_order

__all__ = ["Entities", "Link", "LinkKind", "entities_as_of", "funder_links", "same_slot_links"]

LinkKind = Literal["strong", "weak"]
ALL_KINDS: frozenset[LinkKind] = frozenset({"strong", "weak"})


@dataclass(frozen=True, slots=True)
class Link:
    a: str
    b: str
    kind: LinkKind
    known_at: datetime
    evidence: str


@dataclass(frozen=True, slots=True)
class Entities:
    version: str
    owner: Mapping[str, str] = field(default_factory=dict[str, str])
    members: Mapping[str, frozenset[str]] = field(default_factory=dict[str, frozenset[str]])

    def of(self, wallet: str) -> str:
        return self.owner.get(wallet, wallet)

    def wallets_of(self, entity: str) -> frozenset[str]:
        return self.members.get(entity, frozenset({entity}))


def funder_links(
    funders: Mapping[str, tuple[str, datetime]], *, excluded: frozenset[str]
) -> tuple[Link, ...]:
    """Link every wallet to the **earliest-known** wallet sharing its funder.

    The head is chosen by ``known_at`` (then address), so a wallet resolved later
    never re-roots links already in force (Astra must-fix 5).
    """
    by_funder: dict[str, list[tuple[str, datetime]]] = {}
    for wallet, (funder, known_at) in funders.items():
        if funder not in excluded:
            by_funder.setdefault(funder, []).append((wallet, known_at))
    links: list[Link] = []
    for funder, group in sorted(by_funder.items()):
        group.sort(key=lambda wk: (wk[1], wk[0]))  # head = earliest known: stable vs. tomorrow
        head, head_known = group[0]
        links.extend(Link(head, w, "strong", max(head_known, k), funder) for w, k in group[1:])
    return tuple(links)


def same_slot_links(fills: Iterable[Fill], *, min_mints: int = 3) -> tuple[Link, ...]:
    """Weak links from same-slot buys of the same mint in ≥ ``min_mints`` mints."""
    groups: dict[tuple[str, int], dict[str, datetime]] = {}
    for f in sorted(fills, key=event_order):
        if f.side != "buy":
            continue
        seen = groups.setdefault((f.mint, f.slot), {})
        seen[f.wallet] = min(seen.get(f.wallet, f.received_at), f.received_at)
    first_known: dict[tuple[str, str], dict[str, datetime]] = {}
    for (mint, _slot), buyers in groups.items():
        for a, b in combinations(sorted(buyers), 2):
            known = max(buyers[a], buyers[b])
            per_mint = first_known.setdefault((a, b), {})
            per_mint[mint] = min(per_mint.get(mint, known), known)
    links: list[Link] = []
    for (a, b), per_mint in sorted(first_known.items()):
        if len(per_mint) < min_mints:
            continue
        ordered = sorted(per_mint.items(), key=lambda kv: (kv[1], kv[0]))
        mints = ",".join(m for m, _ in ordered[:min_mints])
        links.append(Link(a, b, "weak", ordered[min_mints - 1][1], mints))
    return tuple(links)


def _find(parent: dict[str, str], x: str) -> str:
    root = x
    while parent.get(root, root) != root:
        root = parent[root]
    while parent.get(x, x) != root:
        parent[x], x = root, parent[x]
    return root


def entities_as_of(
    links: Iterable[Link], as_of: datetime, *, kinds: frozenset[LinkKind] = ALL_KINDS
) -> Entities:
    """The entity map in force for a snapshot cut at ``as_of``."""
    parent: dict[str, str] = {}
    for link in links:
        if link.kind not in kinds or link.known_at >= as_of:
            continue
        ra, rb = _find(parent, link.a), _find(parent, link.b)
        parent.setdefault(ra, ra)
        parent.setdefault(rb, rb)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    groups: dict[str, set[str]] = {}
    for wallet in list(parent):
        groups.setdefault(_find(parent, wallet), set()).add(wallet)
    owner: dict[str, str] = {}
    members: dict[str, frozenset[str]] = {}
    for group in groups.values():
        entity = "e:" + min(group)
        members[entity] = frozenset(group)
        owner.update(dict.fromkeys(group, entity))
    canon = "|".join(sorted(",".join(sorted(g)) for g in members.values()))
    return Entities(hashlib.sha256(canon.encode()).hexdigest()[:16], owner, members)
