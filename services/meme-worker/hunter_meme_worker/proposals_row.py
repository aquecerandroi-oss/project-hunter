"""``GateRow`` — one judged instant (a closed minute or a 15-second photo),
split out of ``proposals.py`` for the 350-line budget (T4.26, the cut
``repo_rows.py`` took from ``repo.py``). Re-exported from ``proposals.py``,
so every caller still imports from there.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hunter_meme_worker.lab_values import Snapshot


@dataclass(frozen=True, slots=True)
class GateRow:
    """One ``meme_features_1m`` row joined with its token and its snapshot."""

    mint: str
    end_time: datetime
    created_at: datetime | None
    curve_progress_pct: Decimal | None
    """A fraction, as T4.2 stores it; ``None`` with ``progress_reason``."""
    progress_reason: str | None
    mcap_sol: Decimal | None
    creator_sold: bool | None
    curve_volume_1m_sol: Decimal | None
    """No producer today (``no_trade_feed``); the column is here so the day a
    trade feed lands the gate needs no change."""
    completed_at: datetime | None
    migrated_at: datetime | None
    snapshot: Snapshot | None
    """The snapshot the minute was folded from (``snapshot_observed_at``)."""
    higher_lows: bool | None = None
    breakout_15m: bool | None = None
    distance_to_support_pct: Decimal | None = None
    line_reason: str | None = None
    hype_score: Decimal | None = None
    hype_reason: str | None = None
    dev_share: Decimal | None = None
    dev_share_reason: str | None = None
    snipers: int | None = None
    """T4.10 (``0026``): the line and the hype of the minute — read by the
    EXP-M2/EXP-M3 gates, ignored by a gate that does not ask."""
    net_sol_flow_1m: Decimal | None = None
    mcap_delta_60s: Decimal | None = None
    buys_1m: int | None = None
    sells_1m: int | None = None
    unique_buyers_1m: int | None = None
    tape_reason: str | None = None
    holders_rising: bool | None = None
    holders_reason: str | None = None
    progress_rising: bool | None = None
    holders: int | None = None
    holders_prev: int | None = None
    top10_share: Decimal | None = None
    top10_reason: str | None = None
    """T4.21: the two holders readings behind ``holders_rising`` (arm 2's floor and 'not falling')."""
    """T4.16: the flow of the minute (or of the last 60 s on the 15-second
    series) and the two trends — read by the EXP-M5 gate."""
    series: str | None = None
    """``None`` for a closed minute of ``meme_features_1m``; ``SERIES_15S`` for
    a row of the 15-second series, where ``end_time`` is the instant judged."""
    symbol: str | None = None
    """T4.19: the token's ticker, named in the operator's ``manual_plan``;
    ``None`` (identity never came) reads as the mint abbreviated."""
    mayhem_enabled: bool | None = None
    mayhem_state: str | None = None
    """T4.27: ``meme_tokens.mayhem_enabled`` / ``mayhem_state`` — the gate's
    ``is_mayhem`` (``executable.is_mayhem_curve``); ``None`` refuses by name."""

    # --- T4.26: the social identity and the matched event -----------------------
    twitter: str | None = None
    twitter_kind: str | None = None
    twitter_post_at: datetime | None = None
    twitter_reuse_count: int | None = None
    website: str | None = None
    telegram: str | None = None
    description: str | None = None
    """``meme_tokens``'s own social columns (``0041``), read from the same
    join every other identity field already comes through — no new query."""
    event_kind: str | None = None
    event_title: str | None = None
    event_source: str | None = None
    event_confidence: str | None = None
    event_observed_at: datetime | None = None
    event_match_kind: str | None = None
    """T4.26b: ``"buy"``/``"avoid"``, from ``meme_event_matches``. The earliest
    ``meme_events`` row matched to this mint (``0041``,
    ``events.py``'s per-minute job), if any — ``None`` for the overwhelming
    majority of rows judged."""

    initial_real_token_reserves: Decimal | None = None
    """T4.52b-3: ``meme_tokens.initial_real_token_reserves`` — the launch
    denominator the event gate needs to fold ``curve_progress_pct`` itself
    (``hunter_indicators.meme.fast.compute_fast``) over the in-memory series;
    unused by the closed-minute/15-second gate, which already reads a
    precomputed ``curve_progress_pct`` column."""
    recent_drawdown_pct: Decimal | None = None
    recent_drawdown_peak_age_s: Decimal | None = None
    recent_drawdown_reason: str | None = None
    """T4.52b-3 (EXP-M13): :func:`hunter_indicators.meme.drawdown.recent_drawdown`
    over the mint's in-memory reserve series on the event lane, and — since
    T4.61a — over the mint's stored photos on the 15-second lane
    (``lab_repo_drawdown``, one bounded read per tick). ``None`` on a
    closed-minute row, which is exactly ``recent_drawdown_unknown`` for a set
    that turns the guard on."""
    early_retention_pct: Decimal | None = None
    early_age_s: Decimal | None = None
    new_wallets_30s: int | None = None
    quick_flip_share_30s: Decimal | None = None
    """T4.66 (EXP-M19): :class:`hunter_indicators.meme.crowd.CrowdFeatures`,
    filled by the event lane only (``event_gate_rows.build_event_row``); the
    15-second and closed-minute rows leave them ``None`` — ``*_unknown`` for a
    set that asks, fail closed."""


__all__ = ["GateRow"]
