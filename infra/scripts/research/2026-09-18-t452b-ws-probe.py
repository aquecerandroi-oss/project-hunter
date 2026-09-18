"""T4.52b-1 — live probe: Solana RPC WebSocket coverage/lag for pump.fun curve
trades (plan-T4.52b.md §1 item 8, task T4.52b-1).

Read-only, on chain: subscribes ``logsSubscribe`` + ``accountSubscribe`` to
the bonding-curve PDA of N pump.fun mints (the most recently created ones,
read from ``frontend-api-v3.pump.fun`` the way ``rest.py`` does, or an
explicit ``--mints`` list) plus one ``slotSubscribe``, for ``--seconds``
(default 120). Records every raw notification frame verbatim, one per line,
capped at ~2MB per file, into::

    packages/exchange-adapters/tests/fixtures/pumpfun/t452b_ws_logs_notifications_raw.jsonl
    packages/exchange-adapters/tests/fixtures/pumpfun/t452b_ws_account_notifications_raw.jsonl
    packages/exchange-adapters/tests/fixtures/pumpfun/t452b_ws_slot_notifications_raw.jsonl

and prints, at the end: events per source per mint, how many ``logsSubscribe``
trades also produced an ``accountSubscribe`` change at the same slot (and vice
versa), and the lag ``received_at - slot_time`` (``slot * 0.4s`` anchored on
the newest ``slotSubscribe`` reading — plan-T4.52b.md §3, no ``getBlockTime``
call in this script). Run twice with ``--commitment processed|confirmed`` to
compare the two lag distributions.

``--ws-url`` only ever comes from argv (default the public endpoint below) —
never ``.env*`` — so this can never accidentally hit a keyed provider from a
shell profile. Usage::

    uv run python infra/scripts/research/2026-09-18-t452b-ws-probe.py \\
        --seconds 120 --commitment confirmed
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

import httpx

from hunter_exchanges.pumpfun.pdas import bonding_curve_address
from hunter_exchanges.pumpfun.rpc_ws import PUBLIC_WS_URL, SolanaWsClient, WsConnection
from hunter_exchanges.pumpfun.rpc_ws_models import LogsNotification, SlotNotification
from hunter_exchanges.pumpfun.trade_event import trade_events_from_logs

FIXTURES_DIR = Path(__file__).parents[3] / "packages/exchange-adapters/tests/fixtures/pumpfun"
MAX_BYTES_PER_FILE = 2 * 1024 * 1024
FRONTEND_BASE_URL = "https://frontend-api-v3.pump.fun"
_METHOD_TO_KIND = {
    "logsNotification": "logs",
    "accountNotification": "account",
    "slotNotification": "slot",
}


async def fetch_recent_mints(count: int) -> list[str]:
    """The N newest pump.fun mints (``GET /coins?sort=created_timestamp``),
    the same undocumented endpoint ``rest.py`` reads (docs/PUMPFUN.md §4.3)."""
    async with httpx.AsyncClient(base_url=FRONTEND_BASE_URL, timeout=10.0) as client:
        response = await client.get(
            "/coins",
            params={
                "offset": 0,
                "limit": count,
                "sort": "created_timestamp",
                "order": "DESC",
                "includeNsfw": "true",
            },
        )
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, list):
        return []
    items = cast("list[Any]", payload)
    mints: list[str] = []
    for item in items:
        mint = cast("dict[str, Any]", item).get("mint") if isinstance(item, dict) else None
        if isinstance(mint, str) and mint:
            mints.append(mint)
    return mints


class RawRecorder:
    """Every accepted notification frame, verbatim, one JSONL file per kind,
    capped at ``MAX_BYTES_PER_FILE`` each — never a subscribe ack or response
    (those aren't a notification, and the coverage/lag report doesn't want them)."""

    def __init__(self, base: Path) -> None:
        base.mkdir(parents=True, exist_ok=True)
        self._files = {
            kind: (base / f"t452b_ws_{kind}_notifications_raw.jsonl").open("w", encoding="utf-8")
            for kind in ("logs", "account", "slot")
        }
        self._bytes = dict.fromkeys(self._files, 0)

    def record(self, raw: str) -> None:
        try:
            raw_payload: Any = json.loads(raw)
        except json.JSONDecodeError:
            return
        method = (
            cast("dict[str, Any]", raw_payload).get("method")
            if isinstance(raw_payload, dict)
            else None
        )
        kind = _METHOD_TO_KIND.get(method) if isinstance(method, str) else None
        if kind is None or self._bytes[kind] >= MAX_BYTES_PER_FILE:
            return
        line = raw if raw.endswith("\n") else raw + "\n"
        self._files[kind].write(line)
        self._bytes[kind] += len(line.encode("utf-8"))

    def close(self) -> None:
        for fh in self._files.values():
            fh.close()


def _tee_connect_fn(inner_connect: Callable[[str], Any], sink: Callable[[str], None]) -> Any:
    """Wrap ``rpc_ws.default_connect`` so every frame the client receives is
    also handed to ``sink`` before the client parses it — the only way to
    keep the *raw* wire text once ``SolanaWsClient`` decodes it into a
    dataclass."""

    class _TeeConnection:
        def __init__(self, inner: WsConnection) -> None:
            self._inner = inner

        async def recv(self) -> str | bytes:
            raw = await self._inner.recv()
            sink(raw if isinstance(raw, str) else raw.decode("utf-8"))
            return raw

        async def send(self, message: str) -> None:
            await self._inner.send(message)

        async def close(self) -> None:
            await self._inner.close()

    class _TeeCM:
        def __init__(self, url: str) -> None:
            self._cm = inner_connect(url)

        async def __aenter__(self) -> _TeeConnection:
            return _TeeConnection(await self._cm.__aenter__())

        async def __aexit__(self, *exc_info: object) -> None:
            await self._cm.__aexit__(*exc_info)

    return _TeeCM


@dataclass
class MintStat:
    mint: str
    logs_events: int = 0
    account_events: int = 0
    trade_slots: set[int] = field(default_factory=set[int])
    account_slots: set[int] = field(default_factory=set[int])


def _estimate_slot_time(anchor: tuple[int, datetime] | None, slot: int) -> datetime | None:
    if anchor is None:
        return None
    anchor_slot, anchor_time = anchor
    return anchor_time - timedelta(seconds=(anchor_slot - slot) * 0.4)


async def run(args: argparse.Namespace) -> int:
    from hunter_exchanges.pumpfun.rpc_ws import default_connect

    recorder = RawRecorder(FIXTURES_DIR)
    client = SolanaWsClient(
        url=args.ws_url, connect_fn=_tee_connect_fn(default_connect, recorder.record)
    )
    mints = args.mints or await fetch_recent_mints(args.num_mints)
    if not mints:
        print("no mints available (REST list empty or refused)", file=sys.stderr)
        recorder.close()
        return 1

    stats = {mint: MintStat(mint) for mint in mints}
    logical_meta: dict[int, tuple[str, str]] = {}
    anchor: tuple[int, datetime] | None = None
    lags: dict[str, list[float]] = {"logs": [], "account": []}

    async def consume() -> None:
        nonlocal anchor
        async for notif in client.listen():
            if isinstance(notif, SlotNotification):
                anchor = (notif.slot, notif.received_at)
                continue
            mint, _kind = logical_meta.get(notif.subscription_id, (None, None))
            if mint is None:
                continue
            slot_time = _estimate_slot_time(anchor, notif.slot)
            lag = (notif.received_at - slot_time).total_seconds() if slot_time else None
            if isinstance(notif, LogsNotification):
                stats[mint].logs_events += 1
                if notif.err is None and trade_events_from_logs(notif.logs):
                    stats[mint].trade_slots.add(notif.slot)
                if lag is not None:
                    lags["logs"].append(lag)
            else:
                stats[mint].account_events += 1
                stats[mint].account_slots.add(notif.slot)
                if lag is not None:
                    lags["account"].append(lag)

    consumer = asyncio.create_task(consume())
    try:
        for mint in mints:
            curve = bonding_curve_address(mint)
            logs_id = await client.subscribe_logs(mentions=[curve], commitment=args.commitment)
            account_id = await client.subscribe_account(curve, commitment=args.commitment)
            logical_meta[logs_id] = (mint, "logs")
            logical_meta[account_id] = (mint, "account")
        await client.subscribe_slot()
        await asyncio.sleep(args.seconds)
    finally:
        consumer.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await consumer
        await client.aclose()
        recorder.close()

    print_summary(stats, lags, client)
    return 0


def print_summary(
    stats: dict[str, MintStat], lags: dict[str, list[float]], client: SolanaWsClient
) -> None:
    print("=== events per mint ===")
    for mint, st in stats.items():
        overlap = len(st.trade_slots & st.account_slots)
        print(
            f"{mint}: logs={st.logs_events} trade_slots={len(st.trade_slots)} "
            f"account={st.account_events} account_slots={len(st.account_slots)} "
            f"overlap={overlap}"
        )
    print("=== lag received_at - slot_time (s) ===")
    for kind, values in lags.items():
        if not values:
            print(f"{kind}: n=0")
            continue
        values = sorted(values)
        p50 = values[len(values) // 2]
        p95 = values[min(len(values) - 1, int(len(values) * 0.95))]
        print(
            f"{kind}: n={len(values)} p50={p50:.3f} p95={p95:.3f} min={values[0]:.3f} max={values[-1]:.3f}"
        )
    print(
        f"ws: reconnects={client.state.reconnects} messages={client.state.messages} "
        f"dropped={client.state.dropped} malformed={client.state.malformed}"
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ws-url", default=PUBLIC_WS_URL)
    parser.add_argument("--mints", nargs="*", default=None)
    parser.add_argument("--num-mints", "-n", type=int, default=5)
    parser.add_argument("--seconds", type=int, default=120)
    parser.add_argument("--commitment", choices=["processed", "confirmed"], default="confirmed")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
