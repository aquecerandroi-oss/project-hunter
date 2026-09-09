"""The hours gate: may *this version* decide at *this hour of the day*?

T3.59. The second rule of the eligibility envelope
(:mod:`hunter_strategy_worker.gate_policy`), and the first one that reads
**nothing** — no table, no clock, no Redis. A bar is eligible when the UTC hour
of its ``source_bar_close`` falls inside one of the declared windows.

**Why it exists as a rule and not as a filter in an analysis.** T3.54 §5 found
that 12:00-12:59 UTC (09:00 BRT) is the only hour positive in both ``momentum``
cohorts (+0,69 R with n = 6 and +0,70 R with n = 16). That is best-of-24 with
n <= 16, which is a hypothesis and not a finding — and the honest way to test a
hypothesis like that is to declare the window *before* looking again and let the
same machinery that decides live decide the replay (EXP-0023).

**Non-anticipation is structural here, not defended.** The verdict is a function
of ``source_bar_close`` and of the frozen policy, and of nothing else: the hour
of a closed bar is a property of that bar. There is no clock read (a decision
replayed today and the same decision taken live in August get the same verdict),
no series that can be late, no row that can be stale. That is also why the gate
is evaluated **before** the regime gate in :mod:`hunter_strategy_worker.context`:
it is free, and it saves the regime gate's indexed query on every bar it refuses.

**The window is over the decision hour** — the hour in which the bar *closes*,
which is when the version decides and (with the 2 s replay lag) when it would
enter. It is deliberately the same clock T3.54 bucketed by
(``extract(hour from emitted_at at time zone 'UTC')``), so a pre-registered
window means the same thing as the evidence that suggested it. Consequence to
say out loud: a 15 min bar closing exactly at 12:00 is the *first* eligible bar
of a ``12-15`` window and the price action it summarises is 11:45-12:00 — the
gate selects when the decision is taken, never where the data came from.

**Half-open, ``[start, end)``**, in UTC only. ``12-15`` is 12:00:00-14:59:59.
A window may wrap midnight (``22-02`` is 22, 23, 00, 01). What is refused, and
never guessed: a frame other than ``utc``, a bound outside 0-24, a non-integer,
an empty list, two windows that overlap, and a set of windows that covers all
twenty-four hours (a gate that lets every hour through is a gate someone
believes in and does not have).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from hunter_core.domain.types import ensure_utc
from hunter_strategy_worker.regime_gate import PolicyError

__all__ = [
    "HOURS_KEY",
    "HOURS_REASON_PREFIX",
    "UTC_FRAME",
    "HoursGate",
    "HoursPolicy",
    "evaluate_hours_gate",
    "hours_clause",
    "parse_hours_policy",
]

HOURS_KEY = "hours"
"""The key this rule occupies in the eligibility envelope."""

UTC_FRAME = "utc"
"""The only frame accepted, and it is written into the stored JSON rather than
assumed. A future ``"brt"`` would be a *new* field with its own daylight-saving
argument; silently reading a local-time window as UTC is the mistake this
spelling makes impossible."""

HOURS_REASON_PREFIX = "hours_gate"
_DAY = 24


@dataclass(frozen=True, slots=True)
class HoursPolicy:
    """A parsed ``{"hours": {"utc": [[12, 15]]}}``. Immutable, like the row."""

    windows: tuple[tuple[int, int], ...]
    """As stored, sorted, half-open; ``start > end`` means "wraps midnight"."""
    hours: frozenset[int]
    """The same thing expanded, which is what the verdict actually asks. Derived
    once at parse time: the policy is frozen with the version, so re-deriving it
    per bar would re-answer a settled question thousands of times a day."""

    def to_body(self) -> dict[str, Any]:
        """Exactly the shape that was stored — the canonical order."""
        return {UTC_FRAME: [list(window) for window in self.windows]}

    @property
    def note(self) -> str:
        """The human copy that travels in the lineage: ``hours=12-15+22-02``."""
        joined = "+".join(f"{start:02d}-{end:02d}" for start, end in self.windows)
        return f"{HOURS_KEY}={joined}"


def _bound(raw: object, *, label: str, ceiling: int) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise PolicyError(f"{HOURS_KEY} policy: {label} {raw!r} is not an integer hour")
    if not 0 <= raw <= ceiling:
        raise PolicyError(f"{HOURS_KEY} policy: {label} {raw} is outside 0-{ceiling}")
    return raw


def _expand(start: int, end: int) -> frozenset[int]:
    """The hours a half-open window covers, wrap-around included."""
    if start < end:
        return frozenset(range(start, end))
    return frozenset(range(start, _DAY)) | frozenset(range(end))


def _window(entry: object) -> tuple[int, int]:
    if not isinstance(entry, list | tuple) or len(cast("list[object]", entry)) != 2:
        raise PolicyError(f"{HOURS_KEY} policy: {entry!r} is not a [start, end] pair")
    pair = list(cast("list[object]", entry))
    start = _bound(pair[0], label="start", ceiling=_DAY - 1)
    end = _bound(pair[1], label="end", ceiling=_DAY)
    if start == end or (start == 0 and end == _DAY):
        raise PolicyError(
            f"{HOURS_KEY} policy: [{start}, {end}] is not a window — a gate that lets every "
            "hour through (or none) is a gate someone believes in and does not have"
        )
    return start, end


def parse_hours_policy(body: object) -> HoursPolicy:
    """The ``hours`` body of the envelope, or :class:`PolicyError`.

    Everything unreadable is refused rather than ignored: a version gated to a
    window this build cannot read must not decide *ungated* — its signals would
    be attributed to an experiment nobody ran.
    """
    if not isinstance(body, dict):
        raise PolicyError(f"{HOURS_KEY} policy must be a JSON object")
    typed = cast("dict[str, Any]", body)
    unknown = sorted(set(typed) - {UTC_FRAME})
    if unknown:
        raise PolicyError(f"{HOURS_KEY} policy has unknown field(s): {', '.join(unknown)}")
    raw_windows: object = typed.get(UTC_FRAME)
    if not isinstance(raw_windows, list) or not raw_windows:
        raise PolicyError(f"{HOURS_KEY} policy needs a non-empty {UTC_FRAME!r} list of windows")
    windows: list[tuple[int, int]] = []
    covered: set[int] = set()
    for entry in cast("list[object]", raw_windows):
        start, end = _window(entry)
        hours = _expand(start, end)
        if hours & covered:
            raise PolicyError(
                f"{HOURS_KEY} policy: window [{start}, {end}] overlaps another one; "
                "write one window per stretch of the day"
            )
        covered |= hours
        windows.append((start, end))
    if len(covered) == _DAY:
        raise PolicyError(
            f"{HOURS_KEY} policy: the windows cover all 24 hours, so nothing is ever refused"
        )
    return HoursPolicy(windows=tuple(sorted(windows)), hours=frozenset(covered))


def hours_clause(rest: str) -> dict[str, Any]:
    """``"12-15"`` / ``"12-15+22-02"`` -> the body to store. Refuses the rest.

    The operator's half of the grammar of ``infra/scripts/derive_variant.py
    --policy``. It goes through :func:`parse_hours_policy` before returning, so
    the CLI refuses exactly what the worker would refuse — one validator, not
    two that can drift.
    """
    windows: list[list[int]] = []
    for chunk in rest.split("+"):
        start, dash, end = chunk.strip().partition("-")
        if not dash:
            raise PolicyError(f"--policy {HOURS_KEY}={rest!r}: {chunk!r} is not <HH>-<HH>")
        try:
            windows.append([int(start), int(end)])
        except ValueError as invalid:
            raise PolicyError(
                f"--policy {HOURS_KEY}={rest!r}: {chunk!r} is not <HH>-<HH> in whole hours"
            ) from invalid
    return parse_hours_policy({UTC_FRAME: windows}).to_body()


@dataclass(frozen=True, slots=True)
class HoursGate:
    """The verdict for one (policy, cut): which hour it was, and what it decided."""

    eligible: bool
    hour: int
    detail: str
    """``allowed`` | ``refused``. There is no third answer: unlike the regime
    gate there is nothing here that can be absent, warming up or stale."""
    policy: HoursPolicy

    @property
    def reason(self) -> str:
        """``hours_gate:HH`` — the hour that was refused, in UTC, zero padded."""
        return f"{HOURS_REASON_PREFIX}:{self.hour:02d}"

    def to_jsonable(self) -> dict[str, Any]:
        """What the envelope's provenance block carries — the window that let
        the decision through, and the hour it was taken in."""
        return {
            "eligible": self.eligible,
            "hour": self.hour,
            "detail": self.detail,
            "policy": self.policy.to_body(),
        }


def evaluate_hours_gate(policy: HoursPolicy, *, cut: datetime) -> HoursGate:
    """The verdict — pure, so a replay and a live bar decide it identically.

    ``ensure_utc`` rather than ``cut.hour``: a caller holding the same instant
    in another offset must get the same verdict, and a naive datetime must not
    be read as if it were UTC by accident.
    """
    hour = ensure_utc(cut).hour
    allowed = hour in policy.hours
    return HoursGate(allowed, hour, "allowed" if allowed else "refused", policy)
