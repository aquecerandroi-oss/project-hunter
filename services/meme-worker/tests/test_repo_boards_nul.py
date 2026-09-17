"""A board frame whose name carries a NUL byte becomes parameters PostgreSQL accepts.

Production, 17/09/2026 09:05:02Z and 09:06:00Z: the graduated board delivered
``TIT BRAIN``-style entries, one of them with ``\\x00`` in its name; ``text``
refuses ``0x00``, ``jsonb`` refuses ``\\u0000``, and the fold loop's
``INSERT INTO meme_board_observations`` killed the whole worker twice (restarts
2 and 3 of the new container). T4.47 had cleaned ``meme_tokens`` rows only;
T4.47b cleans this insert's parameters at the same boundary.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from hunter_meme_worker.repo_boards import BoardMinuteRow, board_payload
from hunter_meme_worker.repo_rows import NUL

pytestmark = pytest.mark.unit

_AT = datetime(2026, 9, 17, 9, 5, 59, tzinfo=UTC)


def _row(**fields: object) -> BoardMinuteRow:
    base: dict[str, object] = {
        "observed_at": _AT,
        "board": "graduated",
        "mint": "DwNnxu6c9UJixNogoX2HxP2NmEHv8naqgAMZdubVpump",
        "minute_end": _AT,
        "received_at": _AT,
        "mint_updated_at": None,
        "version": 3959455,
        "position": 0,
        "patches": 69,
        "first_seen_in_board_at": _AT,
        "last_seen_in_board_at": _AT,
        "left_board_at": None,
        "exposure_censored": False,
        "source": "trenches_ws",
    }
    base.update(fields)
    return BoardMinuteRow(**base)  # type: ignore[arg-type]


def test_the_columns_lose_only_the_nul() -> None:
    (values,) = board_payload([_row(name="TIT BRAIN" + NUL, symbol="TIT", chain="solana:mainnet")])
    assert values["name"] == "TIT BRAIN"
    assert values["symbol"] == "TIT"
    assert values["chain"] == "solana:mainnet"
    assert not any(isinstance(v, str) and NUL in v for v in values.values())


def test_a_nul_only_name_is_not_observed() -> None:
    (values,) = board_payload([_row(name=NUL)])
    assert values["name"] is None


def test_extra_json_never_carries_u0000() -> None:
    (values,) = board_payload([_row(extra={"hr": False, "note": "x" + NUL + "y"})])
    assert values["extra"] is not None
    assert "\\u0000" not in values["extra"]
    assert '"note": "xy"' in values["extra"]


def test_a_clean_row_is_untouched() -> None:
    (values,) = board_payload([_row(name="RAMEN", symbol="RAMEN", market_cap_usd=Decimal("1"))])
    assert (values["name"], values["symbol"], values["market_cap_usd"]) == (
        "RAMEN",
        "RAMEN",
        Decimal("1"),
    )
    assert values["extra"] is None
