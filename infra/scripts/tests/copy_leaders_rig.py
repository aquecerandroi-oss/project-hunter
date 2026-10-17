"""Labelled test doubles for the copy-pilot leader selection (never production
data): wire-shaped ``/pnl-leaderboard`` and ``/users/{address}`` payloads that
mirror the shapes recorded in ``docs/PUMPFUN.md`` §10.3, plus the helpers the
tests use to build boards of synthetic wallets.

The addresses are synthetic base58 strings (``Tst`` + two letters + padding);
the personal fields the real API returns (username, profile image, X handle,
userId) are filled with a marker so a test can prove the tool never keeps them.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "copy_leaders"
PERSONAL_MARKER = "PERSONAL-DATA-MARKER"
_ALPHABET = "ABCDEFGHJKLMNPQRSTUV"


def addr(n: int) -> str:
    """A synthetic, valid-looking Solana address (44 base58 chars)."""
    return "Tst" + _ALPHABET[n // 400] + _ALPHABET[n // 20 % 20] + _ALPHABET[n % 20] + "A" * 38


def wire_entry(
    address: str,
    *,
    rank: int = 1,
    realized: str = "10",
    unrealized: str = "2",
    spend: str = "50",
    positions: int = 20,
    verified: bool = False,
) -> dict[str, Any]:
    pnl = Decimal(realized) + Decimal(unrealized)
    return {
        "rank": rank,
        "walletAddress": address,
        "pnlSol": float(pnl),
        "pnlUsd": float(pnl) * 150,
        "pnlPercent": 10.5,
        "buySpendSol": float(Decimal(spend)),
        "realizedPnlSol": float(Decimal(realized)),
        "realizedPnlUsd": float(Decimal(realized)) * 150,
        "unrealizedPnlSol": float(Decimal(unrealized)),
        "unrealizedPnlUsd": float(Decimal(unrealized)) * 150,
        "positionsCount": positions,
        "topPositions": [{"mint": "M" * 43 + "pump", "chainId": "1399811149", "symbol": "X"}],
        "lastRefreshedAtMs": 1_790_000_000_000 + rank,
        "username": PERSONAL_MARKER,
        "profileImage": f"https://img.example/{PERSONAL_MARKER}.png",
        "xUsername": PERSONAL_MARKER,
        "isVerified": verified,
        "verifiedBadgeVisible": verified,
        "userId": PERSONAL_MARKER,
    }


def wire_board(entries: Sequence[dict[str, Any]], *, window: int = 1_789_900_000) -> dict[str, Any]:
    return {
        "entries": list(entries),
        "periodType": 3,
        "periodLabel": "24h",
        "windowStartSec": window,
    }


def dumps(payload: Any) -> str:
    return json.dumps(payload)


def user_payload(followers: int = 1234) -> dict[str, Any]:
    return {
        "address": "x",
        "userId": PERSONAL_MARKER,
        "username": PERSONAL_MARKER,
        "bio": PERSONAL_MARKER,
        "profile_image": PERSONAL_MARKER,
        "followers": followers,
        "following": 3,
    }


class FakeApi:
    """An ``httpx.MockTransport`` handler: boards by (period, sort), users by
    address; records every request so a test can count and inspect them."""

    def __init__(
        self,
        boards: dict[tuple[str, str], dict[str, Any]],
        users: dict[str, int] | None = None,
        *,
        remaining: int | None = 50,
        override: Callable[[httpx.Request], httpx.Response | None] | None = None,
    ) -> None:
        self.boards = boards
        self.users = users or {}
        self.remaining = remaining
        self.override = override
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.override is not None and (forced := self.override(request)) is not None:
            return forced
        headers = (
            {}
            if self.remaining is None
            else {"x-ratelimit-limit": "60", "x-ratelimit-remaining": str(self.remaining)}
        )
        path = request.url.path
        if path == "/pnl-leaderboard":
            key = (request.url.params["period"], request.url.params.get("sort", "combined"))
            board = self.boards.get(key)
            if board is None:
                return httpx.Response(404, json={"error": "no such board"}, headers=headers)
            return httpx.Response(200, content=dumps(board), headers=headers)
        if path.startswith("/users/"):
            address = path.removeprefix("/users/")
            if address not in self.users:
                return httpx.Response(404, json={"error": "not found"}, headers=headers)
            return httpx.Response(
                200, content=dumps(user_payload(self.users[address])), headers=headers
            )
        return httpx.Response(404, headers=headers)

    def client(self) -> httpx.Client:
        return httpx.Client(
            transport=httpx.MockTransport(self), base_url="https://frontend-api-v3.pump.fun"
        )

    @property
    def paths(self) -> list[str]:
        return [r.url.path for r in self.requests]
