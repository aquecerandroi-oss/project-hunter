"""T4.10 — the hype score's arithmetic, checked against the documented table.

15 buys → 0,5 × 0,35 = 0,175; 10 unique buyers → 0,5 × 0,25 = 0,125; position 3
on a board → 1 × 0,20; social → 0,10; one sniper → 0,10. Total 0,700000.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from hunter_indicators.meme.hype import (
    HYPE_DEFINITION,
    HYPE_REASONS,
    NO_TAPE_NO_BOARD,
    PARTIAL,
    WEIGHTS,
    HypeInputs,
    hype_score,
)

pytestmark = pytest.mark.unit


def _inputs(**overrides: object) -> HypeInputs:
    base: dict[str, object] = {
        "buys_1m": 15,
        "unique_buyers_1m": 10,
        "board_position": 3,
        "has_social": True,
        "snipers": 1,
        "tape_present": True,
        "board_present": True,
    }
    base.update(overrides)
    return HypeInputs(**base)  # type: ignore[arg-type]


def test_the_weights_sum_to_one_and_are_the_briefs() -> None:
    assert sum(WEIGHTS.values()) == Decimal(1)
    assert WEIGHTS == {
        "buys_1m": Decimal("0.35"),
        "unique_buyers_1m": Decimal("0.25"),
        "board": Decimal("0.20"),
        "has_social": Decimal("0.10"),
        "snipers_low": Decimal("0.10"),
    }
    assert HYPE_DEFINITION.params["weights"] == {k: str(v) for k, v in WEIGHTS.items()}


def test_the_documented_example_scores_0_7_with_its_decomposition() -> None:
    result = hype_score(_inputs())
    assert result.score == Decimal("0.700000") and result.reason is None
    by_name = {c.name: c for c in result.components}
    assert by_name["buys_1m"].normalized == Decimal("0.5")
    assert by_name["buys_1m"].contribution == Decimal("0.175000")
    assert by_name["unique_buyers_1m"].contribution == Decimal("0.125000")
    assert by_name["board"].contribution == Decimal("0.200000")
    assert by_name["has_social"].contribution == Decimal("0.100000")
    assert by_name["snipers_low"].contribution == Decimal("0.100000")
    assert by_name["buys_1m"].raw == "15" and by_name["buys_1m"].weight == Decimal("0.35")
    payload = result.as_json()
    assert payload["score"] == "0.700000" and len(payload["components"]) == 5  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("position", "expected"),
    [(0, "0.2"), (9, "0.2"), (10, "0.1"), (49, "0.1"), (50, "0"), (None, "0")],
)
def test_board_standing_is_top_10_top_50_or_nothing(position: int | None, expected: str) -> None:
    result = hype_score(_inputs(board_position=position))
    board = next(c for c in result.components if c.name == "board")
    assert board.contribution == Decimal(expected).quantize(Decimal("0.000001"))


def test_buys_and_buyers_are_capped_at_30_and_20() -> None:
    result = hype_score(_inputs(buys_1m=300, unique_buyers_1m=200, board_position=0))
    assert result.score == Decimal("1.000000")
    zero = hype_score(
        _inputs(buys_1m=0, unique_buyers_1m=0, board_position=None, has_social=False, snipers=5)
    )
    assert zero.score == Decimal("0.000000")


def test_snipers_pay_only_when_known_and_at_most_two() -> None:
    assert next(
        c for c in hype_score(_inputs(snipers=2)).components if c.name == "snipers_low"
    ).contribution == Decimal("0.100000")
    assert next(
        c for c in hype_score(_inputs(snipers=3)).components if c.name == "snipers_low"
    ).contribution == Decimal("0.000000")
    assert next(
        c for c in hype_score(_inputs(snipers=None)).components if c.name == "snipers_low"
    ).contribution == Decimal("0.000000"), "an unknown sniper count is not few snipers"


def test_without_tape_and_board_the_score_is_null_with_its_reason() -> None:
    result = hype_score(
        _inputs(
            buys_1m=None,
            unique_buyers_1m=None,
            board_position=None,
            has_social=None,
            tape_present=False,
            board_present=False,
        )
    )
    assert result.score is None and result.reason == NO_TAPE_NO_BOARD
    assert len(result.components) == 5, "the decomposition is still written, at zero"


def test_one_source_alone_is_partial_with_a_number() -> None:
    tape_only = hype_score(_inputs(board_position=None, has_social=None, board_present=False))
    assert tape_only.reason == PARTIAL
    assert tape_only.score == Decimal("0.400000")  # 0,175 + 0,125 + 0 + 0 + 0,1
    board_only = hype_score(_inputs(buys_1m=None, unique_buyers_1m=None, tape_present=False))
    assert board_only.reason == PARTIAL and board_only.score == Decimal("0.400000")


def test_the_reason_vocabulary_is_the_briefs() -> None:
    assert HYPE_REASONS == {"no_tape_no_board", "partial"}
    assert HYPE_DEFINITION.key == "hype_score" and HYPE_DEFINITION.version == 1
