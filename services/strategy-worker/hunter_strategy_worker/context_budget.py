"""How much 1m history **one version** needs — T3.54b.

``SHADOW_CONTEXT_MINUTES`` was a single number for the whole process: every
version, every market, every bar loaded the same 1560 minutes. That number was
sized for the 1455 minutes of ``mean_reversion_v1``'s ATR (97 bars of 15m), and
it silently became a *ceiling on what a version may be*: T3.54 derived two
variants with ``atr_timeframe = 1h`` and ``atr_bars = 97`` — 5820 minutes of
reach — activated them, and they answered ``unavailable: atr_warmup`` on all
5760 bars of their replay. They were born mute, and the only fix available was
a knob shared by everybody: raising it multiplies the candles read by *every*
live version by ~3.8 (notes-T3.54 §3.4 and §6.5).

So the requirement stops being a property of the environment and becomes a
property of the **version**, which is what it always was: it follows from the
grid the version decides on and from the parameters that size its longest
lookback, both frozen in ``strategy_versions.default_parameters``.

**Why a declared table and not a guess.** Every strategy in this build reads
history through exactly one door — ``hunter_core.strategies.aggregate`` — and
each call names a timeframe and a number of bars derived from the parameters.
This module transcribes those call sites, one :class:`WindowClaim` per call,
and ``tests/test_context_budget.py`` spies on ``aggregate`` while the real
strategy evaluates a real context to prove the transcription covers what the
code actually asks for. A number nobody checked against the code would be worse
than the shared knob it replaces.

The table lives here and not on the strategies for a reason that is not style:
``version_code_ref`` freezes each live version by the digest of its module and
its transitive imports, so adding a method to ``momentum_v1`` would move the
digest of an activated version and mute the whole Lab behind a green
``/ready`` (SHADOW-LAB.md §1, notes-T3.54 §6.2). The seven live digests must not
move; therefore the declaration lives on this side of the fence.

**Fail closed, and loudly.** A strategy this module cannot size is refused by
the catalogue (``context_budget_unknown``) and by
``infra/scripts/activate_strategy_version.py``, instead of running on a window
nobody sized — which is precisely how the two ``v9`` variants died. A registry
entry without a declaration fails a unit test, so the refusal happens in CI and
never in production.

**Test strategies are declared too, through :func:`declare` (T3.54c).** The
refusal applies to every strategy this module sizes, registered or not — a
synthetic test key (``tests/builders.py``'s ``NamedStrategy``, born under a
throwaway key so a contract can be activated many times without colliding on a
frozen row) is simply never in the transcribed :data:`WINDOWS` above, which is
keyed by the real ``(strategy.key, strategy.version)``. So ``NamedStrategy``
calls :func:`declare` with the real ``volume_anomaly_v1`` windows it wraps,
the same way a migration would add a new live strategy's call sites here.
Exempting unregistered strategies instead was rejected: it would turn every
*production* gap in :data:`WINDOWS` (a live strategy nobody transcribed) into a
quiet pass — the T3.54 failure with extra steps.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from hunter_core.domain.enums import Timeframe
from hunter_core.domain.market import timeframe_seconds
from hunter_core.strategies.base import param_int

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hunter_core.strategies.base import Strategy
    from hunter_strategy_worker.config import ShadowConfig

__all__ = [
    "WINDOWS",
    "ContextBudgetUnknown",
    "WindowClaim",
    "claim_reach_minutes",
    "context_minutes_for",
    "declare",
    "declared_windows",
    "over_ceiling",
    "required_context_minutes",
]


class ContextBudgetUnknown(Exception):
    """This build cannot size a version's window from its parameters.

    Either the strategy has no declaration in :data:`WINDOWS` (a new module
    whose call sites nobody transcribed) or a declared parameter is missing from
    the row's frozen ``default_parameters``. Both are refusals, never a default:
    a window guessed too short produces a version that decides nothing and says
    ``warmup``, which is the failure this module exists to end.
    """


@dataclass(frozen=True, slots=True)
class WindowClaim:
    """One ``aggregate()`` call site, as much of it as the budget needs.

    ``bars`` is a *maximum* over terms, each ``(parameter name, addend)``,
    transcribed from the expression the call passes as ``bars_needed`` — so a
    variant that lengthens any of them lengthens the window with it, which is
    the whole point of deriving the number instead of writing it down.
    """

    name: str
    """``signal``/``atr``/``trend`` — the name the strategy's own reasons use
    (``atr_warmup``, ``trend_gap``), so a refusal can be read against a branch."""

    timeframe: str | None
    """The parameter holding this window's timeframe, or ``None`` for the
    strategy's own decision grid."""

    bars: tuple[tuple[str, int], ...]
    """``max(params[name] + addend for name, addend in bars)``."""

    aligned: bool = False
    """Whether the window *ends* at ``align_open_time(cut, timeframe)`` instead
    of at the cut itself.

    It costs history: a 15m bar closing at 12:45 floors a 1h window to 12:00, so
    the window reaches 45 minutes further back than its bars alone say. The
    worst case is one timeframe minus one decision bar, and the worst case is
    what has to be loaded — the budget is per version, not per bar.
    """


_ATR: Final = WindowClaim(
    name="atr", timeframe="atr_timeframe", bars=(("atr_bars", 0),), aligned=True
)
"""Every live strategy computes its ATR the same way — the shared claim is the
shared code path (``atr_end = align_open_time(cut, atr_timeframe)``)."""

_TRENDLINE: Final = WindowClaim(
    name="signal", timeframe=None, bars=(("pattern_bars", 0), ("rvol_window", 1), ("atr_bars", 0))
)
"""The trend-line family's signal window, shared for the same reason ``_ATR`` is:
``trendline_bounce_v1`` (T3.57) inherited the call site from
``trendline_breakout_v1`` verbatim, so it really is one code path. Splitting it
the day they diverge is a two-line change, and the spy test would notice."""

_MEAN_REVERSION: Final = (
    WindowClaim(name="signal", timeframe=None, bars=(("zscore_bars", 0),)),
    _ATR,
    WindowClaim("trend", "trend_timeframe", (("trend_sma_bars", 1),), aligned=True),
)
"""Shared for the reason ``_TRENDLINE`` is: ``mean_reversion_h1_v1`` (T3.54) and
``mean_reversion_m5_v1`` (T3.84) transport the mother's body onto another grid, so the
three are one code path — what differs is the *timeframe parameters* each claim reads,
which a claim already defers to the frozen row."""

WINDOWS: Final[Mapping[tuple[str, str], tuple[WindowClaim, ...]]] = {
    ("momentum_v1", "v1"): (
        WindowClaim(
            name="signal", timeframe=None, bars=(("lookback_closes", 1), ("rvol_window", 1))
        ),
        _ATR,
    ),
    ("volume_anomaly_v1", "v1"): (
        WindowClaim(name="signal", timeframe=None, bars=(("volume_window", 1),)),
        _ATR,
    ),
    ("breakout_v1", "v1"): (
        WindowClaim(
            name="signal",
            timeframe=None,
            bars=(("breakout_highs", 1), ("rvol_window", 1), ("squeeze_baseline_bars", 2)),
        ),
        _ATR,
    ),
    ("mean_reversion_v1", "v1"): _MEAN_REVERSION,
    ("mean_reversion_h1_v1", "v1"): _MEAN_REVERSION,
    ("mean_reversion_m5_v1", "v1"): _MEAN_REVERSION,
    ("session_orb_v1", "v1"): (
        # ``bars_since_open`` is the real term, and the branch above the call
        # refuses anything past ``session_window_bars`` (``outside_session_window``),
        # so that parameter is its upper bound — which is what a budget needs.
        WindowClaim(
            name="signal",
            timeframe=None,
            bars=(("session_window_bars", 0), ("rvol_window", 1)),
        ),
        _ATR,
    ),
    ("sweep_reclaim_v1", "v1"): (
        WindowClaim(
            name="signal",
            timeframe=None,
            bars=(("pivot_lookback_bars", 4), ("rvol_window", 1)),
        ),
        _ATR,
    ),
    ("trendline_breakout_v1", "v1"): (_TRENDLINE, _ATR),
    ("trendline_bounce_v1", "v1"): (_TRENDLINE, _ATR),
}
"""``(strategy.key, strategy.version) -> the windows that version reads``.

``sweep_reclaim_v1``'s signal term is ``pivot_lookback_bars + pivot_k + 1`` in
the code; ``pivot_k`` is frozen at 3 in every live row, so the addend here is
``4`` — the only place a declaration folds a second parameter into a constant,
and the spy test is what proves the fold: a variant that moved ``pivot_k`` would
be caught there instead of being under-served in production.
"""


_DECLARED: dict[tuple[str, str], tuple[WindowClaim, ...]] = {}
"""Windows registered at runtime through :func:`declare`, for a key
:data:`WINDOWS` does not carry. Never consulted ahead of :data:`WINDOWS` itself
(see :func:`declared_windows`) — a real, transcribed entry always wins, so this
table can never shadow the one thing this module exists to keep honest."""


def declare(key: str, version: str, windows: tuple[WindowClaim, ...]) -> None:
    """Register ``windows`` for ``(key, version)`` outside the frozen table.

    For test-only strategies, not for production code (module docstring,
    "Test strategies are declared too"): ``NamedStrategy`` in
    ``services/strategy-worker/tests/builders.py`` wraps a real, frozen
    contract (``volume_anomaly_v1``) under a throwaway key so a test can
    activate the same contract many times without colliding on an
    already-frozen row, and that throwaway key needs the real contract's
    windows to size correctly — the same windows :data:`WINDOWS` already
    carries for the strategy it wraps, passed through unchanged.

    Idempotent: called once per ``NamedStrategy`` construction, and the same
    key is constructed more than once across a test module.
    """
    _DECLARED[(key, version)] = windows


def declared_windows(strategy: Strategy) -> tuple[WindowClaim, ...]:
    """The claims of ``strategy``; ``ContextBudgetUnknown`` when there are none.

    :data:`WINDOWS` — the transcription of this build's real call sites — is
    checked first and always wins: a key :func:`declare` was given can never
    shadow a production entry, only fill in for a key that has none.
    """
    claims = WINDOWS.get((strategy.key, strategy.version)) or _DECLARED.get(
        (strategy.key, strategy.version)
    )
    if claims is None:
        raise ContextBudgetUnknown(
            f"no declared context window for {strategy.key} {strategy.version}: "
            "add its aggregate() call sites to hunter_strategy_worker.context_budget.WINDOWS"
        )
    return claims


def _minutes(timeframe: Timeframe) -> int:
    return timeframe_seconds(timeframe) // 60


def _timeframe_of(claim: WindowClaim, strategy: Strategy, params: Mapping[str, Any]) -> Timeframe:
    if claim.timeframe is None:
        return strategy.timeframe
    try:
        raw = params[claim.timeframe]
    except KeyError as missing:
        raise ContextBudgetUnknown(
            f"{strategy.key} {strategy.version}: window {claim.name!r} needs parameter "
            f"{claim.timeframe!r} and the frozen parameters do not carry it"
        ) from missing
    try:
        return Timeframe(raw)
    except ValueError as bad:
        raise ContextBudgetUnknown(
            f"{strategy.key} {strategy.version}: {claim.timeframe} = {raw!r} is not a timeframe"
        ) from bad


def claim_reach_minutes(claim: WindowClaim, strategy: Strategy, params: Mapping[str, Any]) -> int:
    """How far back of ``source_bar_close`` this one window reaches, in minutes.

    No slack: this is the reach the code will actually ask ``aggregate`` for, so
    the spy test can compare it with the observed ``window_start``.
    """
    timeframe = _timeframe_of(claim, strategy, params)
    step = _minutes(timeframe)
    bars = 0
    for name, addend in claim.bars:
        try:
            bars = max(bars, param_int(params, name) + addend)
        except KeyError as missing:
            raise ContextBudgetUnknown(
                f"{strategy.key} {strategy.version}: window {claim.name!r} needs parameter "
                f"{name!r} and the frozen parameters do not carry it"
            ) from missing
    offset = max(0, step - _minutes(strategy.timeframe)) if claim.aligned else 0
    return bars * step + offset


def required_context_minutes(strategy: Strategy, params: Mapping[str, Any]) -> int:
    """The 1m history one version needs behind every bar it evaluates.

    Pure: no clock, no IO, no environment — the same two inputs the frozen row
    already carries (its code and its ``default_parameters``) always give the
    same number, which is what lets a replay claim it ran the same experiment.

    Each window gets **one bar of its own grid** as slack, and the longest wins.
    Slack is not arithmetic necessity — a context of exactly the reach makes
    ``aggregate`` find its first minute — it is the margin that keeps a warm-up
    a warm-up instead of a truncation, and one bar is the smallest unit in which
    that sentence means anything on the grid it is measured in.
    """
    claims = declared_windows(strategy)
    return max(
        claim_reach_minutes(claim, strategy, params)
        + _minutes(_timeframe_of(claim, strategy, params))
        for claim in claims
    )


def context_minutes_for(strategy: Strategy, params: Mapping[str, Any], config: ShadowConfig) -> int:
    """What the worker actually loads for this version: the requirement, clamped.

    ``SHADOW_CONTEXT_MINUTES`` keeps its name and its 1560 and becomes the
    **floor** — every version that needed less keeps reading exactly what it read
    before this change, so no live population moves — and
    ``SHADOW_CONTEXT_MAX_MINUTES`` is the ceiling that keeps one expensive
    version from being able to cost the process anything at all.

    A requirement above the ceiling is clamped *here* and refused at activation:
    the worker never silently mutes, it loads what it is allowed to and records
    the number in the envelope, so a short context reads as a reason instead of
    a mystery.
    """
    required = required_context_minutes(strategy, params)
    return min(max(required, config.context_minutes), config.context_max_minutes)


def over_ceiling(strategy: Strategy, params: Mapping[str, Any], *, ceiling: int) -> str | None:
    """The refusal message for a version that does not fit, or ``None``.

    Used by ``infra/scripts/activate_strategy_version.py``: a version whose
    longest window does not fit the ceiling would be activated into permanent
    ``warmup``, and an experiment that cannot decide is not an experiment. The
    message carries both numbers because the operator's next move is to decide
    whether ``SHADOW_CONTEXT_MAX_MINUTES`` should rise or the parameters shrink.
    """
    required = required_context_minutes(strategy, params)
    if required <= ceiling:
        return None
    widest = max(
        declared_windows(strategy),
        key=lambda claim: claim_reach_minutes(claim, strategy, params),
    )
    return (
        f"{strategy.key} {strategy.version} needs {required} minutes of 1m context "
        f"(window {widest.name!r}) and SHADOW_CONTEXT_MAX_MINUTES is {ceiling}: it would "
        "evaluate every bar as unavailable/warmup. Raise the ceiling deliberately (it costs "
        "candle reads on every version) or shorten the window in the parameters."
    )
