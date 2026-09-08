"""Unit tests: ``ScoreboardRowOut.replication`` block builder — briefs T3.18b
(item 2) e T3.18c (itens 3, 6, 8, 11 e 13).

No IO, no Postgres: ``Outcome``/``SiblingPopulation`` built by hand. O que se
prova aqui é o **contrato** do bloco: evidência contada uma vez, rótulo de
replay com janela, proveniência da semente e o caminho barato do ``null``.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_api.repositories.lab_replication import (
    SEED_SOURCE_DERIVED,
    SEED_SOURCE_REGISTERED,
    ReplayWindow,
    SiblingMeta,
    SiblingPopulation,
)
from hunter_api.repositories.lab_replication_rows import EMPTY_WINDOW, dedupe
from hunter_api.services.lab_replication import (
    build_replication_block,
    resolve_seed,
    siblings_label,
)
from hunter_indicators.replication import MATURITY_HALF_DAYS, MATURITY_HALF_OUTCOMES, Outcome

pytestmark = pytest.mark.unit

VERSION_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
START = datetime(2026, 1, 1, tzinfo=UTC)
HOLD = timedelta(hours=1)


def _outcomes(
    n: int,
    *,
    r: Decimal,
    start: datetime,
    market: str = "binance:BTCUSDT",
    step: timedelta = timedelta(days=1),
) -> list[Outcome]:
    return [
        Outcome(
            r=r,
            decision_at=start + step * i,
            market=market,
            exit_at=start + step * i + HOLD,
        )
        for i in range(n)
    ]


def _sibling(
    k: int,
    *,
    live: list[Outcome],
    replay: list[Outcome],
    window: ReplayWindow = EMPTY_WINDOW,
) -> SiblingPopulation:
    """Uma irmã montada pela **mesma** junção que o repositório usa."""
    meta = SiblingMeta(id=uuid.uuid4(), version=f"v{k + 1}", k=k, changelog=None)
    outcomes, (live_kept, replay_kept), dropped = dedupe([live, replay])
    if live_kept and replay_kept:
        evidence = "mixed"
    elif replay_kept:
        evidence = "replay"
    elif live_kept:
        evidence = "prospective"
    else:
        evidence = None
    return SiblingPopulation(
        meta=meta,
        outcomes=outcomes,
        evidence=evidence,
        replay_window=window if replay_kept else EMPTY_WINDOW,
        duplicates_dropped=dropped,
    )


class TestNullWhenNeverValidated:
    def test_no_promising_at_and_no_siblings_is_none(self) -> None:
        block = build_replication_block(
            version_id=VERSION_ID, promising_at=None, parent_outcomes=[], siblings=[]
        )
        assert block is None

    def test_no_promising_at_even_with_a_positive_parent_population_is_still_none(self) -> None:
        outcomes = _outcomes(MATURITY_HALF_OUTCOMES + 10, r=Decimal("1"), start=START)
        block = build_replication_block(
            version_id=VERSION_ID, promising_at=None, parent_outcomes=outcomes, siblings=[]
        )
        assert block is None

    def test_without_promising_at_no_statistics_are_computed_at_all(self) -> None:
        """T3.18c, item 8: o bloco caro nem roda.

        Sem ``promising_at`` o resultado é ``null`` por definição, e mil
        reamostras + um bootstrap por dias + um teste de sinal por linha do
        placar eram pagos para produzir esse ``null``. A prova é indireta e
        suficiente: uma população que faria ``replication_report`` levantar
        (nenhuma) não é tocada — aqui, uma lista que o teste sabota.
        """

        class Exploding(list[Outcome]):
            def __iter__(self) -> Iterator[Outcome]:  # pragma: no cover - inalcançável
                raise AssertionError("replication_report não deveria ler esta população")

        assert (
            build_replication_block(
                version_id=VERSION_ID,
                promising_at=None,
                parent_outcomes=Exploding(),
                siblings=[],
            )
            is None
        )


class TestPromissoraWithNoSiblingsYet:
    def test_status_is_promissora_and_siblings_block_says_sem_irmas(self) -> None:
        block = build_replication_block(
            version_id=VERSION_ID, promising_at=START, parent_outcomes=[], siblings=[]
        )
        assert block is not None
        assert block.status == "promissora"
        assert block.promising_at == START
        assert block.siblings.n == 0
        assert block.siblings.pool == 10
        assert block.siblings.reason == "sem_irmas"
        assert block.siblings.arms == []
        assert block.siblings.label is None


class TestSiblingEvidenceCountedOnce:
    """T3.18c, item 3 (Astra, HIGH): a mesma evidência não amadurece uma irmã
    duas vezes."""

    def test_the_same_decisions_replayed_under_two_runs_count_once(self) -> None:
        replayed = _outcomes(25, r=Decimal("1"), start=START)
        under_two_cohorts = [*replayed, *replayed]
        arm = _sibling(1, live=[], replay=under_two_cohorts)

        assert len(under_two_cohorts) == 50
        assert arm.duplicates_dropped == 25
        assert len(arm.outcomes) == 25

        block = build_replication_block(
            version_id=VERSION_ID, promising_at=START, parent_outcomes=[], siblings=[arm]
        )
        assert block is not None
        published = block.siblings.arms[0]
        assert published.evaluable == 25
        assert published.duplicates_dropped == 25
        assert published.mature is False

    def test_a_replay_that_covers_a_live_decision_never_displaces_it(self) -> None:
        """Item 13: uma irmã promovida a viva **mantém** a evidência
        prospectiva — a coorte viva tem precedência na junção."""
        live = _outcomes(10, r=Decimal("1"), start=START)
        replay_over_the_same_days = _outcomes(10, r=Decimal("-1"), start=START)

        arm = _sibling(1, live=live, replay=replay_over_the_same_days)

        assert arm.evidence == "prospective"
        assert arm.duplicates_dropped == 10
        assert [outcome.r for outcome in arm.outcomes] == [Decimal("1")] * 10

    def test_replay_beyond_the_live_window_still_adds_its_own_decisions(self) -> None:
        live = _outcomes(5, r=Decimal("1"), start=START)
        replay = _outcomes(5, r=Decimal("1"), start=START + timedelta(days=30))

        arm = _sibling(1, live=live, replay=replay)

        assert arm.evidence == "mixed"
        assert arm.duplicates_dropped == 0
        assert len(arm.outcomes) == 10


class TestSiblingLabelAndWindow:
    """REPLICATION.md §3.5 item 4: o bloco 2 por replay é rotulado, com janela."""

    WINDOW = ReplayWindow(
        window_from=datetime(2026, 8, 8, tzinfo=UTC), window_to=datetime(2026, 9, 8, tzinfo=UTC)
    )

    def test_an_arm_matured_by_replay_carries_its_window_and_labels_the_block(self) -> None:
        arm = _sibling(
            1, live=[], replay=_outcomes(5, r=Decimal("1"), start=START), window=self.WINDOW
        )
        block = build_replication_block(
            version_id=VERSION_ID, promising_at=START, parent_outcomes=[], siblings=[arm]
        )
        assert block is not None
        assert block.siblings.label == "siblings: replay sobre 2026-08-08 → 2026-09-08"
        published = block.siblings.arms[0]
        assert published.evidence == "replay"
        assert published.window_from == self.WINDOW.window_from
        assert published.window_to == self.WINDOW.window_to

    def test_a_purely_prospective_block_has_no_replay_label(self) -> None:
        arm = _sibling(1, live=_outcomes(5, r=Decimal("1"), start=START), replay=[])
        assert siblings_label([arm]) is None

    def test_a_replayed_arm_without_a_receipt_says_the_window_is_undeclared(self) -> None:
        arm = _sibling(1, live=[], replay=_outcomes(5, r=Decimal("1"), start=START))
        assert siblings_label([arm]) == "siblings: replay sobre janela não declarada"

    def test_evidence_labels_survive_into_the_payload(self) -> None:
        arms = [
            _sibling(1, live=_outcomes(5, r=Decimal("1"), start=START), replay=[]),
            _sibling(2, live=[], replay=_outcomes(5, r=Decimal("1"), start=START)),
            _sibling(
                3,
                live=_outcomes(3, r=Decimal("1"), start=START),
                replay=_outcomes(3, r=Decimal("-1"), start=START + timedelta(days=100)),
            ),
            _sibling(4, live=[], replay=[]),
        ]
        block = build_replication_block(
            version_id=VERSION_ID, promising_at=START, parent_outcomes=[], siblings=arms
        )
        assert block is not None
        assert {arm.k: arm.evidence for arm in block.siblings.arms} == {
            1: "prospective",
            2: "replay",
            3: "mixed",
            4: None,
        }


class TestResolveSeed:
    """T3.18c, item 6: a semente diz de onde veio."""

    def test_no_registered_round_derives_from_the_version_id_and_says_so(self) -> None:
        seed, source = resolve_seed(VERSION_ID, None)
        assert seed == int.from_bytes(VERSION_ID.bytes[:4], "big")
        assert source == SEED_SOURCE_DERIVED

    def test_the_registered_seed_wins_and_is_labelled_registrada(self) -> None:
        assert resolve_seed(VERSION_ID, 20260908) == (20260908, SEED_SOURCE_REGISTERED)

    def test_the_payload_publishes_the_provenance_on_both_intervals(self) -> None:
        block = build_replication_block(
            version_id=VERSION_ID,
            promising_at=START,
            parent_outcomes=[],
            siblings=[],
            registered_seed=20260908,
        )
        assert block is not None
        assert block.bootstrap.seed == 20260908
        assert block.bootstrap.seed_source == SEED_SOURCE_REGISTERED
        assert block.bootstrap.day_cluster.seed_source == SEED_SOURCE_REGISTERED


class TestOutOfSampleStaysProspectiveOnly:
    """D15 (b): the parent population this module is handed already has to be
    ``prospective``-filtered by the repository — this block builder trusts
    its caller and asserts only that it never mixes anything back in."""

    def test_out_of_sample_reads_exactly_the_outcomes_it_was_given(self) -> None:
        after = START + timedelta(days=1)
        # >= 50 avaliáveis em >= 15 dias de saída distintos -> meia-régua (§1.5)
        parent_outcomes = _outcomes(MATURITY_HALF_DAYS + 5, r=Decimal("1"), start=after) * 5
        parent_outcomes = parent_outcomes[: MATURITY_HALF_OUTCOMES + 5]

        block = build_replication_block(
            version_id=VERSION_ID,
            promising_at=START,
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
