"""The Clerk webhook against a real database.

Signature verification is unit-tested; what needs Postgres is the effect and
the idempotency guard. Svix retries a delivery until it gets a 2xx, so the
handler has to be exactly-once *in effect* — the ``svix-id`` is claimed in
``processed_events`` before any change is applied.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import func, select
from svix.webhooks import Webhook

from hunter_api.services import clerk_webhook
from hunter_core.db.models.identity import OrganizationMember, User
from hunter_core.db.models.system import AuditLog, ProcessedEvent
from hunter_core.db.session import role_session, tenant_session
from hunter_core.domain.enums import MemberStatus

from .conftest import FAKE_WEBHOOK_SECRET, Actor, auth_header, create_org

if TYPE_CHECKING:
    from collections.abc import Callable

    import httpx
    from cryptography.hazmat.primitives.asymmetric import rsa
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

WEBHOOK_URL = "/api/webhooks/clerk"


def _clerk_user(
    subject: str, email: str, *, verification: str = "verified", **extra: Any
) -> dict[str, Any]:
    return {
        "id": subject,
        "email_addresses": [
            {
                "id": "idn_FAKE_1",
                "email_address": email,
                "verification": {"status": verification},
            }
        ],
        "primary_email_address_id": "idn_FAKE_1",
        "first_name": "Web",
        "last_name": "Hook",
        **extra,
    }


def _delivery(payload: dict[str, Any], delivery_id: str) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(payload).encode()
    moment = datetime.now(UTC)
    return body, {
        "svix-id": delivery_id,
        "svix-timestamp": str(int(moment.timestamp())),
        "svix-signature": Webhook(FAKE_WEBHOOK_SECRET).sign(delivery_id, moment, body.decode()),
        "content-type": "application/json",
    }


async def _post(client: httpx.AsyncClient, payload: dict[str, Any], delivery_id: str) -> Any:
    body, headers = _delivery(payload, delivery_id)
    return await client.post(WEBHOOK_URL, content=body, headers=headers)


async def test_user_created_mirrors_the_user_and_me_then_works(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    signing_key: rsa.RSAPrivateKey,
) -> None:
    subject = f"user_FAKE_hook_{uuid.uuid4().hex[:8]}"
    email = f"{subject}@example.test"

    response = await _post(
        client,
        {"type": "user.created", "data": _clerk_user(subject, email)},
        f"msg_FAKE_{uuid.uuid4().hex[:8]}",
    )

    assert response.status_code == 200
    assert response.json() == {"status": "applied", "type": "user.created"}

    async with role_session(session_factory, db_role="hunter_worker") as session:
        row = (
            await session.execute(
                select(User.email, User.display_name).where(User.external_auth_id == subject)
            )
        ).one()
    assert row.email == email
    assert row.display_name == "Web Hook"

    # and the mirrored user can now authenticate without any JIT provisioning:
    # the profile source in this suite is empty, so a 200 proves the row is
    # what was found
    me = await client.get("/api/v1/me", headers=auth_header(signing_key, subject))
    assert me.status_code == 200
    assert me.json()["user"]["email"] == email
    assert me.json()["memberships"] == []


async def test_a_replayed_delivery_changes_nothing(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    subject = f"user_FAKE_replay_{uuid.uuid4().hex[:8]}"
    delivery_id = f"msg_FAKE_{uuid.uuid4().hex[:8]}"
    payload = {"type": "user.created", "data": _clerk_user(subject, f"{subject}@example.test")}

    first = await _post(client, payload, delivery_id)
    second = await _post(client, payload, delivery_id)

    assert first.json()["status"] == "applied"
    assert second.json() == {"status": "duplicate", "type": "user.created"}

    async with role_session(session_factory, db_role="hunter_worker") as session:
        users = await session.scalar(
            select(func.count()).select_from(User).where(User.external_auth_id == subject)
        )
        audits = await session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.action == "user.created",
                AuditLog.organization_id.is_(None),
                AuditLog.after["external_auth_id"].astext == subject,
            )
        )
        claimed = await session.scalar(
            select(func.count())
            .select_from(ProcessedEvent)
            .where(ProcessedEvent.event_id == delivery_id)
        )
    assert users == 1
    assert audits == 1, "a retried delivery must not add a second audit row"
    assert claimed == 1


async def test_user_updated_refreshes_the_mirror(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    subject = f"user_FAKE_upd_{uuid.uuid4().hex[:8]}"
    await _post(
        client,
        {"type": "user.created", "data": _clerk_user(subject, f"{subject}@example.test")},
        f"msg_FAKE_{uuid.uuid4().hex[:8]}",
    )

    await _post(
        client,
        {
            "type": "user.updated",
            "data": _clerk_user(
                subject, f"{subject}-new@example.test", first_name="Renamed", last_name="Person"
            ),
        },
        f"msg_FAKE_{uuid.uuid4().hex[:8]}",
    )

    async with role_session(session_factory, db_role="hunter_worker") as session:
        row = (
            await session.execute(
                select(User.email, User.display_name).where(User.external_auth_id == subject)
            )
        ).one()
    assert row.email == f"{subject}-new@example.test"
    assert row.display_name == "Renamed Person"


async def test_user_deleted_revokes_every_membership_and_keeps_the_history(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """``users`` has no ``deleted_at`` column in the M0 schema, so a deletion is
    expressed where it has teeth: the memberships go to ``suspended``, which
    RBAC treats as no membership at all. The rows survive, so the audit trail
    still resolves who did what.
    """
    unique = uuid.uuid4().hex[:8]
    owner = await create_org(client, make_actor(f"deleted-{unique}"), f"Deleted Org {unique}")
    assert owner.org_id is not None and owner.user_id is not None

    response = await _post(
        client,
        {"type": "user.deleted", "data": {"id": owner.subject, "deleted": True}},
        f"msg_FAKE_{uuid.uuid4().hex[:8]}",
    )

    assert response.json() == {"status": "applied", "type": "user.deleted"}
    async with role_session(session_factory, db_role="hunter_worker") as session:
        member = await session.get(OrganizationMember, (owner.org_id, owner.user_id))
        still_there = await session.get(User, owner.user_id)
    assert member is not None, "membership history is kept, not deleted"
    assert member.status is MemberStatus.SUSPENDED
    assert still_there is not None

    # and the access is really gone: a suspended membership is a 404, not a 403
    after = await client.get(f"/api/v1/orgs/{owner.org_id}", headers=owner.headers)
    assert after.status_code == 404


async def test_an_unsigned_delivery_is_401_and_writes_nothing(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    subject = f"user_FAKE_forged_{uuid.uuid4().hex[:8]}"
    payload = {"type": "user.created", "data": _clerk_user(subject, f"{subject}@example.test")}

    response = await client.post(
        WEBHOOK_URL,
        content=json.dumps(payload).encode(),
        headers={
            "svix-id": "msg_FAKE_forged",
            "svix-timestamp": str(int(datetime.now(UTC).timestamp())),
            "svix-signature": "v1,Zm9yZ2VkCg==",
            "content-type": "application/json",
        },
    )

    assert response.status_code == 401
    async with role_session(session_factory, db_role="hunter_worker") as session:
        found = await session.scalar(
            select(func.count()).select_from(User).where(User.external_auth_id == subject)
        )
    assert found == 0


async def test_a_delivery_with_no_svix_headers_is_422(client: httpx.AsyncClient) -> None:
    response = await client.post(WEBHOOK_URL, json={"type": "user.created", "data": {}})

    # svix-id is a declared header parameter, so FastAPI refuses the request
    # before the handler ever runs
    assert response.status_code == 422


async def test_an_event_type_we_do_not_handle_is_acknowledged_not_errored(
    client: httpx.AsyncClient,
) -> None:
    # Svix retries anything that is not 2xx, so an unhandled type must still
    # be acknowledged or it becomes an infinite redelivery loop
    response = await _post(
        client,
        {"type": "session.created", "data": {"id": "sess_FAKE_1"}},
        f"msg_FAKE_{uuid.uuid4().hex[:8]}",
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ignored", "type": "session.created"}


async def test_the_webhook_audit_row_is_system_scope(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    subject = f"user_FAKE_audit_{uuid.uuid4().hex[:8]}"
    delivery_id = f"msg_FAKE_{uuid.uuid4().hex[:8]}"

    await _post(
        client,
        {"type": "user.created", "data": _clerk_user(subject, f"{subject}@example.test")},
        delivery_id,
    )

    async with role_session(session_factory, db_role="hunter_worker") as session:
        row = (
            (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.action == "user.created",
                        AuditLog.after["external_auth_id"].astext == subject,
                    )
                )
            )
            .scalars()
            .one()
        )

    assert row.organization_id is None
    assert row.actor_type == "system"
    assert row.actor_id is None
    assert row.meta["delivery_id"] == delivery_id


async def test_a_tenant_cannot_read_the_system_scope_audit_rows(
    client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
) -> None:
    unique = uuid.uuid4().hex[:8]
    owner = await create_org(client, make_actor(f"sysaudit-{unique}"), f"Sys Audit {unique}")
    await _post(
        client,
        {"type": "user.created", "data": _clerk_user(f"user_FAKE_x_{unique}", f"x{unique}@e.test")},
        f"msg_FAKE_{uuid.uuid4().hex[:8]}",
    )

    body = (await client.get(f"/api/v1/orgs/{owner.org_id}/audit", headers=owner.headers)).json()

    assert all(row["actor_type"] == "user" for row in body["items"])
    assert all(row["action"] != "user.created" for row in body["items"])


async def test_tenant_session_still_cannot_see_another_orgs_audit(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    unique = uuid.uuid4().hex[:8]
    owner = await create_org(client, make_actor(f"auditscope-{unique}"), f"Scope {unique}")
    assert owner.org_id is not None

    async with tenant_session(session_factory, owner.org_id, owner.user_id) as session:
        orgs = (await session.execute(select(AuditLog.organization_id).distinct())).scalars().all()

    assert set(orgs) == {owner.org_id}


async def test_an_unverified_primary_email_is_acknowledged_and_recorded(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Svix retries anything that is not 2xx, so refusing this payload with an
    error would be an infinite redelivery loop. It is acknowledged and *not*
    mirrored: ``users.email`` is what invitations are matched against, so an
    address Clerk has not verified must never land there. The audit row is what
    makes the refusal visible afterwards.
    """
    subject = f"user_FAKE_unver_{uuid.uuid4().hex[:8]}"

    response = await _post(
        client,
        {
            "type": "user.created",
            "data": _clerk_user(subject, f"{subject}@example.test", verification="unverified"),
        },
        f"msg_FAKE_{uuid.uuid4().hex[:8]}",
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ignored", "reason": "no_verified_email"}
    async with role_session(session_factory, db_role="hunter_worker") as session:
        mirrored = await session.scalar(
            select(func.count()).select_from(User).where(User.external_auth_id == subject)
        )
        recorded = (
            (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.action == "user.email_unverified",
                        AuditLog.after["external_auth_id"].astext == subject,
                    )
                )
            )
            .scalars()
            .all()
        )
    assert mirrored == 0
    assert len(recorded) == 1
    assert recorded[0].organization_id is None


async def test_a_delivery_that_fails_midway_is_retried_and_completes(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ``svix-id`` claim has to be reversible, or a partial failure is
    permanent.

    ``user.deleted`` revokes one organization per transaction. If the second
    one fails, the first is already committed and Svix retries — and with an
    unconditional claim that retry answers "duplicate", leaving organizations B
    and C with an active membership for an account Clerk has deleted. Releasing
    the claim on the way out is what makes the retry do the remaining work.
    """
    unique = uuid.uuid4().hex[:8]
    actor = make_actor(f"multi-{unique}")
    org_ids: list[uuid.UUID] = []
    for index in range(3):
        await create_org(client, actor, f"Multi {unique} {index}")
        assert actor.org_id is not None
        org_ids.append(actor.org_id)

    calls = {"n": 0}
    original = clerk_webhook.record_audit

    async def _fail_on_the_second_org(*args: Any, **kwargs: Any) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("audit sink exploded")
        await original(*args, **kwargs)

    monkeypatch.setattr(clerk_webhook, "record_audit", _fail_on_the_second_org)

    delivery_id = f"msg_FAKE_{uuid.uuid4().hex[:8]}"
    payload = {"type": "user.deleted", "data": {"id": actor.subject, "deleted": True}}
    failed = await _post(client, payload, delivery_id)

    assert failed.status_code == 500
    monkeypatch.setattr(clerk_webhook, "record_audit", original)

    retried = await _post(client, payload, delivery_id)

    assert retried.status_code == 200
    assert retried.json() == {"status": "applied", "type": "user.deleted"}, (
        "the retry must re-run the work, not report the failed delivery as a duplicate"
    )
    async with role_session(session_factory, db_role="hunter_worker") as session:
        statuses = (
            (
                await session.execute(
                    select(OrganizationMember.status).where(
                        OrganizationMember.user_id == actor.user_id,
                        OrganizationMember.organization_id.in_(org_ids),
                    )
                )
            )
            .scalars()
            .all()
        )
    assert list(statuses) == [MemberStatus.SUSPENDED] * 3


async def test_a_failed_delivery_leaves_no_claim_behind(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subject = f"user_FAKE_boom_{uuid.uuid4().hex[:8]}"
    delivery_id = f"msg_FAKE_{uuid.uuid4().hex[:8]}"

    async def _explode(*_args: Any, **_kwargs: Any) -> dict[str, str]:
        raise RuntimeError("mirror exploded")

    monkeypatch.setattr(clerk_webhook, "_upsert_user", _explode)

    response = await _post(
        client,
        {"type": "user.created", "data": _clerk_user(subject, f"{subject}@example.test")},
        delivery_id,
    )

    assert response.status_code == 500
    async with role_session(session_factory, db_role="hunter_worker") as session:
        claimed = await session.scalar(
            select(func.count())
            .select_from(ProcessedEvent)
            .where(ProcessedEvent.event_id == delivery_id)
        )
    assert claimed == 0, "a delivery that did not take effect must not stay claimed"
