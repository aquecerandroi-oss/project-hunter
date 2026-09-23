"""The ``since``/``until`` pair shared by every windowed read — T4.82.

Three endpoints of the confluence screen (``docs/design/tela-confluencia-
mercado.md`` §7a) cut the same time window: the candles, the Lab's signals
and the ``spot/1`` desk trail. The rules are here once instead of three
times, because the interesting ones are not obvious:

- **An inverted or empty window is a 422, never an empty list.** An empty
  list reads as "nothing happened in this period", which is a different fact
  from "you asked for a period that cannot contain anything".
- **A window wider than the endpoint can answer completely is a 422 too.**
  Silently returning the newest slice of a wider request would let the screen
  draw a period it does not actually hold — the exact class of lie §3 of the
  design forbids ("um elemento sem dado nunca é desenhado"). The caller is
  told the cap, in seconds, so it can split the request itself.
- **Only a span can be capped.** ``until`` alone has no span: how far back it
  reaches is decided by ``limit``, which is already bounded. ``since`` alone
  does have one — ``now - since`` — or an open-ended ``since`` would dodge
  the cap entirely.

Every datetime that arrives here is already tz-aware UTC: the routers annotate
the parameters with ``UtcDatetime`` (``ensure_utc``), which turns a naive value
into a 422 at the boundary. Nothing here re-checks that, and nothing here
calls ``utcnow()`` — ``now`` is always passed in, so the tests are not a
function of the clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Annotated

from fastapi import status
from pydantic import AfterValidator

from hunter_api.errors import HunterError
from hunter_core.domain.types import ensure_utc

if TYPE_CHECKING:
    from datetime import timedelta

__all__ = [
    "TimeWindow",
    "TimeWindowTooWideError",
    "TimeWindowUnorderedError",
    "UtcDatetime",
    "check_window",
    "resolve_window",
]

UtcDatetime = Annotated[datetime, AfterValidator(ensure_utc)]
"""A query parameter that must be tz-aware, normalised to UTC.

``ensure_utc`` raises ``ValueError`` for a naive datetime, which FastAPI turns
into a 422 in the project's RFC 9457 shape, and converts any explicit offset to
UTC — so the cut happens at the same instant asyncpg is told about regardless
of the offset the caller sent. Without it a naive value would be interpreted in
the *process*'s timezone by asyncpg, silently moving the window.

``routers/markets.py`` keeps its own identical alias: it predates T4.82 and is
part of that module's published surface."""


class TimeWindowUnorderedError(HunterError):
    def __init__(self) -> None:
        super().__init__(
            type_slug="invalid-time-window",
            title="Unprocessable Entity",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="`since` must be strictly before `until`.",
        )


class TimeWindowTooWideError(HunterError):
    def __init__(self, *, span_s: int, max_span_s: int) -> None:
        super().__init__(
            type_slug="time-window-too-wide",
            title="Unprocessable Entity",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"The requested window spans {span_s}s; this endpoint answers at most "
                f"{max_span_s}s in one call. Ask for a narrower window: a wider one would "
                "be truncated without saying so."
            ),
        )


@dataclass(frozen=True, slots=True)
class TimeWindow:
    """A resolved, half-open window ``[since, until)``, both tz-aware UTC."""

    since: datetime
    until: datetime


def _cap(span: timedelta, max_span: timedelta) -> None:
    if span > max_span:
        raise TimeWindowTooWideError(
            span_s=int(span.total_seconds()), max_span_s=int(max_span.total_seconds())
        )


def check_window(
    *,
    since: datetime | None,
    until: datetime | None,
    now: datetime,
    max_span: timedelta,
) -> None:
    """Validate an **optional** window without defaulting either bound.

    For the reads whose no-window behaviour predates T4.82 and must not change
    (``GET /markets/{exchange}/{symbol}/candles``, ``GET /lab/shadow/signals``):
    passing neither bound is still "the ``limit`` most recent rows".
    """
    if since is not None and until is not None:
        if since >= until:
            raise TimeWindowUnorderedError
        _cap(until - since, max_span)
    elif since is not None:
        _cap(now - since, max_span)


def resolve_window(
    *,
    since: datetime | None,
    until: datetime | None,
    now: datetime,
    default_span: timedelta,
    max_span: timedelta,
) -> TimeWindow:
    """Fill both bounds in, validate, and hand back what the server will apply.

    The caller echoes the result in its payload: the desk read defaults its
    own window, and a screen that does not know which window it got cannot
    honestly say "nada aconteceu neste período".
    """
    resolved_until = until if until is not None else now
    resolved_since = since if since is not None else resolved_until - default_span
    if resolved_since >= resolved_until:
        raise TimeWindowUnorderedError
    _cap(resolved_until - resolved_since, max_span)
    return TimeWindow(since=resolved_since, until=resolved_until)
