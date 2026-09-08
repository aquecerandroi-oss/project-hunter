"""Unit tests: ``ScoreboardRowOut.replication`` block builder — brief T3.18b,
item 2. No IO, no Postgres: ``Outcome``/``SiblingPopulation`` built by hand.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_api.repositories.lab_replication import SiblingMeta, SiblingPopulation
from hunter_api.services.lab_replication import build_replication_block, resolve_seed
from hunter_indicators.replication import MATURITY_HALF_DAYS, MATURITY_HALF_OUTCOMES, Outcome

pytestmark = pytest.mark.unit

VERSION_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")


def _outcomes(
    n: int, *, r: Decimal, start: datetime, market: str = "binance:BTCUSDT"
) -> list[Outcome]:
    return [Outcome(r=r, decision_at=start + timedelta(days=i), market=market) for i in range(n)]


class TestNullWhenNeverValidated:
    def test_no_promising_at_and_no_siblings_is_none(self) -> None:
        block = build_replication_block(
            version_id=VERSION_ID, promising_at=None, parent_outcomes=[], siblings=[]
        )
        assert block is None

    def test_no_promising_at_even_with_a_positive_parent_population_is_still_none(self) -> None:
        outcomes = _outcomes(
            MATURITY_HALF_OUTCOMES + 10,
            r=Decimal("1"),
            start=datetime(2026, 1, 1, tzinfo=UTC),
        )
        block = build_replication_block(
            version_id=VERSION_ID, promising_at=None, parent_outcomes=outcomes, siblings=[]
        )
        assert block is None


class TestPromissoraWithNoSiblingsYet:
    def test_status_is_promissora_and_siblings_block_says_sem_irmas(self) -> None:
        promising_at = datetime(2026, 1, 1, tzinfo=UTC)
        block = build_replication_block(
            version_id=VERSION_ID, promising_at=promising_at, parent_outcomes=[], siblings=[]
        )
        assert block is not None
        assert block.status == "promissora"
        assert block.promising_at == promising_at
        assert block.siblings.n == 0
        assert block.siblings.reason == "sem_irmas"
        assert block.siblings.arms == []


class TestSiblingEvidenceLabel:
    def _sibling(self, k: int, *, live: list[Outcome], replay: list[Outcome]) -> SiblingPopulation:
        meta = SiblingMeta(id=uuid.uuid4(), version=f"v{k + 1}", k=k, changelog=None)
        if live and replay:
            evidence = "mixed"
        elif replay:
            evidence = "replay"
        elif live:
            evidence = "prospective"
        else:
            evidence = None
        return SiblingPopulation(meta=meta, outcomes=[*live, *replay], evidence=evidence)

    def test_arm_evidence_is_carried_through_to_the_payload(self) -> None:
        promising_at = datetime(2026, 1, 1, tzinfo=UTC)
        start = promising_at + timedelta(days=1)
        prospective_only = self._sibling(
            1, live=_outcomes(5, r=Decimal("1"), start=start), replay=[]
        )
        replay_only = self._sibling(2, live=[], replay=_outcomes(5, r=Decimal("1"), start=start))
        mixed = self._sibling(
            3,
            live=_outcomes(3, r=Decimal("1"), start=start),
            replay=_outcomes(3, r=Decimal("-1"), start=start),
        )
        no_outcomes_yet = self._sibling(4, live=[], replay=[])

        block = build_replication_block(
            version_id=VERSION_ID,
            promising_at=promising_at,
            parent_outcomes=[],
            siblings=[prospective_only, replay_only, mixed, no_outcomes_yet],
        )

        assert block is not None
        by_k = {arm.k: arm.evidence for arm in block.siblings.arms}
        assert by_k == {1: "prospective", 2: "replay", 3: "mixed", 4: None}


class TestResolveSeed:
    def test_no_siblings_falls_back_to_a_seed_derived_from_the_version_id(self) -> None:
        seed = resolve_seed(VERSION_ID, [])
        assert seed == int.from_bytes(VERSION_ID.bytes[:4], "big")

    def test_reads_the_registered_seed_off_the_first_siblings_changelog(self) -> None:
        meta = SiblingMeta(
            id=uuid.uuid4(),
            version="v2",
            k=1,
            changelog="replication:...:1 | irmã 1 de v1 | promising_at=2026-01-01T00:00:00+00:00 "
            "| seed=20260908 | pct=0.15 | nota",
        )
        sibling = SiblingPopulation(meta=meta, outcomes=[], evidence=None)

        assert resolve_seed(VERSION_ID, [sibling]) == 20260908


class TestOutOfSampleStaysProspectiveOnly:
    """D15 (b): the parent population this module is handed already has to be
    ``prospective``-filtered by the repository — this block builder trusts
    its caller and asserts only that it never mixes anything back in."""

    def test_out_of_sample_reads_exactly_the_outcomes_it_was_given(self) -> None:
        promising_at = datetime(2026, 1, 1, tzinfo=UTC)
        after = promising_at + timedelta(days=1)
        # >= 50 evaluable over >= 15 distinct days -> half-ruler mature (§1.5)
        parent_outcomes = [
            Outcome(r=Decimal("1"), decision_at=after + timedelta(days=i), market="binance:BTCUSDT")
            for i in range(MATURITY_HALF_DAYS + 5)
        ] * 5
        parent_outcomes = parent_outcomes[: MATURITY_HALF_OUTCOMES + 5]

        block = build_replication_block(
            version_id=VERSION_ID,
            promising_at=promising_at,
            parent_outcomes=parent_outcomes,
            siblings=[],
        )

        assert block is not None
        assert block.out_of_sample.mature is True
        assert block.out_of_sample.passed is True
        assert block.out_of_sample.evaluable == len(parent_outcomes)


def test_maturity_half_ruler_constants_are_the_documented_values() -> None:
    """Guards the fixture builders above against the constants moving under
    them silently (REPLICATION.md §1.5)."""
    assert MATURITY_HALF_OUTCOMES == 50
    assert MATURITY_HALF_DAYS == 15
