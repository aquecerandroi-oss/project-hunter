"""``POST /api/webhooks/clerk`` — Clerk's user events, via Svix.

Not under ``/api/v1``: it is not part of the product API surface and is not
versioned by us — its shape is Clerk's. It is also the one endpoint with no
``Authorization`` header, which is exactly why the Svix signature is checked
before the body is parsed.

Two things happen *before* ``await request.body()``, in this order, because
after it the bytes are already in memory:

1. ``Content-Length`` must be present (Svix always sends it; a delivery
   without one is either not Svix or a chunked upload of unknown size, and
   neither can be size-checked) and must be a number — 411 otherwise.
2. It must be within ``MAX_BODY_BYTES``, which is far below the global
   ``/api/*`` cap — a Clerk user event is a few kilobytes — so this endpoint,
   the only unauthenticated POST on the surface, is the tightest one.

The handler declares no body parameter on purpose: FastAPI reads the request
body while solving dependencies when one is declared, which would happen
before either check.

Rate limiting still applies (SECURITY.md §5), on two buckets: the client
address and the ``svix-id``, which ``TenantContextMiddleware`` puts on
``request.state.delivery_key``. Keying only on the delivery id would let a
caller mint a fresh bucket per request; keying only on the address would put
every customer's deliveries — all arriving from Svix — into one.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, Request, status

from hunter_api.deps import get_session_factory, get_settings
from hunter_api.errors import HunterError
from hunter_api.middleware.body_size import content_length
from hunter_api.services.clerk_webhook import handle_event, system_audit
from hunter_api.services.webhook_delivery import MAX_BODY_BYTES, verify_signature

router = APIRouter(prefix="/api/webhooks", tags=["system"])


class LengthRequiredError(HunterError):
    def __init__(self) -> None:
        super().__init__(
            type_slug="length-required",
            title="Length Required",
            status_code=status.HTTP_411_LENGTH_REQUIRED,
            detail="A Content-Length header is required on this endpoint.",
        )


class DeliveryTooLargeError(HunterError):
    def __init__(self) -> None:
        super().__init__(
            type_slug="payload-too-large",
            title="Content Too Large",
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"A webhook delivery must not exceed {MAX_BODY_BYTES} bytes.",
        )


@router.post("/clerk", summary="Clerk user events (Svix-signed)")
async def clerk_webhook(
    request: Request,
    svix_id: Annotated[str, Header(alias="svix-id", max_length=128)],
) -> dict[str, str]:
    declared = content_length(request)
    if declared is None:
        raise LengthRequiredError
    if declared > MAX_BODY_BYTES:
        raise DeliveryTooLargeError
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
