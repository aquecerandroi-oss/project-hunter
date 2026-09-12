"""``GET /api/v1/orgs/{org_id}/meme/sources`` — every source of the meme radar,
as the worker reports it and as the database shows it (T4.2c).

Two witnesses per source, both named: the worker's heartbeat (``hb:meme:radar``,
the ``sources`` JSON field the worker writes every 15 s) and the newest row
each source left in its table. **Never a silent zero**: a source that is off
says ``disabled``, one that never spoke says ``never_observed``, a heartbeat that
is missing or stale says so in ``radar_status``, and a table with no rows says
``no_rows`` — each an explicit ``reason`` next to a ``null``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

__all__ = [
    "COVERAGE_EXPLANATION",
    "DISCOVERY_BLIND_EXPLANATION",
    "MEME_SOURCES_LABEL",
    "MemeSourceOut",
    "MemeSourcesOut",
    "RadarStatus",
    "SourceStatus",
]

MEME_SOURCES_LABEL = "Meme Radar — fontes de dados; só monitoramento, nunca execução (pump.fun)"

DISCOVERY_BLIND_EXPLANATION = (
    "programa fora do escopo do adaptador: a descoberta ouve só o programa pump "
    "(PumpPortal subscribeNewToken + boards new/graduating com pg = pump); entradas do "
    "board new em raydium_launchpad/StonkFun e afins são invisíveis por construção e não "
    "são rastreadas — a fração declara o tamanho da cegueira, não a corrige"
)
"""The declared blindness (T4.2d, item 3). Fixed text: the reason is structural."""

COVERAGE_EXPLANATION = (
    "cobertura do último minuto dobrado: linhas com progresso ÷ linhas e linhas com fita ÷ "
    "linhas; uma linha sem fita diz o motivo em tape_reason (no_trade_feed = nunca puxada, "
    "not_polled = o orçamento da fita não a alcançou no ciclo, rate_limited = a fonte recusou); "
    "uma linha sem progresso diz progress_reason (denominator_unknown = Mayhem ainda sem a "
    "leitura on-chain de MayhemState, mayhem_pending conta quantas); desde a T4.2f a curva de "
    "todos os rastreados vem da cadeia uma vez por minuto (chain_read_mints ÷ chain_tracked_mints) "
    "e a fita é limitada pela regra do Cloudflare do swap-api (~20 req/60 s por IP, medida — "
    "swap_api_effective_budget_60s é o orçamento em vigor), não pelo x-ratelimit-limit de 1000; "
    "desde a T4.2g a fita por lote (POST market-activity/batch, 50 moedas por requisição, "
    "activity_batch_calls_60s dentro do mesmo orçamento) preenche buys/sells/compradores do "
    "minuto quando a fita por mint não cobriu (tape_source = activity_1m; tape_activity_pct é a "
    "fração das linhas que vieram do lote; activity_dark_60s conta moedas cuja janela 1m veio "
    "nula num ciclo em que ninguém a teve preenchida — nada é escrito como zero nesse caso; "
    "no_sol_quote = o lote falou em USD e não havia cotação SOL/USD com menos de 5 min)"
)
"""T4.2e/T4.2f/T4.2g: what the coverage numbers are and where the missing rows explain themselves."""

RadarStatus = Literal["alive", "stale", "never", "heartbeat_missing", "redis_unavailable"]
"""The worker's own heartbeat fields: ``alive`` when ``sources_at`` is fresh,
``stale`` when older than ``stalled_after_s``, ``never`` when the runtime
heartbeat exists but the radar never wrote its fields."""

SourceStatus = Literal["connected", "disconnected", "ok", "erroring", "disabled", "unknown"]
"""Per source. Socket sources are ``connected``/``disconnected``; request
sources are ``ok`` (a recent observation) or ``erroring`` (errors in the last
hour and nothing observed since); ``disabled`` by switch; ``unknown`` when the
heartbeat carries nothing about the source."""


class MemeSourceOut(BaseModel):
    name: str
    status: SourceStatus
    enabled: bool | None
    connected: bool | None
    last_observed_at: datetime | None
    last_received_at: datetime | None
    lag_s: float | None
    """``received_at − observed_at`` of the newest observation: how far behind
    the source's own clock ours is."""
    age_s: float | None
    """Seconds since the newest observation reached the worker (as of ``as_of``)."""
    used_60s: int | None
    budget_60s: int | None
    errors_1h: int | None
    last_error: str | None
    last_error_at: datetime | None
    reason: str | None
    """Why there is no observation: ``disabled`` | ``never_observed`` |
    ``heartbeat_missing`` — the worker's word, never inferred here."""
    table: str | None
    last_row_observed_at: datetime | None
    """The newest row the source left in ``table`` — the database's witness."""
    row_reason: str | None
    """``no_rows`` when the table has none, ``no_table`` when the source
    writes no table of its own."""


class MemeSourcesOut(BaseModel):
    label: str = MEME_SOURCES_LABEL
    as_of: datetime
    heartbeat_key: str
    heartbeat_ts: datetime | None
    heartbeat_age_s: int | None
    radar_status: RadarStatus
    radar_reason: str | None
    sources_at: datetime | None
    stalled_after_s: int
    tracked: int | None
    budget_used_60s: int | None
    budget_60s: int | None
    gaps_60s: int | None
    ws_malformed_60s: int | None
    last_snapshot_observed_at: datetime | None
    lag_s: float | None
    trenches_connected: bool | None
    trenches_patches_60s: int | None
    swap_api_used_60s: int | None
    swap_api_budget_60s: int | None
    discovery_blind_share_1h: float | None = None
    """Share of the ``new`` board's listings in the last hour whose program is
    not ``pump`` (``blind_share_1h`` of the heartbeat). ``None`` when the board
    listed nothing in the hour, or when the worker predates T4.2d."""
    discovery_new_board_entries_1h: int | None = None
    discovery_non_pump_entries_1h: int | None = None
    discovery_blind_explanation: str = DISCOVERY_BLIND_EXPLANATION
    progress_coverage_pct: float | None = None
    """T4.2e: rows of the last folded minute with a ``curve_progress_pct`` over
    its rows (heartbeat ``progress_coverage_pct``). ``None`` before the first
    fold, on an empty minute, or from a worker that predates T4.2e."""
    tape_coverage_pct: float | None = None
    """Rows of the last folded minute with a tape over its rows."""
    fold_minute: datetime | None = None
    fold_rows: int | None = None
    tape_tracked_mints: int | None = None
    tape_covered_mints: int | None = None
    tape_never_pulled: int | None = None
    tape_cycle_s: float | None = None
    """How long the last tape cycle took: the T4.2c sequential puller needed
    ~90 s for 250 mints, which is why 109 of 250 rows had no tape."""
    tape_deferred_60s: int | None = None
    """Due mints the tape cap left out in the last minute (``not_polled``)."""
    mayhem_pending: int | None = None
    """Tracked Mayhem mints still without a denominator (the loop reads 25 a minute)."""
    mayhem_denominators_60s: int | None = None
    chain_cycle_s: float | None = None
    """T4.2f: the chain loop's last cycle — every tracked curve from the chain
    once a minute (``getMultipleAccounts``, 100 per call). ``None`` before the
    first cycle or from a worker that predates T4.2f."""
    chain_tracked_mints: int | None = None
    chain_read_mints: int | None = None
    """How many of the tracked mints the last cycle photographed; the rest are
    refused by name (``chain_refused_1h``: not SOL-quoted, emptied, not found)."""
    chain_calls_60s: int | None = None
    chain_refused_1h: int | None = None
    swap_api_effective_budget_60s: int | None = None
    """The tape budget in force: the configured value, or 80 % of what
    succeeded before the last real 429 (Cloudflare's ~20/60 s per IP)."""
    swap_api_measured_60s: int | None = None
    swap_api_429_1h: int | None = None
    swap_api_blocked_until: datetime | None = None
    fast_lane_mints: int | None = None
    """T4.16: young mints (< 5 min, known birth) the 15-second chain clock read
    in its last cycle; ``None`` from a worker that predates T4.16 or whose
    last read failed."""
    fast_lane_reads_60s: int | None = None
    fast_lane_calls_60s: int | None = None
    fast_lane_cycle_s: float | None = None
    lab_decision_to_fill_s_p50: int | None = None
    """T4.16: the **measured** decision → fill latency (seconds) over the last
    fills the Lab made — nearest-rank median; ``None`` before the first fill."""
    lab_decision_to_fill_s_p95: int | None = None
    lab_decision_to_fill_n: int | None = None
    lab_bets_indeterminate_total: int | None = None
    """T4.16: bets closed without a photo to price them (``outcome_quality =
    indeterminate``), from the rows — left out of every sum of R/PnL."""
    tape_activity_pct: float | None = None
    """T4.2g: rows of the last folded minute whose tape came from the batch
    route (``tape_source = activity_1m``) over its rows; ``tape_coverage_pct``
    counts both sources. ``None`` from a worker that predates T4.2g."""
    activity_coverage_pct: float | None = None
    """Coins with a ``1m`` reading (a number or a stated zero) over the coins
    the batch loop asked for in its last cycle."""
    activity_mints: int | None = None
    activity_covered: int | None = None
    activity_live_1m: int | None = None
    """Coins the route filled ``1m`` for (non-null) in the last cycle: the
    proof the window is computed; ``0`` with ``activity_dark_60s > 0`` means
    the route answered ``null`` for everyone and nothing was written as a zero."""
    activity_batch_calls_60s: int | None = None
    activity_dark_60s: int | None = None
    activity_skipped_60s: int | None = None
    """Cycles the loop skipped in the last minute because the edge's block was in force."""
    activity_cycle_s: float | None = None
    activity_quote_age_s: float | None = None
    """Age of the SOL/USD quote the batch's USD was turned into SOL with."""
    coverage_explanation: str = COVERAGE_EXPLANATION
    sources: list[MemeSourceOut]
