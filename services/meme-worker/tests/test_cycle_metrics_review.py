"""Code-review round 2 of the cycle meter (07/10/2026): the cases a first pass missed.

- an external cancel that arrives *while the publication is in flight* must
  propagate (``except BaseException`` in the publisher would swallow it, and no
  other test reaches that line);
- a loop that is switched off still announces itself at every boot, so the
  previous process's numbers never look current (zombie metrics);
- the generation's start is UTC like everything else.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta, timezone

import pytest

from hunter_meme_worker.cycle_metrics import CycleMeter, announce, announce_all, timed_step

from .test_cycle_metrics import _Clock  # pyright: ignore[reportPrivateUsage]

pytestmark = pytest.mark.unit

T0 = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


async def _hang_after_entering(entered: asyncio.Event) -> None:
    entered.set()
    await asyncio.sleep(3600)


async def test_a_cancel_during_the_publication_propagates_and_is_not_a_failure() -> None:
    meter, clock = CycleMeter("chain", nominal_s=60.0, window=3), _Clock()
    entered = asyncio.Event()

    async def step(ctx: object) -> None:
        clock.advance(0.01)

    async def publish(fields: dict[str, str]) -> None:
        await _hang_after_entering(entered)

    task = asyncio.create_task(timed_step(meter, step, publish, clock=clock)(object()))
    await asyncio.wait_for(entered.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert meter.publish_failed_total == 0


async def test_a_cancel_during_announce_propagates_and_is_not_a_failure() -> None:
    meter = CycleMeter("lab", nominal_s=15.0, window=3)
    entered = asyncio.Event()

    async def publish(fields: dict[str, str]) -> None:
        await _hang_after_entering(entered)

    task = asyncio.create_task(announce(meter, publish))
    await asyncio.wait_for(entered.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert meter.publish_failed_total == 0


async def test_a_disabled_loop_still_replaces_the_previous_process_fields() -> None:
    """The hash already holds process A's chain numbers; process B boots with the
    chain and the lab switched off. B's announce must overwrite every cycle field."""
    hash_: dict[str, str] = {}

    async def hset(fields: dict[str, str]) -> None:
        hash_.update(fields)

    old = CycleMeter("chain", nominal_s=60.0, window=3, started_at=T0)
    old.record(70_000, T0)
    await announce(old, hset)
    assert hash_["chain_cycle_ms_p95"] == "70000"

    chain = CycleMeter("chain", nominal_s=60.0, window=3, enabled=False)
    lab = CycleMeter("lab", nominal_s=15.0, window=3, enabled=False)
    await announce_all([chain, lab], hset)

    assert hash_["chain_cycle_run_id"] == chain.run_id != old.run_id
    assert hash_["chain_cycle_ms_p95"] == ""
    assert hash_["chain_cycles_total"] == "0"
    assert hash_["chain_cycle_enabled"] == "false"
    assert hash_["lab_cycle_run_id"] == lab.run_id
    assert hash_["lab_cycle_enabled"] == "false"


async def test_announce_all_tries_every_meter_even_when_one_publication_fails() -> None:
    seen: list[str] = []

    async def hset(fields: dict[str, str]) -> None:
        if "chain_cycle_run_id" in fields:
            raise ConnectionError("redis down")
        seen.append(fields["lab_cycle_run_id"])

    chain = CycleMeter("chain", nominal_s=60.0, window=3)
    lab = CycleMeter("lab", nominal_s=15.0, window=3)
    await announce_all([chain, lab], hset)
    assert seen == [lab.run_id]
    assert chain.publish_failed_total == 1


def test_an_enabled_meter_says_so() -> None:
    assert CycleMeter("lab", nominal_s=15.0, window=3).fields()["lab_cycle_enabled"] == "true"


@pytest.mark.parametrize(
    "started_at",
    [
        datetime(2026, 10, 7, 12, 0),  # noqa: DTZ001 - naive on purpose
        datetime(2026, 10, 7, 9, 0, tzinfo=timezone(timedelta(hours=-3))),
    ],
)
def test_the_generation_start_must_be_utc(started_at: datetime) -> None:
    with pytest.raises(ValueError, match="UTC"):
        CycleMeter("chain", nominal_s=60.0, window=3, started_at=started_at)
