"""Entities (§1.2): strong links by a shared non-exchange funder, weak links by
same-slot buys in ≥ 3 mints, union-find, valid only from ``known_at`` on.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from hunter_indicators.meme.wallets.entities import (
    Link,
    entities_as_of,
    funder_links,
    same_slot_links,
)
from hunter_indicators.meme.wallets.tape import Fill
from packages.indicators.tests.meme.test_wallets_builders import SOL, TOKEN, at, fill

pytestmark = pytest.mark.unit


def test_shared_funder_links_wallets_unless_the_funder_is_an_exchange() -> None:
    funders = {"A": ("F", at(10)), "B": ("F", at(20)), "C": ("OKX", at(5)), "D": ("OKX", at(6))}
    links = funder_links(funders, excluded=frozenset({"OKX"}))
    assert links == (Link("A", "B", "strong", at(20), "F"),)


def test_same_slot_buys_link_only_from_the_third_distinct_mint_when_it_became_known() -> None:
    fills: list[Fill] = []
    for i, mint in enumerate(["M1", "M2", "M1", "M3"]):
        slot = 100 * (i + 1)
        fills.append(fill(wallet="A", side="buy", slot=slot, sol=SOL, atoms=TOKEN, mint=mint))
        fills.append(
            fill(
                wallet="B",
                side="buy",
                slot=slot,
                sol=SOL,
                atoms=TOKEN,
                mint=mint,
                received_delay=0.9,
            )
        )
    fills.append(fill(wallet="C", side="buy", slot=100, sol=SOL, atoms=TOKEN, mint="M1"))
    (link,) = same_slot_links(fills)
    third = [f for f in fills if f.mint == "M3" and f.wallet == "B"][0]
    assert (link.a, link.b, link.kind, link.known_at) == ("A", "B", "weak", third.received_at)
    assert same_slot_links(fills[:6]) == ()  # only M1, M2 (twice M1) so far


def test_entities_are_point_in_time_and_transitive() -> None:
    links = (
        Link("A", "B", "strong", at(10), "F"),
        Link("B", "C", "weak", at(20), "M1,M2,M3"),
        Link("D", "E", "strong", at(30), "G"),
    )
    early = entities_as_of(links, at(15))
    assert early.of("A") == early.of("B") != early.of("C")
    late = entities_as_of(links, at(25))
    assert late.of("A") == late.of("B") == late.of("C") == "e:A"
    assert late.of("D") == "D"  # link not known yet: alone
    assert late.members["e:A"] == frozenset({"A", "B", "C"})
    assert early.version != late.version


def test_a_link_known_exactly_at_the_cut_does_not_merge() -> None:
    links = (Link("A", "B", "strong", at(10), "F"),)
    assert entities_as_of(links, at(10)).of("A") != entities_as_of(links, at(10)).of("B")
    assert entities_as_of(links, at(10) + timedelta(microseconds=1)).of("B") == "e:A"


def test_strong_only_sensitivity_ignores_weak_links() -> None:
    links = (Link("A", "B", "strong", at(1), "F"), Link("B", "C", "weak", at(1), "x"))
    strong = entities_as_of(links, at(2), kinds=frozenset({"strong"}))
    assert strong.of("C") == "C"
    assert strong.of("B") == "e:A"


def test_a_wallet_resolved_tomorrow_does_not_undo_todays_funder_links() -> None:
    # Astra must-fix 5: "A" sorts first but is known only later; B–C must stay linked today
    today = {"B": ("F", at(10)), "C": ("F", at(20))}
    later = {**today, "A": ("F", at(500))}
    cut = at(100)
    assert entities_as_of(funder_links(later, excluded=frozenset()), cut).of("C") == "e:B"
    assert entities_as_of(funder_links(later, excluded=frozenset()), at(600)).of("C") == "e:A"
