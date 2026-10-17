"""``copy_leaders_http`` — the polite anonymous reader of the pilot's selection
tool: a hard request budget, a minimum gap, the rate-limit headers honoured,
no retry, and a stop (not a retry loop) on 401/403/429. Everything runs over
``httpx.MockTransport``; no socket is opened.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
for extra in (SCRIPTS_DIR, SCRIPTS_DIR / "tests"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import copy_leaders_http as http  # noqa: E402
from copy_leaders_rig import PERSONAL_MARKER, FakeApi, addr, wire_board, wire_entry  # noqa: E402

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


class Clock:
    """A fake monotonic clock whose ``sleep`` advances it."""

    def __init__(self) -> None:
        self.t = 100.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds


def reader(api: FakeApi, *, budget: int = 30, gap: float = 1.5) -> tuple[http.PumpReader, Clock]:
    clock = Clock()
    return (
        http.PumpReader(
            api.client(),
            budget=budget,
            min_gap_s=gap,
            sleep=clock.sleep,
            monotonic=clock.monotonic,
            now=lambda: NOW,
        ),
        clock,
    )


def full_entries(n: int = 100) -> list[dict[str, Any]]:
    return [wire_entry(addr(i), rank=i + 1) for i in range(n)]


def all_boards(
    entries: list[dict[str, Any]] | None = None,
) -> dict[tuple[str, str], dict[str, Any]]:
    board = wire_board(entries or full_entries())
    return {(p, s): board for p in ("daily", "weekly", "monthly") for s in ("combined", "realized")}


def test_fetch_boards_reads_the_six_views_with_limit_100_and_keeps_no_personal_field() -> None:
    api = FakeApi(all_boards())
    rd, _ = reader(api)
    boards = http.fetch_boards(rd)
    records = rd.records
    assert [(b.period, b.sort) for b in boards] == [
        ("daily", "combined"),
        ("daily", "realized"),
        ("weekly", "combined"),
        ("weekly", "realized"),
        ("monthly", "combined"),
        ("monthly", "realized"),
    ]
    assert len(api.requests) == 6 == rd.used
    assert all(r.url.params["limit"] == "100" for r in api.requests)
    assert {r.url.params["sort"] for r in api.requests} == {"combined", "realized"}
    assert len(records) == 6
    assert all(rec.rows == 100 and rec.malformed_rows == 0 for rec in records)
    assert all(len(rec.body_sha256) == 64 for rec in records)
    assert all(rec.window_start_sec == 1_789_900_000 for rec in records)
    assert all(rec.status == 200 and rec.received_at == NOW for rec in records)
    assert PERSONAL_MARKER not in repr(boards) + repr(records)


def test_requests_are_anonymous_and_identify_the_tool() -> None:
    api = FakeApi(all_boards())
    rd, _ = reader(api)
    http.fetch_boards(rd)
    for request in api.requests:
        assert "authorization" not in request.headers
        assert "cookie" not in request.headers
        assert "copy-pilot" in request.headers["user-agent"]
        assert request.method == "GET"


def test_a_minimum_gap_separates_consecutive_requests() -> None:
    api = FakeApi(all_boards())
    rd, clock = reader(api, gap=1.5)
    http.fetch_boards(rd)
    assert len(clock.sleeps) == 5  # the first request does not wait
    assert all(s == pytest.approx(1.5) for s in clock.sleeps)


def test_the_budget_is_a_hard_wall_checked_before_the_request() -> None:
    api = FakeApi(all_boards())
    rd, _ = reader(api, budget=3)
    with pytest.raises(http.BoardsIncomplete) as excinfo:
        http.fetch_boards(rd)
    assert "budget" in str(excinfo.value)
    assert len(api.requests) == 3


@pytest.mark.parametrize("status", [401, 403, 429])
def test_stop_statuses_end_the_run_and_nothing_else_is_sent(status: int) -> None:
    calls = 0

    def override(request: httpx.Request) -> httpx.Response | None:
        nonlocal calls
        calls += 1
        return httpx.Response(status, headers={"retry-after": "1"}) if calls == 2 else None

    api = FakeApi(all_boards(), override=override)
    rd, _ = reader(api)
    with pytest.raises(http.BoardsIncomplete) as excinfo:
        http.fetch_boards(rd)
    assert f"http_{status}" in str(excinfo.value)
    assert len(api.requests) == 2  # the 429 was the last request: no retry, no next board
    with pytest.raises(http.StopRun):
        rd.get_json("/users/x")
    assert len(api.requests) == 2
    assert rd.stop_reason == f"http_{status}"


def test_a_server_error_is_not_retried() -> None:
    api = FakeApi(all_boards(), override=lambda r: httpx.Response(503))
    rd, _ = reader(api)
    with pytest.raises(http.BoardsIncomplete):
        http.fetch_boards(rd)
    assert len(api.requests) == 1


def test_a_transport_error_is_not_retried() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    rd = http.PumpReader(httpx.Client(transport=httpx.MockTransport(boom)), sleep=lambda s: None)
    with pytest.raises(http.BoardsIncomplete):
        http.fetch_boards(rd)
    assert rd.used == 1


def test_a_malformed_board_makes_the_selection_invalid() -> None:
    boards = all_boards()
    boards[("weekly", "realized")] = {"entries": []}
    api = FakeApi(boards)
    rd, _ = reader(api)
    with pytest.raises(http.BoardsIncomplete) as excinfo:
        http.fetch_boards(rd)
    assert "weekly:realized" in str(excinfo.value)


def test_low_remaining_header_stops_before_the_next_request_in_that_group() -> None:
    api = FakeApi({}, {addr(1): 5, addr(2): 7}, remaining=1)
    rd, _ = reader(api)
    reads = http.fetch_followers(rd, [addr(1), addr(2)])
    assert reads[addr(1)].count == 5
    assert reads[addr(2)].count is None
    assert reads[addr(2)].status == "not_read:rate_limit_headroom"
    assert len(api.requests) == 1
    assert rd.stop_reason == "rate_limit_headroom"


def test_followers_read_the_count_with_a_per_wallet_read_time() -> None:
    api = FakeApi({}, {addr(1): 27709, addr(2): 0})
    rd, _ = reader(api)
    reads = http.fetch_followers(rd, [addr(1), addr(2)])
    assert reads[addr(1)].count == 27709
    assert reads[addr(2)].count == 0  # a real zero is a zero
    assert reads[addr(1)].read_at == NOW
    assert api.paths == [f"/users/{addr(1)}", f"/users/{addr(2)}"]
    assert PERSONAL_MARKER not in repr(reads)


def test_unreadable_followers_are_unknown_never_zero() -> None:
    def override(request: httpx.Request) -> httpx.Response | None:
        if request.url.path.endswith(addr(2)):
            return httpx.Response(200, json={"followers": "many"})
        if request.url.path.endswith(addr(3)):
            return httpx.Response(200, text="<html>")
        return None

    api = FakeApi({}, {addr(1): 1}, override=override)
    rd, _ = reader(api)
    reads = http.fetch_followers(rd, [addr(1), addr(2), addr(3), addr(4)])
    assert reads[addr(2)].count is None and reads[addr(2)].status == "malformed"
    assert reads[addr(3)].count is None and reads[addr(3)].status == "malformed"
    assert reads[addr(4)].count is None and reads[addr(4)].status == "http_404"
    assert reads[addr(1)].count == 1  # one failure does not poison the rest


def test_a_429_while_reading_followers_marks_the_rest_not_read() -> None:
    def override(request: httpx.Request) -> httpx.Response | None:
        return httpx.Response(429) if request.url.path.endswith(addr(2)) else None

    api = FakeApi({}, {addr(1): 3, addr(2): 4, addr(3): 5}, override=override)
    rd, _ = reader(api)
    reads = http.fetch_followers(rd, [addr(1), addr(2), addr(3)])
    assert reads[addr(1)].count == 3
    assert reads[addr(2)].status == "http_429"  # this one got the 429 itself
    assert reads[addr(3)].status == "not_read:http_429"  # this one was never asked
    assert len(api.requests) == 2
    assert rd.stop_reason == "http_429"
    assert [rec.status for rec in rd.records] == [200, 429]  # follower responses are recorded


def test_budget_exhaustion_while_reading_followers_marks_the_rest_not_read() -> None:
    api = FakeApi({}, {addr(i): i for i in range(5)})
    rd, _ = reader(api, budget=2)
    reads = http.fetch_followers(rd, [addr(i) for i in range(5)])
    assert [reads[addr(i)].count for i in range(5)] == [0, 1, None, None, None]
    assert reads[addr(4)].status == "not_read:budget"
    assert rd.stop_reason == "budget"


def test_cookies_set_by_the_server_are_never_sent_back() -> None:
    """The API answers with a Cloudflare ``Set-Cookie``; the tool stays stateless."""

    def override(request: httpx.Request) -> httpx.Response | None:
        board = wire_board(full_entries())
        return httpx.Response(
            200, json=board, headers={"set-cookie": "__cf_bm=abc; Path=/; Domain=pump.fun"}
        )

    api = FakeApi(all_boards(), override=override)
    rd, _ = reader(api)
    http.fetch_boards(rd)
    assert len(api.requests) == 6
    assert all("cookie" not in request.headers for request in api.requests)


def test_a_view_with_fewer_than_100_rows_makes_the_selection_invalid() -> None:
    boards = all_boards()
    boards[("monthly", "combined")] = wire_board(full_entries(99))
    api = FakeApi(boards)
    rd, _ = reader(api)
    with pytest.raises(http.BoardsIncomplete) as excinfo:
        http.fetch_boards(rd)
    assert "monthly:combined" in str(excinfo.value) and "99" in str(excinfo.value)


def test_one_malformed_row_makes_the_view_incomplete_instead_of_hiding_a_wallet() -> None:
    entries = full_entries()
    del entries[7]["positionsCount"]  # e.g. a wallet whose negative row would be silently dropped
    boards = all_boards()
    boards[("daily", "combined")] = wire_board(entries)
    api = FakeApi(boards)
    rd, _ = reader(api)
    with pytest.raises(http.BoardsIncomplete) as excinfo:
        http.fetch_boards(rd)
    assert "daily:combined" in str(excinfo.value) and "1 malformed" in str(excinfo.value)
    assert len(api.requests) == 1


def test_the_expected_row_count_is_the_rule_constant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http, "BOARD_ROWS", 30)  # recorded fixtures are truncated to 30 rows
    api = FakeApi(all_boards([wire_entry(addr(i)) for i in range(30)]))
    rd, _ = reader(api)
    assert len(http.fetch_boards(rd)) == 6


def test_a_duplicate_address_in_a_full_view_makes_it_incomplete() -> None:
    entries = full_entries()
    entries[89] = wire_entry(addr(0), rank=90)  # the wallet of position 1 again at position 90
    boards = all_boards()
    boards[("weekly", "realized")] = wire_board(entries)
    api = FakeApi(boards)
    rd, _ = reader(api)
    with pytest.raises(http.BoardsIncomplete) as excinfo:
        http.fetch_boards(rd)
    assert "weekly:realized" in str(excinfo.value) and "1 malformed" in str(excinfo.value)
