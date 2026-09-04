"""``SqlAuditSink`` maps an ``AuditEvent`` onto an ``audit_logs`` row.

Unit-level: a fake session records what was added and flushed, so the mapping
(actor id coercion, JSON coercion of ``before``/``after``, the 512-char
user-agent cap) is asserted without Postgres. The append-only round trip
against a real database is in the integration suite.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest

from hunter_core.audit import USER_AGENT_MAX_LENGTH, AuditEvent, SqlAuditSink
from hunter_core.db.models.system import AuditLog

pytestmark = pytest.mark.unit


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.flushed = 0

    def add(self, instance: Any) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        self.flushed += 1


async def _record(event: AuditEvent) -> AuditLog:
    session = _FakeSession()
    await SqlAuditSink(session).record(event)  # type: ignore[arg-type]
    assert session.flushed == 1
    row = session.added[0]
    assert isinstance(row, AuditLog)
    return row


async def test_maps_a_tenant_event_onto_an_audit_log_row() -> None:
    org_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    event = AuditEvent(
        actor_type="user",
        actor_id=str(actor_id),
        organization_id=org_id,
        action="organization.updated",
        entity_type="organization",
        entity_id=str(entity_id),
        before={"name": "Old"},
        after={"name": "New"},
        ip="203.0.113.7",
        user_agent="hunter-tests/1.0",
        metadata={"request_id": "req-1"},
    )

    row = await _record(event)

    assert row.organization_id == org_id
    assert row.actor_type == "user"
    assert row.actor_id == actor_id
    assert row.action == "organization.updated"
    assert row.entity_type == "organization"
    assert row.entity_id == entity_id
    assert row.before == {"name": "Old"}
    assert row.after == {"name": "New"}
    assert row.ip == "203.0.113.7"
    assert row.request_id == "req-1"
    assert row.meta == {"request_id": "req-1"}
    # supplied, never left to the column default: a server default forces an
    # INSERT ... RETURNING, and RETURNING makes Postgres apply the SELECT
    # policy, which no system-scope row can pass
    assert row.created_at == event.ts


async def test_system_scope_keeps_a_null_organization_and_a_null_actor_uuid() -> None:
    event = AuditEvent(
        actor_type="system",
        actor_id="clerk-webhook",
        action="user.provisioned",
        entity_type="user",
    )

    row = await _record(event)

    # audit_system_scope is the policy that accepts this row; a non-UUID actor
    # (a worker name, "system") has no place in a uuid column and becomes NULL
    assert row.organization_id is None
    assert row.actor_id is None
    assert row.actor_type == "system"
    assert row.before is None
    assert row.after is None


async def test_non_dict_and_non_json_native_payloads_are_coerced() -> None:
    event = AuditEvent(
        actor_type="user",
        actor_id="system",
        action="workspace.onboarded",
        entity_type="workspace",
        before=["a", "b"],
        after={"capital": Decimal("10000.5"), "when": uuid.UUID(int=1)},
    )

    row = await _record(event)

    # JSONB columns take an object; a bare list/scalar is wrapped rather than
    # dropped, and Decimal/UUID survive as strings instead of raising
    assert row.before == {"value": ["a", "b"]}
    assert row.after is not None
    assert row.after["capital"] == "10000.5"
    assert row.after["when"] == str(uuid.UUID(int=1))


async def test_user_agent_is_truncated_to_the_column_budget() -> None:
    event = AuditEvent(
        actor_type="user",
        actor_id="system",
        action="organization.created",
        entity_type="organization",
        user_agent="x" * (USER_AGENT_MAX_LENGTH + 50),
    )

    row = await _record(event)

    assert row.user_agent is not None
    assert len(row.user_agent) == USER_AGENT_MAX_LENGTH


async def test_a_malformed_ip_is_dropped_rather_than_failing_the_insert() -> None:
    event = AuditEvent(
        actor_type="user",
        actor_id="system",
        action="organization.created",
        entity_type="organization",
        ip="not-an-address",
    )

    row = await _record(event)

    # the column is INET: a bogus value would abort the whole transaction —
    # and with it the mutation being audited — so it is dropped instead
    assert row.ip is None
