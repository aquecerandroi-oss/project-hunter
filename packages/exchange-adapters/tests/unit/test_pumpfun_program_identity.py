"""Upgrade detection: the captured IDL and ``ProgramData`` fixtures are what the
builder was proven against; the chain differing from them is ``program_upgraded``.

T4.8d (2026-09-23, deploy slot 449734335 / 14:45:19 UTC) is the case that proves
why the detector needs **both** fields: the deploy moved, and the on-chain IDL
account was *not* republished — its bytes are still, to the byte, T4.8c's. A
detector watching only the hash would have said "unchanged" about a program whose
bytecode had just been replaced. :data:`EXPECTED_PUMP_PROGRAM` now points at the
T4.8d capture, :data:`PREVIOUS_PUMP_PROGRAM` at T4.8c's, and
:data:`PUMP_PROGRAM_HISTORY` carries all three deploys, oldest first.

The loud test is the first one: whoever re-captures the IDL account and finds a
different hash, or reads a different deploy slot, has a program that changed —
re-run this task's method (parity against real post-upgrade trades, mainnet
simulation through the executor's path, docs) before touching
``EXPECTED_PUMP_PROGRAM`` again. ``.claude/state/notes-T4.8d.md`` §"checklist".
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
IDL_SLOT_T48D = 449773161
PROGRAMDATA_SLOT_T48D = 449773156


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_the_captured_idl_hashes_to_the_expectation_or_the_program_changed() -> None:
    sha = canonical_idl_sha256((FIXTURES / "t48c_idl_pump_onchain_raw.json").read_bytes())
    assert sha == EXPECTED_PUMP_PROGRAM.idl_sha256, (
        f"{UPGRADE_MESSAGE}: IDL on-chain sha256 {sha} != {EXPECTED_PUMP_PROGRAM.idl_sha256}"
    )


def test_the_t48d_deploy_did_not_republish_the_idl_account() -> None:
    """The finding that justifies keeping the deploy slot in the detector: T4.8d's
    IDL account is byte-for-byte T4.8c's (same base64, same decompressed bytes,
    same hash), read at a much later context slot. Only ``last_deploy_slot`` moved."""
    old = _fixture("t48c_rpc_idl_account_raw.json")
    new = _fixture("t48d_rpc_idl_account_raw.json")
    assert new["address"] == old["address"] == pump_idl_account_address()
    assert new["result"]["value"]["data"][0] == old["result"]["value"]["data"][0]
    assert new["result"]["context"]["slot"] == IDL_SLOT_T48D
    assert new["result"]["context"]["slot"] > old["result"]["context"]["slot"]
    value = new["result"]["value"]
    decoded = decode_idl_account(value["data"][0], owner=value["owner"])
    assert decoded.idl_bytes == (FIXTURES / "t48c_idl_pump_onchain_raw.json").read_bytes()
    assert canonical_idl_sha256(decoded.idl_bytes) == EXPECTED_PUMP_PROGRAM.idl_sha256
    assert EXPECTED_PUMP_PROGRAM.idl_sha256 == PREVIOUS_PUMP_PROGRAM.idl_sha256
    idl = json.loads(decoded.idl_bytes)
    assert idl["address"] == PUMP_PROGRAM_ID and len(idl["instructions"]) == 47
    # T4.8b's copy is still a different, older IDL (40 instructions) — the T4.8c
    # deploy *did* republish it, which is why the hash alone is not the detector.
    older = (FIXTURES / "t48b_idl_pump_onchain_raw.json").read_bytes()
    assert canonical_idl_sha256(older) == PUMP_PROGRAM_HISTORY[0].idl_sha256
    assert canonical_idl_sha256(older) != EXPECTED_PUMP_PROGRAM.idl_sha256
    assert len(json.loads(older)["instructions"]) == 40


def test_the_programdata_header_gives_the_deploy_slot_and_its_block_time() -> None:
    raw = _fixture("t48d_rpc_programdata_raw.json")
    assert raw["address"] == pump_programdata_address()
    value = raw["result"]["value"]
    assert value["owner"] == BPF_UPGRADEABLE_LOADER_ID
    slot = decode_programdata_header(value["data"][0], owner=value["owner"])
    assert slot == EXPECTED_PUMP_PROGRAM.last_deploy_slot == 449734335
    block_time = _fixture("t48d_rpc_deploy_block_time_raw.json")
    assert block_time["slot"] == slot
    assert datetime.fromtimestamp(block_time["result"], UTC) == datetime(
        2026, 9, 23, 14, 45, 19, tzinfo=UTC
    )  # 11:45:19 BRT
    # the upgrade authority did not change from T4.8c's capture
    old_raw = base64.b64decode(
        _fixture("t48c_rpc_programdata_raw.json")["result"]["value"]["data"][0]
    )
    new_raw = base64.b64decode(value["data"][0])
    assert old_raw[12] == new_raw[12] == 1, "Option<Pubkey> present (still upgradeable)"
    assert old_raw[13:45] == new_raw[13:45]


def test_addresses_are_derived_not_typed() -> None:
    assert pump_idl_account_address() == "AYgC53tU5BbP2NAnv5nConJxAdpQZctvmZK88pu69xRs"
    assert pump_programdata_address() == "B5MvUwXdiW1NMM6QFFD3ssPKBujD4zMohncbM73Z2BQu"


def test_history_keeps_the_previous_two_deploys_and_the_current_one_in_order() -> None:
    assert len(PUMP_PROGRAM_HISTORY) == 3
    assert PUMP_PROGRAM_HISTORY[-1] is EXPECTED_PUMP_PROGRAM
    assert PUMP_PROGRAM_HISTORY[-2] is PREVIOUS_PUMP_PROGRAM
    assert [entry.task for entry in PUMP_PROGRAM_HISTORY] == ["T4.8b", "T4.8c", "T4.8d"]
    assert [entry.last_deploy_slot for entry in PUMP_PROGRAM_HISTORY] == [
        446462760,
        447228373,
        449734335,
    ]
    slots = [entry.last_deploy_slot for entry in PUMP_PROGRAM_HISTORY]
    assert slots == sorted(slots), "oldest first, strictly increasing"
    assert len(set(slots)) == 3
    assert EXPECTED_PUMP_PROGRAM.task == "T4.8d"
    assert EXPECTED_PUMP_PROGRAM.captured_at == "2026-09-23T17:37:58Z"
    assert UPGRADE_MESSAGE == "programa mudou: regravar T4.8e"


def test_the_previous_expectations_now_read_as_diverged() -> None:
    """Both older deploys, if they were still ``EXPECTED_PUMP_PROGRAM``, would no
    longer match the chain this task captured — the whole point of re-running.
    T4.8c is the sharp case: **same IDL hash**, so only the slot names it."""
    identity = _identity()
    assert program_divergence(identity, EXPECTED_PUMP_PROGRAM) is None
    for older in PUMP_PROGRAM_HISTORY[:-1]:
        reason = program_divergence(identity, older)
        assert reason is not None and "last_deploy_slot 449734335" in reason
    against_t48c = program_divergence(identity, PREVIOUS_PUMP_PROGRAM)
    assert against_t48c is not None
    assert "idl_sha256" not in against_t48c, "the T4.8d deploy left the IDL untouched"
    against_t48b = program_divergence(identity, PUMP_PROGRAM_HISTORY[0])
    assert against_t48b is not None and "idl_sha256" in against_t48b


def _identity(**overrides: Any) -> ProgramIdentity:
    base = ProgramIdentity(
        idl_sha256=EXPECTED_PUMP_PROGRAM.idl_sha256,
        idl_authority="x",
        idl_slot=IDL_SLOT_T48D,
        last_deploy_slot=EXPECTED_PUMP_PROGRAM.last_deploy_slot,
        programdata_slot=PROGRAMDATA_SLOT_T48D,
    )
    return replace(base, **overrides)


def test_divergence_is_none_when_matching_and_named_otherwise() -> None:
    assert program_divergence(_identity()) is None
    moved = program_divergence(_identity(last_deploy_slot=449734336))
    assert moved is not None and "last_deploy_slot 449734336 != 449734335" in moved
    assert UPGRADE_MESSAGE in moved and "T4.8d" in moved
    rehashed = program_divergence(_identity(idl_sha256="ab" * 32))
    assert rehashed is not None and "idl_sha256" in rehashed and UPGRADE_MESSAGE in rehashed
    both = program_divergence(_identity(idl_sha256="ab" * 32, last_deploy_slot=1))
    assert both is not None and "last_deploy_slot" in both and "idl_sha256" in both


class _FakeRpc:
    """``getAccountInfo`` answered from the fixtures; every call recorded."""

    def __init__(self, *, programdata_slot: int | None = None) -> None:
        self.calls: list[tuple[str, list[Any]]] = []
        self.idl = _fixture("t48d_rpc_idl_account_raw.json")["result"]
        self.programdata = _fixture("t48d_rpc_programdata_raw.json")["result"]
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
    assert identity.last_deploy_slot == 449734335
    moved = _FakeRpc(programdata_slot=449734335 + 5)
    assert read_last_deploy_slot(moved) == 449734340  # type: ignore[arg-type]
    assert len(moved.calls) == 1
    assert program_divergence(read_program_identity(moved)) is not None  # type: ignore[arg-type]


def test_malformed_accounts_are_refused_not_guessed() -> None:
    raw = _fixture("t48d_rpc_idl_account_raw.json")["result"]["value"]
    with pytest.raises(MalformedMessage, match="owner"):
        decode_idl_account(raw["data"][0], owner=BPF_UPGRADEABLE_LOADER_ID)
    with pytest.raises(MalformedMessage, match="discriminator"):
        decode_idl_account(base64.b64encode(b"\x00" * 64).decode(), owner=PUMP_PROGRAM_ID)
    with pytest.raises(MalformedMessage, match="base64"):
        decode_idl_account("not base64!", owner=PUMP_PROGRAM_ID)
    pd = _fixture("t48d_rpc_programdata_raw.json")["result"]["value"]
    with pytest.raises(MalformedMessage, match="loader"):
        decode_programdata_header(pd["data"][0], owner=PUMP_PROGRAM_ID)
    wrong_tag = base64.b64encode(struct.pack("<IQ", 2, 1) + b"\x00" * 33).decode()
    with pytest.raises(MalformedMessage, match="tag"):
        decode_programdata_header(wrong_tag, owner=BPF_UPGRADEABLE_LOADER_ID)
    with pytest.raises(MalformedMessage, match="JSON"):
        canonical_idl_sha256(b"{not json")
