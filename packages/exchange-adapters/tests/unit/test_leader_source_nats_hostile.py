"""Copy-trade pilot (H-037), security review R1: what a hostile or failing server / home page can make
the NATS leader source do. Offline; reuses the scripted socket of ``test_leader_source_nats``."""

from __future__ import annotations

import asyncio

import pytest
from structlog.testing import capture_logs

from hunter_exchanges.pumpfun.leader_events import LeaderGap
from hunter_exchanges.pumpfun.leader_source_nats import NatsLeaderSource
from hunter_exchanges.pumpfun.leader_source_nats_io import WalletSnapshot
from hunter_exchanges.pumpfun.leader_source_nats_wire import NatsRefused

from .test_leader_source_nats import CFG, FakeWs, Harness, W, ready, seeder, take, until

pytestmark = pytest.mark.unit

JUNK = b"x"


def junk_frame() -> bytes:
    return b"MSG account_balance_change.%s.X 1 %d\r\n%s\r\n" % (W.encode(), len(JUNK), JUNK)


# --------------------------------------------------------------------------- HIGH-1 / MEDIUM-1
async def test_a_negative_length_from_the_server_drops_the_connection_and_names_the_gap() -> None:
    ws1, ws2 = FakeWs(), FakeWs()
    h = Harness([ws1, ws2])
    agen = h.source(seeder=None).stream([W])
    await ready(agen)
    ws1.push(b"MSG account_balance_change.x.y 1 -100\r\n")
    gap = await until(agen, LeaderGap)
    assert (gap.wallet, gap.reason, gap.end) == (None, "nats_protocol_error", None)
    await until(agen, LeaderGap)  # closed on the reconnect
    assert len(h.opened) == 2
    await agen.aclose()  # type: ignore[attr-defined]


async def test_an_oversized_declared_message_is_a_protocol_error_too() -> None:
    ws1, ws2 = FakeWs(), FakeWs()
    h = Harness([ws1, ws2])
    agen = h.source(seeder=None).stream([W])
    await ready(agen)
    ws1.push(b"MSG account_balance_change.x.y 1 999999999\r\n")
    assert (await until(agen, LeaderGap)).reason == "nats_protocol_error"
    await agen.aclose()  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- MEDIUM-2: no RPC storm
async def test_many_malformed_legs_of_one_wallet_cost_at_most_one_more_seed() -> None:
    ws = FakeWs()
    h = Harness([ws])
    seed = seeder()
    agen = h.source(seeder=seed, seed_min_interval_s=0.3).stream([W])
    await ready(agen)
    await take(agen, 2)  # the unseeded pair of the initial snapshot
    assert len(seed.calls) == 1
    for _ in range(30):  # 30 hostile frames in well under a second
        ws.push(junk_frame())
        await asyncio.sleep(0.005)
    assert len(seed.calls) == 1  # debounced: nothing storms the RPC
    await asyncio.sleep(0.5)
    assert len(seed.calls) == 2  # exactly one coalesced resync
    assert len(h.opened) == 1
    await agen.aclose()  # type: ignore[attr-defined]


async def test_a_loss_during_a_seed_in_flight_reuses_it_and_asks_for_one_follow_up() -> None:
    ws = FakeWs()
    h = Harness([ws])
    gate = asyncio.Event()
    calls: list[int] = []

    async def slow(wallet: str) -> WalletSnapshot:
        calls.append(1)
        if len(calls) == 1:
            await gate.wait()
        return WalletSnapshot(10**10, 50, {}, 50)

    agen = h.source(seeder=slow, seed_min_interval_s=0.0).stream([W])
    await ready(agen)
    await take(agen, 1)
    for _ in range(10):
        ws.push(junk_frame())
    await asyncio.sleep(0.05)
    assert len(calls) == 1  # the in-flight read is not restarted ten times
    gate.set()
    await asyncio.sleep(0.1)
    assert len(calls) == 2  # one follow-up, because a loss happened while it was reading
    await agen.aclose()  # type: ignore[attr-defined]


async def test_the_seed_backoff_survives_new_triggers_instead_of_restarting_at_one_second() -> None:
    ws = FakeWs()
    h = Harness([ws])

    async def failing(wallet: str) -> WalletSnapshot:
        raise ConnectionError("rpc down")

    agen = h.source(seeder=failing, seed_min_interval_s=0.0).stream([W])
    await ready(agen)
    for _ in range(6):
        await asyncio.sleep(0.02)
        ws.push(junk_frame())
    await asyncio.sleep(0.05)
    seed_delays = [d for d in h.delays if d >= 1.0]
    assert seed_delays == sorted(seed_delays) and len(seed_delays) >= 4 and seed_delays[-1] > 1.0
    await agen.aclose()  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- MEDIUM-3: stop at the first block
async def test_a_home_page_error_uses_the_slow_ladder_and_honours_retry_after() -> None:
    ws = FakeWs()
    h = Harness([ws], configs=[NatsRefused(503, 300.0), CFG])
    agen = h.source(seeder=None).stream([W])
    await take(agen, 1)
    gap = await until(agen, LeaderGap)
    assert gap.reason == "nats_refused_503"
    assert h.delays[0] >= 300.0  # Retry-After wins over the 60 s base
    await agen.aclose()  # type: ignore[attr-defined]


@pytest.mark.parametrize("rand", [0.0, 0.5, 1.0])
def test_the_first_refusal_wait_is_at_least_the_base_whatever_the_jitter(rand: float) -> None:
    src = NatsLeaderSource(rand=lambda: rand)
    assert 60.0 <= src.delay_for(60.0, 600.0, 0) <= 75.0
    assert src.delay_for(60.0, 600.0, 20) <= 600.0  # jitter after the cap never breaks the ceiling


async def test_after_three_refusals_of_a_fresh_credential_the_nats_side_stops_for_an_hour() -> None:
    ws = FakeWs()
    h = Harness([ws], configs=[NatsRefused(403)] * 3 + [CFG])
    agen = h.source(seeder=None).stream([W])
    with capture_logs() as logs:
        reasons: list[str] = []
        while "nats_stopped" not in reasons:
            reasons.append((await until(agen, LeaderGap)).reason)
    assert h.fetches == 3 and h.delays[-1] >= 3600.0
    assert [e for e in logs if e.get("kind") == "leader_nats_stopped"]
    await agen.aclose()  # type: ignore[attr-defined]


async def test_three_auth_refusals_of_fresh_credentials_also_stop_it() -> None:
    sockets = [FakeWs(reject="Authorization Violation") for _ in range(3)] + [FakeWs()]
    h = Harness(sockets)
    agen = h.source(seeder=None).stream([W])
    reasons: list[str] = []
    while "nats_stopped" not in reasons:
        reasons.append((await until(agen, LeaderGap)).reason)
    assert "nats_auth" in reasons and h.fetches == 3 and h.delays[-1] >= 3600.0
    await agen.aclose()  # type: ignore[attr-defined]


async def test_a_reused_credential_refused_is_a_rotation_not_a_strike() -> None:
    ws1 = FakeWs()
    rejected = [FakeWs(reject="Authorization Violation") for _ in range(2)]
    h = Harness([ws1, *rejected, FakeWs()], configs=[CFG, CFG, CFG])
    agen = h.source(seeder=None).stream([W])
    await ready(agen)
    ws1.push(ConnectionError("reset"))
    for _ in range(100):
        if len(h.opened) >= 4:
            break
        await asyncio.sleep(0.01)
    assert all(d < 3600.0 for d in h.delays)
    await agen.aclose()  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- review R2: silence reseeds
async def test_a_lull_costs_one_reseed_not_one_per_watchdog_tick_and_it_is_debounced() -> None:
    import time

    ws = FakeWs()
    h = Harness([ws])
    seed = seeder()
    agen = h.source(
        seeder=seed,
        mono=time.perf_counter,
        silence_s=0.05,
        active_s=5.0,
        watch_interval_s=0.01,
        seed_min_interval_s=0.4,
    ).stream([W])
    await ready(agen)
    await take(agen, 2)  # the unseeded pair of the first snapshot
    assert len(seed.calls) == 1
    from .test_leader_source_nats import msg

    ws.push(msg(W, "MintA", "1", "s1", slot=1))  # the wallet speaks, then goes quiet
    await asyncio.sleep(0.2)  # ~15 watchdog ticks inside the lull
    assert len(seed.calls) == 1  # debounced: the first snapshot was less than 0.4 s ago
    await asyncio.sleep(0.5)
    assert len(seed.calls) == 2  # exactly one reseed for the whole lull
    await agen.aclose()  # type: ignore[attr-defined]


async def test_a_flood_of_invented_mints_is_a_named_gap_not_unbounded_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hunter_exchanges.pumpfun import leader_source_nats_state as state

    from .test_leader_source_nats import msg

    monkeypatch.setattr(state, "HELD_MAX", 4)
    ws = FakeWs()
    h = Harness([ws])
    agen = h.source(seeder=None).stream([W])
    await ready(agen)
    for i in range(10):
        ws.push(msg(W, f"Mint{i}", "1", f"s{i}", slot=i + 1))
    gap = await until(agen, LeaderGap)
    assert (gap.wallet, gap.reason) == (W, "nats_baseline_overflow")
    await agen.aclose()  # type: ignore[attr-defined]


def test_at_the_ceiling_the_jitter_goes_down_so_persistent_reconnects_do_not_synchronise() -> None:
    low = NatsLeaderSource(rand=lambda: 1.0).delay_for(60.0, 600.0, 20)
    high = NatsLeaderSource(rand=lambda: 0.0).delay_for(60.0, 600.0, 20)
    assert high == 600.0 and 450.0 <= low < 600.0


async def test_a_snapshot_over_the_cap_leaves_the_wallet_degraded_with_a_named_gap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hunter_exchanges.pumpfun import leader_source_nats_state as state

    monkeypatch.setattr(state, "HELD_MAX", 3)

    async def huge(wallet: str) -> WalletSnapshot:
        return WalletSnapshot(10**10, 50, {f"M{i}": (1, 50) for i in range(5)}, 50)

    ws = FakeWs()
    h = Harness([ws])
    agen = h.source(seeder=huge).stream([W])
    await ready(agen)
    reasons: list[tuple[str, bool]] = []
    for _ in range(2):
        gap = await until(agen, LeaderGap)
        reasons.append((gap.reason, gap.end is not None))
    assert ("nats_unseeded", False) in reasons and ("nats_baseline_overflow", False) in reasons
    with pytest.raises(TimeoutError):  # nothing closes either gap: the wallet stays degraded
        await asyncio.wait_for(agen.__anext__(), 0.2)
    await agen.aclose()  # type: ignore[attr-defined]


async def test_a_seed_backoff_interrupted_by_a_reconnect_is_still_served_in_the_next_session() -> (
    None
):
    ws1, ws2 = FakeWs(), FakeWs()
    h = Harness([ws1, ws2])
    calls: list[int] = []

    async def flaky(wallet: str) -> WalletSnapshot:
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionError("rpc down")
        return WalletSnapshot(10**10, 50, {}, 50)

    async def hanging(delay: float) -> None:
        h.delays.append(delay)
        if delay >= 1.0:  # the seed's backoff: never completes, the socket is about to drop
            await asyncio.sleep(3600)

    h.sleep = hanging  # type: ignore[method-assign]
    agen = h.source(mono=lambda: 1000.0, seeder=flaky, seed_min_interval_s=0.0).stream([W])
    await ready(agen)
    await asyncio.sleep(0.1)
    assert len(calls) == 1  # failed, and is now "sleeping" its 1 s backoff
    ws1.push(ConnectionError("reset"))
    await asyncio.sleep(0.4)
    assert len(calls) == 1  # the new session does NOT read again before the backoff deadline
    await asyncio.sleep(1.1)
    assert len(calls) == 2  # ... and does once it has passed
    await agen.aclose()  # type: ignore[attr-defined]


async def test_the_hour_long_stop_also_waits_for_what_the_server_asked() -> None:
    ws = FakeWs()
    h = Harness([ws], configs=[NatsRefused(429, 7200.0)] * 3 + [CFG])
    agen = h.source(seeder=None).stream([W])
    reasons: list[str] = []
    while "nats_stopped" not in reasons:
        reasons.append((await until(agen, LeaderGap)).reason)
    assert h.delays[-1] >= 7200.0  # the third refusal does not come back an hour early
    await agen.aclose()  # type: ignore[attr-defined]
