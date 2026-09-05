"""MEDIUM-1: ``/ready``'s payload must never contain a key literally named
``ready`` that is really just one check's own result, not the endpoint's
verdict. ``main.py`` registers the partition-lookahead check under a
distinct name (``partitions``) instead of the bound method
``PartitionReadiness.ready`` (whose ``__name__`` is literally ``"ready"``).
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from hunter_core.runtime import WorkerRuntime
from hunter_core.settings import Settings
from hunter_market_worker.partitions import PartitionReadiness

pytestmark = pytest.mark.unit


class _FakeEngine:
    healthy = True


class _FakeRedis:
    healthy = True

    async def ping(self) -> bool:
        return True

    async def hset(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    async def expire(self, *_args: Any, **_kwargs: Any) -> None:
        return None


class _NeverFactory:
    """A ``session_factory`` PartitionReadiness must never actually call in
    these tests -- it always fails open (see ``PartitionReadiness._check``),
    so what matters here is the registered check's *name*, not its result."""

    def __call__(self) -> Any:
        raise AssertionError("must not be called")


@pytest.fixture(autouse=True)
def _patch_check_database(  # pyright: ignore[reportUnusedFunction] - pytest autouse fixture
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_check_database(_engine: Any) -> bool:
        return True

    monkeypatch.setattr("hunter_core.runtime.check_database", fake_check_database)


def test_partition_readiness_ready_method_name_is_the_ambiguous_one() -> None:
    """Documents the root cause: a bound method's ``__name__`` is the
    function's name regardless of the instance attribute it is registered
    under, so ``partitions.ready`` (the pre-fix registration in ``main.py``)
    produced ``details["ready"]``, not ``details["partitions"]``."""
    checker = PartitionReadiness(_NeverFactory())  # type: ignore[arg-type]
    assert checker.ready.__name__ == "ready"


async def test_ready_endpoint_never_exposes_a_key_named_ready() -> None:
    """The fix: wrap the check in a plainly-named function (exactly what
    ``run_market`` in ``main.py`` does) before registering it."""
    runtime = WorkerRuntime(
        "market",
        Settings(),
        instance="host-1:123",
        engine=_FakeEngine(),  # type: ignore[arg-type]
        redis_client=_FakeRedis(),  # type: ignore[arg-type]
    )
    partition_readiness = PartitionReadiness(_NeverFactory())  # type: ignore[arg-type]

    async def partitions() -> bool:
        return await partition_readiness.ready()

    runtime.readiness_checks.append(partitions)
    transport = httpx.ASGITransport(app=runtime.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ready")

    body = response.json()
    assert "ready" not in body
    assert body["partitions"] is True
