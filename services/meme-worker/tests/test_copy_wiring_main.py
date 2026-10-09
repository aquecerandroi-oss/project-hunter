"""``MEME_COPY_LANE`` (H-037, task F): the flag that lets the paper copy lane run in the meme-worker.

Proved here: ``off``/unset/garbage start nothing and open nothing (every builder explodes if touched);
``paper`` starts one task with the real arguments and a fresh source per ``stream()`` (the production
``ChainLeaderSource`` closes its WS feed for good when a stream ends); a crash inside the lane never
reaches the sibling tasks of the worker's ``TaskGroup``; shutdown closes the lane's RPC client.
Everything outside the lane is a labeled fake; nothing here opens a socket.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Collection
from types import SimpleNamespace
from typing import Any

import pytest
from structlog.testing import capture_logs

from hunter_meme_worker import copy_main
from hunter_meme_worker import main as meme_main
from hunter_meme_worker.config import MemeConfig
from hunter_meme_worker.copy_main import build_copy_lane, copy_lane_mode

from .test_cycle_history import _Db  # pyright: ignore[reportPrivateUsage]
from .test_cycle_history import db as db
from .test_cycle_lifecycle import _runtime  # pyright: ignore[reportPrivateUsage]
from .test_cycle_lifecycle import chain as chain  # the fixture: every other loop stubbed

pytestmark = pytest.mark.unit

WS_URL = "wss://example.invalid/ws"


def _boom(*args: object, **kwargs: object) -> Any:
    raise AssertionError("touched although MEME_COPY_LANE is not 'paper'")


class _FakeRpc:
    def __init__(self) -> None:
        self.closed = 0

    async def aclose(self) -> None:
        self.closed += 1


class _FakeWs:
    def __init__(self, *, url: str) -> None:
        self.url = url
        self.closed = 0

    async def aclose(self) -> None:
        self.closed += 1


class _Rig:
    """The names ``copy_main`` imports, replaced by fakes that record what they were given."""

    def __init__(self) -> None:
        self.rpcs: list[_FakeRpc] = []
        self.feeds: list[_FakeWs] = []
        self.builds: list[dict[str, Any]] = []
        self.lane_calls: list[dict[str, Any]] = []
        self.lane_started = asyncio.Event()
        self.third_call = asyncio.Event()
        self.lane_crashes = 0  # how many calls to ``start_copy_lane`` raise before one parks

    def new_rpc(self) -> _FakeRpc:
        rpc = _FakeRpc()
        self.rpcs.append(rpc)
        return rpc

    def new_feed(self, *, url: str) -> _FakeWs:
        feed = _FakeWs(url=url)
        self.feeds.append(feed)
        return feed

    def build(self, rpc: object, feed: object, **kwargs: Any) -> Any:
        self.builds.append({"rpc": rpc, "feed": feed, **kwargs})

        async def stream(wallets: Collection[str]) -> AsyncIterator[str]:
            yield f"item-for-{sorted(wallets)[0]}"

        return SimpleNamespace(stream=stream)

    async def start_copy_lane(self, **kwargs: Any) -> None:
        self.lane_calls.append(kwargs)
        self.lane_started.set()
        if len(self.lane_calls) >= 3:
            self.third_call.set()
        if self.lane_crashes > 0:
            self.lane_crashes -= 1
            raise RuntimeError("the copy lane crashed")
        await asyncio.Event().wait()


@pytest.fixture
def rig(monkeypatch: pytest.MonkeyPatch) -> _Rig:
    rig = _Rig()
    monkeypatch.setenv("SOLANA_RPC_WS_URL", WS_URL)
    monkeypatch.setattr(copy_main, "SolanaRpcClient", rig.new_rpc)
    monkeypatch.setattr(copy_main, "SolanaWsClient", rig.new_feed)
    monkeypatch.setattr(copy_main, "build_leader_source", rig.build)
    monkeypatch.setattr(copy_main, "start_copy_lane", rig.start_copy_lane)
    monkeypatch.setattr(copy_main, "RESTART_S", 0.01)
    return rig


@pytest.fixture
def nothing_may_open(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("SolanaRpcClient", "SolanaWsClient", "build_leader_source", "start_copy_lane"):
        monkeypatch.setattr(copy_main, name, _boom)


def _ctx() -> Any:
    return SimpleNamespace(session_factory=object(), chain=object())


async def _heartbeat(fields: dict[str, str]) -> None:
    return None


@pytest.mark.parametrize("raw", [None, "", "off", " OFF "])
def test_the_flag_defaults_to_off(monkeypatch: pytest.MonkeyPatch, raw: str | None) -> None:
    if raw is None:
        monkeypatch.delenv("MEME_COPY_LANE", raising=False)
    else:
        monkeypatch.setenv("MEME_COPY_LANE", raw)
    with capture_logs() as logs:
        assert copy_lane_mode() == "off"
    assert logs == []  # unset and a plain "off" are not a misconfiguration


@pytest.mark.parametrize("raw", ["paper", " PAPER "])
def test_the_flag_reads_paper(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    monkeypatch.setenv("MEME_COPY_LANE", raw)
    assert copy_lane_mode() == "paper"


@pytest.mark.parametrize(
    "raw", ["on", "live", "true", "1", "shadow", "papers", "paper,live", "yes"]
)
def test_any_other_value_fails_closed_with_a_warning(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    """There is no ``on`` and no ``live``: the lane is paper or it is off."""
    monkeypatch.setenv("MEME_COPY_LANE", raw)
    with capture_logs() as logs:
        assert copy_lane_mode() == "off"
    assert [(r["event"], r["log_level"], r["variable"]) for r in logs] == [
        ("meme_copy_lane_config_invalid", "warning", "MEME_COPY_LANE")
    ]


@pytest.mark.parametrize("raw", [None, "off", "on", "live", "garbage"])
def test_off_unset_and_garbage_build_nothing(
    monkeypatch: pytest.MonkeyPatch, nothing_may_open: None, raw: str | None
) -> None:
    if raw is None:
        monkeypatch.delenv("MEME_COPY_LANE", raising=False)
    else:
        monkeypatch.setenv("MEME_COPY_LANE", raw)
    # a ctx with no attribute at all: reading ctx.chain or ctx.session_factory would fail the test
    assert build_copy_lane(SimpleNamespace(), _heartbeat) is None  # type: ignore[arg-type]


async def test_paper_runs_the_lane_with_the_real_arguments(
    monkeypatch: pytest.MonkeyPatch, rig: _Rig
) -> None:
    monkeypatch.setenv("MEME_COPY_LANE", "paper")
    ctx = _ctx()
    lane = build_copy_lane(ctx, _heartbeat)
    assert lane is not None
    assert rig.feeds == [] and rig.builds == []  # constructing the lane opens nothing
    task = asyncio.ensure_future(lane.run())
    await asyncio.wait_for(rig.lane_started.wait(), timeout=5)
    (call,) = rig.lane_calls
    assert call["session_factory"] is ctx.session_factory
    assert call["chain"] is ctx.chain  # the lane prices from the radar's own chain client
    assert call["heartbeat"] is _heartbeat
    items = [item async for item in call["source"].stream(["W1", "W2"])]
    assert items == ["item-for-W1"]
    (build,) = rig.builds
    assert build["rpc"] is rig.rpcs[0]  # the dedicated client: ``call`` is not on ChainSource
    assert build["feed"] is rig.feeds[0] and rig.feeds[0].url == WS_URL
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


async def test_every_stream_gets_a_fresh_source_and_closes_its_feed(
    monkeypatch: pytest.MonkeyPatch, rig: _Rig
) -> None:
    """``ChainLeaderSource.stream`` closes its feed in its ``finally`` and ``SolanaWsClient.aclose`` is
    final: reusing one source after a source failure or a rule-set change would leave the chain side
    deaf. A new source per stream, one shared stats object, the feed closed when the stream ends."""
    monkeypatch.setenv("MEME_COPY_LANE", "paper")
    lane = build_copy_lane(_ctx(), _heartbeat)
    assert lane is not None
    for _ in range(2):
        assert [i async for i in lane.source.stream(["W1"])] == ["item-for-W1"]
    assert len(rig.builds) == len(rig.feeds) == 2
    assert rig.feeds[0] is not rig.feeds[1]
    assert [feed.closed for feed in rig.feeds] == [1, 1]
    assert rig.builds[0]["stats"] is rig.builds[1]["stats"]
    assert len(rig.rpcs) == 1  # one RPC client for the lane's whole life


async def test_a_stream_cancelled_midway_closes_its_feed(
    monkeypatch: pytest.MonkeyPatch, rig: _Rig
) -> None:
    monkeypatch.setenv("MEME_COPY_LANE", "paper")

    def parked_build(rpc: object, feed: object, **kwargs: Any) -> Any:
        async def stream(wallets: Collection[str]) -> AsyncIterator[str]:
            yield "first"
            await asyncio.Event().wait()

        return SimpleNamespace(stream=stream)

    monkeypatch.setattr(copy_main, "build_leader_source", parked_build)
    lane = build_copy_lane(_ctx(), _heartbeat)
    assert lane is not None
    got = asyncio.Event()

    async def consume() -> None:
        async for _ in lane.source.stream(["W1"]):
            got.set()

    task = asyncio.ensure_future(consume())
    await asyncio.wait_for(got.wait(), timeout=5)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert [feed.closed for feed in rig.feeds] == [1]


async def test_a_crash_inside_the_lane_restarts_it_and_spares_its_siblings(
    monkeypatch: pytest.MonkeyPatch, rig: _Rig
) -> None:
    monkeypatch.setenv("MEME_COPY_LANE", "paper")
    rig.lane_crashes = 2
    lane = build_copy_lane(_ctx(), _heartbeat)
    assert lane is not None
    sibling_alive = asyncio.Event()

    async def sibling() -> None:
        sibling_alive.set()
        await asyncio.Event().wait()

    async with asyncio.timeout(5), asyncio.TaskGroup() as group:
        other = group.create_task(sibling(), name="meme-other")
        runner = group.create_task(lane.run(), name="meme-copy-lane")
        await rig.third_call.wait()  # crashed twice, the third call is the one that parks
        assert sibling_alive.is_set()
        assert not other.done() and not runner.done()  # a crash would have cancelled the sibling
        other.cancel()
        runner.cancel()
    assert len(rig.lane_calls) == 3


async def test_a_lane_that_returns_is_restarted_not_left_dead(
    monkeypatch: pytest.MonkeyPatch, rig: _Rig
) -> None:
    monkeypatch.setenv("MEME_COPY_LANE", "paper")
    calls = 0

    async def returns_once(**kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        if calls > 1:
            await asyncio.Event().wait()

    monkeypatch.setattr(copy_main, "start_copy_lane", returns_once)
    lane = build_copy_lane(_ctx(), _heartbeat)
    assert lane is not None
    task = asyncio.ensure_future(lane.run())
    for _ in range(200):
        if calls >= 2:
            break
        await asyncio.sleep(0.01)
    assert calls == 2
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


async def test_cancelling_the_lane_is_not_swallowed(
    monkeypatch: pytest.MonkeyPatch, rig: _Rig
) -> None:
    monkeypatch.setenv("MEME_COPY_LANE", "paper")
    lane = build_copy_lane(_ctx(), _heartbeat)
    assert lane is not None
    task = asyncio.ensure_future(lane.run())
    await asyncio.wait_for(rig.lane_started.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def _enabled(monkeypatch: pytest.MonkeyPatch, ctx: Any) -> None:
    def load_config(settings: object) -> MemeConfig:
        return MemeConfig(
            enabled=True, lab_enabled=False, creator_watch_enabled=False, fast_lane_enabled=False
        )

    def build_context(*args: object, **kwargs: object) -> tuple[Any, dict[str, object]]:
        return ctx, {}

    monkeypatch.setattr(meme_main, "load_config", load_config)
    monkeypatch.setattr(meme_main, "build_context", build_context)


async def test_run_meme_with_the_flag_off_starts_nothing_and_opens_nothing(
    monkeypatch: pytest.MonkeyPatch, chain: Any, db: _Db, nothing_may_open: None
) -> None:
    monkeypatch.delenv("MEME_COPY_LANE", raising=False)
    _enabled(monkeypatch, SimpleNamespace(session_factory=object(), trades=None, activity=None,
                                          risk=None, wallets=None, launch_lane=None))  # fmt: skip
    task = asyncio.ensure_future(meme_main.run_meme(_runtime()))
    await asyncio.wait_for(chain.started.wait(), timeout=5)
    await asyncio.sleep(0.05)
    assert not task.done()
    assert "meme-copy-lane" not in {t.get_name() for t in asyncio.all_tasks()}
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_run_meme_with_paper_isolates_a_lane_crash_and_closes_the_source(
    monkeypatch: pytest.MonkeyPatch, chain: Any, db: _Db, rig: _Rig
) -> None:
    monkeypatch.setenv("MEME_COPY_LANE", "paper")
    ctx = SimpleNamespace(session_factory=object(), chain=object(), trades=None, activity=None,
                          risk=None, wallets=None, launch_lane=None)  # fmt: skip
    _enabled(monkeypatch, ctx)
    rig.lane_crashes = 1
    task = asyncio.ensure_future(meme_main.run_meme(_runtime()))
    await asyncio.wait_for(chain.started.wait(), timeout=5)
    for _ in range(300):  # the lane crashed once and came back
        if len(rig.lane_calls) >= 2:
            break
        await asyncio.sleep(0.01)
    assert len(rig.lane_calls) == 2
    assert rig.lane_calls[0]["chain"] is ctx.chain
    assert rig.lane_calls[0]["session_factory"] is ctx.session_factory
    assert not task.done()  # the worker's TaskGroup is alive
    assert rig.rpcs[0].closed == 0
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert rig.rpcs[0].closed == 1  # shutdown closed the lane's RPC client
