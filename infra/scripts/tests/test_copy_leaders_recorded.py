"""Regression over RECORDED responses (``fixtures/copy_leaders/``): the six
``/pnl-leaderboard`` views and the ``/users/{address}`` bodies exactly as the
API returned them on 2026-10-09 04:47Z, truncated to 30 rows and anonymised
(synthetic addresses and mints, names/images/handles redacted; the numbers are
the real ones). They pin that the parser reads the real wire shape and that
the frozen rule gives the same list on it.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
for extra in (SCRIPTS_DIR, SCRIPTS_DIR / "tests"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import copy_leaders_http as http  # noqa: E402
import copy_leaders_rule as rule  # noqa: E402
import copy_select_leaders as cli  # noqa: E402
from copy_leaders_rig import FIXTURES, FakeApi  # noqa: E402

NOW = datetime(2026, 10, 9, 5, 0, 0, tzinfo=UTC)
GOLDEN_ORDER = [
    "FxMMfzvAuJtxwBLixW2T7tRcJECoWfvnGX",
    "FxWd9nCS3w1RzDiJWzY1xGiBuoNwMuFN7A",
    "Fx8pRf6cVSYyTS9SzRSt3x3y4Rc8DgNDbE",
    "FxNkX88rfQqbyJGWooQnpk5K72ezhCZBMG",
    "Fxe6VpU9Dnsso74mtp2ZhysNUVGY4frx8P",
    "FxKNtEyGjTXgfK5JkPJhV4jCQQG26Ho1Pi",
]


def recorded_boards() -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (p, s): json.loads((FIXTURES / f"board_{p}_{s}.json").read_text(encoding="utf-8"))
        for p in ("daily", "weekly", "monthly")
        for s in ("combined", "realized")
    }


def recorded_users() -> dict[str, int]:
    raw = json.loads((FIXTURES / "users.json").read_text(encoding="utf-8"))["users"]
    return {address: user["followers"] for address, user in raw.items()}


def test_the_real_wire_shape_parses_with_no_malformed_row() -> None:
    for (period, sort), payload in recorded_boards().items():
        board = rule.parse_board(period, sort, json.loads(json.dumps(payload)))
        assert len(board.rows) == 30 and board.malformed == 0
        assert board.window_start_sec is not None and board.window_start_sec > 1_788_000_000


def test_the_frozen_rule_on_the_recorded_boards_gives_the_pinned_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(http, "BOARD_ROWS", 30)  # the recorded views are truncated to 30 rows
    api = FakeApi(recorded_boards(), recorded_users(), remaining=59)
    code = cli.main(
        ["--out-dir", str(tmp_path)],
        client=api.client(),
        now=lambda: NOW,
        sleep=lambda s: None,
    )
    assert code == 0
    doc = json.loads(next(tmp_path.glob("leaders-*.json")).read_text(encoding="utf-8"))
    assert [w["address"] for w in doc["wallets"]] == GOLDEN_ORDER
    assert doc["funnel"] == {
        "wallets_seen": 86,
        "rejected_one_period": 57,
        "rejected_realized_not_positive": 7,
        "rejected_too_few_positions": 13,
        "rejected_mostly_unrealized": 2,
        "rejected_net_not_positive": 1,
        "eligible": 6,
        "rule_selected": 6,
        "includes": 0,
    }
    users = recorded_users()
    for wallet in doc["wallets"]:
        follower = wallet["followers"]
        if wallet["address"] in users:
            assert follower["count"] == users[wallet["address"]] and follower["status"] == "ok"
        else:  # a wallet whose profile could not be read is unknown, never 0
            assert follower["count"] is None and follower["status"] == "http_404"
    assert any(w["followers"]["status"] == "ok" for w in doc["wallets"])
    assert "redacted" not in json.dumps(doc).lower()
    assert [b["window_start_sec"] for b in doc["responses"]][0] > 1_788_000_000
