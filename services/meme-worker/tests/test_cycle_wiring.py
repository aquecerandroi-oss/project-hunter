"""The wiring of the cycle meters (``cycle_wiring``): who is enabled, what a boot
announces over a hash that still holds the previous process's numbers, and that a
wrapped step feeds the history.
"""

from __future__ import annotations

import pytest

from hunter_meme_worker.config import MemeConfig
from hunter_meme_worker.cycle_wiring import CycleInstruments, build_cycle_instruments

pytestmark = pytest.mark.unit


def _instruments(hash_: dict[str, str], **config: object) -> CycleInstruments:
    async def write(fields: dict[str, str]) -> None:
        hash_.update(fields)

    return build_cycle_instruments(MemeConfig(**config), object(), write)  # type: ignore[arg-type]


async def test_a_boot_with_everything_off_still_replaces_the_previous_numbers() -> None:
    hash_ = {
        "chain_cycle_run_id": "old-process",
        "chain_cycle_ms_p95": "70000",
        "lab_cycle_run_id": "old-process",
        "lab_cycle_ms_p95": "20000",
    }
    cycles = _instruments(hash_, enabled=False)
    await cycles.announce()
    for loop in ("chain", "lab"):
        assert hash_[f"{loop}_cycle_run_id"] != "old-process"
        assert hash_[f"{loop}_cycle_ms_p95"] == ""
        assert hash_[f"{loop}_cycle_enabled"] == "false"
        assert hash_[f"{loop}_cycles_total"] == "0"


async def test_each_loop_is_enabled_only_when_the_radar_and_the_loop_are() -> None:
    hash_: dict[str, str] = {}
    cycles = _instruments(hash_, enabled=True, chain_curves_enabled=False, lab_enabled=True)
    await cycles.announce()
    assert hash_["chain_cycle_enabled"] == "false"
    assert hash_["lab_cycle_enabled"] == "true"
    assert hash_["chain_cycle_nominal_ms"] == "60000"
    assert hash_["lab_cycle_nominal_ms"] == "15000"


async def test_a_wrapped_step_publishes_and_queues_one_sample_per_cycle() -> None:
    hash_: dict[str, str] = {}
    cycles = _instruments(hash_, enabled=True)

    async def step(ctx: object) -> str:
        return "ok"

    assert await cycles.chain_step(step)(object()) == "ok"
    assert await cycles.lab_step(step)(object()) == "ok"
    assert hash_["chain_cycles_total"] == "1"
    assert hash_["lab_cycles_total"] == "1"
    queued = [(r.data["loop"], r.data["seq"], r.data["run_id"]) for _, r in cycles.history.peek(10)]
    assert queued == [
        ("chain", 1, cycles.chain.run_id),
        ("lab", 1, cycles.lab.run_id),
    ]
