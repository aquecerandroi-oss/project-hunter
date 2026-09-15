"""Upgrade detection: the captured IDL and ``ProgramData`` fixtures are what the
builder was proven against; the chain differing from them is ``program_upgraded``.

T4.8c (2026-09-15): the program's *second* deploy that week (slot 447228373,
07:34:32 BRT) republished the on-chain IDL account too — unlike T4.8b's, which
left it untouched. :data:`EXPECTED_PUMP_PROGRAM` now points at the T4.8c capture;
:data:`PREVIOUS_PUMP_PROGRAM` keeps T4.8b's values for history.

The loud test is the first one: whoever re-captures ``t48c_idl_pump_onchain_raw.json``
and finds a different hash has a program that changed — re-run this task's method
(parity, simulation, docs) before touching ``EXPECTED_PUMP_PROGRAM`` again.
"""

from __future__ import annotations

import base64
import json
import struct
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.program_identity import (
    BPF_UPGRADEABLE_LOADER_ID,
    EXPECTED_PUMP_PROGRAM,
    PREVIOUS_PUMP_PROGRAM,
    PUMP_PROGRAM_HISTORY,
    UPGRADE_MESSAGE,
    ProgramIdentity,
    canonical_idl_sha256,
    decode_idl_account,
    decode_programdata_header,
    program_divergence,
    pump_idl_account_address,
    pump_programdata_address,
    read_last_deploy_slot,
    read_program_identity,
)

FIXTURES = Path(__file__).parents[1] / "fixtures/pumpfun"


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_the_captured_idl_hashes_to_the_expectation_or_the_program_changed() -> None:
    sha = canonical_idl_sha256((FIXTURES / "t48c_idl_pump_onchain_raw.json").read_bytes())
    assert sha == EXPECTED_PUMP_PROGRAM.idl_sha256, (
        f"{UPGRADE_MESSAGE}: IDL on-chain sha256 {sha} != {EXPECTED_PUMP_PROGRAM.idl_sha256}"
    )


def test_the_raw_idl_account_decodes_to_the_same_idl() -> None:
    raw = _fixture("t48c_rpc_idl_account_raw.json")
    assert raw["address"] == pump_idl_account_address()
    value = raw["result"]["value"]
    decoded = decode_idl_account(value["data"][0], owner=value["owner"])
    assert decoded.idl_bytes == (FIXTURES / "t48c_idl_pump_onchain_raw.json").read_bytes()
    assert canonical_idl_sha256(decoded.idl_bytes) == EXPECTED_PUMP_PROGRAM.idl_sha256
    idl = json.loads(decoded.idl_bytes)
    assert idl["address"] == PUMP_PROGRAM_ID and len(idl["instructions"]) == 47
    assert len(decoded.authority) in (43, 44)
    # T4.8b's copy is a *different*, older IDL — republished this deploy, unlike 09-12's.
    older = (FIXTURES / "t48b_idl_pump_onchain_raw.json").read_bytes()
    assert canonical_idl_sha256(older) == PREVIOUS_PUMP_PROGRAM.idl_sha256
    assert canonical_idl_sha256(older) != EXPECTED_PUMP_PROGRAM.idl_sha256
    old_idl = json.loads(older)
    assert len(old_idl["instructions"]) == 40 and old_idl != idl


def test_the_programdata_header_gives_the_deploy_slot_and_its_block_time() -> None:
    raw = _fixture("t48c_rpc_programdata_raw.json")
    assert raw["address"] == pump_programdata_address()
    value = raw["result"]["value"]
    assert value["owner"] == BPF_UPGRADEABLE_LOADER_ID
    slot = decode_programdata_header(value["data"][0], owner=value["owner"])
    assert slot == EXPECTED_PUMP_PROGRAM.last_deploy_slot == 447228373
    block_time = _fixture("t48c_rpc_deploy_block_time_raw.json")
    assert block_time["slot"] == slot
    assert datetime.fromtimestamp(block_time["result"], UTC) == datetime(
        2026, 9, 15, 10, 34, 32, tzinfo=UTC
    )  # 07:34:32 BRT — read independently of, and matching, the plantão's KB-0096
    # the upgrade authority did not change from T4.8b's capture
    old_raw = base64.b64decode(
        _fixture("t48b_rpc_programdata_raw.json")["result"]["value"]["data"][0]
    )
    new_raw = base64.b64decode(value["data"][0])
    assert old_raw[13:45] == new_raw[13:45]


def test_addresses_are_derived_not_typed() -> None:
    assert pump_idl_account_address() == "AYgC53tU5BbP2NAnv5nConJxAdpQZctvmZK88pu69xRs"
    assert pump_programdata_address() == "B5MvUwXdiW1NMM6QFFD3ssPKBujD4zMohncbM73Z2BQu"


def test_history_keeps_t48b_and_the_current_expectation_in_order() -> None:
    assert PUMP_PROGRAM_HISTORY == (PREVIOUS_PUMP_PROGRAM, EXPECTED_PUMP_PROGRAM)
    assert (
        PREVIOUS_PUMP_PROGRAM.task == "T4.8b"
        and PREVIOUS_PUMP_PROGRAM.last_deploy_slot == 446462760
    )
    assert (
        EXPECTED_PUMP_PROGRAM.task == "T4.8c"
        and EXPECTED_PUMP_PROGRAM.last_deploy_slot == 447228373
    )
    assert PREVIOUS_PUMP_PROGRAM.last_deploy_slot < EXPECTED_PUMP_PROGRAM.last_deploy_slot


def test_the_old_t48b_expectation_now_reads_as_diverged() -> None:
    """T4.8b's own values, if they were still ``EXPECTED_PUMP_PROGRAM``, would no
    longer match the chain this task captured — the whole point of re-running."""
    identity = ProgramIdentity(
        idl_sha256=EXPECTED_PUMP_PROGRAM.idl_sha256,
        idl_authority="x",
        idl_slot=447334438,
        last_deploy_slot=EXPECTED_PUMP_PROGRAM.last_deploy_slot,
        programdata_slot=447328953,
    )
    assert program_divergence(identity, PREVIOUS_PUMP_PROGRAM) is not None
    assert program_divergence(identity, EXPECTED_PUMP_PROGRAM) is None


def _identity(**overrides: Any) -> ProgramIdentity:
    base = ProgramIdentity(
        idl_sha256=EXPECTED_PUMP_PROGRAM.idl_sha256,
        idl_authority="x",
        idl_slot=447334438,
        last_deploy_slot=EXPECTED_PUMP_PROGRAM.last_deploy_slot,
        programdata_slot=447328953,
    )
    return replace(base, **overrides)


def test_divergence_is_none_when_matching_and_named_otherwise() -> None:
    assert program_divergence(_identity()) is None
    moved = program_divergence(_identity(last_deploy_slot=447228374))
    assert moved is not None and "last_deploy_slot 447228374 != 447228373" in moved
    assert UPGRADE_MESSAGE in moved and "T4.8c" in moved
    rehashed = program_divergence(_identity(idl_sha256="ab" * 32))
    assert rehashed is not None and "idl_sha256" in rehashed and UPGRADE_MESSAGE in rehashed
    both = program_divergence(_identity(idl_sha256="ab" * 32, last_deploy_slot=1))
    assert both is not None and "last_deploy_slot" in both and "idl_sha256" in both


class _FakeRpc:
    """``getAccountInfo`` answered from the fixtures; every call recorded."""

    def __init__(self, *, programdata_slot: int | None = None) -> None:
        self.calls: list[tuple[str, list[Any]]] = []
        self.idl = _fixture("t48c_rpc_idl_account_raw.json")["result"]
        self.programdata = _fixture("t48c_rpc_programdata_raw.json")["result"]
        if programdata_slot is not None:
            header = struct.pack("<IQ", 3, programdata_slot) + b"\x01" + b"\x00" * 32
            value = dict(self.programdata["value"])
            value["data"] = [base64.b64encode(header).decode("ascii"), "base64"]
            self.programdata = {**self.programdata, "value": value}

    def call(self, method: str, params: list[Any]) -> Any:
        self.calls.append((method, params))
        assert method == "getAccountInfo"
        if params[0] == pump_idl_account_address():
            return self.idl
        if params[0] == pump_programdata_address():
            assert params[1]["dataSlice"] == {"offset": 0, "length": 45}
            return self.programdata
        raise AssertionError(params[0])


def test_read_program_identity_is_two_reads_and_the_runtime_check_one() -> None:
    rpc = _FakeRpc()
    identity = read_program_identity(rpc)  # type: ignore[arg-type]
    assert [m for m, _ in rpc.calls] == ["getAccountInfo", "getAccountInfo"]
    assert program_divergence(identity) is None
    assert identity.last_deploy_slot == 447228373
    moved = _FakeRpc(programdata_slot=447228373 + 5)
    assert read_last_deploy_slot(moved) == 447228378  # type: ignore[arg-type]
    assert len(moved.calls) == 1
    assert program_divergence(read_program_identity(moved)) is not None  # type: ignore[arg-type]


def test_malformed_accounts_are_refused_not_guessed() -> None:
    raw = _fixture("t48c_rpc_idl_account_raw.json")["result"]["value"]
    with pytest.raises(MalformedMessage, match="owner"):
        decode_idl_account(raw["data"][0], owner=BPF_UPGRADEABLE_LOADER_ID)
    with pytest.raises(MalformedMessage, match="discriminator"):
        decode_idl_account(base64.b64encode(b"\x00" * 64).decode(), owner=PUMP_PROGRAM_ID)
    with pytest.raises(MalformedMessage, match="base64"):
        decode_idl_account("not base64!", owner=PUMP_PROGRAM_ID)
    pd = _fixture("t48c_rpc_programdata_raw.json")["result"]["value"]
    with pytest.raises(MalformedMessage, match="loader"):
        decode_programdata_header(pd["data"][0], owner=PUMP_PROGRAM_ID)
    wrong_tag = base64.b64encode(struct.pack("<IQ", 2, 1) + b"\x00" * 33).decode()
    with pytest.raises(MalformedMessage, match="tag"):
        decode_programdata_header(wrong_tag, owner=BPF_UPGRADEABLE_LOADER_ID)
    with pytest.raises(MalformedMessage, match="JSON"):
        canonical_idl_sha256(b"{not json")
