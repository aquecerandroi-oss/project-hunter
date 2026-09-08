"""``session_orb_v1`` — breakout of the opening range of a **declared** UTC session.

Brief T3.33c / EXP-0010 carry the thesis, the sources (Crabel; Zarattini & Aziz
2023) and the break-even table. LONG only, ``research_only``: nothing here
reaches a wallet.

**Crypto has no sessions** — it trades 24/7, so "asia / europe / us" is *our*
convention: three UTC hours frozen in ``default_parameters``, never measured,
and this version exists for that convention to be refuted. KB-0032 and KB-0035
already found the clock sitting inside our thresholds with nobody having decided
it; here it is in the rule, with a name.

**Purity, the one thing to check twice:** :func:`_session_open` resolves the
session from ``ctx.source_bar_close``, which the context carries; ``evaluate``
reads no clock (no ``datetime.now``, ``time`` or ``utcnow``) and a test moves the
system clock forward a day to prove the decision does not follow it.

**The stop is a datum, so the target is in R** — a fixed ATR target over the low
of the range would swing the nominal reward-to-risk from 4:1 to 1.3:1 inside the
allowed band, two strategies with one name. A constant ``target_r`` holds
break-even between 38 % and 45 %, and the same table fixes
``range_risk_atr_min = 1``, below which the 20 bps of assumed cost eat the trade
first. **No invalidation:** the range low *is* the structure and is already the
stop, so a ``close_below`` rule would be a second stop nobody declared or dead
code (KB-0006). The three hours, ``range_bars = 4`` and ``rvol_min = 1.3`` are
declared assumptions, not fits.

Order of reasons, part of the contract: eligibility, session position,
availability (window, ATR, the range itself), the conditions (break, volume,
cost floor), then the two geometry guards. A refused break is ``REJECTED``, never
"condition false", so no market re-arms on it. Every helper lives **in this
module**: ``code_ref`` freezes a version over its own module plus the siblings it
imports, so one new line in ``indicators.py`` would re-freeze the live versions
and silence the Lab.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from typing import Any, Final

from hunter_core.domain.enums import Timeframe, TradeDirection
from hunter_core.domain.market import align_open_time
from hunter_core.strategies.aggregate import Bar, aggregate
from hunter_core.strategies.base import (
    Decision,
    Evaluation,
    EvaluationState,
    StrategyContext,
    assumed_costs,
    canonical_number,
    param_decimal,
    param_int,
)
from hunter_core.strategies.envelope import AtrEvidence, FeatureEvidence, SupportingFeatures
from hunter_core.strategies.indicators import atr_percent, median, relative_volume, wilder_atr
from hunter_core.strategies.numeric import CONTEXT
from hunter_core.strategies.schema import DECIMAL_PARAM, INTEGER_PARAM, TIMEFRAME_PARAM, schema_of

SESSION_MODEL: Final = "declared_utc_sessions_v1"
"""Versioned name of the session convention below; another split is a new name."""

SESSION_NAMES: Final = ("asia", "europe", "us")
"""Declared in UTC; with the defaults they read 21:00 of the previous day, 04:00
and 10:00 in Brasilia — both spellings live here because this is code (D19)."""

_ONE: Final = Decimal("1")
_PERCENT: Final = Decimal("100")
_DISPLAY: Final = Decimal("0.01")
"""Two decimals, for the sentence only — never for a comparison or a persisted
value (the envelope keeps the full precision)."""
_EMPTY: Final[Mapping[str, str]] = {}


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _display(value: Decimal, scale: Decimal = _ONE) -> str:
    with localcontext(CONTEXT):
        return f"{(value * scale).quantize(_DISPLAY):f}"


def _unavailable(reason: str, detail: Mapping[str, str] = _EMPTY) -> Evaluation:
    return Evaluation(None, EvaluationState.UNAVAILABLE, reason, detail)


def _not_triggered(reason: str, detail: Mapping[str, str]) -> Evaluation:
    return Evaluation(None, EvaluationState.NOT_TRIGGERED, reason, detail)


def _rejected(reason: str, detail: Mapping[str, str]) -> Evaluation:
    return Evaluation(None, EvaluationState.REJECTED, reason, detail)


def _session_open(cut: datetime, hours: tuple[int, int, int]) -> tuple[str, datetime] | None:
    """The latest declared session open at or before ``cut``, within the same UTC day.

    A pure function of the cut the context carries — the only "clock" here. With
    the frozen defaults the asia open at 00:00 covers the whole day, so the answer
    is never ``None``; a parameter set whose first session opens later leaves the
    start of the day uncovered, and that is a declared state, not an error.
    """
    day = cut.replace(hour=0, minute=0, second=0, microsecond=0)
    found: tuple[str, datetime] | None = None
    for name, hour in zip(SESSION_NAMES, hours, strict=True):
        opened = day + timedelta(hours=hour)
        if opened <= cut and (found is None or opened >= found[1]):
            found = (name, opened)
    return found


def _opening_range(
    bars: Sequence[Bar], bars_since_open: int, range_bars: int
) -> tuple[Decimal, Decimal]:
    """High and low of the first ``range_bars`` bars of the session.

    ``bars`` ends at the cut, so ``bars[-bars_since_open]`` is the bar that opened
    **at** the session open, and the slice stops strictly before the current bar
    (the caller already refused ``bars_since_open <= range_bars``).
    """
    opening = bars[-bars_since_open : -bars_since_open + range_bars]
    return max(bar.high for bar in opening), min(bar.low for bar in opening)


class SessionOrbV1:
    """The frozen v1 session opening-range breakout. Stateless and pure."""

    key: str = "session_orb_v1"
    version: str = "v1"
    timeframe: Timeframe = Timeframe.M15

    default_parameters: Mapping[str, Any] = {
        "session_asia_open_h": 0,
        "session_europe_open_h": 7,
        "session_us_open_h": 13,
        "range_bars": 4,
        "session_window_bars": 20,
        "rvol_window": 96,
        "rvol_min": Decimal("1.3"),
        "atr_period": 14,
        "atr_timeframe": Timeframe.M15.value,
        "atr_bars": 97,
        "atr_pct_min": Decimal("0.006"),
        "atr_pct_max": Decimal("0.05"),
        "range_risk_atr_min": Decimal("1"),
        "range_risk_atr_max": Decimal("2.5"),
        "target_r": Decimal("2"),
        "target2_r": Decimal("4"),
        "horizon_s": 14400,
        "base_confidence": Decimal("0.5"),
        "assumed_spread_bps": Decimal("2"),
        "slippage_bps": Decimal("5"),
        "fee_bps": Decimal("4"),
        "max_entry_delay_s": 120,
    }

    parameters_schema: Mapping[str, Any] = schema_of(
        {
            "session_asia_open_h": (INTEGER_PARAM, "UTC hour the asia session opens"),
            "session_europe_open_h": (INTEGER_PARAM, "UTC hour the europe session opens"),
            "session_us_open_h": (INTEGER_PARAM, "UTC hour the us session opens"),
            "range_bars": (INTEGER_PARAM, "15m bars that form the opening range"),
            "session_window_bars": (INTEGER_PARAM, "bars past the open a break still counts"),
            "rvol_window": (INTEGER_PARAM, "bars in the relative-volume median, current excluded"),
            "rvol_min": (DECIMAL_PARAM, "minimum relative volume (inclusive)"),
            "atr_period": (INTEGER_PARAM, "Wilder ATR period"),
            "atr_timeframe": (TIMEFRAME_PARAM, "timeframe the ATR is computed on"),
            "atr_bars": (INTEGER_PARAM, "bars the ATR is recomputed from (rolling_window_v1)"),
            "atr_pct_min": (DECIMAL_PARAM, "minimum ATR/close as a fraction (inclusive)"),
            "atr_pct_max": (DECIMAL_PARAM, "maximum ATR/close as a fraction (inclusive)"),
            "range_risk_atr_min": (DECIMAL_PARAM, "minimum (close - range_low)/ATR (inclusive)"),
            "range_risk_atr_max": (DECIMAL_PARAM, "maximum (close - range_low)/ATR (inclusive)"),
            "target_r": (DECIMAL_PARAM, "target1 in nominal R of the range risk"),
            "target2_r": (DECIMAL_PARAM, "informational target 2, in nominal R"),
            "horizon_s": (INTEGER_PARAM, "expected holding, seconds"),
            "base_confidence": (DECIMAL_PARAM, "uncalibrated constant confidence"),
            "assumed_spread_bps": (DECIMAL_PARAM, "assumed total spread, bps"),
            "slippage_bps": (DECIMAL_PARAM, "assumed slippage per side, bps"),
            "fee_bps": (DECIMAL_PARAM, "assumed fee per side, bps"),
            "max_entry_delay_s": (INTEGER_PARAM, "max seconds from reference close to entry open"),
        }
    )

    def evaluate(self, ctx: StrategyContext, params: Mapping[str, Any]) -> Decision | None:
        return self.explain(ctx, params).decision

    # One return per contract branch, in the documented order of reasons.
    def explain(self, ctx: StrategyContext, params: Mapping[str, Any]) -> Evaluation:
        if not ctx.eligible:
            why = {"eligibility_reason": ctx.eligibility_reason or "unknown"}
            return Evaluation(None, EvaluationState.INELIGIBLE, "ineligible", why)

        hours = (
            param_int(params, "session_asia_open_h"),
            param_int(params, "session_europe_open_h"),
            param_int(params, "session_us_open_h"),
        )
        cut = ctx.source_bar_close
        resolved = _session_open(cut, hours)
        if resolved is None:
            return _not_triggered("no_session_open", {"source_bar_close": _iso(cut)})
        session, session_open = resolved
        step = timedelta(minutes=15)
        bars_since_open = int((cut - session_open) // step)
        range_bars = param_int(params, "range_bars")
        window_bars = param_int(params, "session_window_bars")
        where = {
            "session": session,
            "session_open": _iso(session_open),
            "bars_since_open": str(bars_since_open),
        }
        if bars_since_open <= range_bars:
            # still printing the range: observably false, so the market may re-arm
            return _not_triggered("inside_opening_range", where)
        if bars_since_open > window_bars:
            return _not_triggered("outside_session_window", where)

        rvol_window = param_int(params, "rvol_window")
        atr_bars = param_int(params, "atr_bars")
        atr_timeframe = Timeframe(params["atr_timeframe"])
        window = aggregate(
            ctx.candles_1m, self.timeframe, cut, max(bars_since_open, rvol_window + 1)
        )
        if not window.available:
            return _unavailable(window.reason or "", window.detail)

        atr_end = align_open_time(cut, atr_timeframe)
        atr_window = aggregate(ctx.candles_1m, atr_timeframe, atr_end, atr_bars)
        if not atr_window.available:
            return _unavailable(f"atr_{atr_window.reason}", atr_window.detail)
        atr = wilder_atr(atr_window.bars, param_int(params, "atr_period"))
        atr_pct = None if atr is None else atr_percent(atr, atr_window.bars[-1].close)
        if atr is None or atr_pct is None:
            return _unavailable("atr_warmup")

        bars = window.bars
        close = bars[-1].close
        range_high, range_low = _opening_range(bars, bars_since_open, range_bars)
        if range_high <= range_low:
            return _unavailable("degenerate_range", {**where, "range_high": str(range_high)})
        break_levels = {
            "close_15m": canonical_number(close),
            "range_high": canonical_number(range_high),
        }
        if close <= range_high:
            return _not_triggered("no_range_break", break_levels)

        rvol = relative_volume(bars, rvol_window)
        if rvol is None:
            return _unavailable("rvol_unavailable", {"rvol_window": str(rvol_window)})
        if rvol < param_decimal(params, "rvol_min"):
            return _not_triggered("rvol_low", {"relative_volume_15m": canonical_number(rvol)})
        atr_floor = param_decimal(params, "atr_pct_min")
        if not atr_floor <= atr_pct <= param_decimal(params, "atr_pct_max"):
            return _not_triggered("atr_out_of_range", {"atr_pct_15m": canonical_number(atr_pct)})

        with localcontext(CONTEXT):
            risk = close - range_low
            range_risk_atr = risk / atr.value
            target1 = close + param_decimal(params, "target_r") * risk
            informational = (close + param_decimal(params, "target2_r") * risk,)
        # REJECTED, not NOT_TRIGGERED: the break happened and the decision was
        # refused, so the market must not re-arm on it.
        if not (
            param_decimal(params, "range_risk_atr_min")
            <= range_risk_atr
            <= param_decimal(params, "range_risk_atr_max")
        ):
            measured = {"range_risk_atr": canonical_number(range_risk_atr)}
            return _rejected(
                "range_geometry",
                {**where, **measured, "range_low": canonical_number(range_low), **break_levels},
            )
        levels = {
            "stop": canonical_number(range_low),
            "reference_price": canonical_number(close),
            "target1": canonical_number(target1),
        }
        if not 0 < range_low < close < target1:
            return _rejected("geometry", levels)

        volume_median = median([bar.volume for bar in bars[-rvol_window - 1 : -1]])
        envelope = SupportingFeatures(
            observation_ts=cut,
            timeframe=self.timeframe.value,
            strategy_key=self.key,
            strategy_version=self.version,
            features=(
                FeatureEvidence(name="session", value=session),
                FeatureEvidence(name="session_model", value=SESSION_MODEL),
                FeatureEvidence(name="session_open", source_ts=session_open),
                FeatureEvidence(name="bars_since_open", value=bars_since_open),
                FeatureEvidence(name="range_high", value=range_high, window=range_bars),
                FeatureEvidence(name="range_low", value=range_low, window=range_bars),
                FeatureEvidence(name="range_risk_atr", value=range_risk_atr),
                # the reference bar itself, re-checkable after the 1m candles leave retention
                FeatureEvidence(name="open_15m", value=bars[-1].open, source_ts=bars[-1].open_time),
                FeatureEvidence(name="high_15m", value=bars[-1].high),
                FeatureEvidence(name="low_15m", value=bars[-1].low),
                FeatureEvidence(name="volume_15m", value=bars[-1].volume),
                FeatureEvidence(name="close_15m", value=close, source_ts=bars[-1].close_time),
                FeatureEvidence(name="relative_volume_15m", value=rvol, window=rvol_window),
                FeatureEvidence(name="volume_median_15m", value=volume_median, window=rvol_window),
                FeatureEvidence(name="atr_pct_15m", value=atr_pct, window=atr_bars),
            ),
            atr=AtrEvidence(
                method=atr.method,
                origin=atr.origin,
                timeframe=atr_timeframe.value,
                period=atr.period,
                value=atr.value,
                percent=atr_pct,
                seed=atr.seed,
                seed_anchor=atr.seed_anchor,
                bars_used=atr.bars_used,
                window_start=atr.window_start,
                window_end=atr_end,
            ),
            assumed_costs=assumed_costs(params),
            eligible=ctx.eligible,
            eligibility_reason=ctx.eligibility_reason,
        )
        decision = Decision(
            direction=TradeDirection.LONG,
            reference_price=close,
            stop=range_low,
            target1=target1,
            targets_informational=informational,
            invalidations=(),
            horizon_s=param_int(params, "horizon_s"),
            confidence=param_decimal(params, "base_confidence"),
            reason=(
                f"Session ORB 15m: sessão {session} (abertura {session_open.hour:02d}:00Z), "
                f"fechamento {canonical_number(close)} acima da máxima "
                f"{canonical_number(range_high)} da faixa das {range_bars} primeiras barras, "
                f"{bars_since_open} barras após a abertura; stop na mínima da faixa "
                f"({canonical_number(range_low)}), risco {_display(range_risk_atr)} ATR, "
                f"volume relativo {_display(rvol)}x da mediana de {rvol_window} barras, "
                f"ATR% {_display(atr_pct, _PERCENT)}%"
            ),
            supporting_features=envelope,
        )
        return Evaluation(decision, EvaluationState.TRIGGERED, "signal", {})


SESSION_ORB_V1: Final = SessionOrbV1()
"""The registered instance; strategies are stateless, so one is enough."""
