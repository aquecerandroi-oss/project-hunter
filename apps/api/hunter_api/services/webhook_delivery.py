"""Authenticating a Svix delivery, and claiming it exactly once.

Split out of :mod:`hunter_api.services.clerk_webhook` because "is this
delivery genuine and have we already applied it" is a different job from "what
does this event mean", and it is the half that is adversarial.

- **Signature.** The endpoint is public by necessity. Without verification,
  anyone who learns the URL can create a user row with any email — and email
  is what an invitation is matched against, so a forged ``user.created`` is a
  path into somebody else's organization. The raw body is verified *before* it
  is parsed, because the signature covers bytes, not a re-serialization.
- **Idempotency.** Svix retries with the same ``svix-id`` until it gets a 2xx.
  Delivery is at-least-once, so the handler must be exactly-once in effect;
  ``processed_events`` (DATABASE.md §12) is the durable guard, chosen over a
  Redis SET because losing Redis must not turn into replaying webhooks.
- **Reversibility.** The claim is taken *before* the effect, so two concurrent
  retries cannot both proceed — and released if the effect raises, because a
  delivery that only half happened has to be retried, not remembered as done.
- **Crash safety.** Release only covers a failure the process lives to see. So
  the claim is two-phase: :func:`claim_delivery` inserts the row and
  :func:`complete_delivery` stamps ``completed_at`` once the effect is
  committed. A claim left unfinished past ``stale_s`` is available again, so a
  process killed between the two steps costs one delayed redelivery instead of
  a delivery that is answered "duplicate" forever and never applied.

``processed_events`` is written as ``hunter_worker``: it is a system table that
role owns, and the one place in this flow where the elevated role writes.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

from fastapi import status
from sqlalchemy import bindparam, delete, func, text, update
from sqlalchemy.dialects.postgresql import insert
from svix.webhooks import Webhook, WebhookVerificationError

from hunter_api.errors import HunterError
from hunter_core.db.models.system import ProcessedEvent
from hunter_core.db.session import role_session
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = get_logger(__name__)

CONSUMER = "clerk-webhook"
SVIX_HEADERS = ("svix-id", "svix-timestamp", "svix-signature")
MAX_BODY_BYTES = 256 * 1024
"""Far below the global ``/api/*`` cap: a Clerk user event is a few kilobytes,
and this is the one unauthenticated POST on the surface."""

CLAIM_STALE_SECONDS = 300.0
"""How long a claim may sit unfinished before a redelivery may take it over.
Longer than any delivery can legitimately take (the slowest, ``user.deleted``,
is one transaction per organization) and short enough that a crash costs
minutes, not a day."""


class WebhookSignatureError(HunterError):
    def __init__(self) -> None:
        super().__init__(
            type_slug="invalid-webhook-signature",
            title="Unauthorized",
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The webhook signature could not be verified.",
        )


class DeliveryTooLargeError(HunterError):
    """413, not 401: the delivery was refused on its size, and the signature was
    never even looked at.

    Answering this with the signature error would send an operator hunting for
    a signing-secret mismatch that does not exist. It lives here rather than in
    the router because both size checks — the declared length, and the bytes
    actually received — should raise the same thing.
    """

    def __init__(self) -> None:
        super().__init__(
            type_slug="payload-too-large",
            title="Content Too Large",
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"A webhook delivery must not exceed {MAX_BODY_BYTES} bytes.",
        )


class WebhookNotConfiguredError(HunterError):
    def __init__(self) -> None:
        super().__init__(
            type_slug="webhook-not-configured",
            title="Service Unavailable",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook delivery is not configured on this deployment.",
        )


def verify_signature(secret: str, body: bytes, headers: Mapping[str, str]) -> dict[str, Any]:
    """Verify and parse. Raises before any parsing when verification fails.

    An unconfigured secret is a 503, never a bypass: "no secret, so accept
    everything" is the shape of the classic webhook forgery bug.
    """
    if not secret:
        raise WebhookNotConfiguredError
    if len(body) > MAX_BODY_BYTES:
        raise DeliveryTooLargeError
    svix_headers = {name: headers.get(name, "") for name in SVIX_HEADERS}
    if not all(svix_headers.values()):
        raise WebhookSignatureError
    try:
        Webhook(secret).verify(body, svix_headers)
    except WebhookVerificationError:
        logger.warning("webhook_signature_rejected", delivery_id=svix_headers["svix-id"])
        raise WebhookSignatureError from None
    try:
        payload: object = json.loads(body)
    except ValueError:
        raise WebhookSignatureError from None
    return cast("dict[str, Any]", payload) if isinstance(payload, dict) else {}


async def claim_delivery(
    session_factory: async_sessionmaker[AsyncSession],
    delivery_id: str,
    *,
    stale_s: float = CLAIM_STALE_SECONDS,
) -> bool:
    """Take the claim on ``delivery_id``. ``False`` when somebody else has it.

    One statement, so the decision is the database's and not a read followed by
    a write two retries can interleave: insert the row, and on conflict take it
    over *only* if the existing claim is unfinished and older than ``stale_s``.
    Nothing comes back when the row is completed (a genuine duplicate) or when
    it was claimed moments ago (a retry racing the delivery still in flight).

    The cutoff is computed by Postgres rather than in Python: ``claimed_at`` is
    written with ``now()``, and comparing it against a timestamp from a
    different clock is how a stale window silently becomes the wrong length.

    In its own transaction and before the effect, so two concurrent retries of
    the same delivery cannot both proceed.
    """
    stale_cutoff = text("now() - make_interval(secs => :claim_stale_s)").bindparams(
        bindparam("claim_stale_s", float(stale_s))
    )
    async with role_session(session_factory, db_role="hunter_worker") as session:
        claimed = (
            await session.execute(
                insert(ProcessedEvent)
                .values(consumer=CONSUMER, event_id=delivery_id)
                .on_conflict_do_update(
                    index_elements=["consumer", "event_id"],
                    set_={"claimed_at": func.now()},
                    where=ProcessedEvent.completed_at.is_(None)
                    & (ProcessedEvent.claimed_at < stale_cutoff),
                )
                .returning(ProcessedEvent.event_id)
            )
        ).first()
    return claimed is not None


async def complete_delivery(
    session_factory: async_sessionmaker[AsyncSession], delivery_id: str
) -> None:
    """Mark the claim finished — the second half of :func:`claim_delivery`.

    Called only after the effect has committed, so the window between the two
    is exactly the window in which a crash is recoverable. Its own transaction,
    for the same reason the claim is: the effect's transaction is already
    closed by the time we get here.
    """
    async with role_session(session_factory, db_role="hunter_worker") as session:
        await session.execute(
            update(ProcessedEvent)
            .where(
                ProcessedEvent.consumer == CONSUMER,
                ProcessedEvent.event_id == delivery_id,
            )
            .values(completed_at=func.now())
        )


async def release_delivery(
    session_factory: async_sessionmaker[AsyncSession], delivery_id: str
) -> None:
    """Give the claim back after a failure, in a transaction of its own.

    ``user.deleted`` writes one transaction per organization, so a failure
    halfway through leaves earlier organizations committed and later ones
    untouched. Svix will retry — and the retry is the only thing that can
    finish the job, so it must not be answered "duplicate". Its own
    transaction, because the one that failed is already rolling back.

    Best effort by construction: if the release itself fails there is nothing
    useful left to do, and the error that caused all this is the one the caller
    should see. The delivery then stays claimed and unfinished, which is
    visible in ``processed_events``, in this log line, and — after the stale
    window — to the next retry, which may take the claim over.
    """
    try:
        async with role_session(session_factory, db_role="hunter_worker") as session:
            await session.execute(
                delete(ProcessedEvent).where(
                    ProcessedEvent.consumer == CONSUMER,
                    ProcessedEvent.event_id == delivery_id,
                )
            )
    except Exception:
        logger.error("webhook_claim_release_failed", delivery_id=delivery_id)
