"""T3.5 item 8 — the process shell: the role, the refusals, the readiness, the beat.

Unit, no database and no Docker: what is proved here is about the *process*, not
about the wallet. The one thing that must never be true — a paper worker that
came up with ``ENABLE_LIVE_TRADING=true`` — is proved by the refusal, not by a
comment.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import pytest

from hunter_core.domain.types import utcnow
from hunter_execution_worker.config import ExecutionConfig, LiveTradingRefused, load_config
from hunter_execution_worker.state import CycleHealth

pytestmark = pytest.mark.unit


class TestTheRoleIsRegistered:
    def test_hunter_role_execution_resolves_to_this_worker(self) -> None:
        import hunter_execution_worker
        from hunter_core.runtime import RoleRegistry

        assert RoleRegistry["execution"] is hunter_execution_worker.run_execution


class TestTheProcessRefusesWhatItCannotBe:
    def test_enable_live_trading_is_fatal_at_startup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")

        with pytest.raises(LiveTradingRefused) as refusal:
            load_config()

        assert "paper" in str(refusal.value)

    def test_the_default_is_paper_and_autonomy_is_off(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ENABLE_LIVE_TRADING", raising=False)
        monkeypatch.delenv("ENABLE_PAPER_AUTONOMY", raising=False)

        config = load_config()

        assert config.enable_paper_autonomy is False
        assert config.mtm_poll_s == 60.0
        assert config.expiry_poll_s == 5.0

    def test_autonomy_is_opt_in_by_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENABLE_PAPER_AUTONOMY", "true")

        assert load_config().enable_paper_autonomy is True

    def test_the_flag_has_a_single_source_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """T3.14b review item 5: two independent env parsers of the same
        variable is two chances to read it differently. There is exactly one
        now — ``load_config`` reads it off ``hunter_core.settings.Settings``,
        never off ``os.environ`` a second time with its own ad-hoc parser."""
        from hunter_core.settings import Settings

        monkeypatch.setenv("ENABLE_PAPER_AUTONOMY", "true")
        calls: list[bool] = []
        original_init = Settings.__init__

        def _spy(self: Settings, *args: object, **kwargs: object) -> None:
            calls.append(True)
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(Settings, "__init__", _spy)

        config = load_config()

        assert calls, "load_config must construct Settings to read the flag"
        assert config.enable_paper_autonomy is True

    def test_env_and_compose_cannot_disagree_about_which_mode_is_on(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A single source means the worker's config and any other role reading
        ``Settings`` (a diagnostics endpoint, ``/ready``) always agree, whatever
        the exact casing or truthy spelling an operator's env/compose used."""
        from hunter_core.settings import Settings

        for raw in ("true", "TRUE", "1", "yes", "on"):
            monkeypatch.setenv("ENABLE_PAPER_AUTONOMY", raw)
            assert load_config().enable_paper_autonomy is Settings().enable_paper_autonomy is True

        monkeypatch.setenv("ENABLE_PAPER_AUTONOMY", "false")
        assert load_config().enable_paper_autonomy is Settings().enable_paper_autonomy is False


class TestReadinessSaysWhatIsDegraded:
    def _health(self) -> CycleHealth:
        health = CycleHealth()
        health.kill_switch_read_at = utcnow()
        health.mtm_written_at = utcnow()
        return health

    async def _verdicts(self, health: CycleHealth) -> dict[str, bool]:
        from hunter_execution_worker.health import readiness_checks

        local = ("kill_switch_legible", "mtm_fresh", "protection_prompt")
        checks = readiness_checks(_no_database(), ExecutionConfig(), health)
        return {check.__name__: await check() for check in checks if check.__name__ in local}

    async def test_a_stalled_mark_to_market_turns_readiness_red(self) -> None:
        health = self._health()
        health.mtm_written_at = utcnow() - timedelta(seconds=121)

        verdicts = await self._verdicts(health)

        assert verdicts["mtm_fresh"] is False
        assert verdicts["kill_switch_legible"] is True

    async def test_a_protection_waiting_more_than_five_seconds_turns_readiness_red(self) -> None:
        health = self._health()
        health.mark_degraded(uuid.uuid4(), utcnow() - timedelta(seconds=6))

        verdicts = await self._verdicts(health)

        assert verdicts["protection_prompt"] is False

    async def test_an_unreadable_kill_switch_turns_readiness_red(self) -> None:
        health = self._health()
        health.kill_switch_read_at = None

        verdicts = await self._verdicts(health)

        assert verdicts["kill_switch_legible"] is False

    async def test_a_healthy_worker_is_ready(self) -> None:
        verdicts = await self._verdicts(self._health())

        assert verdicts["mtm_fresh"] is True
        assert verdicts["protection_prompt"] is True
        assert verdicts["kill_switch_legible"] is True


class TestTheHeartbeatShowsTheDelayThatMatters:
    async def test_it_carries_the_equity_the_switch_and_the_protection_delay(self) -> None:
        from hunter_execution_worker.heartbeat import write_heartbeat

        health = CycleHealth()
        health.equity = "19903.8475950000"
        health.kill_switch = "TRADING_DISABLED"
        health.open_positions = 1
        health.mark_degraded(uuid.uuid4(), utcnow() - timedelta(seconds=3))
        runtime = _FakeRuntime()

        await write_heartbeat(runtime, health, ExecutionConfig())  # type: ignore[arg-type]

        payload = runtime.redis.written
        assert payload["equity"] == "19903.8475950000"
        assert payload["kill_switch"] == "TRADING_DISABLED"
        assert payload["open_positions"] == "1"
        assert payload["degraded_protections"] == "1"
        assert float(payload["protection_delay_s"]) >= 3.0


class _FakeRedis:
    def __init__(self) -> None:
        self.written: dict[str, str] = {}

    async def hset(self, key: str, *, mapping: dict[str, str]) -> None:
        self.written = mapping

    async def expire(self, key: str, ttl: int) -> None:
        return None


class _FakeRuntime:
    def __init__(self) -> None:
        self.instance = "test:1"
        self.redis = _FakeRedis()


def _no_database() -> Any:
    """A factory that would fail if a check touched the database.

    The four checks asserted above are answers about **this process** and must
    not need a round trip; ``outbox_not_lagging`` is the one that does, and it is
    deliberately not asserted here — it has its own integration coverage.
    """

    class _Refuses:
        def __call__(self, *_: Any, **__: Any) -> Any:
            raise AssertionError("a process-local readiness check must not open a session")

    return _Refuses()
