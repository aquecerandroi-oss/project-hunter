"""The retention table of ``partition_retention.py`` — the 27/09/2026 disk decision.

``docs/design/retencao-e-disco-2026-09-27.md`` §3 and §6 (steps 3 and 5), authorized
by Everton the same day (``obsidian/06-DECISIONS/2026-09-27-retencao-de-dados-e-backup.md``):

- ``opportunity_history`` 90 -> **14 d** (the perpetual radar's explanation, never
  read beyond ~10 h by any reader — design §2);
- ``MEME_RETENTION_DAYS`` 90 -> **30 d** for the meme series, the same window for
  graduated and non-graduated mints (DATABASE.md §33.4 keeps the rule, changes the
  number), and the 15-second series stays at 7 d;
- ``meme_board_observations`` and ``meme_risk_snapshots`` stop being "forever by
  omission": they follow ``MEME_RETENTION_DAYS``, as DATABASE.md §35.4 already said.

Pure: no database. ``prune_partitions.py`` and ``create_partitions.py`` read this
same table, so these numbers are what both jobs act on.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from hunter_core.db.models import monthly_partition_parents
from hunter_core.settings import Settings

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import partition_retention  # noqa: E402

MEME_SERIES = (
    "meme_curve_snapshots",
    "meme_features_1m",
    "meme_trades",
    "meme_board_observations",
    "meme_risk_snapshots",
)


def test_the_meme_window_defaults_to_thirty_days(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEME_RETENTION_DAYS", raising=False)
    assert Settings().meme_retention_days == 30


def test_opportunity_history_is_kept_fourteen_days() -> None:
    assert partition_retention.retention_days()["opportunity_history"] == 14


@pytest.mark.parametrize("owner", MEME_SERIES)
def test_every_meme_series_follows_the_one_window(owner: str) -> None:
    """One number for the five, graduated and non-graduated alike (§33.4)."""
    policy = partition_retention.retention_days(Settings(meme_retention_days=45))
    assert policy[owner] == 45


def test_the_fifteen_second_series_and_the_batch_counts_keep_their_own_windows() -> None:
    policy = partition_retention.retention_days(Settings(meme_retention_days=45))
    assert policy["meme_features_15s"] == 7
    assert policy["meme_market_activity_1m"] == 30


def test_no_monthly_parent_is_kept_forever_by_omission() -> None:
    """Board and risk had no line and so were never pruned (design §1, §7): a parent
    absent from the table is "forever" without anyone having decided it. Forever is
    allowed — ``audit_logs`` — but only as an explicit ``KEEP_FOREVER`` entry."""
    policy = partition_retention.retention_days()
    missing = sorted(set(monthly_partition_parents()) - set(policy))
    assert missing == []


def test_september_of_the_short_windows_falls_when_its_end_is_old_enough() -> None:
    """Monthly partitions drop on the **upper** bound (§1.3): with 14 d the September
    month of ``opportunity_history`` goes on 15/10, with 30 d the meme months on 31/10."""
    policy = partition_retention.retention_days(Settings(meme_retention_days=30))
    expired = partition_retention.is_expired
    history = policy["opportunity_history"]
    assert not expired("opportunity_history_2026_09", history, datetime(2026, 10, 14, tzinfo=UTC))
    assert expired("opportunity_history_2026_09", history, datetime(2026, 10, 15, tzinfo=UTC))
    board = policy["meme_board_observations"]
    assert not expired("meme_board_observations_2026_09", board, datetime(2026, 10, 30, tzinfo=UTC))
    assert expired("meme_board_observations_2026_09", board, datetime(2026, 10, 31, tzinfo=UTC))
