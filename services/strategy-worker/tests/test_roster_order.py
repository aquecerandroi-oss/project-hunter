"""``roster.roster_order`` — quem o worker avalia primeiro (revisão T3.26-risk, A3).

``load_version_roster`` ordenava por ``ORDER BY version`` no SQL, que é ordem de
texto: ``v10`` vinha antes de ``v3``. E nada dizia que a linha ``paper`` — a única
cujas decisões podem chegar numa carteira — devia ser avaliada antes das
variantes de pesquisa que estão ao lado dela. Com uma variante quebrada primeiro
na lista e um laço sem ``try`` (ver ``test_consumer_isolation.py``), a linha paper
parava em silêncio.

Puro: a ordem é uma função total sobre :class:`ActiveVersion`, e é isso que este
arquivo testa — sem Docker, sem banco.

Run: ``uv run pytest services/strategy-worker/tests/test_roster_order.py -q``
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from hunter_core.strategies.envelope import PURPOSE_PAPER, PURPOSE_RESEARCH_ONLY
from hunter_core.strategies.volume_anomaly_v1 import VOLUME_ANOMALY_V1
from hunter_strategy_worker.catalogue import roster_order as roster_order_from_catalogue
from hunter_strategy_worker.roster import ActiveVersion, roster_order

pytestmark = pytest.mark.unit


def _version(version: str, *, purpose: str = PURPOSE_RESEARCH_ONLY, key: str = "momentum") -> Any:
    return ActiveVersion(
        id=uuid.uuid4(),
        strategy_key=key,
        version=version,
        params={"volume_mult": "4"},
        params_hash="0" * 64,
        strategy=VOLUME_ANOMALY_V1,
        code_ref=None,
        purpose=purpose,
    )


def _labels(versions: list[Any]) -> list[str]:
    return [f"{v.strategy_key}:{v.version}:{v.purpose}" for v in sorted(versions, key=roster_order)]


class TestNumericOrder:
    def test_v10_comes_after_v3_not_before_it(self) -> None:
        assert _labels([_version("v10"), _version("v3"), _version("v9")]) == [
            "momentum:v3:research_only",
            "momentum:v9:research_only",
            "momentum:v10:research_only",
        ]

    def test_a_label_this_build_cannot_read_sorts_last(self) -> None:
        """Não é um erro nem um palpite: vai para o fim, e por texto entre si."""
        assert _labels([_version("v2"), _version("rc-1"), _version("v11")]) == [
            "momentum:v2:research_only",
            "momentum:v11:research_only",
            "momentum:rc-1:research_only",
        ]


class TestPaperFirst:
    def test_the_paper_line_is_evaluated_before_the_research_variants(self) -> None:
        assert _labels([_version("v2"), _version("v4"), _version("v3", purpose=PURPOSE_PAPER)]) == [
            "momentum:v3:paper",
            "momentum:v2:research_only",
            "momentum:v4:research_only",
        ]

    def test_paper_first_applies_per_strategy_not_across_them(self) -> None:
        """Estratégias diferentes são experimentos diferentes; a ordem entre elas
        é o nome, e o ``paper`` de uma não pula na frente da outra."""
        assert _labels(
            [
                _version("v1", key="volume_anomaly"),
                _version("v3", key="momentum", purpose=PURPOSE_PAPER),
            ]
        ) == ["momentum:v3:paper", "volume_anomaly:v1:research_only"]


class TestTheReviewScenario:
    def test_a_broken_v10_variant_no_longer_precedes_the_paper_line(self) -> None:
        """O caso exato da A3: ``momentum`` com v2/v3(paper)/v4 e uma variante
        ``v10``. Em ordem de texto, ``v10`` era a primeira da lista."""
        roster = [
            _version("v2"),
            _version("v3", purpose=PURPOSE_PAPER),
            _version("v4"),
            _version("v10"),
        ]
        ordered = _labels(roster)
        assert ordered[0] == "momentum:v3:paper"
        assert ordered[-1] == "momentum:v10:research_only"


def test_the_catalogue_re_export_is_the_same_function() -> None:
    """Todo mundo importa de ``catalogue``; o split da T3.26c não moveu ninguém."""
    assert roster_order_from_catalogue is roster_order
