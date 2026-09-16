"""T4.28h — the dev share on its way into :class:`MemeContext`, with its stamp.

The engine's allowance (``creator_unknown_allowed_if_dev_measured``) only ever
sees a dev share the executor decided is an input. That decision is here, pure
and unit-testable, and it is the same shape as ``bundled_share``'s: the repo
reads the freshest measured value of the two tables, ``context_from`` drops it
when it is older than :data:`DEV_SHARE_MAX_AGE_S`, has no stamp, or carries a
stamp from the future — a share nobody can date is not a share (§8).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_meme_executor.admission import context_from
from hunter_meme_executor.repo import DEV_SHARE_MAX_AGE_S, TokenContext
from hunter_meme_executor.repo_context import freshest_dev_share
from hunter_risk_meme import MemeContext

pytestmark = pytest.mark.unit

MINT = "Cfsb4vQx7ZrHb3tR8t6YpiPVEP1KfwB3jvJKHhHGpump"
NOW = datetime(2026, 9, 16, 18, 33, 15, tzinfo=UTC)


def _token(
    *,
    dev_share: Decimal | None,
    observed_at: datetime | None,
    source: str | None = "meme_risk_snapshots",
    creator_sold: bool | None = None,
) -> TokenContext:
    return TokenContext(
        created_at=NOW - timedelta(seconds=160),
        creator="AsRQHoHxfBYqvxJZxK9RtJUnRZcCwUoh9KNpVxH6Jhnd",
        initial_real_token_reserves=793_100_000,
        completed_at=None,
        migrated_at=None,
        curve_volume_1m_sol=Decimal("11.1"),
        features_end_time=NOW - timedelta(seconds=30),
        creator_sold=creator_sold,
        top10_share=Decimal("0.15"),
        bundled_share=Decimal("0.05"),
        dev_share=dev_share,
        dev_share_source=source,
        dev_share_observed_at=observed_at,
    )


def _context_for(token: TokenContext) -> MemeContext:
    return context_from(MINT, token, participation_used_sol=Decimal(0), now=NOW)


def test_a_fresh_measured_dev_share_reaches_the_engine_with_its_provenance() -> None:
    context = _context_for(
        _token(dev_share=Decimal("0.05"), observed_at=NOW - timedelta(seconds=120))
    )
    assert context.dev_share_pct == Decimal("0.05")
    assert context.dev_share_source == "meme_risk_snapshots"
    assert context.dev_share_ts == NOW - timedelta(seconds=120)


def test_the_boundary_of_the_window_is_still_an_input() -> None:
    context = _context_for(
        _token(dev_share=Decimal("0.05"), observed_at=NOW - timedelta(seconds=DEV_SHARE_MAX_AGE_S))
    )
    assert context.dev_share_pct == Decimal("0.05")


def test_a_reading_older_than_the_window_is_not_an_input() -> None:
    context = _context_for(
        _token(
            dev_share=Decimal("0.05"),
            observed_at=NOW - timedelta(seconds=DEV_SHARE_MAX_AGE_S + 1),
        )
    )
    assert context.dev_share_pct is None
    assert context.dev_share_source is None and context.dev_share_ts is None


def test_a_dev_share_nobody_dated_vouches_for_nothing() -> None:
    context = _context_for(_token(dev_share=Decimal("0.05"), observed_at=None))
    assert context.dev_share_pct is None


def test_a_stamp_from_the_future_is_a_clock_disagreeing_not_a_fresh_reading() -> None:
    context = _context_for(
        _token(dev_share=Decimal("0.05"), observed_at=NOW + timedelta(seconds=5))
    )
    assert context.dev_share_pct is None


def test_an_unmeasured_dev_share_stays_none() -> None:
    context = _context_for(_token(dev_share=None, observed_at=NOW, source=None))
    assert context.dev_share_pct is None
    assert context.dev_share_source is None


def test_the_creator_flow_is_still_none_when_the_fold_has_not_spoken() -> None:
    """The dev share never invents the creator's flow — it only vouches for it."""
    context = _context_for(_token(dev_share=Decimal("0.05"), observed_at=NOW, creator_sold=None))
    assert context.creator_net_sol is None


# ---- which of the two tables the repo believes ------------------------------

SINCE = NOW - timedelta(seconds=DEV_SHARE_MAX_AGE_S)


def _features(
    dev: str | None, *, stamp: datetime | None, source: str | None = "in-memory-coin"
) -> dict[str, object]:
    return {
        "dev_share": None if dev is None else Decimal(dev),
        "holders_observed_at": stamp,
        "holders_source": source,
    }


def _risk(dev: str, *, stamp: datetime) -> dict[str, object]:
    return {"dev_share": Decimal(dev), "observed_at": stamp}


def test_the_newest_reading_wins_when_both_tables_measured_it() -> None:
    older = _features("0.09", stamp=NOW - timedelta(seconds=300))
    newer = _risk("0.04", stamp=NOW - timedelta(seconds=60))
    assert freshest_dev_share(older, newer, SINCE) == (
        Decimal("0.04"),
        "meme_risk_snapshots",
        NOW - timedelta(seconds=60),
    )
    older_risk = _risk("0.04", stamp=NOW - timedelta(seconds=400))
    share, source, stamp = freshest_dev_share(older, older_risk, SINCE)
    assert (share, stamp) == (Decimal("0.09"), NOW - timedelta(seconds=300))
    assert source == "meme_features_1m:in-memory-coin", "the reader is named, not only the table"


def test_a_feature_row_whose_holders_reading_has_no_instant_is_not_dated() -> None:
    """``0023`` stamps ``holders_observed_at`` only when ``holders`` was read; the
    minute's ``end_time`` is the close of the window, not the instant of the read,
    so a share with no stamp is dropped instead of being called fresh."""
    assert freshest_dev_share(_features("0.09", stamp=None), None, SINCE) == (None, None, None)


def test_a_feature_row_older_than_the_window_is_dropped_in_the_repo_too() -> None:
    stale = _features("0.09", stamp=SINCE - timedelta(seconds=1))
    assert freshest_dev_share(stale, None, SINCE) == (None, None, None)


def test_no_reading_at_all_is_three_nones() -> None:
    assert freshest_dev_share(None, None, SINCE) == (None, None, None)
    assert freshest_dev_share(_features(None, stamp=NOW), None, SINCE) == (None, None, None)
