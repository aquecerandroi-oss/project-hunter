"""Unit tests for hunter_core.audit."""

import pytest

from hunter_core.audit import InMemoryAuditSink, LoggingAuditSink, audited, use_audit_sink

pytestmark = pytest.mark.unit


async def test_audited_captures_before_and_after_into_sink() -> None:
    sink = InMemoryAuditSink()

    async def fetch_before(risk_profile_id: str, **_: object) -> dict[str, object]:
        return {"max_position_pct": 0.02}

    @audited("risk_profile.updated", "risk_profile", before=fetch_before)
    async def update_risk_profile(risk_profile_id: str, **_: object) -> dict[str, object]:
        return {"max_position_pct": 0.05}

    with use_audit_sink(sink):
        result = await update_risk_profile(
            "rp-1",
            actor_type="user",
            actor_id="user-1",
            entity_id="rp-1",
        )

    assert result == {"max_position_pct": 0.05}
    assert len(sink.events) == 1
    event = sink.events[0]
    assert event.action == "risk_profile.updated"
    assert event.entity_type == "risk_profile"
    assert event.entity_id == "rp-1"
    assert event.actor_type == "user"
    assert event.actor_id == "user-1"
    assert event.before == {"max_position_pct": 0.02}
    assert event.after == {"max_position_pct": 0.05}


async def test_audited_defaults_actor_to_system() -> None:
    sink = InMemoryAuditSink()

    @audited("agent.enabled", "agent")
    async def enable_agent(agent_id: str) -> str:
        return agent_id

    with use_audit_sink(sink):
        await enable_agent("agent-1")

    event = sink.events[0]
    assert event.actor_type == "system"
    assert event.actor_id == "system"
    assert event.entity_id is None


async def test_audited_is_a_no_op_without_a_bound_sink() -> None:
    @audited("agent.enabled", "agent")
    async def enable_agent(agent_id: str) -> str:
        return agent_id

    # no use_audit_sink() context active — must not raise
    assert await enable_agent("agent-1") == "agent-1"


async def test_use_audit_sink_restores_previous_sink_on_exit() -> None:
    from hunter_core.audit import get_audit_sink

    outer = InMemoryAuditSink()
    inner = InMemoryAuditSink()
    with use_audit_sink(outer):
        with use_audit_sink(inner):
            assert get_audit_sink() is inner
        assert get_audit_sink() is outer
    assert get_audit_sink() is None


async def test_audited_does_not_record_when_the_wrapped_function_raises() -> None:
    """No audit entry for a mutation that never actually happened, and the
    caller sees the real error, not something swallowed/replaced by the
    decorator.

    Mutation that breaks this: wrap `result = await func(*args, **kwargs)` in
    a try/except that still calls `sink.record(...)` (e.g. with `after=None`)
    before re-raising — `sink.events` would then be non-empty.
    """
    sink = InMemoryAuditSink()

    class _Boom(Exception):
        pass

    @audited("agent.enabled", "agent")
    async def enable_agent(agent_id: str) -> str:
        raise _Boom("cannot enable")

    with use_audit_sink(sink):
        with pytest.raises(_Boom, match="cannot enable"):
            await enable_agent("agent-1")

    assert sink.events == []


async def test_logging_audit_sink_records_without_raising() -> None:
    calls: list[dict[str, object]] = []

    class _FakeLogger:
        def info(self, event: str, **kwargs: object) -> None:
            calls.append({"event": event, **kwargs})

    sink = LoggingAuditSink(logger=_FakeLogger())

    @audited("kill_switch.changed", "organization")
    async def flip_kill_switch(organization_id: str) -> str:
        return "EMERGENCY"

    with use_audit_sink(sink):
        await flip_kill_switch(organization_id="0198c1c2-30b0-7c33-8b7e-3c1a2b3c4d5e")

    assert len(calls) == 1
    assert calls[0]["action"] == "kill_switch.changed"
