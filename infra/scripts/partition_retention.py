"""Retention per monthly partition owner — DATABASE.md §1.3.

One table, read by both daily jobs. ``prune_partitions.py`` drops the months it
declares expired; ``create_partitions.py`` refuses to *create* a backward month
it declares expired (T2.5f). While only the pruner had an opinion about the past
this lived inside it; now that both do, a second copy would be a second policy —
and the two would disagree exactly once, on the night one of them was edited,
with the daily jobs then fighting over the same partition: the creator making it
at 04:07 and the pruner dropping it at 04:12, every day, each taking an ``ACCESS
EXCLUSIVE`` lock on the parent for nothing.

Nothing here touches the database. ``retention_days`` reads two figures from
``Settings`` (the tunable ones) and hard-codes the rest of DATABASE.md §1.3;
``is_expired`` and :func:`month_is_retained` are pure calendar arithmetic on a
partition's **upper** bound, which is the only bound that proves no retained row
can fall inside it.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from hunter_core.db.models import list_partition_name, month_bounds, partition_name
from hunter_core.settings import Settings

if TYPE_CHECKING:
    from collections.abc import Mapping

KEEP_FOREVER: int | None = None
"""Retention for a relation DATABASE.md §1.3 gives no limit for."""

MONTH_SUFFIX = re.compile(r"^(?P<owner>.+)_(?P<year>(?:19|20)\d{2})_(?P<month>0[1-9]|1[0-2])$")


def retention_days(settings: Settings | None = None) -> dict[str, int | None]:
    """Days of history to keep, per relation that directly owns monthly children.

    The two figures the platform tunes at runtime come from ``Settings``; the
    rest are the fixed table in DATABASE.md §1.3. Timeframes the document does
    not give a limit for (``15m``, ``4h``) are kept forever on purpose —
    inventing a retention for them here would silently delete data no decision
    covers.
    """
    config = settings or Settings()
    candles = {
        "1m": config.retention_candles_1m_days,
        "5m": 365,
        "15m": KEEP_FOREVER,
        "1h": KEEP_FOREVER,
        "4h": KEEP_FOREVER,
        "1d": KEEP_FOREVER,
    }
    equity = {
        "1m": 30,
        "5m": KEEP_FOREVER,
        "15m": KEEP_FOREVER,
        "1h": KEEP_FOREVER,
        "4h": KEEP_FOREVER,
        "1d": KEEP_FOREVER,
    }
    policy: dict[str, int | None] = {
        "audit_logs": KEEP_FOREVER,
        "system_events": 30,
        "market_snapshots": 30,
        "liquidations": 30,
        "opportunity_history": 90,
        "feature_snapshots": config.retention_feature_snapshots_days,
    }
    for label, days in candles.items():
        policy[list_partition_name("candles", label)] = days
    for label, days in equity.items():
        policy[list_partition_name("portfolio_equity_snapshots", label)] = days
    return policy


def is_expired(child: str, keep_days: int | None, now: datetime) -> bool:
    """True when every row ``child`` can hold is older than the retention window.

    A monthly partition covers ``[start, end)``; it is expired only once ``end``
    itself is past the cutoff, so the month a retained row could still fall in is
    never a candidate.
    """
    if keep_days is None:
        return False
    match = MONTH_SUFFIX.match(child)
    if match is None:
        return False
    _lower, upper = month_bounds(int(match["year"]), int(match["month"]))
    cutoff = now.timestamp() - keep_days * 86400
    return datetime.strptime(upper, "%Y-%m-%d").replace(tzinfo=UTC).timestamp() <= cutoff


def month_is_retained(
    owner: str, year: int, month: int, now: datetime, policy: Mapping[str, int | None]
) -> bool:
    """Would retention still keep ``owner``'s ``year``-``month`` partition today?

    The creator's half of the contract (T2.5f): a backward month is worth
    creating only while the pruner would leave it standing. Expressed per owner
    and per month, on purpose, instead of as one global "retention must be >=
    months-behind + 1": the owners have different windows (``candles_1m`` 90 d,
    ``market_snapshots`` 30 d, ``audit_logs`` forever), so one global number
    would either starve the long ones or make the short ones churn. Reading the
    same :func:`is_expired` the pruner reads is what makes "the creator never
    creates what the pruner drops" true by construction rather than by comment.

    An owner absent from ``policy`` is kept forever (:data:`KEEP_FOREVER`) — the
    honest default for a parent no retention decision covers.

    **The guarantee is per instant**, and ``now`` is what carries it. Retention
    is counted in whole days, so a month expires at a UTC midnight: a plan built
    at 23:59 and pruned at 00:01 can create a month the pruner then drops —
    once, since the next day's plan no longer contains it, and never at the cost
    of a retained row (what is dropped in that case is a month whose last
    retained row has just aged out). 04:07 to 04:12, the real schedule, does not
    cross a boundary at all.
    """
    return not is_expired(partition_name(owner, year, month), policy.get(owner, KEEP_FOREVER), now)
