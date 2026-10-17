"""The polite, anonymous reader behind ``copy_select_leaders.py``.

Public ``GET`` only (docs/PUMPFUN.md §10): no login, no cookie, no key, an
honest ``User-Agent``. A hard request budget checked before each call, a
minimum gap between calls, the ``x-ratelimit-*`` headers honoured, and **no
retry anywhere**: a 401/403/429 stops the run (nothing else is sent), any other
failure is one failed read. Nothing here evades a limit or a challenge.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

import httpx
from copy_leaders_rule import (
    BOARD_ROWS,
    PERIODS_LONGEST_FIRST,
    SORTS,
    BoardShapeError,
    ParsedBoard,
    parse_board,
)

BASE_URL = "https://frontend-api-v3.pump.fun"
USER_AGENT = "project-hunter-copy-pilot/1 (read-only public leaderboard and follower counts)"
REQUEST_BUDGET = 30
MIN_GAP_S = 1.5
LOW_HEADROOM = 1
STOP_STATUSES = frozenset({401, 403, 429})
BOARD_LIMIT = "100"


class StopRun(Exception):
    """No further request may be sent in this run."""

    def __init__(self, reason: str, *, sent: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.sent = sent  # True when the stop came from a response (the request was made)


class BudgetExhausted(StopRun):
    def __init__(self) -> None:
        super().__init__("budget")


class ReadError(Exception):
    """One request failed in a way that is not a stop (5xx, 404, transport, bad JSON)."""

    def __init__(self, status: str) -> None:
        super().__init__(status)
        self.status = status


class BoardsIncomplete(Exception):
    """A mandatory leaderboard view could not be read: the selection is invalid."""


@dataclass(frozen=True, slots=True)
class ResponseRecord:
    endpoint: str
    params: dict[str, str]
    requested_at: datetime
    received_at: datetime
    status: int
    body_sha256: str
    ratelimit_limit: str | None
    ratelimit_remaining: str | None
    window_start_sec: int | None = None
    rows: int | None = None
    malformed_rows: int | None = None


@dataclass(frozen=True, slots=True)
class FollowerRead:
    count: int | None
    read_at: datetime | None
    status: str
    """``ok``, ``malformed``, ``http_<code>``, ``transport`` or ``not_read:<reason>``."""


def _utcnow() -> datetime:
    return datetime.now(UTC)


class PumpReader:
    def __init__(
        self,
        client: httpx.Client,
        *,
        budget: int = REQUEST_BUDGET,
        min_gap_s: float = MIN_GAP_S,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._client = client
        self._budget = budget
        self._gap = min_gap_s
        self._sleep = sleep
        self._monotonic = monotonic
        self._now = now
        self._last_at: float | None = None
        self._remaining: dict[str, int] = {}
        self.used = 0
        self.stop_reason: str | None = None
        self.records: list[ResponseRecord] = []

    def get_json(
        self, path: str, params: dict[str, str] | None = None
    ) -> tuple[Any, ResponseRecord]:
        group = path.strip("/").split("/", 1)[0]
        if self.stop_reason is not None:
            raise StopRun(self.stop_reason)
        if self.used >= self._budget:
            self.stop_reason = "budget"
            raise BudgetExhausted
        if self._remaining.get(group, LOW_HEADROOM + 1) <= LOW_HEADROOM:
            self.stop_reason = "rate_limit_headroom"
            raise StopRun(self.stop_reason)
        if self._last_at is not None:
            wait = self._gap - (self._monotonic() - self._last_at)
            if wait > 0:
                self._sleep(wait)
        self.used += 1
        requested_at = self._now()
        self._last_at = self._monotonic()
        try:
            response = self._client.get(
                path,
                params=params,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise ReadError("transport") from exc
        finally:
            self._client.cookies.clear()  # stateless: nothing the server sets is ever sent back
        record = ResponseRecord(
            endpoint=path,
            params=dict(params or {}),
            requested_at=requested_at,
            received_at=self._now(),
            status=response.status_code,
            body_sha256=hashlib.sha256(response.content).hexdigest(),
            ratelimit_limit=response.headers.get("x-ratelimit-limit"),
            ratelimit_remaining=response.headers.get("x-ratelimit-remaining"),
        )
        self.records.append(record)
        if record.ratelimit_remaining is not None and record.ratelimit_remaining.isdigit():
            self._remaining[group] = int(record.ratelimit_remaining)
        if response.status_code in STOP_STATUSES:
            self.stop_reason = f"http_{response.status_code}"
            raise StopRun(self.stop_reason, sent=True)
        if response.status_code != 200:
            raise ReadError(f"http_{response.status_code}")
        try:
            return json.loads(response.text, parse_float=Decimal), record
        except ValueError as exc:
            raise ReadError("malformed") from exc


def fetch_boards(reader: PumpReader) -> list[ParsedBoard]:
    """The six mandatory views, each complete (``BOARD_ROWS`` readable rows, none malformed);
    any failure makes the whole selection invalid. Annotates ``reader.records``."""
    boards: list[ParsedBoard] = []
    for period in reversed(PERIODS_LONGEST_FIRST):
        for sort in SORTS:
            name = f"{period}:{sort}"
            try:
                payload, record = reader.get_json(
                    "/pnl-leaderboard", {"period": period, "sort": sort, "limit": BOARD_LIMIT}
                )
                board = parse_board(period, sort, payload)
            except StopRun as exc:
                raise BoardsIncomplete(f"{name}: stopped ({exc.reason})") from exc
            except ReadError as exc:
                raise BoardsIncomplete(f"{name}: {exc.status}") from exc
            except BoardShapeError as exc:
                raise BoardsIncomplete(str(exc)) from exc
            reader.records[-1] = replace(
                record,
                window_start_sec=board.window_start_sec,
                rows=len(board.rows),
                malformed_rows=board.malformed,
            )
            if board.malformed or len(board.rows) != BOARD_ROWS:
                raise BoardsIncomplete(
                    f"{name}: {len(board.rows)} readable rows and {board.malformed} malformed "
                    f"(a complete view has {BOARD_ROWS} and none malformed)"
                )
            boards.append(board)
    return boards


def _followers(payload: Any) -> int | None:
    value = cast("dict[str, Any]", payload).get("followers") if isinstance(payload, dict) else None
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        return None
    return int(value) if value == int(value) and value >= 0 else None


def fetch_followers(reader: PumpReader, addresses: list[str]) -> dict[str, FollowerRead]:
    """``GET /users/{address}`` -> ``followers`` only. Unreadable is unknown, never 0;
    a stop (429/403/401, low headroom, budget) leaves the rest ``not_read``."""
    reads: dict[str, FollowerRead] = {}
    stopped: str | None = None
    for address in addresses:
        if stopped is not None:
            reads[address] = FollowerRead(None, None, f"not_read:{stopped}")
            continue
        try:
            payload, record = reader.get_json(f"/users/{address}")
        except StopRun as exc:
            stopped = exc.reason
            status = exc.reason if exc.sent else f"not_read:{exc.reason}"
            reads[address] = FollowerRead(None, None, status)
            continue
        except ReadError as exc:
            reads[address] = FollowerRead(None, None, exc.status)
            continue
        count = _followers(payload)
        if count is None:
            reads[address] = FollowerRead(None, record.received_at, "malformed")
        else:
            reads[address] = FollowerRead(count, record.received_at, "ok")
    return reads
