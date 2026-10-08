"""T4.8f/T4.8g: the runtime detector watches the programs our builders also depend on, not only
the pump program — PumpSwap (``sell`` of a migrated position) and the pump **fee** program (both
builders pass ``pfeeUx…``). Redeployed together twice: 2026-10-02 within 32 s and 2026-10-08
within 27 s of each other (16:20:03Z, 16:20:17Z, 16:20:30Z): ``FeeConfig`` unchanged proves nothing
about bytecode.

Fixtures ``t48g_rpc_programdata_*_raw.json``: the 45-byte ``ProgramData`` headers of the three
programs, read-only, 2026-10-08 (context slots 454629029..454629051).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.program_identity import decode_programdata_header
from hunter_exchanges.pumpfun.program_watch import (
    WATCHED_PROGRAMS,
    programdata_address,
    read_deploy_slots,
    watched_divergence,
)
from hunter_exchanges.pumpswap.decode import PUMPSWAP_PROGRAM_ID
from hunter_exchanges.pumpswap.pdas import PUMP_FEE_PROGRAM_ID

FIXTURES = Path(__file__).parents[1] / "fixtures/pumpfun"


def _fx(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


def _header(label: str) -> dict[str, Any]:
    return _fx(f"t48g_rpc_programdata_{label}_raw.json")["result"]["value"]


class FakeRpc:
    """``getMultipleAccounts`` over the recorded headers; ``slots`` overrides a program's slot."""

    def __init__(self, *, missing: set[str] | None = None) -> None:
        self.calls: list[tuple[str, list[Any]]] = []
        self.missing = missing or set()
        by_address = {
            v["programdata"]: _header(label)
            for label, v in _fx("t48g_rpc_deploy_block_times.json").items()
        }
        self.by_address = by_address

    def call(self, method: str, params: list[Any]) -> Any:
        self.calls.append((method, params))
        assert method == "getMultipleAccounts"
        values = [
            None if address in self.missing else self.by_address[address] for address in params[0]
        ]
        return {"context": {"slot": 454629051}, "value": values}


def test_the_recorded_headers_carry_the_deploy_slots_of_2026_10_08() -> None:
    slots = {
        label: decode_programdata_header(
            str(_header(label)["data"][0]), owner=_header(label)["owner"]
        )
        for label in ("pump", "pumpswap", "pump_fees")
    }
    assert slots == {"pump": 454_596_459, "pumpswap": 454_596_406, "pump_fees": 454_596_501}
    # 16:20:03Z, 16:20:17Z, 16:20:30Z — within 27 s
    times = {label: v["block_time"] for label, v in _fx("t48g_rpc_deploy_block_times.json").items()}
    assert max(times.values()) - min(times.values()) == 27


def test_the_watch_list_covers_pumpswap_and_the_fee_program_at_these_slots() -> None:
    by_id = {w.program_id: w for w in WATCHED_PROGRAMS}
    assert set(by_id) == {PUMPSWAP_PROGRAM_ID, PUMP_FEE_PROGRAM_ID}
    assert by_id[PUMPSWAP_PROGRAM_ID].last_deploy_slot == 454_596_406
    assert by_id[PUMP_FEE_PROGRAM_ID].last_deploy_slot == 454_596_501
    for w in WATCHED_PROGRAMS:
        assert w.label and w.task and w.captured_at


def test_programdata_addresses_match_the_chain() -> None:
    for label, v in _fx("t48g_rpc_deploy_block_times.json").items():
        assert programdata_address(v["program"]) == v["programdata"], label


def test_one_multiple_accounts_call_reads_every_slot() -> None:
    rpc = FakeRpc()
    ids = [PUMP_PROGRAM_ID, *(w.program_id for w in WATCHED_PROGRAMS)]
    slots = read_deploy_slots(rpc, ids)  # type: ignore[arg-type]
    assert slots == {
        PUMP_PROGRAM_ID: 454_596_459,
        PUMPSWAP_PROGRAM_ID: 454_596_406,
        PUMP_FEE_PROGRAM_ID: 454_596_501,
    }
    assert len(rpc.calls) == 1 and rpc.calls[0][0] == "getMultipleAccounts"
    assert rpc.calls[0][1][1]["dataSlice"] == {"offset": 0, "length": 45}


def test_a_program_missing_from_the_answer_is_an_error_not_a_zero() -> None:
    rpc = FakeRpc(missing={programdata_address(PUMPSWAP_PROGRAM_ID)})
    with pytest.raises(MalformedMessage):
        read_deploy_slots(rpc, [PUMPSWAP_PROGRAM_ID])  # type: ignore[arg-type]


def test_divergence_names_the_program_and_both_slots() -> None:
    watch = next(w for w in WATCHED_PROGRAMS if w.program_id == PUMPSWAP_PROGRAM_ID)
    assert watched_divergence(watch, watch.last_deploy_slot) is None
    text = watched_divergence(watch, watch.last_deploy_slot + 1)
    assert text is not None
    assert "pumpswap" in text and "454596407" in text and "454596406" in text
