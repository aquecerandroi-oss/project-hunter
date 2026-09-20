"""The event gate's own counters (T4.52b-3) — a rolling 60-second window for
the rates plan-T4.52b.md §3/§4 wants measured, cumulative totals for the
rest, mirroring ``lab_heartbeat.py``'s own shape (strings, an absent number is
``""``, never a ``0`` that reads as a measurement).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from hunter_meme_worker.lab_heartbeat import percentile

__all__ = ["EventGateStats", "heartbeat_fields"]

HEARTBEAT_PREFIX = "event_gate_"
WINDOW_S = 60
LATENCY_SAMPLE = 500
SUBSCRIBE_AT_CREATE_FAILED_LOG_INTERVAL_S = 30
"""T4.70b: minimum gap between two ``meme_event_gate_subscribe_at_create_failed``
log lines — the counter below still counts every one of them."""


def _trim(window: deque[datetime], now: datetime) -> None:
    horizon = now - timedelta(seconds=WINDOW_S)
    while window and window[0] < horizon:
        window.popleft()


def _trim_pairs(window: deque[tuple[datetime, str]], now: datetime) -> None:
    horizon = now - timedelta(seconds=WINDOW_S)
    while window and window[0][0] < horizon:
        window.popleft()


@dataclass
class EventGateStats:
    """Since boot, plus a 60-second rolling count for the rates."""

    events_total: int = 0
    events_window: deque[datetime] = field(default_factory=deque[datetime])
    dropped_total: int = 0
    dropped_window: deque[datetime] = field(default_factory=deque[datetime])
    evaluations_total: int = 0
    evaluations_window: deque[datetime] = field(default_factory=deque[datetime])
    proposals_total: int = 0
    shadow_proposals_total: int = 0
    shadow_only_window: deque[tuple[datetime, str]] = field(
        default_factory=deque[tuple[datetime, str]]
    )
    """(``at``, ``mint``) of a mint ``shadow`` would propose that the
    15-second lane's own recent proposals did not cover — metrics §5."""
    shadow_agree_window: deque[tuple[datetime, str]] = field(
        default_factory=deque[tuple[datetime, str]]
    )
    """(``at``, ``mint``) of a mint the 15-second lane already proposed
    recently that ``shadow`` also judged (agreed or would have)."""
    no_base_row_total: int = 0
    no_base_row_window: deque[datetime] = field(default_factory=deque[datetime])
    unsubscribed_total: int = 0
    reconnects: int = 0
    restarts_total: int = 0
    """S-T4.62 MEDIUM: :func:`event_gate.run_event_gate_forever` restarts —
    the 13/h signal the security review flagged; exposed on the heartbeat so
    a spike is visible without grepping logs."""
    gap_write_failed_total: int = 0
    """S-T4.62 MEDIUM: a reconnect gap ``INSERT`` that raised instead of
    landing (``event_gate_eval.handle_reconnect``) — counted, never raised."""
    bad_frames_total: int = 0
    """S-T4.62 MEDIUM: a notification that crashed folding/evaluation
    (malformed ``TradeEvent``, bad pydantic frame, ...) and was dropped
    instead of killing the gate."""
    subscriptions: int = 0
    ws_state: str = "disconnected"
    last_event_at: datetime | None = None
    latency_s: deque[float] = field(default_factory=lambda: deque(maxlen=LATENCY_SAMPLE))
    """``event_to_proposal_s`` of every proposal this process wrote."""
    subscribed_at_create_total: int = 0
    """T4.70 (notes-T4.66.md §7, P0): ``create`` frames that opened a
    subscription right there — never the periodic 5 s sync — since boot."""
    create_to_subscribe_ms: deque[float] = field(
        default_factory=lambda: deque(maxlen=LATENCY_SAMPLE)
    )
    """Milliseconds from the ``create`` frame's own ``received_at`` to the
    subscription landing in ``rt.subs`` — the number the P0 finding asks for."""
    early_retention_unknown_window: deque[datetime] = field(default_factory=deque[datetime])
    """``at`` of every judged evaluation whose row measured
    ``early_retention_pct is None`` — the heartbeat's share is this over
    ``evaluations_window`` (same 60 s), the P0 acceptance number itself."""
    subscribe_at_create_failed_total: int = 0
    """T4.70b (incident 2026-09-19): a transient WS error
    (``ConnectionError``/``TimeoutError``/``OSError``) inside
    ``subscribe_at_create`` — counted and degraded to the periodic sync
    picking the mint up instead, never a crash of the discovery task."""
    _subscribe_at_create_failed_last_logged_at: datetime | None = field(
        default=None, repr=False, compare=False
    )

    def record_event(self, now: datetime) -> None:
        self.events_total += 1
        self.events_window.append(now)
        self.last_event_at = now
        _trim(self.events_window, now)

    def record_dropped(self, now: datetime) -> None:
        self.dropped_total += 1
        self.dropped_window.append(now)
        _trim(self.dropped_window, now)

    def record_evaluation(self, now: datetime) -> None:
        self.evaluations_total += 1
        self.evaluations_window.append(now)
        _trim(self.evaluations_window, now)

    def record_no_base_row(self, now: datetime) -> None:
        self.no_base_row_total += 1
        self.no_base_row_window.append(now)
        _trim(self.no_base_row_window, now)

    def record_proposals(self, count: int, *, latencies: list[float] | None = None) -> None:
        self.proposals_total += count
        for value in latencies or ():
            self.latency_s.append(value)

    def record_shadow_proposals(self, count: int) -> None:
        self.shadow_proposals_total += count

    def record_shadow_only(self, mint: str, now: datetime) -> None:
        self.shadow_only_window.append((now, mint))
        _trim_pairs(self.shadow_only_window, now)

    def record_shadow_agree(self, mint: str, now: datetime) -> None:
        self.shadow_agree_window.append((now, mint))
        _trim_pairs(self.shadow_agree_window, now)

    def record_unsubscribed(self, count: int = 1) -> None:
        self.unsubscribed_total += count

    def record_reconnect(self) -> None:
        self.reconnects += 1

    def record_restart(self) -> None:
        self.restarts_total += 1

    def record_gap_write_failed(self) -> None:
        self.gap_write_failed_total += 1

    def record_bad_frame(self) -> None:
        self.bad_frames_total += 1

    def record_subscribed_at_create(self, latency_ms: float) -> None:
        self.subscribed_at_create_total += 1
        self.create_to_subscribe_ms.append(latency_ms)

    def record_early_retention_unknown(self, now: datetime) -> None:
        self.early_retention_unknown_window.append(now)
        _trim(self.early_retention_unknown_window, now)

    def record_subscribe_at_create_failed(self, now: datetime) -> bool:
        """Counts every failure; returns whether *this one* should be logged
        — at most once every :data:`SUBSCRIBE_AT_CREATE_FAILED_LOG_INTERVAL_S`,
        so a repeating RPC outage never floods the logs while the counter
        keeps an exact tally."""
        self.subscribe_at_create_failed_total += 1
        last = self._subscribe_at_create_failed_last_logged_at
        if last is not None and (now - last).total_seconds() < (
            SUBSCRIBE_AT_CREATE_FAILED_LOG_INTERVAL_S
        ):
            return False
        self._subscribe_at_create_failed_last_logged_at = now
        return True


def heartbeat_fields(
    stats: EventGateStats,
    *,
    now: datetime,
    enabled: bool,
    cache_sizes: dict[str, int] | None = None,
) -> dict[str, str]:
    _trim(stats.events_window, now)
    _trim(stats.dropped_window, now)
    _trim(stats.evaluations_window, now)
    _trim(stats.no_base_row_window, now)
    _trim_pairs(stats.shadow_only_window, now)
    _trim_pairs(stats.shadow_agree_window, now)
    _trim(stats.early_retention_unknown_window, now)
    latencies = list(stats.latency_s)
    p50, p95 = (
        percentile([int(v * 1000) for v in latencies], 0.50),
        percentile([int(v * 1000) for v in latencies], 0.95),
    )
    subscribe_latencies = [int(v) for v in stats.create_to_subscribe_ms]
    subscribe_p50, subscribe_p95 = (
        percentile(subscribe_latencies, 0.50),
        percentile(subscribe_latencies, 0.95),
    )
    judged = len(stats.evaluations_window)
    unknown_share = (
        "" if judged == 0 else str(round(len(stats.early_retention_unknown_window) / judged, 4))
    )
    age = (
        "" if stats.last_event_at is None else str(int((now - stats.last_event_at).total_seconds()))
    )
    fields: dict[str, str] = {
        "enabled": "true" if enabled else "false",
        "events_60s": str(len(stats.events_window)),
        "dropped": str(len(stats.dropped_window)),
        "evaluations": str(len(stats.evaluations_window)),
        "proposals_total": str(stats.proposals_total),
        "shadow_proposals_total": str(stats.shadow_proposals_total),
        "shadow_only_event_mints": str(len({m for _, m in stats.shadow_only_window})),
        "shadow_agree_mints": str(len({m for _, m in stats.shadow_agree_window})),
        "event_to_proposal_s_p50": "" if p50 is None else str(p50 / 1000),
        "event_to_proposal_s_p95": "" if p95 is None else str(p95 / 1000),
        "ws_state": stats.ws_state,
        "subscriptions": str(stats.subscriptions),
        "reconnects": str(stats.reconnects),
        "restarts_total": str(stats.restarts_total),
        "gap_write_failed_total": str(stats.gap_write_failed_total),
        "bad_frames": str(stats.bad_frames_total),
        "last_event_age_s": age,
        "no_base_row_60s": str(len(stats.no_base_row_window)),
        "unsubscribed_total": str(stats.unsubscribed_total),
        "subscribed_at_create_total": str(stats.subscribed_at_create_total),
        "subscribe_at_create_failed_total": str(stats.subscribe_at_create_failed_total),
        "create_to_subscribe_ms_p50": "" if subscribe_p50 is None else str(subscribe_p50),
        "create_to_subscribe_ms_p95": "" if subscribe_p95 is None else str(subscribe_p95),
        "early_retention_unknown_share_60s": unknown_share,
    }
    for key, value in (cache_sizes or {}).items():
        fields[f"cache_{key}"] = str(value)
    return {HEARTBEAT_PREFIX + key: value for key, value in fields.items()}
