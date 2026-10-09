"""Copy-trade pilot (H-037): the on-chain leader source against fakes — no network.

The transactions are the real third-party mainnet fixtures of T4.12 (buy of ``AsRQ...``, sell of
``sssss...``); the logs feed and the RPC reads are scripted fakes. The signature lister honours
``until``/``limit``/``before`` like the node (a fake that ignored them hid a recovery bug).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from structlog.testing import capture_logs

from hunter_exchanges.base import ExchangeUnavailable, RateLimited
from hunter_exchanges.pumpfun import leader_source_chain_run as run_module
from hunter_exchanges.pumpfun.leader_events import LeaderConfirmation, LeaderEvent, LeaderGap
from hunter_exchanges.pumpfun.leader_source_chain import ChainLeaderSource
from hunter_exchanges.pumpfun.rpc_wallet import SignatureInfo
from hunter_exchanges.pumpfun.rpc_ws_models import ConnectionState, LogsNotification

pytestmark = pytest.mark.unit

FX = Path(__file__).parents[1] / "fixtures/pumpfun"
BUYER = "AsRQHoHxfBYqvxJZxK9RtJUnRZcCwUoh9KNpVxH6Jhnd"
SELLER = "sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d"
MINT = "5ejAEbzxiZuwUNgZcoryoAY8gA5oCAVJZx5AyDnApump"
BUY_TX = cast("dict[str, Any]", json.loads((FX / "rpc_tx_buy_raw.json").read_text())["result"])
SELL_TX = cast("dict[str, Any]", json.loads((FX / "rpc_tx_probe_raw.json").read_text())["result"])
T0 = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)
Item = LeaderEvent | LeaderGap | LeaderConfirmation


def notif(sub: int, sig: str, *, err: object = None, at: datetime = T0) -> LogsNotification:
    return LogsNotification(sub, "logs", 1, sig, err, ("Program log: x",), at)


class FakeFeed:
    def __init__(self) -> None:
        self.state = ConnectionState(ws_state="connected")
        self.inbox: asyncio.Queue[LogsNotification] = asyncio.Queue()
        self.subscribed: list[tuple[int, str, str]] = []
        self.closed = False

    async def subscribe_logs(
        self, *, mentions: Sequence[str], commitment: str = "confirmed"
    ) -> int:
        sub = len(self.subscribed) + 1
        self.subscribed.append((sub, mentions[0], commitment))
        return sub

    async def listen(self) -> AsyncIterator[LogsNotification]:
        while True:
            yield await self.inbox.get()

    async def aclose(self) -> None:
        self.closed = True


class Rpc:
    def __init__(self, txs: dict[str, Any] | None = None) -> None:
        self.txs: dict[str, Any] = txs or {}
        self.calls: list[str] = []
        self.chain: dict[str, list[str]] = {}  # wallet -> signatures, newest first
        self.sig_calls: list[tuple[str, str | None, int, str | None]] = []
        self.list_error: Exception | None = None
        self.after_first_list: Any = None  # runs once, after the first lister answer

    async def fetch(self, signature: str) -> dict[str, Any] | None:
        self.calls.append(signature)
        item: Any = self.txs.get(signature)
        if isinstance(item, list):  # a script: successive answers
            script = cast("list[Any]", item)
            item = script.pop(0) if len(script) > 1 else script[0]
        if isinstance(item, Exception):
            raise item
        return cast("dict[str, Any] | None", item)

    async def signatures(
        self, wallet: str, until: str | None, limit: int, before: str | None
    ) -> list[SignatureInfo]:
        self.sig_calls.append((wallet, until, limit, before))
        if self.list_error is not None:
            raise self.list_error
        sigs = self.chain.get(wallet, [])
        if before is not None:
            sigs = sigs[sigs.index(before) + 1 :]
        if until is not None and until in sigs:
            sigs = sigs[: sigs.index(until)]
        answer = [SignatureInfo(s, 100 - i, None, False) for i, s in enumerate(sigs[:limit])]
        hook, self.after_first_list = self.after_first_list, None
        if hook is not None:
            hook()
        return answer


def make(feed: FakeFeed, rpc: Rpc, **kw: Any) -> ChainLeaderSource:
    sleeps: list[float] = kw.pop("sleeps", [])
    clock = {"now": T0 + timedelta(seconds=1)}

    async def sleep(delay: float) -> None:
        sleeps.append(delay)
        clock["now"] += timedelta(seconds=delay)
        await asyncio.sleep(0)

    return ChainLeaderSource(
        feed=feed,
        fetch_tx=rpc.fetch,
        list_signatures=kw.pop("list_signatures", rpc.signatures),
        wall=kw.pop("wall", lambda: clock["now"]),
        sleep=sleep,
        monitor_interval_s=0.01,
        settle_s=0.0,
        **kw,
    )


async def take(agen: AsyncIterator[Item], n: int) -> list[Item]:
    return [await asyncio.wait_for(agen.__anext__(), 3) for _ in range(n)]


async def started(src: ChainLeaderSource, wallets: list[str]) -> AsyncIterator[Item]:
    agen = src.stream(wallets)
    first, second = await take(agen, 2)
    assert isinstance(first, LeaderGap) and (first.reason, first.end) == ("chain_connect", None)
    assert isinstance(second, LeaderGap) and second.end is not None
    return agen


async def test_subscribes_per_wallet_at_confirmed_and_turns_a_notification_into_a_chain_event() -> (
    None
):
    feed, rpc = FakeFeed(), Rpc({"SIG-B": BUY_TX})
    agen = await started(make(feed, rpc), [BUYER, SELLER])
    assert sorted((w, c) for _, w, c in feed.subscribed) == [
        (BUYER, "confirmed"),
        (SELLER, "confirmed"),
    ]
    sub = next(s for s, w, _ in feed.subscribed if w == BUYER)
    feed.inbox.put_nowait(notif(sub, "SIG-B"))
    (ev,) = await take(agen, 1)
    assert isinstance(ev, LeaderEvent)
    assert (ev.wallet, ev.side, ev.signature, ev.source, ev.confirmed, ev.kind) == (
        BUYER,
        "buy",
        "SIG-B",
        "chain",
        True,
        "swap",
    )
    assert ev.first_seen_at == T0  # when the notification reached us, not when the fetch finished
    assert ev.fields_complete_at >= ev.first_seen_at
    await agen.aclose()  # type: ignore[attr-defined]


async def test_failed_transactions_and_duplicates_cost_no_fetch_and_no_event() -> None:
    feed, rpc = FakeFeed(), Rpc({"SIG-B": BUY_TX})
    src = make(feed, rpc)
    agen = await started(src, [BUYER])
    feed.inbox.put_nowait(notif(1, "FAILED", err={"InstructionError": [0, "x"]}))
    feed.inbox.put_nowait(notif(1, "SIG-B"))
    feed.inbox.put_nowait(notif(1, "SIG-B"))  # the same transaction announced twice
    (ev,) = await take(agen, 1)
    await asyncio.sleep(0.05)
    assert isinstance(ev, LeaderEvent) and rpc.calls == ["SIG-B"]
    assert src.stats.counters["logs_err"] == 1 and src.stats.counters["duplicate"] == 1
    await agen.aclose()  # type: ignore[attr-defined]


async def test_a_transaction_not_visible_yet_is_retried_with_backoff() -> None:
    feed, rpc = FakeFeed(), Rpc({"SIG-B": [None, None, BUY_TX]})  # the 3rd attempt of the design
    sleeps: list[float] = []
    agen = await started(make(feed, rpc, sleeps=sleeps), [BUYER])
    feed.inbox.put_nowait(notif(1, "SIG-B"))
    (ev,) = await take(agen, 1)
    assert isinstance(ev, LeaderEvent) and rpc.calls == ["SIG-B"] * 3
    assert sleeps[:2] == [1.0, 5.0]
    await agen.aclose()  # type: ignore[attr-defined]


async def test_the_ladder_stays_inside_the_design_thirty_seconds() -> None:
    from hunter_exchanges.pumpfun.leader_source_chain import RETRY_DELAYS_S

    assert sum(RETRY_DELAYS_S) <= 30.0


async def test_a_transaction_that_never_appears_is_a_named_wallet_gap_not_a_silence() -> None:
    feed, rpc = FakeFeed(), Rpc({"SIG-X": None})
    agen = await started(make(feed, rpc), [BUYER])
    feed.inbox.put_nowait(notif(1, "SIG-X"))
    (gap,) = await take(agen, 1)
    assert isinstance(gap, LeaderGap)
    assert (gap.wallet, gap.reason) == (BUYER, "chain_tx_not_found") and gap.end is not None
    await agen.aclose()  # type: ignore[attr-defined]


async def test_rate_limit_is_a_system_event_a_gap_and_a_pause_never_a_loop() -> None:
    feed = FakeFeed()
    limited = RateLimited("429", exchange="pumpfun", retry_after_s=10.0)
    rpc = Rpc({"SIG-1": limited, "SIG-2": BUY_TX})
    agen = await started(make(feed, rpc), [BUYER])
    with capture_logs() as logs:
        feed.inbox.put_nowait(notif(1, "SIG-1"))
        (gap,) = await take(agen, 1)
        feed.inbox.put_nowait(notif(1, "SIG-2"))  # inside the cool-down
        (gap2,) = await take(agen, 1)
    assert isinstance(gap, LeaderGap) and gap.reason == "chain_rate_limited"
    assert isinstance(gap2, LeaderGap) and gap2.reason == "chain_rate_limited"
    assert rpc.calls == ["SIG-1"]  # one call, then nothing until the cool-down passes
    assert [e for e in logs if e["event"] == "system_event"]
    await agen.aclose()  # type: ignore[attr-defined]


@pytest.mark.parametrize("status", [401, 403, 418])
async def test_a_refusal_status_from_the_rpc_client_is_a_system_event_and_stops_the_ladder(
    status: int,
) -> None:
    feed = FakeFeed()
    rpc = Rpc({"SIG-1": ExchangeUnavailable(f"Solana RPC HTTP {status}", exchange="pumpfun")})
    agen = await started(make(feed, rpc), [BUYER])
    with capture_logs() as logs:
        feed.inbox.put_nowait(notif(1, "SIG-1"))
        (gap,) = await take(agen, 1)
    assert isinstance(gap, LeaderGap) and gap.reason == f"chain_refused_{status}"
    assert len(rpc.calls) == 1 and [e for e in logs if e["event"] == "system_event"]
    await agen.aclose()  # type: ignore[attr-defined]


async def test_a_transient_rpc_error_is_retried_then_gives_a_gap() -> None:
    feed = FakeFeed()
    rpc = Rpc({"SIG-B": ExchangeUnavailable("Solana RPC transport failure", exchange="pumpfun")})
    agen = await started(make(feed, rpc), [BUYER])
    feed.inbox.put_nowait(notif(1, "SIG-B"))
    (gap,) = await take(agen, 1)
    assert isinstance(gap, LeaderGap) and gap.reason == "chain_tx_unavailable"
    assert len(rpc.calls) > 1
    await agen.aclose()  # type: ignore[attr-defined]


async def test_a_transaction_whose_logs_cannot_be_read_is_a_gap_never_assumed_no_trade() -> None:
    feed, rpc = FakeFeed(), Rpc({"BAD": {"nonsense": True}, "SIG-B": BUY_TX})
    agen = await started(make(feed, rpc), [BUYER])
    feed.inbox.put_nowait(notif(1, "BAD"))
    (gap,) = await take(agen, 1)
    assert isinstance(gap, LeaderGap) and gap.reason == "chain_logs_unreadable"
    feed.inbox.put_nowait(notif(1, "SIG-B"))
    (ev,) = await take(agen, 1)
    assert isinstance(ev, LeaderEvent)
    await agen.aclose()  # type: ignore[attr-defined]


async def test_a_legible_trade_with_a_truncated_log_is_delivered_and_the_loss_is_a_gap() -> None:
    truncated = json.loads(json.dumps(BUY_TX))
    truncated["meta"]["logMessages"].append("Log truncated")
    feed, rpc = FakeFeed(), Rpc({"SIG-T": truncated})
    agen = await started(make(feed, rpc), [BUYER])
    feed.inbox.put_nowait(notif(1, "SIG-T"))
    got = await take(agen, 2)
    assert sum(isinstance(g, LeaderEvent) for g in got) == 1
    gap = next(g for g in got if isinstance(g, LeaderGap))
    assert (gap.wallet, gap.reason) == (BUYER, "chain_logs_partial")
    assert gap.end is not None and gap.end > gap.start  # an interval a consumer can test against
    await agen.aclose()  # type: ignore[attr-defined]


async def test_a_refused_read_is_a_named_gap_not_just_a_counter() -> None:
    bad = json.loads(json.dumps(BUY_TX))
    mine = next(b for b in bad["meta"]["postTokenBalances"] if b["owner"] == BUYER)
    pre = json.loads(json.dumps(mine))
    pre["uiTokenAmount"]["amount"] = str(int(mine["uiTokenAmount"]["amount"]) + 10)
    bad["meta"]["preTokenBalances"].append(pre)  # synthetic: a "buy" that lowers the balance
    feed, rpc = FakeFeed(), Rpc({"SIG-X": bad})
    agen = await started(make(feed, rpc), [BUYER])
    feed.inbox.put_nowait(notif(1, "SIG-X"))
    (gap,) = await take(agen, 1)
    assert isinstance(gap, LeaderGap) and gap.reason == "chain_sign_mismatch"
    await agen.aclose()  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- reconnects and recovery
async def test_a_failed_start_cut_is_not_a_proven_empty_history() -> None:
    feed, rpc = FakeFeed(), Rpc({})
    rpc.list_error = ExchangeUnavailable("down", exchange="pumpfun")
    agen = make(feed, rpc).stream([BUYER])
    got = await take(agen, 3)
    assert [g.reason for g in got if isinstance(g, LeaderGap)] == [
        "chain_connect",
        "chain_connect",
        "chain_recovery_failed",
    ]
    await agen.aclose()  # type: ignore[attr-defined]


async def test_a_wallet_with_no_history_at_all_is_a_proven_empty_start() -> None:
    feed, rpc = FakeFeed(), Rpc({})
    agen = make(feed, rpc).stream([BUYER])  # the lister answers [] without error
    got = await take(agen, 2)
    assert [g.reason for g in got if isinstance(g, LeaderGap)] == ["chain_connect", "chain_connect"]
    await agen.aclose()  # type: ignore[attr-defined]


async def test_the_start_cut_is_read_before_subscribing_and_backfilled_after() -> None:
    feed = FakeFeed()
    rpc = Rpc({"S-NEW": BUY_TX, "S-MID": BUY_TX})
    rpc.chain[BUYER] = ["A0"]
    # two transactions land after the cut was read and before/while the subscription is made
    rpc.after_first_list = lambda: rpc.chain.update({BUYER: ["S-NEW", "S-MID", "A0"]})
    agen = make(feed, rpc).stream([BUYER])
    got = await take(agen, 4)  # open gap, the two backfilled events, closed gap
    assert [g.signature for g in got if isinstance(g, LeaderEvent)] == ["S-MID", "S-NEW"]
    assert isinstance(got[0], LeaderGap) and isinstance(got[-1], LeaderGap) and got[-1].end
    assert rpc.sig_calls[0] == (BUYER, None, 1, None)  # the cut was read first
    await agen.aclose()  # type: ignore[attr-defined]


async def test_a_ws_reconnect_recovers_every_missed_signature_paging_back_to_the_frozen_anchor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_module, "RECOVERY_PAGE", 2)
    feed = FakeFeed()
    sigs = ["D", "C", "B", "A"]
    rpc = Rpc({s: BUY_TX for s in sigs})
    rpc.chain[BUYER] = ["A"]
    agen = await started(make(feed, rpc), [BUYER])
    rpc.chain[BUYER] = sigs
    feed.state.reconnects += 1  # the client reconnected silently...
    feed.inbox.put_nowait(notif(1, "D"))  # ...and delivered D before the monitor recovered
    got = await take(agen, 5)
    events = [g.signature for g in got if isinstance(g, LeaderEvent)]
    assert sorted(events) == ["B", "C", "D"]  # B and C survive: the anchor did not jump to D
    assert events.index("B") < events.index("C")  # recovery runs oldest first
    gaps = [g for g in got if isinstance(g, LeaderGap)]
    assert [g.reason for g in gaps] == ["chain_ws_down", "chain_ws_down"]
    assert gaps[0].end is None and gaps[1].end is not None and gaps[1].start == gaps[0].start
    assert any(call[3] is not None for call in rpc.sig_calls)  # it paged with a cursor
    await agen.aclose()  # type: ignore[attr-defined]


async def test_a_recovery_that_cannot_finish_leaves_the_loss_on_record() -> None:
    feed = FakeFeed()
    rpc = Rpc({})
    rpc.chain[BUYER] = ["A"]
    agen = await started(make(feed, rpc), [BUYER])
    rpc.list_error = ExchangeUnavailable("down", exchange="pumpfun")
    feed.state.reconnects += 1
    got = await take(agen, 3)
    reasons = [g.reason for g in got if isinstance(g, LeaderGap)]
    assert reasons == ["chain_ws_down", "chain_ws_down", "chain_recovery_failed"]
    await agen.aclose()  # type: ignore[attr-defined]


async def test_a_source_without_a_lister_cannot_claim_a_recovery() -> None:
    feed, rpc = FakeFeed(), Rpc({})
    src = make(feed, rpc, list_signatures=None)
    agen = src.stream([BUYER])
    await take(agen, 2)
    feed.state.reconnects += 1
    got = await take(agen, 3)
    assert "chain_recovery_failed" in [g.reason for g in got if isinstance(g, LeaderGap)]
    await agen.aclose()  # type: ignore[attr-defined]


async def test_a_disconnected_feed_is_a_gap_until_it_is_connected_again() -> None:
    feed, rpc = FakeFeed(), Rpc()
    agen = await started(make(feed, rpc), [BUYER])
    feed.state.ws_state = "reconnecting"
    (down,) = await take(agen, 1)
    assert isinstance(down, LeaderGap) and (down.reason, down.end) == ("chain_ws_down", None)
    feed.state.ws_state = "connected"
    (up,) = await take(agen, 1)
    assert isinstance(up, LeaderGap) and up.end is not None
    await agen.aclose()  # type: ignore[attr-defined]


async def test_a_notification_the_client_dropped_triggers_a_gap_and_a_recovery() -> None:
    """``SolanaWsClient`` drops (and counts) a notification whose subscription id it has not registered
    yet; the source cannot see it, so the counter itself is the alarm."""
    feed = FakeFeed()
    rpc = Rpc({"LOST": BUY_TX})
    rpc.chain[BUYER] = ["A"]
    agen = await started(make(feed, rpc), [BUYER])
    rpc.chain[BUYER] = ["LOST", "A"]
    feed.state.dropped += 1
    got = await take(agen, 3)
    assert [g.reason for g in got if isinstance(g, LeaderGap)] == ["chain_ws_down", "chain_ws_down"]
    assert [e.signature for e in got if isinstance(e, LeaderEvent)] == ["LOST"]
    await agen.aclose()  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- confirm
def preview(**kw: Any) -> LeaderEvent:
    base: dict[str, Any] = {
        "wallet": BUYER,
        "mint": MINT,
        "side": "buy",
        "token_delta_atoms": 22_628_881_309_131,
        "sol_delta_lamports": None,
        "position_after_atoms": 22_628_881_309_131,
        "signature": "SIG-B",
        "slot": 446369982,
        "block_time": None,
        "first_seen_at": T0,
        "fields_complete_at": T0,
        "source": "nats",
        "confirmed": False,
    }
    base.update(kw)
    return LeaderEvent(**base)


async def test_confirm_says_confirmed_with_the_reserves_and_the_chain_numbers() -> None:
    src = make(FakeFeed(), Rpc({"SIG-B": BUY_TX}))
    c = await src.confirm(preview())
    assert c.status == "confirmed" and c.reason is None
    assert c.post_reserves is not None and c.post_reserves.venue == "curve"
    assert c.chain_token_delta_atoms == 22_628_881_309_131 and c.block_time is not None
    assert c.confirmed_at > T0  # local reception of the result, not a block time
    again = await src.confirm(preview())  # idempotent
    assert (again.status, again.chain_token_delta_atoms) == (c.status, c.chain_token_delta_atoms)


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"token_delta_atoms": 22_628_881_309_132, "position_after_atoms": 1}, "token_delta"),
        ({"slot": 1}, "slot"),
        ({"mint": "OtherMint"}, "mint_not_in_tx"),
        ({"wallet": "Nobody"}, "not_a_trade"),
    ],
)
async def test_confirm_says_divergent_and_names_the_field(
    change: dict[str, Any], reason: str
) -> None:
    c = await make(FakeFeed(), Rpc({"SIG-B": BUY_TX})).confirm(preview(**change))
    assert (c.status, c.reason) == ("divergent", reason)
    if reason == "token_delta":
        assert c.chain_token_delta_atoms == 22_628_881_309_131  # the chain's number rides along


async def test_confirm_does_not_call_unreadable_logs_a_divergence() -> None:
    src = make(FakeFeed(), Rpc({"BAD": {"nonsense": True}}))
    c = await src.confirm(preview(signature="BAD"))
    assert (c.status, c.reason) == ("rpc_error", "logs_unreadable")


async def test_confirm_failed_tx_not_found_and_rpc_error_are_three_different_states() -> None:
    failed = json.loads(json.dumps(BUY_TX))
    failed["meta"]["err"] = {"InstructionError": [0, "x"]}
    src = make(
        FakeFeed(),
        Rpc(
            {"F": failed, "GONE": None, "LIM": RateLimited("429", exchange="p", retry_after_s=1.0)}
        ),
    )
    assert (await src.confirm(preview(signature="F"))).status == "failed_tx"
    gone = await src.confirm(preview(signature="GONE"))
    assert (gone.status, gone.reason) == ("not_found", "not_found")
    limited = await src.confirm(preview(signature="LIM"))
    assert (limited.status, limited.reason) == ("rpc_error", "rate_limited")


async def test_confirm_and_the_logs_path_share_one_fetch_per_signature() -> None:
    feed, rpc = FakeFeed(), Rpc({"SIG-B": BUY_TX})
    src = make(feed, rpc)
    agen = await started(src, [BUYER])
    assert (await src.confirm(preview())).status == "confirmed"
    feed.inbox.put_nowait(notif(1, "SIG-B"))
    await take(agen, 1)
    assert rpc.calls == ["SIG-B"]
    await agen.aclose()  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- lifecycle
async def test_closing_the_stream_closes_the_feed_and_cancels_a_fetch_in_flight() -> None:
    feed = FakeFeed()
    hang = asyncio.Event()
    calls: list[str] = []

    async def fetch(sig: str) -> dict[str, Any] | None:
        calls.append(sig)
        await hang.wait()
        return None

    src = ChainLeaderSource(feed=feed, fetch_tx=fetch, list_signatures=None, settle_s=0.0)
    agen = src.stream([BUYER])
    await take(agen, 2)
    feed.inbox.put_nowait(notif(1, "SIG-HANG"))
    for _ in range(100):
        if calls:
            break
        await asyncio.sleep(0.01)
    before = {t for t in asyncio.all_tasks() if t is not asyncio.current_task()}
    await agen.aclose()  # type: ignore[attr-defined]
    await asyncio.sleep(0.02)
    assert feed.closed and calls == ["SIG-HANG"] and all(t.done() for t in before)


async def test_empty_wallet_set_is_refused() -> None:
    with pytest.raises(ValueError, match="wallet"):
        await make(FakeFeed(), Rpc()).stream([]).__anext__()


async def test_the_partial_gap_is_announced_before_the_events_it_qualifies() -> None:
    truncated = json.loads(json.dumps(BUY_TX))
    truncated["meta"]["logMessages"].append("Log truncated")
    feed, rpc = FakeFeed(), Rpc({"SIG-T": truncated})
    agen = await started(make(feed, rpc), [BUYER])
    feed.inbox.put_nowait(notif(1, "SIG-T"))
    first, second = await take(agen, 2)
    assert isinstance(first, LeaderGap) and first.reason == "chain_logs_partial"
    assert isinstance(second, LeaderEvent) and second.sol_delta_lamports is None
    await agen.aclose()  # type: ignore[attr-defined]


async def test_confirm_with_a_partial_read_and_a_missing_mint_cannot_say_divergent() -> None:
    truncated = json.loads(json.dumps(BUY_TX))
    truncated["meta"]["logMessages"].append("Log truncated")
    src = make(FakeFeed(), Rpc({"SIG-T": truncated}))
    c = await src.confirm(preview(signature="SIG-T", mint="HiddenMint"))
    assert (c.status, c.reason) == ("rpc_error", "logs_partial")


async def test_a_history_that_was_empty_at_the_cut_is_still_backfilled_after_the_subscribe() -> (
    None
):
    feed = FakeFeed()
    rpc = Rpc({"FIRST": BUY_TX})
    # the cut finds nothing; then the wallet's first ever trade lands before the subscription is live
    rpc.after_first_list = lambda: rpc.chain.update({BUYER: ["FIRST"]})
    agen = make(feed, rpc).stream([BUYER])
    got = await take(agen, 3)
    assert [e.signature for e in got if isinstance(e, LeaderEvent)] == ["FIRST"]
    assert rpc.sig_calls[0] == (BUYER, None, 1, None) and rpc.sig_calls[1][1] is None
    await agen.aclose()  # type: ignore[attr-defined]
