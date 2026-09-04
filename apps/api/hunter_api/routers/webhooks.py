"""``POST /api/webhooks/clerk`` — Clerk's user events, via Svix.

Not under ``/api/v1``: it is not part of the product API surface and is not
versioned by us — its shape is Clerk's. It is also the one endpoint with no
``Authorization`` header, which is exactly why the Svix signature is checked
before the body is parsed.

Rate limiting still applies (SECURITY.md §5). The limiter keys on
``request.state.principal_id``, which ``TenantContextMiddleware`` sets from the
``svix-id`` for this path: keying on the source IP would put every Clerk
delivery — for every customer — into one bucket and drop legitimate events
under load, while a per-delivery key still bounds a retry storm.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, Request

from hunter_api.deps import get_session_factory, get_settings
from hunter_api.services.clerk_webhook import (
    handle_event,
    system_audit,
    verify_signature,
)

router = APIRouter(prefix="/api/webhooks", tags=["system"])


@router.post("/clerk", summary="Clerk user events (Svix-signed)")
async def clerk_webhook(
    request: Request,
    svix_id: Annotated[str, Header(alias="svix-id", max_length=128)],
) -> dict[str, str]:
    settings = get_settings(request)
    body = await request.body()
    payload = verify_signature(
        settings.clerk_webhook_secret.get_secret_value(), body, request.headers
    )
    return await handle_event(
        get_session_factory(request),
        delivery_id=svix_id,
        payload=payload,
        audit=system_audit(svix_id, getattr(request.state, "request_id", None)),
    )
