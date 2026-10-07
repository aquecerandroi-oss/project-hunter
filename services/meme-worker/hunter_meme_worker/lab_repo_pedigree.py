"""The pedigree read of the Lab loop (T4.16, EXP-M6) — a mint's counts at proposal time, as
``hunter_worker`` and bounded (T4.24b). Split out of ``lab_repo_fast.py`` (350-line budget)
when EXP-M26 F gave it a second statement; ``lab_repo_fast`` still re-exports the names the
rest of the tree imports from there.

**Non-anticipation in SQL:** the counts include only coins created **at or before** the coin
judged (a launch that came later is not a prior mint).

**Two statements, one lane each (EXP-M26 F, 01/10/2026).** :data:`_PEDIGREE` is the full read
the 15-second lane — the real desk — has always run, byte for byte
(``test_pedigree_light.py`` pins its hash). :data:`_PEDIGREE_COUNTS` is the same two first
counts and nothing else, for the minute lane when no set of that clock asks for
``pedigree_repeat_dumper``: the funnel F measured the full read at 6-14 s for ~385 mints on the
VPS (EXPLAIN ANALYZE 7.89 s, 24 of 30 minutes over the 8 s cut), nearly all of it in
``creator_prior_dump_count`` and the diagnostic ``creator_prior_dead_count`` (63 559 prior
coins of the same creators walked); the two counts of ``PEDIGREE_V1`` took 28-69 ms. A read cut
at 8 s returns ``{}`` and every row of the minute becomes ``pedigree_unknown``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from hunter_core.logging import get_logger
from hunter_indicators.meme.pedigree import PEDIGREE_V1, PedigreeFeatures, PedigreeGate
from hunter_meme_worker.db_errors import db_error_fields
from hunter_meme_worker.entry_pullback import PULLBACK_ARM_RULE_SET_ID, PULLBACK_CONTROL_RULE_SET_ID
from hunter_meme_worker.lab_opportunities import MATURE_CHART_RULE_SET_IDS
from hunter_meme_worker.refused_probe import PROBE_RULE_SET_ID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["ABSORB_SEMDUMP_RULE_SET_ID", "PRIOR_WINDOW_S", "pedigree_for", "pedigree_params"]

_logger = get_logger(__name__)

ABSORB_SEMDUMP_RULE_SET_ID: Final = "01994d00-6c1a-7000-8000-000000000022"
"""H-031b (EXP-M27): the twin ``absorb_semdump_v0/1`` (``absorb_v0/2`` without the
``creator_dump`` exit) — ``ddl/meme_absorb_semdump_arm``'s own id."""

PRIOR_WINDOW_S = 7 * 86_400
"""T4.24b (hotfix, 15/09/2026 19:3x BRT): the prior-coin counts look back **7 days**, not
forever — the unbounded version scanned ``meme_tokens`` (105 k rows, no creator index)
once per judged mint per tick and hit the statement timeout, killing the Lab loop
(11 restarts after deploy 8293c2b). ``0040`` adds the ``(creator, created_at)`` index."""
_PRIOR_MINTS = (
    "SELECT count(*) FROM meme_tokens o WHERE o.creator = t.creator "
    "  AND o.mint <> t.mint AND o.created_at IS NOT NULL AND o.created_at <= t.created_at "
    "  AND o.created_at > t.created_at - make_interval(secs => :prior_window_s)"
)
"""Every prior coin of this creator, any window — the base ``creator_prior_dump_count``
and ``creator_prior_dead_count`` (T4.24) both start from and narrow with an ``AND``."""

_CREATOR_1H = (
    "CASE WHEN t.creator IS NULL OR t.created_at IS NULL THEN NULL ELSE ("
    "         SELECT count(*) FROM meme_tokens o WHERE o.creator = t.creator "
    "           AND o.mint <> t.mint AND o.created_at IS NOT NULL "
    "           AND o.created_at <= t.created_at "
    "           AND o.created_at > t.created_at - make_interval(secs => :creator_window_s)"
    "       ) END AS creator_prior_mints_1h"
)
_SYMBOL_24H = (
    "CASE WHEN t.symbol IS NULL OR t.created_at IS NULL THEN NULL ELSE ("
    "         SELECT count(*) FROM meme_tokens o WHERE o.symbol = t.symbol "
    "           AND o.mint <> t.mint AND o.created_at IS NOT NULL "
    "           AND o.created_at <= t.created_at "
    "           AND o.created_at > t.created_at - make_interval(secs => :symbol_window_s)"
    "       ) END AS symbol_dup_24h"
)
_DUMP_COUNT = (
    "CASE WHEN t.creator IS NULL OR t.created_at IS NULL THEN NULL ELSE ("  # noqa: S608  # nosec B608 -- identifiers and fragments are module-level constants, never an argument or a row; values are bound parameters
    f"        {_PRIOR_MINTS}"
    "           AND ("
    "             EXISTS (SELECT 1 FROM meme_features_1m pf WHERE pf.mint = o.mint "
    "                       AND pf.creator_sold = true AND pf.end_time < t.created_at)"
    "             OR EXISTS (SELECT 1 FROM meme_paper_bets pb WHERE pb.mint = o.mint "
    "                          AND pb.rule_set_id <> :probe_rule_set_id "
    "                          AND pb.rule_set_id <> :pullback_rule_set_id "
    "                          AND pb.rule_set_id <> :pullback_control_rule_set_id "
    "                          AND pb.rule_set_id <> ALL(CAST(:mature_rule_set_ids AS uuid[])) "
    "                          AND pb.creator_sold_seen_at IS NOT NULL "
    "                          AND pb.creator_sold_seen_at < t.created_at)"
    "             OR EXISTS (SELECT 1 FROM meme_paper_bets pb2 WHERE pb2.mint = o.mint "
    "                          AND pb2.rule_set_id <> :probe_rule_set_id "
    "                          AND pb2.rule_set_id <> :pullback_rule_set_id "
    "                          AND pb2.rule_set_id <> :pullback_control_rule_set_id "
    "                          AND pb2.rule_set_id <> ALL(CAST(:mature_rule_set_ids AS uuid[])) "
    "                          AND pb2.exit ->> 'reason' = 'creator_dump' "
    "                          AND pb2.exit_at < t.created_at)"
    "           )"
    "       ) END AS creator_prior_dump_count"
)
_DEAD_COUNT = (
    "CASE WHEN t.creator IS NULL OR t.created_at IS NULL THEN NULL ELSE ("  # noqa: S608  # nosec B608 -- identifiers and fragments are module-level constants, never an argument or a row; values are bound parameters
    f"        {_PRIOR_MINTS}"
    "           AND EXISTS ("
    "             SELECT 1 FROM ("
    "               SELECT max(w.mcap_sol) AS peak, min(w.mcap_sol) AS trough "
    "               FROM meme_features_1m w WHERE w.mint = o.mint AND w.mcap_sol IS NOT NULL "
    "                 AND w.end_time > o.created_at "
    "                 AND w.end_time <= o.created_at + interval '30 minutes'"
    "             ) window_30m "
    "             WHERE window_30m.peak IS NOT NULL AND window_30m.peak > 0 "
    "               AND window_30m.trough < window_30m.peak * 0.2"
    "           )"
    "       ) END AS creator_prior_dead_count"
)
_COLUMN = "       "  # the original statement's column indent, kept so its text never changes
_FROM = "FROM meme_tokens t WHERE t.mint = ANY(:mints)"

_PEDIGREE = text(
    "SELECT t.mint, "
    f"{_COLUMN}{_CREATOR_1H}, "
    f"{_COLUMN}{_SYMBOL_24H}, "
    f"{_COLUMN}{_DUMP_COUNT}, "
    f"{_COLUMN}{_DEAD_COUNT} "
    f"{_FROM}"
)
"""Four correlated counts over ``meme_tokens``, index ranges on ``(symbol, created_at)`` (``0064``;
329 mints took 14 s without it) and ``(creator, created_at)`` (``0040``). ``NULL`` when the identity
is unknown — the gate refuses that by name, never reads it as zero.

T4.24 (EXP-M6, braço 2): ``creator_prior_dump_count`` counts **any** window
(unlike the 1 h/24 h of the two above) up to the judged coin's own creation,
over three sources of evidence — the tape (``meme_features_1m.creator_sold``),
the chain watch (``meme_paper_bets.creator_sold_seen_at``, T4.2h) or one of
our own bets exiting ``creator_dump``. ``creator_prior_dead_count`` is
diagnostic only (never a refusal): a prior coin whose ``mcap_sol`` fell under
20 % of its own 30-minute peak; a coin with **no** ``meme_features_1m`` row in
that window is excluded from the count either way (declared "not measured"),
never read as alive nor as dead."""
_PEDIGREE_COUNTS = text(f"SELECT t.mint, {_COLUMN}{_CREATOR_1H}, {_COLUMN}{_SYMBOL_24H} {_FROM}")
"""EXP-M26 F: the two counts of ``PEDIGREE_V1`` and no more — no ``meme_features_1m``, no
``meme_paper_bets``, no ``:prior_window_s``. The same SQL text per count as :data:`_PEDIGREE`
(one definition, two statements)."""


def pedigree_params(mints: Sequence[str], gate: PedigreeGate, *, full: bool) -> dict[str, Any]:
    """The bound parameters of :data:`_PEDIGREE` (``full``) or :data:`_PEDIGREE_COUNTS`."""
    params: dict[str, Any] = {
        "mints": list(mints),
        "creator_window_s": gate.creator_window_s,
        "symbol_window_s": gate.symbol_window_s,
    }
    if full:
        params |= {
            "prior_window_s": PRIOR_WINDOW_S,
            # T4.85 (EXP-M23): the probe's own paper bets are evidence the desk would
            # never have had — its bets make the creator watcher stamp
            # ``creator_sold_seen_at`` on mints nobody was watching, which would
            # change the real desk's ``creator_repeat_dumper`` refusals. Excluded by id.
            "probe_rule_set_id": PROBE_RULE_SET_ID,
            # T4.91 (EXP-M24): the same for recuo_v1/1 — its bets could witness a creator sale.
            "pullback_rule_set_id": PULLBACK_ARM_RULE_SET_ID,
            "pullback_control_rule_set_id": PULLBACK_CONTROL_RULE_SET_ID,  # T4.95: and its control
            # EXP-M26 (0068): the 3 arms; H-031b: and the twin, through the same list so the
            # statement's text (pinned by test_pedigree_light) does not change.
            "mature_rule_set_ids": [*MATURE_CHART_RULE_SET_IDS, ABSORB_SEMDUMP_RULE_SET_ID],
        }
    return params


def _count(value: Any) -> int | None:
    return None if value is None else int(value)


async def pedigree_for(
    session: AsyncSession,
    mints: Sequence[str],
    *,
    gate: PedigreeGate = PEDIGREE_V1,
    full: bool = True,
) -> dict[str, PedigreeFeatures]:
    """The counts of EXP-M6 per mint, from ``meme_tokens`` at this instant.

    ``full=False`` (EXP-M26 F, the minute lane when no set of that clock asks for
    ``pedigree_repeat_dumper``): only ``creator_prior_mints_1h`` and ``symbol_dup_24h``; the
    two others come back **absent** (``None``, "not read"), never ``0`` — a zero would say "this
    creator never dumped" about a coin whose dumps nobody counted. ``full=True`` is the read the
    desk has always had."""
    if not mints:
        return {}
    statement = _PEDIGREE if full else _PEDIGREE_COUNTS
    try:
        async with session.begin_nested():
            await session.execute(text("SET LOCAL statement_timeout = 8000"))
            rows = (
                (await session.execute(statement, pedigree_params(mints, gate, full=full)))
                .mappings()
                .all()
            )
    except DBAPIError as exc:
        # T4.24b: the savepoint rolled back; the tick goes on with the pedigree unread
        # (every gate refuses ``pedigree_unknown`` by name) instead of dying.
        _logger.warning(
            "meme_pedigree_read_failed", mints=len(mints), full=full, **db_error_fields(exc)
        )
        return {}
    return {
        str(r["mint"]): PedigreeFeatures(
            creator_prior_mints_1h=_count(r["creator_prior_mints_1h"]),
            symbol_dup_24h=_count(r["symbol_dup_24h"]),
            creator_prior_dump_count=_count(r["creator_prior_dump_count"]) if full else None,
            creator_prior_dead_count=_count(r["creator_prior_dead_count"]) if full else None,
        )
        for r in rows
    }
