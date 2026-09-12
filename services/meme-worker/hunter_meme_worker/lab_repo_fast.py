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

from hunter_indicators.meme.pedigree import PEDIGREE_V1, PedigreeFeatures, PedigreeGate
from hunter_meme_worker.lab_rows import snapshot_from_row
from hunter_meme_worker.proposals import SERIES_15S, GateRow

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["load_fast_gate_rows", "pedigree_for"]

_FAST_ROWS = text(
    "SELECT f.as_of, f.mint, f.snapshot_observed_at, f.snapshot_source, f.mcap_sol, "
    "       f.mcap_delta_60s, f.curve_progress_pct, f.progress_reason, f.progress_rising, "
    "       f.holders_rising, f.holders_reason, f.buys_60s, f.sells_60s, f.unique_buyers_60s, "
    "       f.net_sol_flow_60s, f.curve_volume_60s_sol, f.tape_reason, f.creator_net_seller, "
    "       f.dev_share, f.dev_share_reason, f.snipers, "
    "       t.created_at, t.completed_at, t.migrated_at, t.initial_real_token_reserves, "
    "       s.virtual_sol_reserves, s.virtual_token_reserves, s.real_sol_reserves, "
    "       s.real_token_reserves, s.total_supply, s.complete, s.mcap_sol AS snapshot_mcap_sol "
    "FROM meme_features_15s f "
    "JOIN meme_tokens t ON t.mint = f.mint "
    "LEFT JOIN meme_curve_snapshots s ON s.mint = f.mint "
    "  AND s.observed_at = f.snapshot_observed_at AND s.source = f.snapshot_source "
    "WHERE f.as_of > :since AND f.as_of <= :until AND f.features_version = :version "
    "ORDER BY f.as_of, f.mint"
)

_PEDIGREE = text(
    "SELECT t.mint, "
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
    "       ) END AS symbol_dup_24h "
    "FROM meme_tokens t WHERE t.mint = ANY(:mints)"
)
"""Two correlated counts over ``meme_tokens`` (indexed on ``created_at``; the
tracked set is ~130 mints, the table ~40 k/day). ``NULL`` when the identity
is unknown — the gate refuses that by name, never reads it as zero."""


async def load_fast_gate_rows(
    session: AsyncSession, *, since: datetime, until: datetime, features_version: str
) -> list[GateRow]:
    """Every 15-second row with ``since < as_of <= until``, as the gate reads it
    (``end_time`` = ``as_of``, ``series = SERIES_15S``)."""
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
                holders_rising=r["holders_rising"],
                holders_reason=r["holders_reason"],
                progress_rising=r["progress_rising"],
                series=SERIES_15S,
            )
        )
    return out


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
    }
    return {
        str(r["mint"]): PedigreeFeatures(
            creator_prior_mints_1h=(
                None if r["creator_prior_mints_1h"] is None else int(r["creator_prior_mints_1h"])
            ),
            symbol_dup_24h=None if r["symbol_dup_24h"] is None else int(r["symbol_dup_24h"]),
        )
        for r in (await session.execute(_PEDIGREE, params)).mappings()
    }


def fast_window(now: datetime, last: datetime | None, *, backlog_s: int) -> datetime:
    """``since`` for :func:`load_fast_gate_rows`: what this process already
    judged, never further back than ``backlog_s`` (an old instant is not a
    proposal, it is a price that already moved)."""
    floor = now - timedelta(seconds=backlog_s)
    return floor if last is None else max(last, floor)
