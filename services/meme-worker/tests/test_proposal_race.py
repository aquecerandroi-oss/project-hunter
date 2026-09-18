"""T4.52b-4, pure (no Docker): the race fix's own reserve-then-insert
(review-T4.52b.md §2) — ``insert_proposals`` is monkeypatched so this is
about the ordering (reserve *before* the ``await``, release on a failed
insert), not about SQL.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import hunter_meme_worker.proposal_race as proposal_race
from hunter_meme_worker.event_gate_caches import EventGateCaches
from hunter_meme_worker.proposal_race import insert_proposals_reserved

if TYPE_CHECKING:
    import pytest

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class _Draft:
    mint: str


async def test_the_mint_is_reserved_before_the_insert_await(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    caches = EventGateCaches()
    reserved_before_insert: dict[str, bool] = {}

    async def fake_insert(_session: Any, drafts: list[_Draft]) -> int:
        (draft,) = drafts
        reserved_before_insert[draft.mint] = caches.recently_proposed_mints(
            "rs-1", now=NOW
        ) == frozenset({draft.mint})
        return 1

    monkeypatch.setattr(proposal_race, "insert_proposals", fake_insert)
    inserted = await insert_proposals_reserved(
        object(),  # type: ignore[arg-type]
        caches,
        "rs-1",
        [_Draft("MINT")],  # type: ignore[arg-type]
        now=NOW,
        ttl_s=60,
    )
    assert inserted == 1
    assert reserved_before_insert == {"MINT": True}
    assert caches.recently_proposed_mints("rs-1", now=NOW) == frozenset({"MINT"})


async def test_a_failed_insert_releases_the_reservation(monkeypatch: pytest.MonkeyPatch) -> None:
    caches = EventGateCaches()

    async def fake_insert_zero(_session: Any, _drafts: list[_Draft]) -> int:
        return 0  # the unique index already had this row -- the other lane's

    monkeypatch.setattr(proposal_race, "insert_proposals", fake_insert_zero)
    inserted = await insert_proposals_reserved(
        object(),  # type: ignore[arg-type]
        caches,
        "rs-1",
        [_Draft("MINT")],  # type: ignore[arg-type]
        now=NOW,
        ttl_s=60,
    )
    assert inserted == 0
    assert caches.recently_proposed_mints("rs-1", now=NOW) == frozenset()


async def test_a_successful_insert_among_several_drafts_only_keeps_its_own_reservation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    caches = EventGateCaches()

    async def fake_insert(_session: Any, drafts: list[_Draft]) -> int:
        (draft,) = drafts
        return 1 if draft.mint == "WINS" else 0

    monkeypatch.setattr(proposal_race, "insert_proposals", fake_insert)
    inserted = await insert_proposals_reserved(
        object(),  # type: ignore[arg-type]
        caches,
        "rs-1",
        [_Draft("WINS"), _Draft("LOSES")],  # type: ignore[arg-type]
        now=NOW,
        ttl_s=60,
    )
    assert inserted == 1
    assert caches.recently_proposed_mints("rs-1", now=NOW) == frozenset({"WINS"})


async def test_no_caches_inserts_with_no_reservation_at_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_insert(_session: Any, _drafts: list[_Draft]) -> int:
        return 1

    monkeypatch.setattr(proposal_race, "insert_proposals", fake_insert)
    inserted = await insert_proposals_reserved(
        object(),  # type: ignore[arg-type]
        None,
        "rs-1",
        [_Draft("MINT")],  # type: ignore[arg-type]
        now=NOW,
        ttl_s=60,
    )
    assert inserted == 1
