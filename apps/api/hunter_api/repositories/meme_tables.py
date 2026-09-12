"""SQLAlchemy Core table metadata for the Meme Radar (T4.3) — read-only.

**Schema source: the frozen contract.** ``.claude/state/notes-T4.2.md``
§"contrato" (T4.2, database-architect, migration ``0021_meme_radar``)
published its read model after this task started; every column below is
copied from that section verbatim, not reconstructed — see
``.claude/state/notes-T4.3.md`` for the timeline (this file briefly held a
provisional reconstruction before the contract landed; it has since been
rewritten to match). Declared on a private :data:`MEME_METADATA` instance
rather than imported from ``hunter_core.db.models`` — that module is T4.2's
to own (``packages/**``, brief T4.3 rule); reconciling this against the real
ORM model (once one exists) is a follow-up, not a contract change.

``meme_trades`` (contract §3) is deliberately **not** declared here: it has
no producer in this slice (the trade feed is paid, the on-chain decoder is
T4.2b) and none of T4.3's endpoints read it — the four dependent columns on
``meme_features_1m`` already carry ``no_trade_feed``/``no_holders_reader``
instead of ever reading an empty table as "zero".
"""

from __future__ import annotations

from sqlalchemy import Boolean, Column, Date, DateTime, Integer, MetaData, Numeric, Table, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

__all__ = [
    "MEME_METADATA",
    "meme_curve_snapshots",
    "meme_features_1m",
    "meme_graduation_matrix_v1",
    "meme_ingest_gaps",
    "meme_radar_features_v1",
    "meme_tokens",
]

MEME_METADATA = MetaData()

meme_tokens = Table(
    "meme_tokens",
    MEME_METADATA,
    Column("mint", Text, primary_key=True),
    Column("name", Text),
    Column("symbol", Text),
    Column("uri", Text),
    Column("creator", Text),
    Column("created_at", DateTime(timezone=True)),
    Column("bonding_curve", Text),
    Column("initial_virtual_sol_reserves", Numeric()),
    Column("initial_virtual_token_reserves", Numeric()),
    Column("initial_real_token_reserves", Numeric()),
    Column("total_supply", Numeric()),
    Column("pool", Text),
    Column("mayhem_enabled", Boolean),
    Column("mayhem_mode", Text),
    Column("mayhem_state", Text),
    Column("completed_at", DateTime(timezone=True)),
    Column("migrated_at", DateTime(timezone=True)),
    Column("migrated_pool", Text),
    Column("first_seen_source", Text, nullable=False),
    Column("first_seen_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    # 0024 (T4.2d): the four completion signals and the denominator's provenance.
    Column("rest_complete_seen_at", DateTime(timezone=True)),
    Column("curve_filled_seen_at", DateTime(timezone=True)),
    Column("graduated_board_seen_at", DateTime(timezone=True)),
    Column("pool_created_at", DateTime(timezone=True)),
    Column("pool_created_source", Text),
    Column("progress_denominator_source", Text),
)

meme_curve_snapshots = Table(
    "meme_curve_snapshots",
    MEME_METADATA,
    Column("observed_at", DateTime(timezone=True), primary_key=True),
    Column("mint", Text, primary_key=True),
    Column("source", Text, primary_key=True),
    Column("received_at", DateTime(timezone=True), nullable=False),
    Column("virtual_sol_reserves", Numeric(), nullable=False),
    Column("virtual_token_reserves", Numeric(), nullable=False),
    Column("real_sol_reserves", Numeric(), nullable=False),
    Column("real_token_reserves", Numeric(), nullable=False),
    Column("total_supply", Numeric(), nullable=False),
    Column("complete", Boolean, nullable=False),
    Column("slot", Integer),
    Column("commitment", Text),
    Column("mayhem_enabled", Boolean),
    Column("mayhem_state", Text),
    Column("mayhem_mode", Text),
    Column("mcap_sol", Numeric()),  # GENERATED ALWAYS column -- read-only from here
)

meme_features_1m = Table(
    "meme_features_1m",
    MEME_METADATA,
    Column("end_time", DateTime(timezone=True), primary_key=True),
    Column("mint", Text, primary_key=True),
    Column("features_version", Text, primary_key=True),
    Column("curve_progress_pct", Numeric()),
    Column("progress_reason", Text),
    Column("mcap_sol", Numeric()),
    Column("curve_reason", Text),
    Column("unique_buyers", Integer),
    Column("unique_buyers_reason", Text),
    Column("buy_sell_ratio", Numeric()),
    Column("buy_sell_ratio_reason", Text),
    Column("top10_share", Numeric()),
    Column("top10_share_reason", Text),
    Column("creator_sold", Boolean),
    Column("creator_sold_reason", Text),
    Column("age_minutes", Integer),
    Column("coverage", Numeric(), nullable=False),
    Column("snapshot_observed_at", DateTime(timezone=True)),
    Column("snapshot_source", Text),
    Column("computed_at", DateTime(timezone=True), nullable=False),
    # 0026 (T4.10) — the drawn lines and the hype.
    Column("mcap_slope_5m", Numeric()),
    Column("mcap_slope_15m", Numeric()),
    Column("high_15m_sol", Numeric()),
    Column("low_15m_sol", Numeric()),
    Column("breakout_15m", Boolean),
    Column("support_line_sol", Numeric()),
    Column("support_line_slope", Numeric()),
    Column("higher_lows", Boolean),
    Column("distance_to_support_pct", Numeric()),
    Column("line_points", Integer),
    Column("line_reason", Text),
    Column("hype_score", Numeric()),
    Column("hype_reason", Text),
)

meme_ingest_gaps = Table(
    "meme_ingest_gaps",
    MEME_METADATA,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("stream", Text, nullable=False),
    Column("mint", Text),
    Column("gap_start", DateTime(timezone=True), nullable=False),
    Column("gap_end", DateTime(timezone=True), nullable=False),
    Column("detected_at", DateTime(timezone=True), nullable=False),
    Column("reason", Text),
    Column("generation", Integer),
    Column("detail", JSONB),
)

meme_radar_features_v1 = Table(
    "meme_radar_features_v1",
    MEME_METADATA,
    Column("mint", Text, primary_key=True),
    Column("end_time", DateTime(timezone=True), primary_key=True),
    Column("features_version", Text),
    Column("curve_progress_pct", Numeric()),
    Column("progress_reason", Text),
    Column("mcap_sol", Numeric()),
    Column("curve_reason", Text),
    Column("unique_buyers", Integer),
    Column("unique_buyers_reason", Text),
    Column("buy_sell_ratio", Numeric()),
    Column("buy_sell_ratio_reason", Text),
    Column("top10_share", Numeric()),
    Column("top10_share_reason", Text),
    Column("creator_sold", Boolean),
    Column("creator_sold_reason", Text),
    Column("age_minutes", Integer),
    Column("coverage", Numeric()),
    Column("snapshot_observed_at", DateTime(timezone=True)),
    Column("snapshot_source", Text),
    Column("name", Text),
    Column("symbol", Text),
    Column("creator", Text),
    Column("token_created_at", DateTime(timezone=True)),
    Column("pool", Text),
    Column("mayhem_enabled", Boolean),
    Column("mayhem_mode", Text),
    Column("mayhem_state", Text),
    Column("completed_at", DateTime(timezone=True)),
    Column("migrated_at", DateTime(timezone=True)),
    Column("migrated_pool", Text),
    Column("first_seen_source", Text),
    Column("last_seen_at", DateTime(timezone=True)),
    # 0024 (T4.2d), appended to the view in this order.
    Column("rest_complete_seen_at", DateTime(timezone=True)),
    Column("curve_filled_seen_at", DateTime(timezone=True)),
    Column("graduated_board_seen_at", DateTime(timezone=True)),
    Column("pool_created_at", DateTime(timezone=True)),
    Column("pool_created_source", Text),
    Column("progress_denominator_source", Text),
)

meme_graduation_matrix_v1 = Table(
    "meme_graduation_matrix_v1",
    MEME_METADATA,
    Column("day_brt", Date, primary_key=True),
    Column("mints", Integer),
    Column("completed", Integer),
    Column("rest_complete", Integer),
    Column("curve_filled", Integer),
    Column("graduated_board", Integer),
    Column("pool_created", Integer),
    Column("signals_1", Integer),
    Column("signals_2", Integer),
    Column("signals_3", Integer),
    Column("signals_4", Integer),
    Column("disagree_rest_filled", Integer),
    Column("disagree_rest_board", Integer),
    Column("disagree_rest_pool", Integer),
    Column("disagree_filled_board", Integer),
    Column("disagree_filled_pool", Integer),
    Column("disagree_board_pool", Integer),
    Column("rest_only_unclassified", Integer),
)
"""``0024`` (T4.2d): the agreement matrix of the four completion signals, one
row per Brasília day of the earliest signal (``docs/DATABASE.md`` §36)."""
