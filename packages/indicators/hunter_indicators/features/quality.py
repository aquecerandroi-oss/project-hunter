"""The freshness policy: how old an input may be before a feature is degraded.

Versioned (``quality_v1``) and stored next to every vector, because it is a
**policy**, not a fact: changing a budget changes which snapshots were degraded
and must be traceable.

Two things this deliberately does not do:

- it does not reuse the hot-state TTLs as budgets. A TTL is how long Redis keeps
  a key; freshness is how old an observation may be and still describe the
  market. They coincide today by construction, not by definition (Astra, T2.2
  design review, 2a);
- it does not judge the whole vector by its worst input. Each input is judged on
  its own function, and each feature only inherits the quality of the inputs it
  actually used — a warming-up funding history must not degrade a perfectly good
  return.

The minute feed is judged against the minute close a healthy feed would already
have printed (``expected_last_close``), not against a blanket age: at 12:14 an
ATR built on the 15-minute bar that closed at 12:00 is still the current closed
bar, and it is the *1-minute* feed behind it that has to be fresh.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType

from hunter_core.strategies.canonical import canonical_json
from hunter_indicators.features.atr import AtrAdvance, last_bar_close
from hunter_indicators.features.context import (
    INPUT_ATR_STATE,
    INPUT_BOOK,
    INPUT_CANDLES,
    INPUT_DERIV_HISTORY,
    INPUT_FORMING,
    INPUT_FUNDING,
    INPUT_MARK,
    INPUT_OI,
    INPUT_TRADES,
    MISSING_INPUT,
    MarketContext,
    SourceEntry,
    expected_last_close,
    seconds_between,
)
from hunter_indicators.features.hotstate import AFTER_CUT, CORRUPT, CROSSED, EMPTY
from hunter_indicators.features.vector import InputProvenance, Quality, Reason
from hunter_indicators.features.windows import bars_15m

QUALITY_POLICY_VERSION = "quality_v1"
"""Bump with any change to :class:`FreshnessPolicy`'s defaults or rules."""

_SOURCE_REASONS: Mapping[str, Reason] = MappingProxyType(
    {
        MISSING_INPUT: Reason.MISSING_INPUT,
        EMPTY: Reason.MISSING_INPUT,
        AFTER_CUT: Reason.AFTER_CUT,
        CORRUPT: Reason.CORRUPT_INPUT,
        CROSSED: Reason.CORRUPT_INPUT,
    }
)


def source_reason(reason: str | None) -> Reason:
    """Why a refused :class:`SourceEntry` is refused, in the feature vocabulary.

    The loader's verdict must survive to the sample: a crossed book that arrives
    as ``missing_input`` is indistinguishable from Redis having no book at all,
    and the operator reading the envelope cannot tell an outage from a broken
    decode (Astra, fix-pass review, must-fix 2). A spelling this table does not
    know falls back to ``missing_input`` — the value is genuinely absent — and
    adding a refusal to the loader means adding it here.
    """
    return _SOURCE_REASONS.get(reason or MISSING_INPUT, Reason.MISSING_INPUT)


@dataclass(frozen=True, slots=True)
class FreshnessPolicy:
    """Per-input budgets, in seconds. Defaults are declared assumptions.

    ``candle_lag_grace_s = 60`` — one whole extra minute late before the 1m feed
    is called stale (a candle that closes at 12:10 is normally in Redis within
    milliseconds; missing *two* closes is a real symptom).
    ``book_max_age_s = 10`` — the depth stream pushes every 250 ms.
    ``mark/funding_max_age_s = 120`` — ``markPrice`` pushes every 1–3 s.
    ``oi_max_age_s = 600`` — open interest is polled every 5 min (PIPELINE §1.5),
    so 600 s is two polls, not one.
    """

    candle_lag_grace_s: int = 60
    forming_max_age_s: int = 30
    book_max_age_s: int = 10
    funding_max_age_s: int = 120
    mark_max_age_s: int = 120
    oi_max_age_s: int = 600

    @property
    def identity(self) -> str:
        """What the vector publishes: ``quality_v1``, or a suffixed variant.

        An overridden budget must not travel under the identity of the default
        policy — a 45-second book that a caller declared acceptable would
        otherwise look like the same rule that calls it degraded (Astra, T2.2
        diff review, nice-to-have).
        """
        if self == FreshnessPolicy():
            return QUALITY_POLICY_VERSION
        digest = hashlib.sha256(canonical_json(asdict(self))).hexdigest()[:12]
        return f"{QUALITY_POLICY_VERSION}+{digest}"


def _age(as_of: datetime, ts: datetime | None) -> Decimal | None:
    """Exact seconds, never a float (``context.seconds_between``)."""
    return None if ts is None else seconds_between(ts, as_of)


def _timed(
    input_name: str,
    as_of: datetime,
    ts: datetime | None,
    budget: int,
    absent: Reason = Reason.MISSING_INPUT,
    **extra: object,
) -> InputProvenance:
    """Provenance of a single timestamped observation against its budget."""
    if ts is None:
        return InputProvenance(
            input=input_name,
            available=False,
            quality=Quality.UNAVAILABLE,
            reason=absent,
            **extra,  # type: ignore[arg-type]
        )
    age = _age(as_of, ts)
    stale = age is not None and age > budget
    return InputProvenance(
        input=input_name,
        available=True,
        quality=Quality.DEGRADED if stale else Quality.OK,
        reason=Reason.STALE_INPUT if stale else None,
        ts=ts,
        age_s=age,
        **extra,  # type: ignore[arg-type]
    )


def _candles(ctx: MarketContext, policy: FreshnessPolicy) -> InputProvenance:
    last = ctx.last_final
    if last is None:
        return InputProvenance(
            input=INPUT_CANDLES,
            available=False,
            quality=Quality.UNAVAILABLE,
            reason=Reason.MISSING_INPUT,
        )
    lag = expected_last_close(ctx.as_of) - last.close_time
    late = lag.total_seconds() > policy.candle_lag_grace_s
    return InputProvenance(
        input=INPUT_CANDLES,
        available=True,
        quality=Quality.DEGRADED if late else Quality.OK,
        reason=Reason.STALE_INPUT if late else None,
        ts=last.close_time,
        age_s=_age(ctx.as_of, last.close_time),
        covers_from=ctx.final_candles[0].open_time,
        truncated=ctx.candles_truncated,
    )


def _forming(ctx: MarketContext, policy: FreshnessPolicy) -> InputProvenance:
    forming = ctx.forming
    if forming is None:
        return InputProvenance(
            input=INPUT_FORMING,
            available=False,
            quality=Quality.UNAVAILABLE,
            reason=Reason.MISSING_INPUT,
        )
    return _timed(
        INPUT_FORMING,
        ctx.as_of,
        forming.event_ts,
        policy.forming_max_age_s,
        covers_from=forming.open_time,
    )


def _trades(entry: SourceEntry[object], as_of: datetime) -> InputProvenance:
    """Silence is information: a quiet tape is not stale, it is quiet.

    What matters for a trade window is **coverage**, which each calculator
    checks against ``covers_from``/``truncated``; the newest trade's age alone
    would flag every illiquid market as degraded.
    """
    if not entry.available:
        return InputProvenance(
            input=INPUT_TRADES,
            available=False,
            quality=Quality.UNAVAILABLE,
            reason=Reason.MISSING_INPUT if entry.reason == MISSING_INPUT else Reason.GAP,
            truncated=entry.truncated,
        )
    return InputProvenance(
        input=INPUT_TRADES,
        available=True,
        quality=Quality.OK,
        ts=entry.ts,
        age_s=_age(as_of, entry.ts),
        covers_from=entry.covers_from,
        covered_until=entry.covered_until,
        truncated=entry.truncated,
    )


def _deriv(ctx: MarketContext, policy: FreshnessPolicy) -> dict[str, InputProvenance]:
    snapshot = ctx.deriv.value
    budgets = {
        INPUT_FUNDING: policy.funding_max_age_s,
        INPUT_MARK: policy.mark_max_age_s,
        INPUT_OI: policy.oi_max_age_s,
    }
    stamps: dict[str, datetime | None] = {
        INPUT_FUNDING: snapshot.funding_ts if snapshot else None,
        INPUT_MARK: snapshot.mark_ts if snapshot else None,
        INPUT_OI: snapshot.oi_ts if snapshot else None,
    }
    return {name: _timed(name, ctx.as_of, stamps[name], budgets[name]) for name in budgets}


def _history(ctx: MarketContext) -> InputProvenance:
    """A historical reference is not penalised for being historical.

    Whether the reference actually lands on the lookback the feature asked for
    is the feature's own check (it reports ``gap``/``warmup``), not a freshness
    budget.
    """
    entry = ctx.deriv_history
    if not entry.available:
        return InputProvenance(
            input=INPUT_DERIV_HISTORY,
            available=False,
            quality=Quality.UNAVAILABLE,
            reason=Reason.MISSING_INPUT if entry.reason == MISSING_INPUT else Reason.GAP,
        )
    return InputProvenance(
        input=INPUT_DERIV_HISTORY,
        available=True,
        quality=Quality.OK,
        ts=entry.ts,
        age_s=_age(ctx.as_of, entry.ts),
        covers_from=entry.covers_from,
    )


def _atr_state(ctx: MarketContext, advance: AtrAdvance | None) -> InputProvenance:
    """The ATR checkpoint judged as what it is: an input with its own instant.

    Four features read it (``atr_14_pct``, ``momentum_*``, ``breakout_*``), so its
    staleness has to reach all four and not only the one that publishes it
    (Astra, T2.2 diff review, must-fix 2). A checkpoint that could not be
    advanced because the bars are gapped keeps its number, but the number is
    from an older bar and says so.
    """
    checkpoint = advance.checkpoint if advance else None
    if checkpoint is None or checkpoint.value is None:
        return InputProvenance(
            input=INPUT_ATR_STATE,
            available=False,
            quality=Quality.UNAVAILABLE,
            reason=(advance.reason if advance and advance.reason else Reason.WARMUP),
        )
    closed_at = last_bar_close(checkpoint)
    bars = bars_15m(ctx)
    behind = bars.available and bars.bars[-1].close_time > closed_at
    stale = behind or advance is not None and advance.reason is not None
    return InputProvenance(
        input=INPUT_ATR_STATE,
        available=True,
        quality=Quality.DEGRADED if stale else Quality.OK,
        reason=(
            (advance.reason if advance and advance.reason else Reason.STALE_INPUT)
            if stale
            else None
        ),
        ts=closed_at,
        age_s=_age(ctx.as_of, closed_at),
        covers_from=checkpoint.origin_bar_open,
    )


def provenance_for(
    ctx: MarketContext,
    policy: FreshnessPolicy | None = None,
    atr: AtrAdvance | None = None,
) -> dict[str, InputProvenance]:
    """What was known about every input of ``ctx`` at ``ctx.as_of``."""
    policy = policy or FreshnessPolicy()
    book = ctx.book
    entries: dict[str, InputProvenance] = {
        INPUT_CANDLES: _candles(ctx, policy),
        INPUT_FORMING: _forming(ctx, policy),
        INPUT_BOOK: _timed(
            INPUT_BOOK,
            ctx.as_of,
            book.ts if book.available else None,
            policy.book_max_age_s,
            absent=source_reason(book.reason),
        ),
        INPUT_TRADES: _trades(ctx.trades, ctx.as_of),
        INPUT_DERIV_HISTORY: _history(ctx),
        INPUT_ATR_STATE: _atr_state(ctx, atr),
    }
    entries |= _deriv(ctx, policy)
    return entries


__all__ = [
    "QUALITY_POLICY_VERSION",
    "FreshnessPolicy",
    "provenance_for",
    "source_reason",
]
