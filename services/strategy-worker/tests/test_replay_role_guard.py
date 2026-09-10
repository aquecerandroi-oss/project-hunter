"""The replay CLI refuses to run inside the live worker's own container (T3.80).

T3.76 ran a replay via ``docker exec hunter-strategy-worker-1 python -m
hunter_strategy_worker.replay.run ...`` -- the live worker's own container,
sharing its CPU and DB pool with the process the whole shadow lane depends on
staying instant. ``HUNTER_ROLE=strategy`` (``infra/docker/docker-
compose.yml``'s ``strategy-worker`` service, what ``entrypoint.sh`` dispatches
on) survives a ``docker exec`` even though it bypasses the entrypoint, so it
is the signal this guard reads.
"""

from __future__ import annotations

from typing import Any

import pytest

from hunter_strategy_worker.replay import run as run_module
from hunter_strategy_worker.replay.role_guard import LIVE_WORKER_ROLE, refuse_inside_live_worker

pytestmark = pytest.mark.unit


class TestRefuseInsideLiveWorker:
    def test_the_live_workers_own_role_is_refused(self) -> None:
        reason = refuse_inside_live_worker("strategy")
        assert reason is not None
        assert "HUNTER_ROLE=strategy" in reason
        assert "compose.sh replay" in reason

    @pytest.mark.parametrize(
        "role", ["api", "market", "scanner", "execution", "analytics", "all", None]
    )
    def test_every_other_role_is_left_alone(self, role: str | None) -> None:
        assert refuse_inside_live_worker(role) is None

    def test_an_unset_role_reads_the_real_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HUNTER_ROLE", LIVE_WORKER_ROLE)
        assert refuse_inside_live_worker() is not None

    def test_no_hunter_role_in_the_environment_at_all_is_safe(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("HUNTER_ROLE", raising=False)
        assert refuse_inside_live_worker() is None


class TestTheCliRefusesBeforeParsingAnything:
    """The guard runs first in ``_main`` -- before argument parsing, before the
    readiness gate, before any queue drain or direct run -- so it refuses the
    exact same way regardless of which replay invocation was attempted."""

    async def test_running_inside_the_live_worker_refuses_a_direct_run(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(run_module, "refuse_inside_live_worker", lambda: "refused: test reason")
        exit_code = await run_module._main(
            ["--version", "momentum:v1", "--from", "2026-08-01", "--to", "2026-08-02"]
        )
        assert exit_code == 1
        assert "refused" in capsys.readouterr().out

    async def test_running_inside_the_live_worker_refuses_a_queue_drain(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        called = False

        async def _fake_drain(*_args: Any, **_kwargs: Any) -> list[Any]:
            nonlocal called
            called = True
            return []

        monkeypatch.setattr(run_module, "refuse_inside_live_worker", lambda: "refused: test reason")
        monkeypatch.setattr(run_module, "_drain", _fake_drain)
        exit_code = await run_module._main(["--drain-queue"])
        assert exit_code == 1
        assert called is False, "the drain must never start once the role guard refuses"
        assert "refused" in capsys.readouterr().out

    async def test_a_normal_role_reaches_argument_parsing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Contra-proof: with the guard clear, a missing required argument still
        raises the usual ``SystemExit`` -- proof the guard did not swallow the
        rest of ``_main``."""
        monkeypatch.setattr(run_module, "refuse_inside_live_worker", lambda: None)
        with pytest.raises(SystemExit):
            await run_module._main([])
