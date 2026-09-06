"""What happens to REST admissions when the shared rate-limit coordination is gone.

The policy (M2 acceptance for T2.9, ``.claude/state/dialogue-M2.md``: "sem
orcamento independente durante indisponibilidade") is **fail-closed**: while
Redis cannot answer, this process admits nothing instead of falling back to a
local budget. N shards each spending a full local bucket add up to N quotas
against the single quota Binance accounts per egress IP, and the penalty for
that is an IP ban we cannot undo. A gap can wait for Redis to come back — the
WebSocket keeps ingesting meanwhile, and the gap recovery resumes afterwards.

The suspension is a *state*, not an exception: the limiter retries on a short
jittered backoff and only reports :class:`~hunter_exchanges.base.RateLimited`
(with ``reason="redis_unavailable"``) once the caller's own wait budget is
spent. Callers already survive that; a raw ``ConnectionError`` would take a
worker loop down.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable

from prometheus_client import Counter

from hunter_core.logging import get_logger
from hunter_core.observability import registry
from hunter_exchanges.base import RateLimited

__all__ = [
    "BACKOFF_BASE_S",
    "BACKOFF_JITTER",
    "BACKOFF_MAX_S",
    "REDIS_UNAVAILABLE",
    "REST_GATE_OK",
    "REST_GATE_SUSPENDED",
    "Suspension",
    "backoff_s",
    "is_coordination_outage",
    "rest_admissions_suspended_total",
]

logger = get_logger(__name__)

REDIS_UNAVAILABLE = "redis_unavailable"
"""The only reason there is today: the coordinating Redis did not answer."""

REST_GATE_OK = "ok"
REST_GATE_SUSPENDED = "suspended"

BACKOFF_BASE_S = 0.25
BACKOFF_MAX_S = 2.0
BACKOFF_JITTER = 0.25
"""Full-jitter fraction added on top of the (capped) exponential delay, so N
shards waiting out the same outage do not retry in lockstep and hammer the
recovering Redis at the same instant."""

rest_admissions_suspended_total = Counter(
    "exchange_rest_admissions_suspended_total",
    "REST admissions refused because the shared rate-limit coordination was unavailable.",
    ["exchange", "bucket", "reason"],
    registry=registry,
)


def is_coordination_outage(error: BaseException | None) -> bool:
    """Was ``error`` "the coordination is unreachable" rather than "no budget"?

    Callers that keep durable per-attempt state (the market-worker's gap
    recovery bumps ``ingestion_gaps.attempts`` and parks a gap as ``failed``
    after a few) must not spend those attempts on an infrastructure outage:
    nothing about the gap is wrong, and the attempt would fail again for the
    same reason. Deliberately narrow — a plain ``RateLimited`` (spent budget,
    ``reason is None``) is the exchange working as designed and still counts.
    """
    return isinstance(error, RateLimited) and error.reason == REDIS_UNAVAILABLE


def backoff_s(attempt: int, *, rand: Callable[[], float] = random.random) -> float:
    """Exponential, capped, jittered delay before re-probing the coordination."""
    delay = min(BACKOFF_MAX_S, BACKOFF_BASE_S * (2**attempt))
    return delay * (1 + BACKOFF_JITTER * rand())


class Suspension:
    """Whether this limiter is currently admitting, and why it is not.

    One instance per :class:`~hunter_exchanges.rate_limit.TokenBucketRateLimiter`.
    Transitions are logged once each — an outage must be visible without a log
    line per refused request.
    """

    __slots__ = ("_clock", "_exchange", "reason", "since")

    def __init__(self, exchange: str, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._exchange = exchange
        self._clock = clock
        self.reason: str | None = None
        self.since: float | None = None

    @property
    def active(self) -> bool:
        return self.reason is not None

    def suspend(self, bucket: str, reason: str, error: object) -> None:
        """Coordination just failed: stop admitting (idempotent, logs once)."""
        if self.active:
            return
        self.reason = reason
        self.since = self._clock()
        logger.warning(
            "rest_admissions_suspended",
            exchange=self._exchange,
            bucket=bucket,
            reason=reason,
            error=str(error),
        )

    def resume(self) -> None:
        """Coordination answered again: admit (idempotent, logs once)."""
        if not self.active:
            return
        outage_s = self._clock() - self.since if self.since is not None else 0.0
        logger.info(
            "rest_admissions_resumed",
            exchange=self._exchange,
            reason=self.reason,
            outage_s=round(outage_s, 3),
        )
        self.reason = None
        self.since = None

    def refused(self, bucket: str) -> None:
        """One admission this process did not make because of the suspension."""
        rest_admissions_suspended_total.labels(
            exchange=self._exchange, bucket=bucket, reason=self.reason or REDIS_UNAVAILABLE
        ).inc()

    def next_delay(self, bucket: str, attempt: int, spent_s: float, max_wait_s: float) -> float:
        """How long to wait before re-probing coordination.

        Raises :class:`RateLimited` instead once ``spent_s`` plus the next
        delay would exceed the caller's own ``max_wait_s`` — the suspension is
        reported through the exception every worker loop already survives, and
        counted once here, on the admission that did not happen (not once per
        re-probe).
        """
        delay = backoff_s(attempt)
        if spent_s + delay > max_wait_s:
            self.refused(bucket)
            raise RateLimited(
                f"{self._exchange} REST admissions are suspended ({self.reason}): the shared "
                f"rate-limit coordination is unreachable, so this process admits nothing",
                exchange=self._exchange,
                retry_after_s=delay,
                reason=self.reason or REDIS_UNAVAILABLE,
            )
        return delay
