"""T4.35 — the per-mint refusal trail's own selector (a row worth keeping is a
proposal or a near-miss, never a pile of failures) and its per-tick cap."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from hunter_indicators.meme.rules import EntryFeatures, EntryGate
from hunter_meme_worker.gate_refusal_trail import (
    RefusalTrailRow,
    cap_trail_rows,
    decode_value_limit,
    is_trail_candidate,
    select_trail_row,
)

pytestmark = pytest.mark.unit

AS_OF = datetime(2026, 9, 16, 16, 20, tzinfo=UTC)
RULE_SET_ID = "01994d00-6c1a-7000-8000-000000000001"
MINT = "BiCp7Nhz111111111111111111111111111111111111"
_GATE = EntryGate(
    key="teste_trilha",
    version=1,
    description="Test fixture for decode_value_limit.",
    min_age_s=30,
    max_age_s=300,
    min_progress_pct=Decimal(2),
    max_progress_pct=Decimal(50),
    max_participation_pct=Decimal(5),
    max_snipers=20,
    min_holders=5,
)
_FEATURES = EntryFeatures(
    mint=MINT,
    age_s=64,
    progress_pct=Decimal(8),
    creator_net_seller=False,
    curve_volume_1m_sol=Decimal(10),
    intended_size_sol=Decimal("0.4"),
    snipers=64,
    holders=3,
)


@pytest.mark.parametrize(
    ("refusal_count", "expected"),
    [(0, True), (1, True), (2, False), (3, False), (10, False)],
)
def test_is_trail_candidate_keeps_only_a_proposal_or_a_single_miss(
    refusal_count: int, expected: bool
) -> None:
    assert is_trail_candidate(refusal_count) is expected


def test_is_trail_candidate_refuses_a_negative_count() -> None:
    with pytest.raises(ValueError, match="refusal_count must be >= 0"):
        is_trail_candidate(-1)


def test_select_trail_row_records_a_proposal_with_no_refusal() -> None:
    row = select_trail_row(as_of=AS_OF, rule_set_id=RULE_SET_ID, mint=MINT, refusals=())
    assert row == RefusalTrailRow(
        as_of=AS_OF, rule_set_id=RULE_SET_ID, mint=MINT, refusal=None, value=None, limit=None
    )


def test_select_trail_row_records_a_near_miss_with_its_one_refusal_and_numbers() -> None:
    row = select_trail_row(
        as_of=AS_OF,
        rule_set_id=RULE_SET_ID,
        mint=MINT,
        refusals=("snipers_above_max",),
        value=64,
        limit=20,
    )
    assert row is not None
    assert row.refusal == "snipers_above_max"
    assert row.value == 64 and row.limit == 20


def test_select_trail_row_is_none_for_two_or_more_failed_criteria() -> None:
    refused = select_trail_row(
        as_of=AS_OF,
        rule_set_id=RULE_SET_ID,
        mint=MINT,
        refusals=("age_below_min", "holders_below_min"),
    )
    assert refused is None


def _rows(n: int) -> list[RefusalTrailRow]:
    return [
        RefusalTrailRow(as_of=AS_OF, rule_set_id=RULE_SET_ID, mint=f"mint{i}", refusal=None)
        for i in range(n)
    ]


def test_cap_trail_rows_keeps_everything_under_the_limit_uncapped() -> None:
    kept, capped = cap_trail_rows(_rows(5), limit=200)
    assert len(kept) == 5 and capped is False


def test_cap_trail_rows_truncates_and_says_so_at_the_limit() -> None:
    kept, capped = cap_trail_rows(_rows(250), limit=200)
    assert len(kept) == 200 and capped is True
    assert [r.mint for r in kept] == [f"mint{i}" for i in range(200)]


def test_cap_trail_rows_at_exactly_the_limit_is_not_capped() -> None:
    kept, capped = cap_trail_rows(_rows(200), limit=200)
    assert len(kept) == 200 and capped is False


def test_cap_trail_rows_refuses_a_negative_limit() -> None:
    with pytest.raises(ValueError, match="limit must be >= 0"):
        cap_trail_rows(_rows(3), limit=-1)


def test_decode_value_limit_reads_the_named_pair_off_features_and_gate() -> None:
    assert decode_value_limit("snipers_above_max", _FEATURES, _GATE) == (64, 20)
    assert decode_value_limit("holders_below_min", _FEATURES, _GATE) == (3, 5)


def test_decode_value_limit_is_none_none_for_an_undecoded_name() -> None:
    assert decode_value_limit("creator_is_net_seller", _FEATURES, _GATE) == (None, None)
    assert decode_value_limit("mayhem_curve", _FEATURES, _GATE) == (None, None)
