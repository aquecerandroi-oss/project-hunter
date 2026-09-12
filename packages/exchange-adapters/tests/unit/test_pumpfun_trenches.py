"""``/ws/trenches`` — the board mirror and the client, over the live capture of
2026-09-12 (``fixtures/pumpfun/trenches_{new,graduating,graduated,movers}.json``:
one snapshot and every delta received, verbatim, with our receive clock)."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.pumpfun.board_models import BOARDS, NormalizedBoardEntry
from hunter_exchanges.pumpfun.trenches import (
    BACKOFF_MAX_MS,
    TrenchesWsClient,
    backoff_delay_s,
    subscribe_message,
    subscription_url,
)
from hunter_exchanges.pumpfun.trenches_state import BoardState, OutOfOrderDelta, parse_entry

FIXTURES = Path(__file__).parents[1] / "fixtures/pumpfun"
NOW = datetime(2026, 9, 12, 9, 0, tzinfo=UTC)


def _capture(board: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"trenches_{board}.json").read_text(encoding="utf-8"))


def _frames(board: str) -> list[str]:
    return [frame["raw"] for frame in _capture(board)["frames"]]


@pytest.mark.parametrize("board", BOARDS)
def test_the_live_capture_replays_into_a_consistent_board(board: str) -> None:
    """Every frame of every board applies in order; the version chain is
    contiguous; the mirror ends with exactly the mints the last state lists."""
    capture = _capture(board)
    state = BoardState(board)
    kinds: list[str] = []
    gaps = 0
    for frame in capture["frames"]:
        payload = json.loads(frame["raw"], parse_float=Decimal)
        event = state.apply(payload, received_at=datetime.fromisoformat(frame["received_at"]))
        kinds.append(event.kind)
        gaps += event.version_gap > 0
        assert event.version == payload["version"]
        assert set(event.positions) == set(state.entries)
        assert list(event.positions.values()) == list(range(len(state.entries)))
        assert event.observed_at <= event.received_at, "serverTs is ahead of our clock"
    assert kinds.count("snapshot") == capture["counts"]["snapshot"] >= 1
    assert kinds.count("delta") == capture["counts"]["delta"] >= 1
    assert state.version == json.loads(capture["frames"][-1]["raw"])["version"]
    if board == "graduating":
        assert gaps >= 1, "the graduating capture is the evidence that versions skip"
    else:
        assert gaps == 0


def test_the_new_board_capture_carries_adds_and_removes_and_they_move_positions() -> None:
    capture = _capture("new")
    assert capture["patch_ops"].get("add", 0) >= 1 and capture["patch_ops"].get("remove", 0) >= 1
    state = BoardState("new")
    added: list[str] = []
    removed: list[str] = []
    for frame in capture["frames"]:
        event = state.apply(json.loads(frame["raw"], parse_float=Decimal), received_at=NOW)
        if event.kind == "delta" and "add" in event.patch_ops:
            first = next(e for e in event.entries if e.position == 0)
            added.append(first.mint)
            assert state.order[0] == first.mint, "an add at idx 0 is not at the top"
        removed.extend(event.removed)
    assert added and removed
    assert not set(removed) & set(state.entries), "a removed mint is still on the board"


def test_entries_are_normalized_to_long_names_decimals_and_fractions() -> None:
    snapshot = json.loads(_frames("graduated")[0], parse_float=Decimal)
    raw = snapshot["entries"][0]
    entry = parse_entry(
        raw, board="graduated", position=0, version=1, observed_at=NOW, received_at=NOW
    )
    assert isinstance(entry, NormalizedBoardEntry)
    assert entry.mint == raw["m"] and entry.holders == raw["nh"] and entry.snipers == raw["sn"]
    assert isinstance(entry.market_cap_usd, Decimal) and entry.market_cap_usd == raw["mc"]
    assert entry.top10_share == Decimal(raw["t10"]) / 100
    assert entry.dev_share == Decimal(raw["dh"]) / 100
    assert entry.buys == raw["bc"] and entry.sells == raw["sc"] and entry.txs == raw["txc"]
    assert entry.graduated_at == datetime.fromtimestamp(raw["gd"] / 1000, tz=UTC)
    assert entry.progress_pct == Decimal(100)
    assert entry.program == "pump" and entry.quote_asset == "SOL" and entry.is_pump_curve_on_sol
    assert entry.age_s == raw["age"]
    assert set(entry.extra) >= {"ic", "so", "bo"}, "unknown short keys must stay labelled raw"
    assert "nh" not in entry.model_dump(), "a short wire key leaked out of the adapter"


def test_a_zero_graduation_date_and_an_empty_platform_are_absent_not_values() -> None:
    raw = {"m": "MINT", "gd": 0, "pl": "", "pa": "SOL", "pg": "pump"}
    entry = parse_entry(raw, board="new", position=3, version=7, observed_at=NOW, received_at=NOW)
    assert entry.graduated_at is None and entry.platform is None
    assert entry.position == 3 and entry.version == 7


def test_the_movers_board_lists_other_chains_and_they_are_not_the_curve() -> None:
    snapshot = json.loads(_frames("movers")[0], parse_float=Decimal)
    entries = [
        parse_entry(e, board="movers", position=i, version=0, observed_at=NOW, received_at=NOW)
        for i, e in enumerate(snapshot["entries"])
    ]
    assert any(e.chain != "solana:mainnet" for e in entries)
    assert all(not e.is_pump_curve_on_sol for e in entries if e.chain != "solana:mainnet")


def test_an_out_of_order_delta_is_refused_and_leaves_the_mirror_untouched() -> None:
    frames = _frames("graduated")
    state = BoardState("graduated")
    state.apply(json.loads(frames[0], parse_float=Decimal), received_at=NOW)
    first = json.loads(frames[1], parse_float=Decimal)
    assert state.apply(first, received_at=NOW).version_gap == 0
    before = (state.version, dict(state.entries), list(state.order))
    with pytest.raises(OutOfOrderDelta) as error:
        state.apply(first, received_at=NOW)  # the same delta twice is a backwards base
    assert error.value.expected == before[0] and error.value.base_version == first["baseVersion"]
    assert (state.version, state.entries, state.order) == before
    with pytest.raises(OutOfOrderDelta, match="no_snapshot"):
        BoardState("graduated").apply(first, received_at=NOW)
    # A forward gap (skipping frames[2]) applies and reports how far it jumped.
    third = json.loads(frames[3], parse_float=Decimal)
    event = state.apply(third, received_at=NOW)
    assert event.version_gap == third["baseVersion"] - before[0] == 1
    assert state.version == third["version"]


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "delta", "board": "new", "baseVersion": 1, "version": 2, "serverTs": 1},
        {"type": "snapshot", "board": "new", "version": 1, "serverTs": 1},
        {"type": "snapshot", "board": "new", "version": 1, "serverTs": 1, "entries": [{"n": "x"}]},
        {"type": "snapshot", "board": "new", "version": 1, "entries": []},
        {"type": "snapshot", "board": "graduated", "version": 1, "serverTs": 1, "entries": []},
        {"type": "weird", "board": "new"},
    ],
)
def test_malformed_messages_are_refused_by_name(payload: dict[str, Any]) -> None:
    with pytest.raises(MalformedMessage):
        BoardState("new").apply(payload, received_at=NOW)


def test_an_update_for_an_unknown_mint_resyncs_and_a_move_repositions() -> None:
    state = BoardState("new")
    snapshot = {
        "type": "snapshot",
        "board": "new",
        "version": 5,
        "serverTs": 1789203313097,
        "entries": [{"m": "A", "nh": 1}, {"m": "B", "nh": 2}, {"m": "C", "nh": 3}],
    }
    state.apply(snapshot, received_at=NOW)
    with pytest.raises(OutOfOrderDelta, match="unknown_mint"):
        state.apply(
            {
                "type": "delta",
                "board": "new",
                "baseVersion": 5,
                "version": 6,
                "serverTs": 1789203313098,
                "patches": [{"op": "update", "mint": "Z", "fields": {"nh": 9}}],
            },
            received_at=NOW,
        )
    assert state.version == 5, "a refused delta moved the version"
    event = state.apply(
        {
            "type": "delta",
            "board": "new",
            "baseVersion": 5,
            "version": 6,
            "serverTs": 1789203313098,
            "patches": [
                {"op": "move", "mint": "C", "idx": 0},
                {"op": "update", "mint": "A", "fields": {"nh": 11, "t10": Decimal("12.5")}},
                {"op": "remove", "mint": "B"},
            ],
        },
        received_at=NOW,
    )
    assert state.order == ["C", "A"] and event.removed == ("B",)
    assert event.patch_ops == {"move": 1, "update": 1, "remove": 1}
    by_mint = {e.mint: e for e in event.entries}
    assert by_mint["A"].holders == 11 and by_mint["A"].top10_share == Decimal("0.125")
    assert by_mint["A"].position == 1 and by_mint["C"].position == 0


def test_backoff_is_the_sites_formula_capped_at_thirty_seconds() -> None:
    delays = [backoff_delay_s(n, rand=lambda: 0.0) for n in range(7)]
    assert delays == [1, 2, 4, 8, 16, 30, 30]
    assert backoff_delay_s(0, rand=lambda: 1.0) == pytest.approx(1.1)
    assert backoff_delay_s(10, rand=lambda: 0.5) == pytest.approx(BACKOFF_MAX_MS / 1000 * 1.05)


def test_the_subscription_is_in_the_url_and_in_the_first_message() -> None:
    url = subscription_url("graduating")
    assert url.startswith("wss://advanced-indexer.pump.fun/ws/trenches?subscription=%7B%22board")
    assert "%22graduating%22" in url and "%22tier%22%3A%22web%22" in url
    assert json.loads(subscribe_message("graduating")) == {
        "event": "subscribe",
        "data": {"board": "graduating", "tier": "web", "platform": "WEB", "surface": "WEB"},
    }
    with pytest.raises(ValueError):
        TrenchesWsClient("koth")


class Socket:
    def __init__(self, frames: list[str]) -> None:
        self.frames = iter(frames)
        self.sent: list[str] = []
        self.closed = 0

    async def recv(self) -> str:
        frame = next(self.frames, None)
        if frame is None:
            raise ConnectionError("test disconnect")
        return frame

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def close(self) -> None:
        self.closed += 1


def _client(
    sockets_frames: list[list[str]], delays: list[float], board: str = "new"
) -> tuple[TrenchesWsClient, list[Socket]]:
    sockets = [Socket(frames) for frames in sockets_frames]
    handed = iter(sockets)

    @asynccontextmanager
    async def connect(_: str) -> AsyncGenerator[Socket]:
        socket = next(handed, None)
        if socket is None:
            raise RuntimeError("no more sockets")
        try:
            yield socket
        finally:
            await socket.close()

    async def sleep(delay: float) -> None:
        delays.append(delay)
        if len(delays) > 6:
            raise RuntimeError("unbounded retries in a test")

    client = TrenchesWsClient(board, connect_fn=connect, sleep=sleep, rand=lambda: 0.0)
    return client, sockets


async def test_the_client_subscribes_yields_events_counts_malformed_and_reconnects() -> None:
    frames = _frames("new")
    delays: list[float] = []
    client, sockets = _client(
        [[frames[0], "not json", "[]", frames[1], frames[2]], [frames[0]]], delays
    )
    stream = client.stream()
    first = await anext(stream)
    assert first.kind == "snapshot" and client.state.ws_state == "connected"
    second = await anext(stream)
    assert second.kind == "delta" and second.version == first.version + 1
    assert client.state.malformed == 2, "two malformed frames were not counted"
    third = await anext(stream)
    assert third.version == second.version + 1
    # Disconnect -> backoff -> a fresh socket with a fresh snapshot.
    fourth = await anext(stream)
    assert fourth.kind == "snapshot" and client.state.reconnects == 1
    assert delays == [1.0], "the first reconnect did not wait 1 s"
    assert client.state.snapshots == 2 and client.state.deltas == 2
    assert json.loads(sockets[0].sent[0])["event"] == "subscribe"
    assert sockets[0].closed == 1
    await client.aclose()


async def test_an_out_of_order_delta_makes_the_client_resubscribe_for_a_snapshot() -> None:
    frames = _frames("graduated")
    delays: list[float] = []
    client, _ = _client(
        [[frames[0], frames[1], frames[1]], [frames[0], frames[2]]], delays, board="graduated"
    )
    stream = client.stream()
    assert (await anext(stream)).kind == "snapshot"
    assert (await anext(stream)).kind == "delta"
    resynced = await anext(stream)  # the same delta again: backwards, so resubscribe
    assert resynced.kind == "snapshot", "a stale delta did not trigger a fresh snapshot"
    assert client.state.resyncs == 1 and client.state.reconnects == 1
    assert delays == [], "a resync is a resubscribe, not a failure backoff"
    following = await anext(stream)  # snapshot + 2: a forward gap applies and is counted
    assert following.kind == "delta" and following.version_gap == 1
    assert client.state.version_gaps == 1
    await client.aclose()


async def test_consecutive_connect_failures_back_off_by_the_formula_and_never_raise() -> None:
    delays: list[float] = []
    attempts = 0

    @asynccontextmanager
    async def connect(_: str) -> AsyncGenerator[Socket]:
        nonlocal attempts
        attempts += 1
        raise ConnectionError("refused")
        yield Socket([])  # pragma: no cover

    async def sleep(delay: float) -> None:
        delays.append(delay)
        if len(delays) == 6:
            raise RuntimeError("stop the test here")

    client = TrenchesWsClient("movers", connect_fn=connect, sleep=sleep, rand=lambda: 0.0)
    with pytest.raises(RuntimeError, match="stop the test here"):
        await anext(client.stream())
    assert delays == [1, 2, 4, 8, 16, 30]
    assert client.state.consecutive_failures == 6 and client.state.ws_state != "connected"
