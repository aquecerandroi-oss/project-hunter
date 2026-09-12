"""``/api/v1/orgs/{org_id}/meme/*`` — Meme Radar read payloads (T4.3).

Schema source: ``.claude/state/notes-T4.2.md`` §"contrato" (T4.2,
database-architect, migration ``0021_meme_radar``) — the frozen read model
this task waited for and then built against once it was published. Column
names, nullability and the reason vocabulary below are copied from that
section verbatim; see ``.claude/state/notes-T4.3.md`` for the timeline (this
module briefly held a provisional reconstruction before the contract landed).

Every price/reserve/percentage is ``Decimal``, serialized as a JSON string
(``DecimalStr``, same convention as ``schemas/markets.py``/``schemas/lab_common.py``)
— CLAUDE.md's "money is Decimal" rule extends to on-chain reserves and
percentages here, never a float.

**Null-with-reason, not zero.** The contract's six dependent metrics
(``curve_progress_pct``/``mcap_sol`` on features, plus the four trade/holder
metrics) each carry a sibling ``*_reason`` column, biconditional in the
database (value XOR reason, never both, never neither) — this schema mirrors
that exactly, never collapsing an absence into ``0``/``false``.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, PlainSerializer

from hunter_api.schemas.lab_common import decimal_plain

DecimalStr = Annotated[Decimal, PlainSerializer(decimal_plain, return_type=str, when_used="json")]

MEME_LABEL = "Meme Radar — só monitoramento, nunca execução (pump.fun)"
"""Fixed label repeated on every payload of this router — same convention as
``LAB_LABEL``/``REPLAY_LABEL`` (``schemas/lab_common.py``/``schemas/lab_scoreboard.py``):
the "read-only" nature of this screen is stated in the payload itself, not
only in a doc a client might not render."""

MemeSource = Literal["pumpportal_ws", "pumpfun_rest", "solana_rpc", "trenches_ws"]
"""``meme_tokens.first_seen_source`` / ``meme_curve_snapshots.source`` /
``meme_features_1m.snapshot_source`` — the three producers T4.1's adapter has,
plus ``trenches_ws`` (T4.2c: a mint first seen on the site's ``new``/``graduating``
board, migration ``0023``) —
(contract §1-§2), never a fourth, undeclared source string."""

MemeTokenState = Literal["curve", "completed", "migrated"]
"""Derived, never stored: ``migrated`` (``migrated_at`` set) > ``completed``
(``completed_at`` set, not yet migrated) > ``curve`` (neither timestamp set
yet — includes "never observed", the contract's nullable-timestamp way of
saying "unknown", MUST-FIX 2's concern from the original design review).
Since ``0024`` (T4.2d) ``completed_at`` is the **earliest of the four
completion signals** below, never the REST boolean alone."""

PoolCreatedSource = Literal[
    "pumpportal_ws", "trenches_ws", "indexer_rest:/boards", "indexer_rest:/in-memory-coin"
]
"""Who reported the pool first (``meme_tokens.pool_created_source``, ``0024``)."""

ProgressDenominatorSource = Literal["observed_virgin", "global_params", "mayhem_state", "unknown"]
"""Where ``initial_real_token_reserves`` came from (``0024``/``0025``): a virgin
photo of this curve, the ``/global-params`` record in force at creation, the
same record for a Mayhem curve once its ``MayhemState`` account reconciled on
chain (T4.2e — the agent's own billion, sold net into the curve, is what put
the reserve above the initial), or nowhere yet (``unknown`` renders the
column's ``NULL``; see ``services/meme-worker/…/graduation.py``)."""

NullReason = Literal[
    "no_trade_feed",
    "no_holders_reader",
    "denominator_unknown",
    "not_polled",
    "rate_limited",
    "insufficient_coverage",
    "unsupported_quote",
    "no_sells",
    "out_of_range",
]
"""The contract's frozen vocabulary (§4): "a T4.3 renderiza estes, e só
estes" -- shared by all six ``*_reason`` columns on ``meme_features_1m``."""

MemeTokenSort = Literal["mcap", "age", "progress"]


class OverviewWindowCountOut(BaseModel):
    last_24h: int
    last_7d: int


class OverviewByModeOut(BaseModel):
    """pump.fun's own "auto"/"manual" Mayhem sub-modes, straight from the
    upstream ``/mayhem/overview`` passthrough — **not** the same distinction
    as this API's own ``mayhem_mode`` column (contract §1: ``auto`` \\|
    ``manual`` \\| ``unknown``, "eixo separado do estado"). Only populated
    when ``source == "pumpfun_rest_mayhem_overview"``."""

    auto: OverviewWindowCountOut
    manual: OverviewWindowCountOut


class GraduationsOut(BaseModel):
    """Migrations to PumpSwap in the last 24h, **out of how many tokens this
    radar actually tracks** — the numerator/denominator pair
    (``RateWithCountsOut`` convention, ``schemas/lab_scoreboard.py``) that
    turns a real ``0`` into an honest one: "0 of 0 tracked" (no coverage yet)
    reads differently from "0 of 4,000 tracked" (real, measured zero).
    """

    count: int | None
    tracked_tokens: int
    reason: NullReason | None = None


class GraduationMatrixOut(BaseModel):
    """One Brasília day of ``meme_graduation_matrix_v1`` (``0024``, T4.2d): the
    agreement matrix of the four completion signals over the mints whose
    earliest signal fell on ``day_brt`` — the M-D1/M-D2 diagnostic as a panel.
    ``rest_only_unclassified`` is the "77 of 140": REST said complete, nothing
    else did, and the photo's reserve was zero."""

    day_brt: date
    mints: int
    completed: int
    rest_complete: int
    curve_filled: int
    graduated_board: int
    pool_created: int
    signals_1: int
    signals_2: int
    signals_3: int
    signals_4: int
    disagree_rest_filled: int
    disagree_rest_board: int
    disagree_rest_pool: int
    disagree_filled_board: int
    disagree_filled_pool: int
    disagree_board_pool: int
    rest_only_unclassified: int

    @property
    def disagreeing(self) -> int:
        """The six pair disagreements summed — what the strip turns amber on."""
        return (
            self.disagree_rest_filled
            + self.disagree_rest_board
            + self.disagree_rest_pool
            + self.disagree_filled_board
            + self.disagree_filled_pool
            + self.disagree_board_pool
        )


class MemeOverviewOut(BaseModel):
    """``GET /meme/overview``. Two possible shapes, both real, never a
    fabricated number (brief T4.3):

    - ``source="meme_tokens"``: aggregated from this radar's own stored
      tokens once ``meme_tokens`` has any coverage — ``coins_created_by_mode``
      is then ``None`` (``meme_tokens.mayhem_mode`` is a per-token field, not
      the market-wide auto/manual split ``OverviewByModeOut`` describes).
    - ``source="pumpfun_rest_mayhem_overview"``: a labelled passthrough of the
      free, undocumented ``frontend-api-v3.pump.fun`` ``/mayhem/overview`` —
      used whenever ``meme_tokens`` has no coverage yet (T4.2's collector not
      deployed, or freshly started).
    """

    label: str = MEME_LABEL
    source: Literal["meme_tokens", "pumpfun_rest_mayhem_overview"]
    observed_at: datetime
    coins_created_24h: int | None
    coins_created_7d: int | None
    coins_created_by_mode: OverviewByModeOut | None = None
    mayhem_active_coins: int | None
    graduations_24h: GraduationsOut
    graduation_matrix: GraduationMatrixOut | None = None
    """Today's row (Brasília) of the agreement matrix, when this radar has a
    cohort with any completion signal today; ``None`` on the passthrough shape
    and on a day with no signal yet."""


class MemeTokenOut(BaseModel):
    """One row of ``GET /meme/tokens`` — token identity plus its latest known
    curve reading. ``name``/``symbol``/``creator``/``created_at`` are
    ``None`` when a migration event reached this radar before the token's
    own creation event did (contract §1, a documented T4.1 scenario) —
    ``age_minutes`` is then also ``None`` (unknown creation time, not zero).
    ``snapshot_observed_at``/``snapshot_source`` are ``None`` only when this
    mint has no ``meme_features_1m`` row at all yet."""

    mint: str
    name: str | None
    symbol: str | None
    creator: str | None
    created_at: datetime | None
    age_minutes: int | None
    state: MemeTokenState
    mcap_sol: DecimalStr | None
    curve_progress_pct: DecimalStr | None
    mayhem_enabled: bool | None
    mayhem_state: str | None
    migrated_at: datetime | None
    snapshot_observed_at: datetime | None
    snapshot_source: MemeSource | None
    completed_at: datetime | None = None
    """The earliest of the four signals below (``0024``); ``None`` when none
    classifies — a REST ``complete`` with a zero reserve does not, alone."""
    rest_complete_seen_at: datetime | None = None
    curve_filled_seen_at: datetime | None = None
    graduated_board_seen_at: datetime | None = None
    pool_created_at: datetime | None = None
    pool_created_source: PoolCreatedSource | None = None
    progress_denominator_source: ProgressDenominatorSource = "unknown"


class MemeTokenListOut(BaseModel):
    label: str = MEME_LABEL
    items: list[MemeTokenOut]
    next_cursor: str | None = None


class MemeSnapshotPointOut(BaseModel):
    observed_at: datetime
    source: MemeSource
    virtual_sol_reserves: DecimalStr
    virtual_token_reserves: DecimalStr
    real_sol_reserves: DecimalStr
    real_token_reserves: DecimalStr
    complete: bool
    mcap_sol: DecimalStr | None
    """``NULL`` only when ``virtual_token_reserves = 0`` at that instant
    (contract §2's ``NULLIF`` — a generated column, never hand-computed
    here)."""


class MemeFeaturePointOut(BaseModel):
    """One ``meme_features_1m`` row. Every dependent metric carries its own
    ``*_reason`` sibling — see the module docstring."""

    end_time: datetime
    age_minutes: int | None
    """``None`` only when ``meme_tokens.created_at`` itself is unknown — no
    separate reason column for this one (contract §4: a second copy of the
    same reason would be a second, potentially disagreeing, truth)."""
    curve_progress_pct: DecimalStr | None
    progress_reason: NullReason | None = None
    mcap_sol: DecimalStr | None
    curve_reason: NullReason | None = None
    unique_buyers: int | None
    unique_buyers_reason: NullReason | None = None
    buy_sell_ratio: DecimalStr | None
    buy_sell_ratio_reason: NullReason | None = None
    top10_share: DecimalStr | None
    top10_share_reason: NullReason | None = None
    creator_sold: bool | None
    creator_sold_reason: NullReason | None = None
    coverage: DecimalStr
    """Fraction of the minute actually observed (0..1) — never null."""
    features_version: str


class MemeTokenDetailOut(BaseModel):
    label: str = MEME_LABEL
    token: MemeTokenOut
    snapshots: list[MemeSnapshotPointOut]
    features: list[MemeFeaturePointOut]


class MemeGapOut(BaseModel):
    id: uuid.UUID
    stream: Literal["pumpportal_ws", "curve_poll", "features_1m"]
    mint: str | None
    """``None`` — a gap in the stream itself (e.g. the WS connection), not
    one mint's."""
    gap_start: datetime
    gap_end: datetime
    detected_at: datetime
    reason: str | None
    generation: int | None
    """The WS connection generation this gap belongs to (``ws.py``), when
    ``stream == "pumpportal_ws"`` — ``None`` for the poll-based streams."""
    detail: dict[str, Any] | None
    """Opaque, labelled context (contract §5's ``jsonb`` column) — never a
    field this schema promises a shape for."""


class MemeGapListOut(BaseModel):
    label: str = MEME_LABEL
    items: list[MemeGapOut]
    next_cursor: str | None = None


__all__ = [
    "MEME_LABEL",
    "DecimalStr",
    "GraduationMatrixOut",
    "GraduationsOut",
    "MemeFeaturePointOut",
    "MemeGapListOut",
    "MemeGapOut",
    "MemeOverviewOut",
    "MemeSnapshotPointOut",
    "MemeSource",
    "MemeTokenDetailOut",
    "MemeTokenListOut",
    "MemeTokenOut",
    "MemeTokenSort",
    "MemeTokenState",
    "NullReason",
    "OverviewByModeOut",
    "OverviewWindowCountOut",
    "PoolCreatedSource",
    "ProgressDenominatorSource",
]
