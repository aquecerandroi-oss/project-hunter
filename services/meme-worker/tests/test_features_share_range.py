"""A share above 100 % is not a share: NULL with ``out_of_range``, never a clamp.

Production, 12/09/2026 10:40Z: the site's ``new`` board reported ``t10 = 1.002162``
for a coin in its first minute (the plantão had counted 18/50 such entries at
05:51 BRT); ``ck_meme_features_1m_top10_share_is_a_fraction`` refused the row and
the whole fold loop died with it, three minutes in a row. The columns now carry
``NULL`` + ``out_of_range`` for that reading, and the loop writes the other rows.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hunter_meme_worker.features import NO_HOLDERS_READER, OUT_OF_RANGE, share_or_reason
from hunter_meme_worker.features_tape import HoldersObservation

pytestmark = pytest.mark.unit

AT = datetime(2026, 9, 12, 10, 40, tzinfo=UTC)


def _reading(top10: str | None, dev: str | None) -> HoldersObservation:
    return HoldersObservation(
        observed_at=AT,
        received_at=AT,
        source="trenches_ws",
        holders=16,
        top10_share=None if top10 is None else Decimal(top10),
        dev_share=None if dev is None else Decimal(dev),
        snipers=0,
    )


def test_a_share_above_one_is_null_with_its_own_reason() -> None:
    reading = _reading("1.002162", "0.25")
    assert share_or_reason(reading.top10_share) == (None, OUT_OF_RANGE)
    assert share_or_reason(reading.dev_share) == (Decimal("0.250000"), None), (
        "the other readings of the same entry are kept — only the impossible one is refused"
    )


def test_a_negative_share_is_refused_the_same_way() -> None:
    assert share_or_reason(Decimal("-0.01")) == (None, OUT_OF_RANGE)


def test_the_boundaries_are_shares() -> None:
    assert share_or_reason(Decimal("1")) == (Decimal("1.000000"), None)
    assert share_or_reason(Decimal("0")) == (Decimal("0.000000"), None)


def test_an_absent_share_keeps_the_reader_reason() -> None:
    assert share_or_reason(None) == (None, NO_HOLDERS_READER)
