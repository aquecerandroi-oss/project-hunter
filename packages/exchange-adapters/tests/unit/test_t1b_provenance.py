"""Wave 1b of H-030: the recorded ``t1b_*`` fixtures say what they are (see ``test_t1a_provenance``)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from .t1a_chain import FIXTURES, load

_PROVENANCE = load("t1b_provenance.json")
_ENTRIES: list[dict[str, Any]] = _PROVENANCE["fixtures"]
_REDEPLOY_SLOT = 452_654_882


def test_every_t1b_fixture_on_disk_has_provenance_and_vice_versa() -> None:
    on_disk = {
        f"{path.parent.name}/{path.name}" for path in FIXTURES.glob("*/t1b_*") if path.is_file()
    }
    assert on_disk == {entry["file"] for entry in _ENTRIES}


def test_the_provenance_names_its_source_and_never_a_credential() -> None:
    assert _PROVENANCE["rpc"].startswith("https://api.mainnet-beta.solana.com")
    assert "api-key" not in str(_PROVENANCE).lower() and "api_key" not in str(_PROVENANCE).lower()


@pytest.mark.parametrize("entry", _ENTRIES, ids=lambda e: e["file"].split("/")[-1])
def test_each_fixture_is_the_transaction_its_provenance_says(entry: dict[str, Any]) -> None:
    tx = load(entry["file"])
    assert tx["transaction"]["signatures"][0] == entry["signature"]
    assert tx["slot"] == entry["slot"] > _REDEPLOY_SLOT
    assert tx["version"] == entry["version"]
    assert tx["meta"]["err"] is None
    block_time = datetime.fromtimestamp(tx["blockTime"], tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert block_time == entry["block_time_utc"]
