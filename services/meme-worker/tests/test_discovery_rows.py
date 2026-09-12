"""A create frame with an empty identity string becomes a row the schema accepts.

Production, 12/09/2026 08:52:32Z: PumpPortal emitted a ``create`` with ``uri: ""``;
the adapter accepts an empty ``name``/``symbol``/``uri`` (T4.1), ``meme_tokens``
refuses one by CHECK, and the unhandled ``IntegrityError`` restarted the whole
worker. The row mapping now turns ``""`` into ``NULL`` ("not observed"), which is
the only value the schema reserves for an unknown identity.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from hunter_meme_worker.discovery import token_row_from_event

from hunter_exchanges.pumpfun import normalize

pytestmark = pytest.mark.unit

FIXTURES = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "exchange-adapters"
    / "tests"
    / "fixtures"
    / "pumpfun"
)


def _first_pump_create() -> dict[str, Any]:
    raw = (FIXTURES / "pumpportal_ws_capture_raw.jsonl").read_text(encoding="utf-8")
    for line in raw.splitlines():
        if not line.strip():
            continue
        frame = json.loads(line, parse_float=Decimal)
        if frame.get("txType") == "create" and frame.get("pool") == "pump":
            return frame
    raise AssertionError("the T4.1 capture no longer carries a pump.fun create")


def test_an_empty_uri_maps_to_null_not_to_an_empty_string() -> None:
    frame = dict(_first_pump_create())
    frame["uri"] = ""
    row = token_row_from_event(normalize.parse_new_token(frame))
    assert row.uri is None, "the CHECK constraint refuses '' — NULL is the honest value"
    assert row.name == frame["name"] and row.symbol == frame["symbol"], (
        "the other identity fields are kept exactly as observed"
    )


def test_every_identity_field_follows_the_same_rule() -> None:
    frame = dict(_first_pump_create())
    frame["name"] = ""
    frame["symbol"] = ""
    frame["uri"] = ""
    row = token_row_from_event(normalize.parse_new_token(frame))
    assert (row.name, row.symbol, row.uri) == (None, None, None)
    assert row.creator == frame["traderPublicKey"], "the creator is never empty by contract"
    assert row.mint == frame["mint"]


def test_a_real_identity_is_untouched() -> None:
    frame = _first_pump_create()
    row = token_row_from_event(normalize.parse_new_token(frame))
    assert (row.name, row.symbol, row.uri) == (frame["name"], frame["symbol"], frame["uri"])


def _first_migrate() -> dict[str, Any]:
    raw = (FIXTURES / "pumpportal_ws_capture_raw.jsonl").read_text(encoding="utf-8")
    for line in raw.splitlines():
        if line.strip():
            frame = json.loads(line, parse_float=Decimal)
            if frame.get("txType") == "migrate":
                return frame
    raise AssertionError("the T4.1 capture no longer carries a migrate frame")


def test_a_migration_frame_is_the_pool_created_signal_and_therefore_a_completion() -> None:
    """T4.2d: the PumpPortal ``migrate`` is one of the four completion signals
    (``pool_created_at``, source ``pumpportal_ws``), and a pool is evidence
    enough on its own — unlike a REST ``complete`` with a zero reserve."""
    row = token_row_from_event(normalize.parse_migration(_first_migrate()))
    assert row.migrated_at is not None and row.migrated_pool == "pump-amm"
    assert row.pool_created_at == row.migrated_at
    assert row.pool_created_source == "pumpportal_ws"
    assert row.completed_at == row.migrated_at
    assert row.rest_complete_seen_at is None and row.graduated_board_seen_at is None
