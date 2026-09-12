"""Upgrade detection (T4.8b): the captured IDL and ``ProgramData`` fixtures are what the
builder was proven against; the chain differing from them is ``program_upgraded``.

The loud test is the first one: whoever re-captures ``t48b_idl_pump_onchain_raw.json``
and finds a different hash has a program that changed — re-run T4.8b (parity,
simulation, docs) before touching ``EXPECTED_PUMP_PROGRAM``.
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
    sha = canonical_idl_sha256((FIXTURES / "t48b_idl_pump_onchain_raw.json").read_bytes())
    assert sha == EXPECTED_PUMP_PROGRAM.idl_sha256, (
        f"{UPGRADE_MESSAGE}: IDL on-chain sha256 {sha} != {EXPECTED_PUMP_PROGRAM.idl_sha256}"
    )


def test_the_raw_idl_account_decodes_to_the_same_idl_and_the_t48_copy_hashes_alike() -> None:
    raw = _fixture("t48b_rpc_idl_account_raw.json")
    assert raw["address"] == pump_idl_account_address()
    value = raw["result"]["value"]
    decoded = decode_idl_account(value["data"][0], owner=value["owner"])
    assert decoded.idl_bytes == (FIXTURES / "t48b_idl_pump_onchain_raw.json").read_bytes()
    assert canonical_idl_sha256(decoded.idl_bytes) == EXPECTED_PUMP_PROGRAM.idl_sha256
    idl = json.loads(decoded.idl_bytes)
    assert idl["address"] == PUMP_PROGRAM_ID and len(idl["instructions"]) == 40
    # the IDL account was NOT updated by the 2026-09-12 upgrade: the morning's copy hashes the same
    older = (FIXTURES / "idl_pump_onchain_raw.json").read_bytes()
    assert canonical_idl_sha256(older) == EXPECTED_PUMP_PROGRAM.idl_sha256
    assert json.loads(older) == idl
    assert len(decoded.authority) in (43, 44)


def test_the_programdata_header_gives_the_deploy_slot_and_its_block_time() -> None:
    raw = _fixture("t48b_rpc_programdata_raw.json")
    assert raw["address"] == pump_programdata_address()
    value = raw["result"]["value"]
    assert value["owner"] == BPF_UPGRADEABLE_LOADER_ID
    slot = decode_programdata_header(value["data"][0], owner=value["owner"])
    assert slot == EXPECTED_PUMP_PROGRAM.last_deploy_slot == 446462760
    block_time = _fixture("t48b_rpc_deploy_block_time_raw.json")
    assert block_time["slot"] == slot
    assert datetime.fromtimestamp(block_time["result"], UTC) == datetime(
        2026, 9, 12, 15, 24, 4, tzinfo=UTC
    )  # 12:24:04 BRT — after T4.8's fixtures (07:34–08:04 UTC), before T4.14's probe (17:09)


def test_addresses_are_derived_not_typed() -> None:
    assert pump_idl_account_address() == "AYgC53tU5BbP2NAnv5nConJxAdpQZctvmZK88pu69xRs"
    assert pump_programdata_address() == "B5MvUwXdiW1NMM6QFFD3ssPKBujD4zMohncbM73Z2BQu"


def _identity(**overrides: Any) -> ProgramIdentity:
    base = ProgramIdentity(
        idl_sha256=EXPECTED_PUMP_PROGRAM.idl_sha256,
        idl_authority="x",
        idl_slot=446490886,
        last_deploy_slot=EXPECTED_PUMP_PROGRAM.last_deploy_slot,
        programdata_slot=446490888,
    )
    return replace(base, **overrides)


def test_divergence_is_none_when_matching_and_named_otherwise() -> None:
    assert program_divergence(_identity()) is None
    moved = program_divergence(_identity(last_deploy_slot=446462761))
    assert moved is not None and "last_deploy_slot 446462761 != 446462760" in moved
    assert UPGRADE_MESSAGE in moved and "T4.8b" in moved
    rehashed = program_divergence(_identity(idl_sha256="ab" * 32))
    assert rehashed is not None and "idl_sha256" in rehashed and UPGRADE_MESSAGE in rehashed
    both = program_divergence(_identity(idl_sha256="ab" * 32, last_deploy_slot=1))
    assert both is not None and "last_deploy_slot" in both and "idl_sha256" in both


class _FakeRpc:
    """``getAccountInfo`` answered from the fixtures; every call recorded."""

    def __init__(self, *, programdata_slot: int | None = None) -> None:
        self.calls: list[tuple[str, list[Any]]] = []
        self.idl = _fixture("t48b_rpc_idl_account_raw.json")["result"]
        self.programdata = _fixture("t48b_rpc_programdata_raw.json")["result"]
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
    assert identity.idl_slot == 446490886 and identity.last_deploy_slot == 446462760
    moved = _FakeRpc(programdata_slot=446462760 + 5)
    assert read_last_deploy_slot(moved) == 446462765  # type: ignore[arg-type]
    assert len(moved.calls) == 1
    assert program_divergence(read_program_identity(moved)) is not None  # type: ignore[arg-type]


def test_malformed_accounts_are_refused_not_guessed() -> None:
    raw = _fixture("t48b_rpc_idl_account_raw.json")["result"]["value"]
    with pytest.raises(MalformedMessage, match="owner"):
        decode_idl_account(raw["data"][0], owner=BPF_UPGRADEABLE_LOADER_ID)
    with pytest.raises(MalformedMessage, match="discriminator"):
        decode_idl_account(base64.b64encode(b"\x00" * 64).decode(), owner=PUMP_PROGRAM_ID)
    with pytest.raises(MalformedMessage, match="base64"):
        decode_idl_account("not base64!", owner=PUMP_PROGRAM_ID)
    pd = _fixture("t48b_rpc_programdata_raw.json")["result"]["value"]
    with pytest.raises(MalformedMessage, match="loader"):
        decode_programdata_header(pd["data"][0], owner=PUMP_PROGRAM_ID)
    wrong_tag = base64.b64encode(struct.pack("<IQ", 2, 1) + b"\x00" * 33).decode()
    with pytest.raises(MalformedMessage, match="tag"):
        decode_programdata_header(wrong_tag, owner=BPF_UPGRADEABLE_LOADER_ID)
    with pytest.raises(MalformedMessage, match="JSON"):
        canonical_idl_sha256(b"{not json")
