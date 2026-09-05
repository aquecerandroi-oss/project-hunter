"""A fresh, collision-free exchange code per test — the shared Postgres
container is session-scoped, and ``exchanges.code``/``assets.symbol`` are
globally unique, so every integration test that writes markets uses its own
throwaway exchange code instead of a shared ``"fake"``."""

from __future__ import annotations

import uuid


def unique_code(prefix: str = "fake") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"
