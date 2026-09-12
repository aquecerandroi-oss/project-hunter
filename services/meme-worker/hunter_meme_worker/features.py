"""The per-minute feature math — pure, and honest about what it cannot compute.

One row per tracked mint per closed minute in ``meme_features_1m``
(``docs/DATABASE.md`` §33, §35). Since T4.2c the site's boards and the
``swap-api`` tape fill what T4.2 left ``NULL`` with a reason — and the point of
the reasons has not moved: Astra's MUST-FIX 1 is that an absent trade feed read
as "nobody bought" and an absent holders reader read as "the dev did not sell"
were the gravest error of the original design. A mint the tape has not been
pulled for is still ``no_trade_feed``; a mint no board and no risk read has
spoken about is still ``no_holders_reader``.

| column | today | reason |
|---|---|---|
| ``curve_progress_pct`` | computed when the denominator was observed | ``progress_reason`` |
| ``mcap_sol`` | copied from the minute's snapshot | ``curve_reason`` |
| ``holders``, ``top10_share``, ``dev_share``, ``snipers`` | the newest board/risk reading received by ``end_time`` | ``no_holders_reader`` |
| ``unique_buyers``, ``buy_sell_ratio``, ``buys_1m``… | the tape received by ``end_time`` | ``no_trade_feed`` / ``no_sells`` / ``rate_limited`` / ``unsupported_quote`` / ``not_polled`` (T4.2e: the tape budget did not reach the mint this cycle — the curve's word for the same fact) |
| ``creator_sold``, ``creator_net_seller`` | the creator's trades in the tape covered so far | ``no_trade_feed`` |

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

from hunter_meme_worker.features_tape import (
    NO_SELLS,
    HoldersObservation,
    TapeMinute,
    buy_sell_ratio,
    fraction,
)

FEATURES_VERSION = "meme_features_v2"
"""Frozen protocol name. A different formula is a different version — a different
row by the primary key — never an edit of a minute already cut by a hypothesis.
``0023`` added columns to ``meme_features_v1``: a NULL with a reason in an old
row and a number in a new one is the same protocol with more sources, not a new
formula for a number that already existed. **``meme_features_v2`` (T4.2d) is a
new formula for a number that already existed**: ``curve_progress_pct`` may now
be computed over a denominator taken from the ``/global-params`` record
(``progress_denominator_source = global_params``) instead of only from a virgin
photo. The ``v1`` rows are not rewritten; the series breaks at the deploy and
the Lab reads the version its config names (``lab_repo.load_gate_rows``)."""

NO_TRADE_FEED = "no_trade_feed"
NO_HOLDERS_READER = "no_holders_reader"
DENOMINATOR_UNKNOWN = "denominator_unknown"
NOT_POLLED = "not_polled"
RATE_LIMITED = "rate_limited"
INSUFFICIENT_COVERAGE = "insufficient_coverage"
UNSUPPORTED_QUOTE = "unsupported_quote"
OUT_OF_RANGE = "out_of_range"
"""A source reported a value the column cannot hold (a share above 100 %): the
value is not stored, and this says why instead of a silent NULL."""

REASON_VOCABULARY = frozenset(
    {
        NO_TRADE_FEED,
        NO_HOLDERS_READER,
        DENOMINATOR_UNKNOWN,
        NOT_POLLED,
        RATE_LIMITED,
        INSUFFICIENT_COVERAGE,
        UNSUPPORTED_QUOTE,
        NO_SELLS,
        OUT_OF_RANGE,
    }
)
"""The closed set the API renders (T4.3's acceptance criterion: named states, not
an undifferentiated ``null``). Frozen here and copied into
``.claude/state/notes-T4.2.md`` §contrato; ``no_sells`` is the eighth, added by
``0023`` as an amendment there — a decision, not a string typed at a call site."""

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
    did not reach this mint), ``rate_limited`` (the endpoint refused),
    ``unsupported_quote`` or ``insufficient_coverage``. Never used when
    ``snapshot`` is present."""
    holders: HoldersObservation | None = None
    """The newest board/risk reading with ``received_at <= end_time``
    (``features_tape.holders_for``), or ``None``."""
    tape: TapeMinute | None = None
    """The tape of the minute (``features_tape.tape_for``), or ``None`` when the
    mint's tape had not been pulled by ``end_time``."""
    tape_absence_reason: str = NO_TRADE_FEED
    """Why there is no tape when there is none: ``no_trade_feed`` (never pulled),
    ``rate_limited`` (the pull was refused) or ``unsupported_quote``."""


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
    holders: int | None = None
    holders_reason: str | None = NO_HOLDERS_READER
    holders_observed_at: datetime | None = None
    holders_source: str | None = None
    dev_share: Decimal | None = None
    dev_share_reason: str | None = NO_HOLDERS_READER
    snipers: int | None = None
    snipers_reason: str | None = NO_HOLDERS_READER
    buys_1m: int | None = None
    sells_1m: int | None = None
    net_sol_flow_1m: Decimal | None = None
    curve_volume_1m_sol: Decimal | None = None
    tape_reason: str | None = NO_TRADE_FEED
    creator_net_seller: bool | None = None
    creator_net_seller_reason: str | None = NO_TRADE_FEED


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


def _holders_columns(reading: HoldersObservation | None) -> dict[str, object]:
    """The four holder columns plus their provenance, or their reasons."""
    if reading is None:
        return {}
    top10, top10_reason = share_or_reason(reading.top10_share)
    dev, dev_reason = share_or_reason(reading.dev_share)
    return {
        "holders": reading.holders,
        "holders_reason": None if reading.holders is not None else NO_HOLDERS_READER,
        "holders_observed_at": reading.observed_at if reading.holders is not None else None,
        "holders_source": reading.source if reading.holders is not None else None,
        "top10_share": top10,
        "top10_share_reason": top10_reason,
        "dev_share": dev,
        "dev_share_reason": dev_reason,
        "snipers": reading.snipers,
        "snipers_reason": None if reading.snipers is not None else NO_HOLDERS_READER,
    }


def share_or_reason(value: Decimal | None) -> tuple[Decimal | None, str | None]:
    """A share is a fraction or it is not a share.

    The site's boards report ``t10`` above 100 % in a coin's first minute (the
    plantão measured 18/50 on the ``new`` board at 05:51 BRT on 12/09; production
    folded ``1.002162`` at 10:40Z and ``ck_meme_features_1m_top10_share_is_a_fraction``
    refused the row, which killed the fold loop three times). Clamping would
    invent a number; the honest value is NULL with its own reason.
    """
    if value is None:
        return None, NO_HOLDERS_READER
    share = fraction(value)
    if share is None or share < 0 or share > 1:
        return None, OUT_OF_RANGE
    return share, None


def _tape_columns(tape: TapeMinute | None, absence: str) -> dict[str, object]:
    if tape is None:
        return {
            "unique_buyers_reason": absence,
            "buy_sell_ratio_reason": absence,
            "creator_sold_reason": absence,
            "tape_reason": absence,
            "creator_net_seller_reason": absence,
        }
    ratio = buy_sell_ratio(tape.buys, tape.sells)
    return {
        "unique_buyers": tape.unique_buyers,
        "unique_buyers_reason": None,
        "buy_sell_ratio": ratio,
        "buy_sell_ratio_reason": None if ratio is not None else NO_SELLS,
        "buys_1m": tape.buys,
        "sells_1m": tape.sells,
        "net_sol_flow_1m": tape.net_sol_flow,
        "curve_volume_1m_sol": tape.volume_sol,
        "tape_reason": None,
        "creator_sold": tape.creator_sold,
        "creator_sold_reason": None if tape.creator_sold is not None else NO_TRADE_FEED,
        "creator_net_seller": tape.creator_net_seller,
        "creator_net_seller_reason": None if tape.creator_net_seller is not None else NO_TRADE_FEED,
    }


def build_row(inputs: MinuteInputs, *, features_version: str = FEATURES_VERSION) -> FeatureRow:
    """Fold one minute of one mint. Total: every input shape yields a legal row."""
    snapshot = inputs.snapshot
    curve: dict[str, object]
    if snapshot is None:
        curve = {
            "curve_progress_pct": None,
            "progress_reason": inputs.absence_reason,
            "mcap_sol": None,
            "curve_reason": inputs.absence_reason,
            "coverage": Decimal(0),
            "snapshot_observed_at": None,
            "snapshot_source": None,
        }
    else:
        progress = curve_progress_pct(
            snapshot.real_token_reserves, inputs.initial_real_token_reserves
        )
        mcap = snapshot.mcap_sol
        curve = {
            "curve_progress_pct": progress,
            "progress_reason": None if progress is not None else DENOMINATOR_UNKNOWN,
            "mcap_sol": None if mcap is None else mcap.quantize(_MONEY, rounding=ROUND_HALF_EVEN),
            # A snapshot whose market cap is NULL is a curve the generated column
            # could not price (a zero virtual reserve, §15.8): the observation
            # happened, the number does not exist, and ``insufficient_coverage``
            # is the honest label for the second half of that.
            "curve_reason": None if mcap is not None else INSUFFICIENT_COVERAGE,
            "coverage": Decimal(1),
            "snapshot_observed_at": snapshot.observed_at,
            "snapshot_source": snapshot.source,
        }
    columns: dict[str, object] = {
        "unique_buyers": None,
        "unique_buyers_reason": NO_TRADE_FEED,
        "buy_sell_ratio": None,
        "buy_sell_ratio_reason": NO_TRADE_FEED,
        "top10_share": None,
        "top10_share_reason": NO_HOLDERS_READER,
        "creator_sold": None,
        "creator_sold_reason": NO_TRADE_FEED,
        **curve,
        **_holders_columns(inputs.holders),
        **_tape_columns(inputs.tape, inputs.tape_absence_reason),
    }
    return FeatureRow(
        mint=inputs.mint,
        end_time=inputs.end_time,
        features_version=features_version,
        age_minutes=age_minutes(inputs.end_time, inputs.created_at),
        **columns,  # type: ignore[arg-type]
    )
