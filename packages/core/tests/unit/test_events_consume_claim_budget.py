"""The reclaim is paid in pages per round, so reads are never starved by it.

Production, 01/10/2026 (``obsidian/10-PERFORMANCE/Scanner-lag-2026-10-01.md``): a
consumer whose pending list held 17 000 entries reclaimed **all** of it -- page after
page of ``count`` entries -- before every single ``XREADGROUP``, so it read new
messages at the rate they were produced and burned a core on redeliveries. The loop
now claims at most ``MAX_CLAIM_PAGES_PER_ROUND`` pages, remembers where it stopped,
reads, and resumes from that cursor next round; while a backlog remains the read does
not block, so recovering a dead instance's list is not slowed by an idle stream.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest
from redis.exceptions import TimeoutError as RedisTimeoutError
from structlog.testing import capture_logs

from hunter_core.events.consume import DEFAULT_BLOCK_MS, MAX_CLAIM_PAGES_PER_ROUND, consume
from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.produce import FIELD_NAME

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


class ClaimingRedis:
    """``pages`` is the PEL as XAUTOCLAIM would page it; every call is logged in order."""

    def __init__(self, pages: int) -> None:
        self.total = pages
        self.served = 0
        self.events: list[tuple[str, Any]] = []

    async def xgroup_create(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def xautoclaim(self, stream: str, group: str, consumer: str, **kwargs: Any) -> Any:
        raw = kwargs["start_id"]
        start = raw.decode() if isinstance(raw, bytes) else str(raw)
        self.events.append(("claim", start))
        index = 0 if start == "0-0" else int(start.split("-")[0])
        envelope = EventEnvelope(type="t", producer="p", key=f"k:{index}", payload={"i": index})
        entries = [(f"1-{index + 1}".encode(), {FIELD_NAME: envelope.to_bytes()})]
        last = index + 1 >= self.total
        return [b"0-0" if last else f"{index + 1}-0".encode(), entries, []]

    async def xreadgroup(self, *args: Any, **kwargs: Any) -> Any:
        self.events.append(("read", kwargs.get("block")))
        return []

    async def sismember(self, key: str, member: str) -> bool:
        return False

    async def xack(self, *args: Any, **kwargs: Any) -> int:
        return 1


async def _run_until_reads(client: ClaimingRedis, reads: int) -> None:
    gen = consume(cast("Any", client), "market.candles.closed", "g", "c", now=lambda: NOW)
    try:
        async for _message in gen:
            if sum(1 for kind, _ in client.events if kind == "read") >= reads:
                break
    finally:
        await gen.aclose()


async def test_a_round_claims_a_bounded_number_of_pages_then_reads_without_blocking() -> None:
    client = ClaimingRedis(pages=40)

    await _run_until_reads(client, reads=1)

    first_read = next(i for i, (kind, _) in enumerate(client.events) if kind == "read")
    assert first_read == MAX_CLAIM_PAGES_PER_ROUND, "the claim must not run to the end of the PEL"
    assert client.events[first_read] == ("read", None), "a backlog remains: do not block"


async def test_the_next_round_resumes_from_the_cursor_instead_of_starting_over() -> None:
    client = ClaimingRedis(pages=40)

    await _run_until_reads(client, reads=2)

    claims = [value for kind, value in client.events if kind == "claim"]
    assert claims[:MAX_CLAIM_PAGES_PER_ROUND] == ["0-0"] + [
        f"{i}-0" for i in range(1, MAX_CLAIM_PAGES_PER_ROUND)
    ]
    assert claims[MAX_CLAIM_PAGES_PER_ROUND] == f"{MAX_CLAIM_PAGES_PER_ROUND}-0", (
        "the second round starts where the first stopped"
    )


async def test_a_pending_list_that_fits_in_a_round_is_claimed_whole_and_the_read_blocks() -> None:
    client = ClaimingRedis(pages=2)

    await _run_until_reads(client, reads=1)

    assert [kind for kind, _ in client.events][:3] == ["claim", "claim", "read"]
    assert client.events[2] == ("read", DEFAULT_BLOCK_MS), "no backlog: the normal blocking read"


class _Enough(Exception):
    """Raised by the fake when the test has seen all the reads it wanted."""


class ScriptedClaims:
    """``XAUTOCLAIM`` answers from a script; records the cursor each call starts from."""

    def __init__(self, script: list[Any], *, fail_first: bool = False, reads: int = 1) -> None:
        self.script = list(script)
        self.fail_first = fail_first
        self.max_reads = reads
        self.starts: list[str] = []
        self.reads = 0

    async def xgroup_create(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def xautoclaim(self, stream: str, group: str, consumer: str, **kwargs: Any) -> Any:
        raw = kwargs["start_id"]
        self.starts.append(raw.decode() if isinstance(raw, bytes) else str(raw))
        if self.fail_first:
            self.fail_first = False
            raise RedisTimeoutError("Timeout reading from redis:6379")
        return self.script.pop(0) if self.script else [b"0-0", [], []]

    async def xreadgroup(self, *args: Any, **kwargs: Any) -> Any:
        self.reads += 1
        if self.reads >= self.max_reads:
            raise _Enough
        return []

    async def sismember(self, key: str, member: str) -> bool:
        return False

    async def xack(self, *args: Any, **kwargs: Any) -> int:
        return 1


async def _drive(client: ScriptedClaims) -> list[str]:
    delivered: list[str] = []
    gen = consume(
        cast("Any", client), "market.candles.closed", "g", "c", now=lambda: NOW, timeout_backoff_s=0
    )
    try:
        async for message_id, _envelope in gen:
            delivered.append(message_id)
    except _Enough:
        pass
    finally:
        await gen.aclose()
    return delivered


async def test_an_empty_page_with_a_live_cursor_sends_the_next_round_back_to_the_start() -> None:
    """XAUTOCLAIM can scan a stretch of the pending list and find nothing idle while
    still returning a cursor. That ends the round and restarts from ``0-0`` -- the
    behaviour before the budget -- instead of resuming mid-list forever."""
    client = ScriptedClaims([[b"7-0", [], []]], reads=2)

    await _drive(client)

    assert client.starts[:2] == ["0-0", "0-0"]


async def test_the_deleted_ids_the_server_appends_to_a_page_are_ignored() -> None:
    envelope = EventEnvelope(type="t", producer="p", key="k", payload={})
    entries = [(b"1-1", {FIELD_NAME: envelope.to_bytes()})]
    client = ScriptedClaims([[b"0-0", entries, [b"1-9", b"1-10"]]])

    assert await _drive(client) == ["1-1"]


async def test_a_read_deadline_keeps_its_documented_log_name() -> None:
    """``consume_read_deadline`` is the search signature of notes-T3.83 and the
    operations runbook; a rename breaks every saved query."""
    client = ScriptedClaims([], fail_first=True)

    with capture_logs() as logs:
        await _drive(client)

    events = [entry for entry in logs if entry["event"] == "consume_read_deadline"]
    assert events and events[0]["op"] == "xautoclaim" and events[0]["consecutive"] == 1
