"""Wave 1a of H-030: the recorded fixtures say what they are.

``fixtures/t1a_provenance.json`` lists, for every ``t1a_*`` fixture, the signature, slot, block time
and version it was read at from the public RPC on 2026-10-05. This test keeps the file and the
fixtures from drifting apart (a fixture without provenance is a fixture nobody can re-read), and
checks that every fixture is a post-redeploy transaction (the PumpSwap redeployed at slot
452654882, 2026-10-02 15:47:07Z).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from .t1a_chain import FIXTURES, load

_PROVENANCE = load("t1a_provenance.json")
_ENTRIES: list[dict[str, Any]] = _PROVENANCE["fixtures"]
_REDEPLOY_SLOT = 452_654_882
_ERROR_FILE = "pumpfun/t1a_rpc_get_transaction_v1_unsupported_error_raw.json"


def test_every_t1a_fixture_on_disk_has_provenance_and_vice_versa() -> None:
    on_disk = {
        f"{path.parent.name}/{path.name}" for path in FIXTURES.glob("*/t1a_*") if path.is_file()
    }
    assert on_disk == {entry["file"] for entry in _ENTRIES}


def test_the_provenance_names_its_source_and_never_a_credential() -> None:
    assert _PROVENANCE["rpc"].startswith("https://api.mainnet-beta.solana.com")
    assert "api-key" not in str(_PROVENANCE).lower() and "api_key" not in str(_PROVENANCE).lower()


@pytest.mark.parametrize("entry", _ENTRIES, ids=lambda e: e["file"].split("/")[-1])
def test_each_fixture_is_the_transaction_its_provenance_says(entry: dict[str, Any]) -> None:
    assert entry["slot"] > _REDEPLOY_SLOT
    if entry["file"] == _ERROR_FILE:
        reply = load(entry["file"])
        assert reply["error"]["code"] == -32015
        return
    tx = load(entry["file"])
    assert tx["transaction"]["signatures"][0] == entry["signature"]
    assert tx["slot"] == entry["slot"]
    assert tx["version"] == entry["version"]
    assert tx["meta"]["err"] is None
    block_time = datetime.fromtimestamp(tx["blockTime"], tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert block_time == entry["block_time_utc"]
    assert block_time > "2026-10-02T15:47:21Z"  # after both redeploys


def test_the_error_fixture_is_the_reply_to_the_v1_sell_fixture() -> None:
    sell = next(e for e in _ENTRIES if "v1_pump_sell" in e["file"])
    error = next(e for e in _ENTRIES if e["file"] == _ERROR_FILE)
    assert sell["signature"] == error["signature"]
