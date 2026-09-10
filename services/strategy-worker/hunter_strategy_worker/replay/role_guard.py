"""Refuses to run the replay CLI inside the live worker's own container (T3.80).

T3.76 ran a replay via ``docker exec hunter-strategy-worker-1 python -m
hunter_strategy_worker.replay.run ...`` — sharing that container's CPU and
database pool with the process the live lane depends on staying instant
(measured: decision lag median 26 s -> 90 s, p95 -> 171 s for the duration).
``docker exec`` bypasses ``infra/docker/entrypoint.sh``, but not the
container's own environment: ``HUNTER_ROLE=strategy`` (``infra/docker/docker-
compose.yml``'s ``strategy-worker`` service) is still set, and is exactly the
value ``entrypoint.sh`` dispatches the long-running consumer on — proof enough
that this process shares that container, not the dedicated ``replay-worker``
compose service (``compose.sh replay``) meant to run it instead.

``role`` is a parameter, not only an environment read, precisely so a test can
assert the refusal (or its absence) without mutating process environment —
"except in tests" (the brief's own words) falls out of that for free: nothing
here special-cases a test run, a test simply calls the function with the value
it wants to check.
"""

from __future__ import annotations

import os

LIVE_WORKER_ROLE = "strategy"

__all__ = ["LIVE_WORKER_ROLE", "refuse_inside_live_worker"]


def refuse_inside_live_worker(role: str | None = None) -> str | None:
    """``None`` when safe to run, else the reason to refuse.

    ``role`` defaults to ``os.environ.get("HUNTER_ROLE")``.
    """
    value = os.environ.get("HUNTER_ROLE") if role is None else role
    if value != LIVE_WORKER_ROLE:
        return None
    return (
        f"HUNTER_ROLE={LIVE_WORKER_ROLE}: this is the live worker's own container -- "
        "run the replay via `bash infra/vps/compose.sh replay ...` instead (T3.80)"
    )
