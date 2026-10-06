"""The T4.16 reads of the Lab loop — as ``hunter_worker``, never as owner
(``lab_repo.py``'s discipline): the rows of the 15-second series a gate has
not judged yet, and the pedigree of a mint at proposal time (EXP-M6).

**Non-anticipation in SQL**, twice: a 15-second row is read only when its
``as_of`` is at or before the tick (``as_of <= :until``) — the producer
already bounded its inputs by ``received_at <= as_of`` — and the pedigree
counts only coins created **at or before** the coin judged (a launch that
came later is not a prior mint).

The pedigree read itself lives in :mod:`hunter_meme_worker.lab_repo_pedigree` (EXP-M26 F, 350-line
budget); ``pedigree_for``, ``_PEDIGREE`` and ``PRIOR_WINDOW_S`` stay importable from here.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_meme_worker.gate_refusal_trail import RefusalTrailRow
from hunter_meme_worker.lab_repo_drawdown import with_recent_drawdown
from hunter_meme_worker.lab_repo_pedigree import (
    _PEDIGREE as _PEDIGREE,  # pyright: ignore[reportPrivateUsage]  # re-export: tests name it here
)
from hunter_meme_worker.lab_repo_pedigree import PRIOR_WINDOW_S as PRIOR_WINDOW_S
from hunter_meme_worker.lab_repo_pedigree import pedigree_for
from hunter_meme_worker.lab_rows import snapshot_from_row
from hunter_meme_worker.proposals import SERIES_15S, GateRow

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
    "SELECT f.as_of, f.mint, f.snapshot_observed_at, f.snapshot_source, f.mcap_sol, "  # noqa: S608  # nosec B608 -- identifiers and fragments are module-level constants, never an argument or a row; values are bound parameters
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
