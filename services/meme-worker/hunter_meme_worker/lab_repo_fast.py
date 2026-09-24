"""The T4.16 reads of the Lab loop — as ``hunter_worker``, never as owner
(``lab_repo.py``'s discipline): the rows of the 15-second series a gate has
not judged yet, and the pedigree of a mint at proposal time (EXP-M6).

**Non-anticipation in SQL**, twice: a 15-second row is read only when its
``as_of`` is at or before the tick (``as_of <= :until``) — the producer
already bounded its inputs by ``received_at <= as_of`` — and the pedigree
counts only coins created **at or before** the coin judged (a launch that
came later is not a prior mint).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from hunter_core.logging import get_logger
from hunter_indicators.meme.pedigree import PEDIGREE_V1, PedigreeFeatures, PedigreeGate
from hunter_meme_worker.entry_pullback import PULLBACK_ARM_RULE_SET_ID
from hunter_meme_worker.gate_refusal_trail import RefusalTrailRow
from hunter_meme_worker.lab_repo_drawdown import with_recent_drawdown
from hunter_meme_worker.lab_rows import snapshot_from_row
from hunter_meme_worker.proposals import SERIES_15S, GateRow
from hunter_meme_worker.refused_probe import PROBE_RULE_SET_ID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "insert_refusal_trail",
    "load_fast_gate_rows",
    "pedigree_for",
    "prune_refusal_trail",
]

_EVENT_MATCH_LATERAL = (
    "SELECT e.kind, e.title, e.source, e.confidence, e.observed_at, m.match_kind "
    "FROM meme_event_matches m JOIN meme_events e ON e.id = m.event_id "
    "WHERE m.mint = t.mint ORDER BY (m.match_kind = 'avoid') DESC, m.matched_at ASC LIMIT 1"
)
"""T4.26b: see ``lab_repo.py``'s own copy of this join — duplicated rather than
imported, the existing convention between these two modules."""

_FAST_ROWS = text(
    "SELECT f.as_of, f.mint, f.snapshot_observed_at, f.snapshot_source, f.mcap_sol, "  # noqa: S608
    "       f.mcap_delta_60s, f.curve_progress_pct, f.progress_reason, f.progress_rising, "
    "       f.holders, f.holders_prev, f.holders_rising, f.holders_reason, "
    "       f.buys_60s, f.sells_60s, f.unique_buyers_60s, "
    "       f.net_sol_flow_60s, f.curve_volume_60s_sol, f.tape_reason, f.creator_net_seller, "
    "       f.dev_share, f.dev_share_reason, f.snipers, "
    # T4.85 (EXP-M23): the row's own provenance — when it was written and
    # where its tape window ends. Read by ``refused_probe.is_readable_at``;
    # no gate reads them, so no judgement changes.
    "       f.computed_at, f.tape_as_of, "
    "       t.created_at, t.completed_at, t.migrated_at, t.initial_real_token_reserves, "
    "       t.symbol, t.mayhem_enabled, t.mayhem_state, "
    "       t.twitter, t.twitter_kind, t.twitter_post_at, t.twitter_reuse_count, "
    "       t.website, t.telegram, t.description, "
    "       ev.kind AS event_kind, ev.title AS event_title, ev.source AS event_source, "
    "       ev.confidence AS event_confidence, ev.observed_at AS event_observed_at, "
    "       ev.match_kind AS event_match_kind, "
    "       s.virtual_sol_reserves, s.virtual_token_reserves, s.real_sol_reserves, "
    "       s.real_token_reserves, s.total_supply, s.complete, s.mcap_sol AS snapshot_mcap_sol, "
    "       s.mayhem_enabled AS snapshot_mayhem_enabled "
    "FROM meme_features_15s f "
    "JOIN meme_tokens t ON t.mint = f.mint "
    "LEFT JOIN meme_curve_snapshots s ON s.mint = f.mint "
    "  AND s.observed_at = f.snapshot_observed_at AND s.source = f.snapshot_source "
    f"LEFT JOIN LATERAL ({_EVENT_MATCH_LATERAL}) ev ON true "
    "WHERE f.as_of > :since AND f.as_of <= :until AND f.features_version = :version "
    "ORDER BY f.as_of, f.mint"
)

_logger = get_logger(__name__)

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
_PEDIGREE = text(
    "SELECT t.mint, "  # noqa: S608 - every interpolation below is this module's own frozen SQL text
    "       CASE WHEN t.creator IS NULL OR t.created_at IS NULL THEN NULL ELSE ("
    "         SELECT count(*) FROM meme_tokens o WHERE o.creator = t.creator "
    "           AND o.mint <> t.mint AND o.created_at IS NOT NULL "
    "           AND o.created_at <= t.created_at "
    "           AND o.created_at > t.created_at - make_interval(secs => :creator_window_s)"
    "       ) END AS creator_prior_mints_1h, "
    "       CASE WHEN t.symbol IS NULL OR t.created_at IS NULL THEN NULL ELSE ("
    "         SELECT count(*) FROM meme_tokens o WHERE o.symbol = t.symbol "
    "           AND o.mint <> t.mint AND o.created_at IS NOT NULL "
    "           AND o.created_at <= t.created_at "
    "           AND o.created_at > t.created_at - make_interval(secs => :symbol_window_s)"
    "       ) END AS symbol_dup_24h, "
    "       CASE WHEN t.creator IS NULL OR t.created_at IS NULL THEN NULL ELSE ("
    f"        {_PRIOR_MINTS}"
    "           AND ("
    "             EXISTS (SELECT 1 FROM meme_features_1m pf WHERE pf.mint = o.mint "
    "                       AND pf.creator_sold = true AND pf.end_time < t.created_at)"
    "             OR EXISTS (SELECT 1 FROM meme_paper_bets pb WHERE pb.mint = o.mint "
    "                          AND pb.rule_set_id <> :probe_rule_set_id "
    "                          AND pb.rule_set_id <> :pullback_rule_set_id "
    "                          AND pb.creator_sold_seen_at IS NOT NULL "
    "                          AND pb.creator_sold_seen_at < t.created_at)"
    "             OR EXISTS (SELECT 1 FROM meme_paper_bets pb2 WHERE pb2.mint = o.mint "
    "                          AND pb2.rule_set_id <> :probe_rule_set_id "
    "                          AND pb2.rule_set_id <> :pullback_rule_set_id "
    "                          AND pb2.exit ->> 'reason' = 'creator_dump' "
    "                          AND pb2.exit_at < t.created_at)"
    "           )"
    "       ) END AS creator_prior_dump_count, "
    "       CASE WHEN t.creator IS NULL OR t.created_at IS NULL THEN NULL ELSE ("
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
    "       ) END AS creator_prior_dead_count "
    "FROM meme_tokens t WHERE t.mint = ANY(:mints)"
)
"""Four correlated counts over ``meme_tokens`` (indexed on ``created_at``; the
tracked set is ~130 mints, the table ~40 k/day). ``NULL`` when the identity
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


async def load_fast_gate_rows(
    session: AsyncSession, *, since: datetime, until: datetime, features_version: str
) -> list[GateRow]:
    """Every 15-second row with ``since < as_of <= until``, as the gate reads it
    (``end_time`` = ``as_of``, ``series = SERIES_15S``) — including, since
    T4.61a, EXP-M13's ``recent_drawdown_*`` folded from the mint's own photos
    (:mod:`hunter_meme_worker.lab_repo_drawdown`, one bounded read per tick)."""
    rows = (
        await session.execute(
            _FAST_ROWS, {"since": since, "until": until, "version": features_version}
        )
    ).mappings()
    out: list[GateRow] = []
    for r in rows:
        snapshot = None
        if r["virtual_sol_reserves"] is not None and r["virtual_token_reserves"] > 0:
            snapshot = snapshot_from_row(
                {
                    **dict(r),
                    "observed_at": r["snapshot_observed_at"],
                    "source": r["snapshot_source"],
                }  # type: ignore[arg-type]
            )
        out.append(
            GateRow(
                mint=str(r["mint"]),
                end_time=r["as_of"],
                created_at=r["created_at"],
                curve_progress_pct=r["curve_progress_pct"],
                progress_reason=r["progress_reason"],
                mcap_sol=r["mcap_sol"],
                creator_sold=r["creator_net_seller"],
                curve_volume_1m_sol=r["curve_volume_60s_sol"],
                completed_at=r["completed_at"],
                migrated_at=r["migrated_at"],
                snapshot=snapshot,
                dev_share=r["dev_share"],
                dev_share_reason=r["dev_share_reason"],
                snipers=r["snipers"],
                net_sol_flow_1m=r["net_sol_flow_60s"],
                mcap_delta_60s=r["mcap_delta_60s"],
                buys_1m=r["buys_60s"],
                sells_1m=r["sells_60s"],
                unique_buyers_1m=r["unique_buyers_60s"],
                tape_reason=r["tape_reason"],
                holders=r["holders"],
                holders_prev=r["holders_prev"],
                holders_rising=r["holders_rising"],
                holders_reason=r["holders_reason"],
                progress_rising=r["progress_rising"],
                computed_at=r["computed_at"],
                tape_as_of=r["tape_as_of"],
                series=SERIES_15S,
                initial_real_token_reserves=r["initial_real_token_reserves"],
                symbol=None if r["symbol"] is None else str(r["symbol"]),
                # T4.27: the token's bit, else the photo's own (a chain read
                # says it before the token row learns it); the state as a witness.
                mayhem_enabled=(
                    r["snapshot_mayhem_enabled"]
                    if r["mayhem_enabled"] is None
                    else r["mayhem_enabled"]
                ),
                mayhem_state=r["mayhem_state"],
                # T4.26: the social identity and the matched event, same join.
                twitter=r["twitter"],
                twitter_kind=r["twitter_kind"],
                twitter_post_at=r["twitter_post_at"],
                twitter_reuse_count=r["twitter_reuse_count"],
                website=r["website"],
                telegram=r["telegram"],
                description=r["description"],
                event_kind=r["event_kind"],
                event_title=r["event_title"],
                event_source=r["event_source"],
                event_confidence=r["event_confidence"],
                event_observed_at=r["event_observed_at"],
                event_match_kind=r["event_match_kind"],
            )
        )
    return await with_recent_drawdown(session, out)


async def pedigree_for(
    session: AsyncSession, mints: Sequence[str], *, gate: PedigreeGate = PEDIGREE_V1
) -> dict[str, PedigreeFeatures]:
    """The two counts of EXP-M6 per mint, from ``meme_tokens`` at this instant."""
    if not mints:
        return {}
    params = {
        "mints": list(mints),
        "creator_window_s": gate.creator_window_s,
        "symbol_window_s": gate.symbol_window_s,
        "prior_window_s": PRIOR_WINDOW_S,
        # T4.85 (EXP-M23): the probe's own paper bets are evidence the desk
        # would never have had — it follows coins the desk REFUSED, so its
        # bets make the creator watcher stamp ``creator_sold_seen_at`` on
        # mints nobody was watching. Counting them here would let the
        # experiment change the real desk's ``creator_repeat_dumper``
        # refusals. Excluded by id, so the desk reads exactly what it read
        # before this arm existed.
        "probe_rule_set_id": PROBE_RULE_SET_ID,
        # T4.91 (EXP-M24): the same for recuo_v1/1 — its bets outlive the desk's
        # shadow on the same mint and could witness a creator sale it never saw.
        "pullback_rule_set_id": PULLBACK_ARM_RULE_SET_ID,
    }
    try:
        async with session.begin_nested():
            await session.execute(text("SET LOCAL statement_timeout = 8000"))
            rows = (await session.execute(_PEDIGREE, params)).mappings().all()
    except DBAPIError as exc:
        # T4.24b: the savepoint rolled back; the tick goes on with the pedigree unread
        # (every gate refuses ``pedigree_unknown`` by name) instead of dying.
        _logger.warning(
            "meme_pedigree_read_failed", mints=len(mints), error=type(exc.orig).__name__
        )
        return {}
    return {
        str(r["mint"]): PedigreeFeatures(
            creator_prior_mints_1h=(
                None if r["creator_prior_mints_1h"] is None else int(r["creator_prior_mints_1h"])
            ),
            symbol_dup_24h=None if r["symbol_dup_24h"] is None else int(r["symbol_dup_24h"]),
            creator_prior_dump_count=(
                None
                if r["creator_prior_dump_count"] is None
                else int(r["creator_prior_dump_count"])
            ),
            creator_prior_dead_count=(
                None
                if r["creator_prior_dead_count"] is None
                else int(r["creator_prior_dead_count"])
            ),
        )
        for r in rows
    }


def fast_window(now: datetime, last: datetime | None, *, backlog_s: int) -> datetime:
    """``since`` for :func:`load_fast_gate_rows`: what this process already
    judged, never further back than ``backlog_s`` (an old instant is not a
    proposal, it is a price that already moved)."""
    floor = now - timedelta(seconds=backlog_s)
    return floor if last is None else max(last, floor)


_INSERT_REFUSAL_TRAIL = text(
    "INSERT INTO meme_gate_refusals_by_mint "
    '(id, as_of, rule_set_id, mint, refusal, value, "limit") '
    "VALUES (gen_random_uuid(), :as_of, CAST(:rule_set_id AS uuid), :mint, :refusal, :value, :limit) "
    "ON CONFLICT (rule_set_id, mint, as_of) DO NOTHING"
)
_PRUNE_REFUSAL_TRAIL = text(
    "WITH doomed AS ("
    "  SELECT id FROM meme_gate_refusals_by_mint WHERE as_of < :cutoff "
    "  ORDER BY as_of LIMIT :batch"
    ") DELETE FROM meme_gate_refusals_by_mint t USING doomed d WHERE t.id = d.id RETURNING t.id"
)


async def insert_refusal_trail(session: AsyncSession, rows: Sequence[RefusalTrailRow]) -> int:
    """One row per near-miss/proposal the fast lane's selection kept
    (:mod:`hunter_meme_worker.gate_refusal_trail`), already capped by the
    caller. ``ON CONFLICT DO NOTHING`` on the same natural key
    (``rule_set_id``, ``mint``, ``as_of``): a restart re-judging the same
    instant writes nothing twice."""
    if not rows:
        return 0
    await session.execute(
        _INSERT_REFUSAL_TRAIL,
        [
            {
                "as_of": row.as_of,
                "rule_set_id": row.rule_set_id,
                "mint": row.mint,
                "refusal": row.refusal,
                "value": row.value,
                "limit": row.limit,
            }
            for row in rows
        ],
    )
    return len(rows)


async def prune_refusal_trail(session: AsyncSession, *, cutoff: datetime, batch: int) -> int:
    """Row-wise retention (7 d, ``docs/DATABASE.md``): the table is small by
    construction (the selector already keeps it so), so a monthly partition
    buys nothing a batched ``DELETE`` does not — the same shape
    ``repo.prune_tokens`` uses for ``meme_tokens``, in ``as_of`` order (its
    own index) so one call never holds the lock over a whole week at once."""
    deleted = (
        (await session.execute(_PRUNE_REFUSAL_TRAIL, {"cutoff": cutoff, "batch": batch}))
        .scalars()
        .all()
    )
    return len(deleted)
