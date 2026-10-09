"""Copy-trade pilot (H-037): the NATS leader source against a scripted fake socket — no network.

Frames follow the shape of the 06/10 probe samples (KB-0186); every wallet/mint/signature/credential
is an invented placeholder.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from structlog.testing import capture_logs

from hunter_exchanges.pumpfun.leader_events import LeaderConfirmation, LeaderEvent, LeaderGap
from hunter_exchanges.pumpfun.leader_source_nats import NatsLeaderSource
from hunter_exchanges.pumpfun.leader_source_nats_io import WalletSnapshot
from hunter_exchanges.pumpfun.leader_source_nats_wire import NatsAuthError, NatsConfig, NatsRefused

pytestmark = pytest.mark.unit

W, W2, M = "WalletA", "WalletB", "MintA"
PW = "TEST-ONLY-NOT-A-REAL-PASSWORD"
CFG = NatsConfig("wss://core.nats.invalid", "subscriber", PW)
T0 = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)
Item = LeaderEvent | LeaderGap | LeaderConfirmation


def msg(wallet: str, mint: str, balance: str, sig: str, slot: int = 100, idx: int = 1) -> bytes:
    body: dict[str, Any] = {
        "walletAddress": wallet,
        "tokenMint": mint,
        "balance": balance,
        "slot": slot,
        "timestamp": "2026-10-09T12:00:00.000Z",
        "txSignature": sig,
        "txIndex": str(idx),
    }
    payload = json.dumps(body).encode()
    return b"MSG account_balance_change.%s.%s 1 %d\r\n%s\r\n" % (
        wallet.encode(),
        mint.encode(),
        len(payload),
        payload,
    )


def sol(wallet: str, balance: str, sig: str, slot: int = 100, idx: int = 1) -> bytes:
    return msg(wallet, "SOL", balance, sig, slot, idx)


class FakeWs:
    """Scripted socket: INFO on open; PONG answers CONNECT unless ``reject`` is set."""

    def __init__(self, *, reject: str | None = None, drop_after_ready: bool = False) -> None:
        self.inbox: asyncio.Queue[bytes | Exception] = asyncio.Queue()
        self.inbox.put_nowait(b"INFO {}\r\n")
        self.sent: list[str] = []
        self.reject, self.drop = reject, drop_after_ready

    def push(self, data: bytes | Exception) -> None:
        self.inbox.put_nowait(data)

    async def recv(self) -> bytes:
        item = await self.inbox.get()
        if isinstance(item, Exception):
            raise item
        return item

    async def send(self, message: str | bytes) -> None:
        text = message if isinstance(message, str) else message.decode()
        self.sent.append(text)
        if text.startswith("CONNECT"):
            self.push(f"-ERR '{self.reject}'\r\n".encode() if self.reject else b"PONG\r\n")
            if self.drop:
                self.push(ConnectionError("reset right after ready"))

    def subs(self) -> list[str]:
        return [s.split()[1] for s in self.sent if s.startswith("SUB ")]


class Harness:
    def __init__(self, sockets: list[FakeWs], *, configs: list[Any] | None = None) -> None:
        self.sockets = list(sockets)
        self.opened: list[FakeWs] = []
        self.fetches = 0
        self.configs = configs or [CFG]
        self.delays: list[float] = []
        self.clock = T0
        self.mono = 0.0

    async def fetch(self) -> NatsConfig:
        self.fetches += 1
        cfg = self.configs[min(self.fetches, len(self.configs)) - 1]
        if isinstance(cfg, Exception):
            raise cfg
        return cfg  # type: ignore[no-any-return]

    @asynccontextmanager
    async def connect(self, url: str) -> AsyncGenerator[FakeWs]:
        assert url == "wss://core.nats.invalid"
        if not self.sockets:
            await asyncio.sleep(3600)  # out of scripted sockets: a server that never answers
        ws = self.sockets.pop(0)
        self.opened.append(ws)
        yield ws

    async def sleep(self, delay: float) -> None:
        self.delays.append(delay)
        await asyncio.sleep(0)

    def wall(self) -> datetime:
        self.clock += timedelta(milliseconds=10)
        return self.clock

    def tick(self) -> float:
        self.mono += 0.001
        return self.mono

    def source(self, **kw: Any) -> NatsLeaderSource:
        return NatsLeaderSource(
            fetch_config=self.fetch,
            connect=self.connect,
            wall=self.wall,
            mono=kw.pop("mono", self.tick),
            sleep=self.sleep,
            rand=lambda: 0.5,
            idle_timeout_s=kw.pop("idle_timeout_s", 5.0),
            **kw,
        )


def seeder(
    tokens: dict[str, tuple[int, int]] | None = None, lamports: int = 10**10, slot: int = 50
) -> Any:
    calls: list[str] = []

    async def seed(wallet: str) -> WalletSnapshot:
        calls.append(wallet)
        return WalletSnapshot(lamports, slot, dict(tokens or {}), slot)

    seed.calls = calls  # type: ignore[attr-defined]
    return seed


async def take(agen: AsyncIterator[Item], n: int) -> list[Item]:
    return [await asyncio.wait_for(agen.__anext__(), 3) for _ in range(n)]


async def until(agen: AsyncIterator[Item], kind: type, *, tries: int = 20) -> Any:
    for _ in range(tries):
        item = (await take(agen, 1))[0]
        if isinstance(item, kind):
            return item
    raise AssertionError(f"no {kind.__name__} arrived")


async def ready(agen: AsyncIterator[Item]) -> None:
    """Consume the startup gap pair (``nats_connect`` open, then closed at ready)."""
    first, second = await take(agen, 2)
    assert isinstance(first, LeaderGap) and (first.reason, first.end) == ("nats_connect", None)
    assert isinstance(second, LeaderGap) and second.end is not None and second.start == first.start


# --------------------------------------------------------------------------- the happy path
async def test_connects_subscribes_per_wallet_and_emits_each_message_at_once() -> None:
    ws = FakeWs()
    h = Harness([ws])
    src = h.source(seeder=seeder())
    agen = src.stream([W, W2])
    await ready(agen)
    assert sorted(ws.subs()) == [f"account_balance_change.{W}.*", f"account_balance_change.{W2}.*"]
    assert any(s.startswith("CONNECT") and PW in s for s in ws.sent)
    await take(agen, 2)  # the two nats_unseeded gaps opened at ready...
    await take(agen, 2)  # ...and closed as the seeds land
    ws.push(sol(W, "9.0", "s1", slot=100) + msg(W, M, "4", "s1", slot=100))  # ONE frame, two legs
    ev = await until(agen, LeaderEvent)
    assert (ev.wallet, ev.mint, ev.side, ev.token_delta_atoms) == (W, M, "buy", 4_000_000)
    assert (ev.source, ev.confirmed, ev.block_time, ev.signature) == ("nats", False, None, "s1")
    assert ev.sol_delta_lamports == -1_000_000_000 and not ev.multi_mint
    assert ev.first_seen_at == ev.fields_complete_at  # the clock was read once for the frame
    assert ev.server_ts == datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)
    snap = src.stats.snapshot()
    assert snap["receive_to_emit"]["n"] == 1
    await agen.aclose()  # type: ignore[attr-defined]


async def test_a_buy_completes_when_the_sol_leg_arrives_and_keeps_the_first_sight() -> None:
    ws = FakeWs()
    h = Harness([ws])
    agen = h.source(seeder=seeder()).stream([W])
    await ready(agen)
    await take(agen, 2)
    ws.push(msg(W, M, "4", "s1", slot=100))  # token leg first
    await asyncio.sleep(0.05)
    ws.push(sol(W, "9.0", "s1", slot=100))
    ev = await until(agen, LeaderEvent)
    assert ev.sol_delta_lamports == -1_000_000_000
    assert ev.first_seen_at < ev.fields_complete_at
    await agen.aclose()  # type: ignore[attr-defined]


async def test_a_buy_whose_sol_leg_never_comes_is_emitted_by_the_timer_with_none() -> None:
    ws = FakeWs()
    h = Harness([ws])
    src = h.source(seeder=seeder())
    agen = src.stream([W])
    await ready(agen)
    await take(agen, 2)
    ws.push(msg(W, M, "4", "s1", slot=100))
    ev = await until(agen, LeaderEvent)  # the 300 ms timer, not the next frame
    assert ev.sol_delta_lamports is None and src.stats.counters["pair_timeout"] == 1
    await agen.aclose()  # type: ignore[attr-defined]


async def test_a_sell_is_emitted_immediately_without_waiting_for_sol() -> None:
    ws = FakeWs()
    h = Harness([ws])
    agen = h.source(seeder=seeder({M: (10_000_000, 50)})).stream([W])
    await ready(agen)
    await take(agen, 2)
    ws.push(msg(W, M, "6", "s1", slot=100))
    ev = await until(agen, LeaderEvent)
    assert (ev.side, ev.position_after_atoms, ev.sol_delta_lamports) == ("sell", 6_000_000, None)
    await agen.aclose()  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- coverage the session announces
async def test_a_wallet_is_unseeded_until_its_snapshot_lands_and_the_seed_is_retried() -> None:
    ws = FakeWs()
    h = Harness([ws])
    attempts = {"n": 0}

    async def flaky(wallet: str) -> WalletSnapshot:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ConnectionError("rpc down")
        return WalletSnapshot(10**10, 50, {}, 50)

    src = h.source(seeder=flaky)
    agen = src.stream([W])
    await ready(agen)
    opened = (await take(agen, 1))[0]
    assert isinstance(opened, LeaderGap) and (opened.wallet, opened.reason, opened.end) == (
        W,
        "nats_unseeded",
        None,
    )
    closed = (await take(agen, 1))[0]
    assert isinstance(closed, LeaderGap) and closed.end is not None and closed.start == opened.start
    assert attempts["n"] == 3 and src.stats.counters["seed_failed"] == 2
    assert len([d for d in h.delays if d >= 1.0]) >= 2  # backoff between attempts
    await agen.aclose()  # type: ignore[attr-defined]


async def test_without_a_seeder_there_is_no_unseeded_gap_and_the_first_leg_is_only_a_baseline() -> (
    None
):
    ws = FakeWs()
    h = Harness([ws])
    src = h.source(seeder=None)
    agen = src.stream([W])
    await ready(agen)
    ws.push(msg(W, M, "1", "s1", slot=1))
    ws.push(msg(W, M, "2", "s2", slot=2) + sol(W, "9.0", "s2", slot=2))
    ev = await until(agen, LeaderEvent)
    assert (
        ev.token_delta_atoms == 1_000_000 and ev.sol_delta_lamports is None
    )  # SOL had no baseline either
    assert src.stats.counters["no_baseline"] == 2
    await agen.aclose()  # type: ignore[attr-defined]


async def test_a_frame_that_cannot_be_read_is_a_gap_for_that_wallet() -> None:
    ws = FakeWs()
    h = Harness([ws])
    src = h.source(seeder=None)
    agen = src.stream([W])
    await ready(agen)
    junk = b"not json at all"
    ws.push(b"MSG account_balance_change.%s.X 1 %d\r\n%s\r\n" % (W.encode(), len(junk), junk))
    gap = (await take(agen, 1))[0]
    assert isinstance(gap, LeaderGap)
    assert (gap.wallet, gap.reason) == (W, "nats_malformed")
    assert gap.end is not None and gap.end > gap.start  # an interval a consumer can test against
    ws.push(msg("Stranger", M, "1", "sx"))  # a wallet we did not subscribe to
    assert src.stats.counters["malformed"] == 1
    await agen.aclose()  # type: ignore[attr-defined]


async def test_another_mints_scale_is_counted_not_a_gap() -> None:
    ws = FakeWs()
    h = Harness([ws])
    src = h.source(seeder=None)
    agen = src.stream([W])
    await ready(agen)
    ws.push(msg(W, "OtherScale", "1.123456789", "sx"))
    ws.push(msg(W, M, "1", "s1", slot=1))
    ws.push(msg(W, M, "2", "s2", slot=2))
    ev = await until(agen, LeaderEvent)  # no gap came in between
    assert src.stats.counters["unsupported_scale"] == 1 and ev.signature == "s2"
    await agen.aclose()  # type: ignore[attr-defined]


async def test_a_bug_in_one_message_costs_that_message_not_the_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hunter_exchanges.pumpfun import leader_source_nats_state as state

    real = state.LegProcessor.on_leg
    calls = {"n": 0}

    def flaky(self: Any, leg: Any, **kw: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return real(self, leg, **kw)

    monkeypatch.setattr(state.LegProcessor, "on_leg", flaky)
    ws = FakeWs()
    h = Harness([ws])
    src = h.source(seeder=None)
    agen = src.stream([W])
    await ready(agen)
    ws.push(msg(W, M, "1", "s1", slot=1))  # raises inside on_leg
    gap = (await take(agen, 1))[0]
    assert isinstance(gap, LeaderGap) and gap.reason == "nats_message_error" and gap.wallet == W
    ws.push(msg(W, M, "2", "s2", slot=2))
    ws.push(msg(W, M, "5", "s3", slot=3) + sol(W, "9.0", "s3", slot=3))
    ev = await until(agen, LeaderEvent)
    assert ev.signature == "s3" and src.stats.counters["message_error"] == 1 and len(h.opened) == 1
    await agen.aclose()  # type: ignore[attr-defined]


async def test_server_ping_gets_a_pong_and_a_permissions_violation_is_a_wallet_gap() -> None:
    ws = FakeWs()
    h = Harness([ws])
    agen = h.source(seeder=None).stream([W, W2])
    await ready(agen)
    ws.push(b"PING\r\n")
    err = f"-ERR 'Permissions Violation for Subscription to \"account_balance_change.{W2}.*\"'\r\n"
    ws.push(err.encode())
    gap = (await take(agen, 1))[0]
    assert isinstance(gap, LeaderGap)
    assert (gap.wallet, gap.reason) == (W2, "nats_subscription_refused")
    assert "PONG\r\n" in ws.sent
    await agen.aclose()  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- reconnects
async def test_a_dropped_socket_is_a_gap_and_the_credential_is_reused_for_a_fast_reconnect() -> (
    None
):
    ws1, ws2 = FakeWs(), FakeWs()
    h = Harness([ws1, ws2])
    agen = h.source(seeder=None).stream([W])
    await ready(agen)
    ws1.push(ConnectionError("reset"))
    gap = (await take(agen, 1))[0]
    assert isinstance(gap, LeaderGap) and (gap.reason, gap.end) == ("nats_disconnect", None)
    closed = (await take(agen, 1))[0]
    assert isinstance(closed, LeaderGap) and closed.end is not None and closed.start == gap.start
    assert h.fetches == 1 and len(h.opened) == 2  # the page was not fetched again
    assert 0 < h.delays[0] <= 1.0  # reconnect fast
    await agen.aclose()  # type: ignore[attr-defined]


async def test_baselines_and_in_flight_legs_are_forgotten_on_reconnect() -> None:
    ws1, ws2 = FakeWs(), FakeWs()
    h = Harness([ws1, ws2])
    src = h.source(seeder=None)
    agen = src.stream([W])
    await ready(agen)
    ws1.push(msg(W, M, "2", "s1", slot=10))
    ws1.push(ConnectionError("reset"))
    await take(agen, 2)
    ws2.push(msg(W, M, "9", "s2", slot=20))  # a delta against the stale 2 would be a lie
    await asyncio.sleep(0.05)
    assert src.stats.counters["no_baseline"] == 2
    await agen.aclose()  # type: ignore[attr-defined]


async def test_after_a_reconnect_the_wallets_are_reseeded_and_announced_unseeded_again() -> None:
    ws1, ws2 = FakeWs(), FakeWs()
    h = Harness([ws1, ws2])
    seed = seeder()
    agen = h.source(seeder=seed).stream([W])
    await ready(agen)
    await take(agen, 2)
    ws1.push(ConnectionError("reset"))
    items = await take(agen, 4)  # disconnect, its close + the unseeded pair of the new session
    reasons = [i.reason for i in items if isinstance(i, LeaderGap)]
    assert "nats_unseeded" in reasons and len(seed.calls) == 2
    await agen.aclose()  # type: ignore[attr-defined]


async def test_auth_refusal_is_a_named_gap_and_the_credential_is_reread() -> None:
    bad, good = FakeWs(reject="Authorization Violation"), FakeWs()
    h = Harness([bad, good])
    agen = h.source(seeder=None).stream([W])
    reasons = [g.reason for g in await take(agen, 3) if isinstance(g, LeaderGap)]
    assert "nats_auth" in reasons
    assert h.fetches == 2 and len(h.opened) == 2
    await agen.aclose()  # type: ignore[attr-defined]


async def test_a_page_without_the_credential_keeps_trying_slowly_and_says_nats_auth() -> None:
    ws = FakeWs()
    h = Harness([ws], configs=[NatsAuthError("gone"), NatsAuthError("gone"), CFG])
    agen = h.source(seeder=None).stream([W])
    first = (await take(agen, 1))[0]
    second = (await take(agen, 1))[0]
    assert isinstance(first, LeaderGap) and first.reason == "nats_connect"
    assert isinstance(second, LeaderGap) and second.reason == "nats_auth" and second.end is None
    assert h.delays and min(h.delays) >= 1.0  # auth failures never hammer the page
    await agen.aclose()  # type: ignore[attr-defined]


async def test_rate_limit_on_the_page_backs_off_long_inside_the_ceiling_and_is_a_system_event() -> (
    None
):
    ws = FakeWs()
    h = Harness([ws], configs=[NatsRefused(429), CFG])
    agen = h.source(seeder=None).stream([W])
    with capture_logs() as logs:
        gaps = [g for g in await take(agen, 3) if isinstance(g, LeaderGap)]
    assert "nats_refused_429" in [g.reason for g in gaps]
    assert any(d >= 60 for d in h.delays) and all(d <= 600 for d in h.delays)
    assert [e for e in logs if e["event"] == "system_event"]
    assert PW not in str(logs)
    await agen.aclose()  # type: ignore[attr-defined]


async def test_the_refusal_ceiling_is_a_real_ceiling_even_with_the_worst_jitter() -> None:
    h = Harness([])
    src = NatsLeaderSource(fetch_config=h.fetch, connect=h.connect, rand=lambda: 1.0)
    assert max(src.delay_for(60.0, 600.0, n) for n in range(40)) == 600.0


async def test_a_silent_socket_is_dropped_after_the_idle_timeout() -> None:
    ws1, ws2 = FakeWs(), FakeWs()
    h = Harness([ws1, ws2])
    agen = h.source(seeder=None, idle_timeout_s=0.05).stream([W])
    await ready(agen)
    gap = (await take(agen, 1))[0]
    assert isinstance(gap, LeaderGap) and gap.reason == "nats_disconnect"
    await agen.aclose()  # type: ignore[attr-defined]


async def test_a_flapping_server_gets_slower_retries_not_a_hammered_home_page() -> None:
    sockets = [FakeWs(drop_after_ready=True) for _ in range(5)]
    h = Harness(sockets)
    agen = h.source(seeder=None).stream([W])
    await take(agen, 1)  # starts the generator
    for _ in range(200):
        if len(h.opened) >= 5:
            break
        await asyncio.sleep(0.01)
    assert len(h.opened) >= 5 and h.fetches == 1  # the page is not re-fetched per flap
    assert h.delays[:4] == sorted(h.delays[:4]) and h.delays[3] > h.delays[0] * 4  # 0.1 0.2 0.4 0.8
    await agen.aclose()  # type: ignore[attr-defined]


async def test_a_session_that_stayed_up_resets_the_backoff() -> None:
    ws1, ws2 = FakeWs(), FakeWs()
    h = Harness([ws1, ws2])
    agen = h.source(seeder=None).stream([W])
    await ready(agen)
    h.mono += 120.0  # the first session lived two minutes
    ws1.push(ConnectionError("reset"))
    await take(agen, 2)
    assert h.delays == [0.1]
    await agen.aclose()  # type: ignore[attr-defined]


async def test_a_reused_credential_that_gets_refused_is_replaced_by_a_fresh_page_read_at_once() -> (
    None
):
    new_cfg = NatsConfig("wss://core.nats.invalid", "subscriber", "TEST-ONLY-ROTATED-PASSWORD")
    ws1, ws2, ws3 = FakeWs(), FakeWs(reject="Authorization Violation"), FakeWs()
    h = Harness([ws1, ws2, ws3], configs=[CFG, new_cfg])
    agen = h.source(seeder=None).stream([W])
    await ready(agen)
    ws1.push(ConnectionError("reset"))  # reconnect #1 reuses CFG from memory -> refused (rotation)
    for _ in range(100):
        if len(h.opened) >= 3:
            break
        await asyncio.sleep(0.01)
    assert h.fetches == 2  # the page was re-read exactly once, right after the refusal
    assert all(d <= 1.0 for d in h.delays)  # no 5 s auth wait for a rotation
    assert any("TEST-ONLY-ROTATED-PASSWORD" in s for s in ws3.sent if s.startswith("CONNECT"))
    await agen.aclose()  # type: ignore[attr-defined]


async def test_a_credential_older_than_the_ttl_is_re_read_from_the_page() -> None:
    ws1, ws2 = FakeWs(), FakeWs()
    h = Harness([ws1, ws2])
    agen = h.source(seeder=None).stream([W])
    await ready(agen)
    h.mono += 700.0
    ws1.push(ConnectionError("reset"))
    await take(agen, 2)
    assert h.fetches == 2
    await agen.aclose()  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- secrets and lifecycle
async def test_an_exception_that_echoes_the_credential_never_reaches_a_log() -> None:
    """A transport error whose free text carries the password: only the class name is logged."""
    ws = FakeWs()
    h = Harness([ws])
    agen = h.source(seeder=None).stream([W])
    await ready(agen)
    with capture_logs() as logs:
        ws.push(ConnectionError(f"server closed: bad CONNECT {{'pass': '{PW}'}}"))
        await take(agen, 1)
    assert logs and PW not in str(logs) and "bad CONNECT" not in str(logs)
    await agen.aclose()  # type: ignore[attr-defined]


async def test_closing_the_stream_stops_the_background_work_and_the_pairing_timers() -> None:
    ws = FakeWs()
    h = Harness([ws])
    agen = h.source(seeder=seeder()).stream([W])
    await ready(agen)
    await take(agen, 2)
    ws.push(msg(W, M, "4", "s1", slot=100))  # a buy now waits on a timer
    await asyncio.sleep(0.02)
    before = {t for t in asyncio.all_tasks() if t is not asyncio.current_task()}
    await agen.aclose()  # type: ignore[attr-defined]
    await asyncio.sleep(0.4)  # past the pairing deadline: a live timer would have fired
    assert all(t.done() for t in before)


async def test_empty_wallet_set_is_refused() -> None:
    h = Harness([])
    with pytest.raises(ValueError, match="wallet"):
        await h.source(seeder=None).stream([]).__anext__()


# --------------------------------------------------------------------------- resync after a lost leg
async def test_a_lost_leg_resets_that_wallets_baseline_and_reseeds_it() -> None:
    """A frame that cannot be read may have been the sale to zero: the next balance would otherwise turn
    into a false sell of 90. The wallet is degraded (an open gap) until a fresh snapshot lands."""
    ws = FakeWs()
    h = Harness([ws])
    seed = seeder()
    src = h.source(seeder=seed)
    agen = src.stream([W])
    await ready(agen)
    await take(agen, 2)  # unseeded pair
    junk = b"not json at all"
    ws.push(b"MSG account_balance_change.%s.X 1 %d\r\n%s\r\n" % (W.encode(), len(junk), junk))
    opened = (await take(agen, 1))[0]
    assert isinstance(opened, LeaderGap) and (opened.wallet, opened.reason, opened.end) == (
        W,
        "nats_malformed",
        None,
    )
    closed = (await take(agen, 1))[0]
    assert isinstance(closed, LeaderGap) and closed.end is not None and closed.start == opened.start
    assert len(seed.calls) == 2  # the initial snapshot and the resync
    await agen.aclose()  # type: ignore[attr-defined]


async def test_without_a_seeder_a_lost_leg_is_an_interval_gap_and_the_baseline_is_relearned() -> (
    None
):
    ws = FakeWs()
    h = Harness([ws])
    src = h.source(seeder=None)
    agen = src.stream([W])
    await ready(agen)
    ws.push(msg(W, M, "1", "s0", slot=1))  # a baseline
    junk = b"x"
    ws.push(b"MSG account_balance_change.%s.X 1 %d\r\n%s\r\n" % (W.encode(), len(junk), junk))
    gap = (await take(agen, 1))[0]
    assert isinstance(gap, LeaderGap) and gap.end is not None and gap.end > gap.start  # testable
    ws.push(msg(W, M, "9", "s1", slot=2))  # must NOT become a delta against the pre-loss baseline
    await asyncio.sleep(0.05)
    assert src.stats.counters["no_baseline"] == 2
    await agen.aclose()  # type: ignore[attr-defined]


async def test_a_loss_during_a_seed_restarts_the_seed_so_it_cannot_predate_the_loss() -> None:
    ws = FakeWs()
    h = Harness([ws])
    gate = asyncio.Event()
    calls: list[int] = []

    async def slow(wallet: str) -> WalletSnapshot:
        calls.append(1)
        if len(calls) == 1:
            await gate.wait()  # the first read is still in flight when the loss happens
        return WalletSnapshot(10**10, 50, {}, 50)

    agen = h.source(seeder=slow).stream([W])
    await ready(agen)
    await take(agen, 1)  # nats_unseeded opened
    junk = b"x"
    ws.push(b"MSG account_balance_change.%s.X 1 %d\r\n%s\r\n" % (W.encode(), len(junk), junk))
    items = await take(agen, 2)
    assert len(calls) == 2  # restarted, not reused
    assert any(isinstance(i, LeaderGap) and i.end is not None for i in items)
    await agen.aclose()  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- silence per wallet
async def test_a_quiet_wallet_that_was_active_this_hour_is_announced_and_closed_on_its_next_leg() -> (
    None
):
    import time

    ws = FakeWs()
    h = Harness([ws])
    agen = h.source(
        seeder=None, mono=time.perf_counter, silence_s=0.05, active_s=5.0, watch_interval_s=0.01
    ).stream([W, W2])
    await ready(agen)
    ws.push(msg(W, M, "1", "s1", slot=1))
    gap = await until(agen, LeaderGap)
    assert (gap.wallet, gap.reason, gap.end) == (W, "nats_silent", None)  # only W ever spoke
    ws.push(msg(W, M, "2", "s2", slot=2) + sol(W, "9.0", "s2", slot=2))
    closed = await until(agen, LeaderGap)
    assert (closed.wallet, closed.reason) == (W, "nats_silent") and closed.end is not None
    await agen.aclose()  # type: ignore[attr-defined]


async def test_the_gap_closes_before_the_event_that_ended_the_silence() -> None:
    import time

    ws = FakeWs()
    h = Harness([ws])
    agen = h.source(
        seeder=None, mono=time.perf_counter, silence_s=0.05, active_s=5.0, watch_interval_s=0.01
    ).stream([W])
    await ready(agen)
    ws.push(msg(W, M, "1", "s1", slot=1))
    await until(agen, LeaderGap)  # nats_silent opened
    ws.push(sol(W, "9.0", "s2", slot=2) + msg(W, M, "2", "s2", slot=2))
    first = (await take(agen, 1))[0]
    assert isinstance(first, LeaderGap) and first.end is not None  # closed first...
    ev = await until(agen, LeaderEvent)
    assert ev.first_seen_at >= first.end  # ...so the event is outside [start, end)
    await agen.aclose()  # type: ignore[attr-defined]


async def test_a_wallet_never_heard_this_session_is_not_called_silent() -> None:
    import time

    ws = FakeWs()
    h = Harness([ws])
    agen = h.source(
        seeder=None, mono=time.perf_counter, silence_s=0.02, active_s=5.0, watch_interval_s=0.01
    ).stream([W])
    await ready(agen)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(agen.__anext__(), 0.2)
    await agen.aclose()  # type: ignore[attr-defined]


async def test_pairing_timers_that_fired_are_forgotten_and_closing_never_fires_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hunter_exchanges.pumpfun import leader_source_nats_session as module

    flushed: list[float] = []
    real = module.NatsSession.flush_pairing

    def counting(self: Any, deadline: float) -> None:
        flushed.append(deadline)
        real(self, deadline)

    monkeypatch.setattr(module.NatsSession, "flush_pairing", counting)
    ws = FakeWs()
    h = Harness([ws])
    agen = h.source(seeder=seeder()).stream([W])
    await ready(agen)
    await take(agen, 2)
    ws.push(msg(W, M, "4", "s1", slot=100))
    await until(agen, LeaderEvent)  # the first timer fired
    assert len(flushed) == 1
    ws.push(msg(W, M, "6", "s2", slot=101))
    await asyncio.sleep(0.05)
    await agen.aclose()  # type: ignore[attr-defined]
    await asyncio.sleep(0.4)
    assert len(flushed) == 1  # the second timer was cancelled, not fired after the close


async def test_a_silent_wallet_is_resynced_while_it_is_quiet_so_the_next_leg_has_a_fresh_baseline() -> (
    None
):
    """A sale lost during the silence must not become a false sell of 90 when the wallet speaks again:
    the snapshot is retaken the moment the silence is announced, not when the wallet resumes."""
    import time

    ws = FakeWs()
    h = Harness([ws])
    state = {"tokens": {M: (5_000_000, 50)}, "slot": 50}
    calls: list[int] = []

    async def seed(wallet: str) -> WalletSnapshot:
        calls.append(1)
        return WalletSnapshot(10**10, state["slot"], dict(state["tokens"]), state["slot"])  # type: ignore[arg-type]

    agen = h.source(
        seeder=seed, mono=time.perf_counter, silence_s=0.05, active_s=5.0, watch_interval_s=0.01
    ).stream([W])
    await ready(agen)
    await take(agen, 2)
    ws.push(msg(W, M, "6", "s1", slot=100))  # the wallet speaks once (a buy of 1)
    await until(agen, LeaderGap)  # ... then falls silent: nats_silent opens
    state["tokens"], state["slot"] = {}, 150  # meanwhile it sold everything (not seen by NATS)
    await asyncio.sleep(0.1)
    assert len(calls) >= 2  # resynced during the silence
    ws.push(sol(W, "9.0", "s2", slot=200) + msg(W, M, "10", "s2", slot=200))
    ev = await until(agen, LeaderEvent)
    assert (ev.side, ev.token_delta_atoms) == (
        "buy",
        10_000_000,
    )  # vs the fresh zero, not a sell of 90
    await agen.aclose()  # type: ignore[attr-defined]
