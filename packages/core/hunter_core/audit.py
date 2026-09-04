"""Audit trail: the ``AuditEvent`` shape, pluggable sinks and the ``@audited`` decorator.

CLAUDE.md: "Every meaningful mutation is audited (audit_logs, append-only)."
ARCHITECTURE.md §9: "Audit: decorator @audited(action, entity) nos servicos que
mutam." The SQL sink that writes ``audit_logs`` is T04/T06's job (needs the ORM
model); this module only defines the shape, the sink protocol, and two sinks
that need no database: :class:`InMemoryAuditSink` for tests and
:class:`LoggingAuditSink` as a safe default until the SQL sink exists.

Calling convention for ``@audited``: the sink comes from a contextvar (bind it
once per request/worker tick with :func:`use_audit_sink`); actor/tenant
metadata comes from whichever of ``actor_type``, ``actor_id``,
``organization_id``, ``entity_id``, ``ip``, ``user_agent``, ``audit_metadata``
the decorated call receives as keyword arguments — a caller that wants those
recorded passes them as kwargs, everything else defaults. This keeps
`hunter_core` free of any dependency on how T05/T06 model a request principal.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import datetime
from functools import wraps
from ipaddress import ip_address
from typing import TYPE_CHECKING, Any, Literal, Protocol, cast
from uuid import UUID

from pydantic import BaseModel, Field
from pydantic_core import to_jsonable_python

from hunter_core.domain.types import utcnow

if TYPE_CHECKING:
    from collections.abc import Generator

    from sqlalchemy.ext.asyncio import AsyncSession

ActorType = Literal["user", "system", "agent"]


class AuditEvent(BaseModel):
    """One append-only audit record (DATABASE.md §12, ``audit_logs``)."""

    actor_type: ActorType
    actor_id: str
    organization_id: UUID | None = None
    action: str
    entity_type: str
    entity_id: str | None = None
    before: Any = None
    after: Any = None
    ip: str | None = None
    user_agent: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    ts: datetime = Field(default_factory=utcnow)


class AuditSink(Protocol):
    """Anything that can durably record an :class:`AuditEvent`."""

    async def record(self, event: AuditEvent) -> None: ...


class InMemoryAuditSink:
    """Collects events in a list — for tests."""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def record(self, event: AuditEvent) -> None:
        self.events.append(event)


class LoggingAuditSink:
    """Writes each event as a structured log line, via ``hunter_core.logging``.

    Not append-only or queryable — a safe placeholder until T04/T06 wire the
    Postgres ``audit_logs`` sink.
    """

    def __init__(self, logger: Any = None) -> None:
        if logger is None:
            from hunter_core.logging import get_logger

            logger = get_logger("audit")
        self._logger = logger

    async def record(self, event: AuditEvent) -> None:
        self._logger.info("audit_event", **event.model_dump(mode="json"))


USER_AGENT_MAX_LENGTH = 512
"""``audit_logs.user_agent`` is unbounded ``TEXT``, but a request header is
attacker-controlled and unbounded input on an append-only table that is never
pruned is a slow-motion disk-fill. 512 characters keeps every real browser UA
intact."""


def _as_uuid(value: str | None) -> UUID | None:
    """``audit_logs.actor_id`` is a ``uuid`` column, but an actor is not always a
    person: workers and the webhook name themselves (``"system"``,
    ``"clerk-webhook"``). Those keep their name in ``actor_type``/``metadata``
    and leave the uuid column NULL rather than aborting the transaction.
    """
    if value is None:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def _as_jsonb(value: Any) -> dict[str, Any] | None:
    """Coerce a ``before``/``after`` payload into something a JSONB column takes.

    ``fallback=str`` so a ``Decimal`` amount or a ``UUID`` renders instead of
    raising — an audit row must never be the reason a mutation rolls back.
    """
    if value is None:
        return None
    data = to_jsonable_python(value, fallback=str)
    return cast("dict[str, Any]", data) if isinstance(data, dict) else {"value": data}


def _as_inet(value: str | None) -> str | None:
    """Drop anything that is not an IP literal: the column is ``INET`` and a bad
    value aborts the transaction that carries the mutation being audited.
    """
    if value is None:
        return None
    try:
        ip_address(value)
    except ValueError:
        return None
    return value


class SqlAuditSink:
    """Writes each event to ``audit_logs`` **in the caller's own transaction**.

    Constructed with the session the mutation is running in (T06 binds it in
    ``hunter_api.deps``), so the audit row and the change it describes commit
    or roll back together: there is no window in which the database says a
    thing happened and the trail says it did not. ``flush`` — never ``commit``
    — for the same reason; the surrounding ``tenant_session`` owns the commit.

    ``audit_logs`` is append-only for both roles (DATABASE.md §1.2), and a
    system-scope row (``organization_id`` NULL) is accepted by the
    ``audit_system_scope`` policy (§15.4).

    **``created_at`` is set here, never left to the column default.** It is
    part of the primary key, so a server default makes SQLAlchemy emit
    ``INSERT ... RETURNING created_at`` — and Postgres applies the table's
    *SELECT* policies to a RETURNING row. ``tenant_isolation`` cannot see a
    row whose ``organization_id`` is NULL, so every system-scope audit row
    (sign-up, webhook, cron: exactly the ones nobody is watching) was refused
    with "new row violates row-level security policy". Supplying the value
    drops the RETURNING clause and the problem with it — and the timestamp is
    then the moment the event happened rather than the moment it flushed.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, event: AuditEvent) -> None:
        from hunter_core.db.models.system import AuditLog

        user_agent = event.user_agent
        self._session.add(
            AuditLog(
                created_at=event.ts,
                organization_id=event.organization_id,
                actor_type=event.actor_type,
                actor_id=_as_uuid(event.actor_id),
                action=event.action,
                entity_type=event.entity_type,
                entity_id=_as_uuid(event.entity_id),
                before=_as_jsonb(event.before),
                after=_as_jsonb(event.after),
                ip=_as_inet(event.ip),
                user_agent=user_agent[:USER_AGENT_MAX_LENGTH] if user_agent else None,
                request_id=event.metadata.get("request_id"),
                meta=event.metadata,
            )
        )
        await self._session.flush()


_current_sink: ContextVar[AuditSink | None] = ContextVar("hunter_core_audit_sink", default=None)


def get_audit_sink() -> AuditSink | None:
    """The sink bound by the innermost :func:`use_audit_sink`, if any."""
    return _current_sink.get()


@contextmanager
def use_audit_sink(sink: AuditSink | None) -> Generator[None, None, None]:
    """Bind ``sink`` as the active audit sink for the duration of the block."""
    token: Token[AuditSink | None] = _current_sink.set(sink)
    try:
        yield
    finally:
        _current_sink.reset(token)


def audited(
    action: str,
    entity_type: str,
    *,
    before: Callable[..., Any] | None = None,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Decorate an async service function so every call records an ``AuditEvent``.

    ``before``, if given, is called with the wrapped call's own arguments
    (awaited if it returns an awaitable) *before* the function runs, to
    capture pre-mutation state. The function's return value becomes ``after``.
    No-op when no sink is bound (:func:`use_audit_sink`) — callers that never
    opt in pay no cost beyond the ``before`` capture.
    """

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            before_state = None
            if before is not None:
                before_state = before(*args, **kwargs)
                if inspect.isawaitable(before_state):
                    before_state = await before_state

            result = await func(*args, **kwargs)

            sink = get_audit_sink()
            if sink is not None:
                entity_id = kwargs.get("entity_id")
                event = AuditEvent(
                    actor_type=kwargs.get("actor_type", "system"),
                    actor_id=str(kwargs.get("actor_id", "system")),
                    organization_id=kwargs.get("organization_id"),
                    action=action,
                    entity_type=entity_type,
                    entity_id=str(entity_id) if entity_id is not None else None,
                    before=before_state,
                    after=result,
                    ip=kwargs.get("ip"),
                    user_agent=kwargs.get("user_agent"),
                    metadata=kwargs.get("audit_metadata") or {},
                )
                await sink.record(event)
            return result

        return wrapper

    return decorator
