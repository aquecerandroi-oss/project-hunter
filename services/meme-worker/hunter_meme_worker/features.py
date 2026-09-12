"""The per-minute feature math — pure, and honest about what it cannot compute.

One row per tracked mint per closed minute in ``meme_features_1m``
(``docs/DATABASE.md`` §33). Four of the columns the plan wanted are **NULL with a
reason in every row this slice writes**, and that is the point rather than a
shortfall: Astra's MUST-FIX 1 is that an absent trade feed read as "nobody bought"
and an absent holders reader read as "the dev did not sell" were the gravest error
of the original design.

| column | today | reason |
|---|---|---|
| ``curve_progress_pct`` | computed when the denominator was observed | ``progress_reason`` |
| ``mcap_sol`` | copied from the minute's snapshot | ``curve_reason`` |
| ``unique_buyers``, ``buy_sell_ratio`` | never | ``no_trade_feed`` — the channel is paid, the decoder is T4.2b |
| ``top10_share``, ``creator_sold`` | never | ``no_holders_reader`` — nothing reads holders yet |

Nothing here clamps a strange number into a plausible one. ``curve_progress_pct``
is stored as computed even if it falls outside ``[0, 1]``: DATABASE.md §15.8 keeps
market-data tables free of domain CHECKs on purpose, because "a feed occasionally
emits a zero, and a CHECK there turns strange data into an ingestion failure" —
and a progress of 1.2 is a visible bug in a reserve, while a silently clamped 1.0
is a lie that looks like a graduation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal

FEATURES_VERSION = "meme_features_v1"
"""Frozen protocol name. A different formula is a different version — a different
row by the primary key — never an edit of a minute already cut by a hypothesis."""

NO_TRADE_FEED = "no_trade_feed"
NO_HOLDERS_READER = "no_holders_reader"
DENOMINATOR_UNKNOWN = "denominator_unknown"
NOT_POLLED = "not_polled"
RATE_LIMITED = "rate_limited"
INSUFFICIENT_COVERAGE = "insufficient_coverage"
UNSUPPORTED_QUOTE = "unsupported_quote"

REASON_VOCABULARY = frozenset(
    {
        NO_TRADE_FEED,
        NO_HOLDERS_READER,
        DENOMINATOR_UNKNOWN,
        NOT_POLLED,
        RATE_LIMITED,
        INSUFFICIENT_COVERAGE,
        UNSUPPORTED_QUOTE,
    }
)
"""The closed set the API renders (T4.3's acceptance criterion: named states, not
an undifferentiated ``null``). Frozen here and copied into
``.claude/state/notes-T4.2.md`` §contrato; a seventh reason is a decision, not a
string somebody types at a call site."""

_FRACTION = Decimal("0.000001")
"""``NUMERIC(9,6)``'s own scale: quantizing here means the value a test reads back
from Postgres equals the value this module produced, byte for byte."""

_MONEY = Decimal("0.0000000001")


@dataclass(frozen=True, slots=True)
class CurveObservation:
    """The one snapshot a minute is folded from (the newest inside the minute)."""

    observed_at: datetime
    source: str
    real_token_reserves: Decimal
    mcap_sol: Decimal | None
    complete: bool


@dataclass(frozen=True, slots=True)
class MinuteInputs:
    """Everything the fold is allowed to look at."""

    mint: str
    end_time: datetime
    created_at: datetime | None
    initial_real_token_reserves: Decimal | None
    snapshot: CurveObservation | None
    absence_reason: str = NOT_POLLED
    """Why there is no snapshot, when there is none: ``not_polled`` (the budget
    did not reach this mint), ``rate_limited`` (the endpoint refused) or
    ``insufficient_coverage``. Never used when ``snapshot`` is present."""


@dataclass(frozen=True, slots=True)
class FeatureRow:
    """One row of ``meme_features_1m``, ready to insert. Every value/reason pair
    is exclusive by construction here *and* by CHECK in the database."""

    mint: str
    end_time: datetime
    features_version: str
    curve_progress_pct: Decimal | None
    progress_reason: str | None
    mcap_sol: Decimal | None
    curve_reason: str | None
    unique_buyers: int | None
    unique_buyers_reason: str | None
    buy_sell_ratio: Decimal | None
    buy_sell_ratio_reason: str | None
    top10_share: Decimal | None
    top10_share_reason: str | None
    creator_sold: bool | None
    creator_sold_reason: str | None
    age_minutes: int | None
    coverage: Decimal
    snapshot_observed_at: datetime | None
    snapshot_source: str | None


def curve_progress_pct(
    real_token_reserves: Decimal, initial_real_token_reserves: Decimal | None
) -> Decimal | None:
    """``1 - real/initial`` as a fraction, or ``None`` when the denominator is unknown.

    The denominator is the **observed** initial real token reserve
    (T4-MEME-RADAR.md §3, Astra's correction), never the 793,1 M constant every
    blog quotes and never ``real_sol_reserves`` over a SOL threshold — that
    threshold is not a confirmed universal and must not become a constant.
    """
    if initial_real_token_reserves is None or initial_real_token_reserves == 0:
        return None
    progress = Decimal(1) - (real_token_reserves / initial_real_token_reserves)
    return progress.quantize(_FRACTION, rounding=ROUND_HALF_EVEN)


def age_minutes(end_time: datetime, created_at: datetime | None) -> int | None:
    """Whole minutes from creation to the minute's close.

    ``None`` when the creation time is unobserved **and** when it is in the future
    of the minute being folded: a negative age is not a fact about a token, it is a
    clock disagreeing with itself, and the schema would refuse it
    (``ck_meme_features_1m_age_is_not_negative``). Refusing to invent it here is
    what keeps that CHECK from ever aborting a collector cycle.
    """
    if created_at is None or created_at > end_time:
        return None
    return int((end_time - created_at).total_seconds() // 60)


def build_row(inputs: MinuteInputs, *, features_version: str = FEATURES_VERSION) -> FeatureRow:
    """Fold one minute of one mint. Total: every input shape yields a legal row."""
    snapshot = inputs.snapshot
    if snapshot is None:
        return FeatureRow(
            mint=inputs.mint,
            end_time=inputs.end_time,
            features_version=features_version,
            curve_progress_pct=None,
            progress_reason=inputs.absence_reason,
            mcap_sol=None,
            curve_reason=inputs.absence_reason,
            unique_buyers=None,
            unique_buyers_reason=NO_TRADE_FEED,
            buy_sell_ratio=None,
            buy_sell_ratio_reason=NO_TRADE_FEED,
            top10_share=None,
            top10_share_reason=NO_HOLDERS_READER,
            creator_sold=None,
            creator_sold_reason=NO_HOLDERS_READER,
            age_minutes=age_minutes(inputs.end_time, inputs.created_at),
            coverage=Decimal(0),
            snapshot_observed_at=None,
            snapshot_source=None,
        )

    progress = curve_progress_pct(snapshot.real_token_reserves, inputs.initial_real_token_reserves)
    mcap = snapshot.mcap_sol
    return FeatureRow(
        mint=inputs.mint,
        end_time=inputs.end_time,
        features_version=features_version,
        curve_progress_pct=progress,
        progress_reason=None if progress is not None else DENOMINATOR_UNKNOWN,
        mcap_sol=None if mcap is None else mcap.quantize(_MONEY, rounding=ROUND_HALF_EVEN),
        # A snapshot whose market cap is NULL is a curve the generated column
        # could not price (a zero virtual reserve, §15.8): the observation
        # happened, the number does not exist, and ``insufficient_coverage`` is
        # the honest label for the second half of that.
        curve_reason=None if mcap is not None else INSUFFICIENT_COVERAGE,
        unique_buyers=None,
        unique_buyers_reason=NO_TRADE_FEED,
        buy_sell_ratio=None,
        buy_sell_ratio_reason=NO_TRADE_FEED,
        top10_share=None,
        top10_share_reason=NO_HOLDERS_READER,
        creator_sold=None,
        creator_sold_reason=NO_HOLDERS_READER,
        age_minutes=age_minutes(inputs.end_time, inputs.created_at),
        coverage=Decimal(1),
        snapshot_observed_at=snapshot.observed_at,
        snapshot_source=snapshot.source,
    )
