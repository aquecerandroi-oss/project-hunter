"""Svix signature verification on the Clerk webhook — SECURITY.md §5.

The endpoint is public and unauthenticated by design, so the signature is the
*only* thing standing between a stranger and a ``users`` row with an email of
their choosing — and email is what an invitation is matched against. The
secret here is generated per test run and labelled FAKE; no real Clerk secret
exists in this repository.

Idempotency (the ``svix-id`` replay guard) needs Postgres and is covered in
``tests/integration/test_webhook.py``.
"""

from __future__ import annotations

import base64
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from svix.webhooks import Webhook

from hunter_api.services.webhook_delivery import (
    MAX_BODY_BYTES,
    WebhookNotConfiguredError,
    WebhookSignatureError,
    verify_signature,
)

pytestmark = pytest.mark.unit

FAKE_SECRET = "whsec_" + base64.b64encode(secrets.token_bytes(24)).decode()
DELIVERY_ID = "msg_FAKE_delivery_1"


def _signed(
    payload: dict[str, Any],
    *,
    secret: str = FAKE_SECRET,
    delivery_id: str = DELIVERY_ID,
    timestamp: datetime | None = None,
) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(payload).encode()
    moment = timestamp or datetime.now(UTC)
    signature = Webhook(secret).sign(delivery_id, moment, body.decode())
    return body, {
        "svix-id": delivery_id,
        "svix-timestamp": str(int(moment.timestamp())),
        "svix-signature": signature,
    }


def test_a_correctly_signed_delivery_is_parsed() -> None:
    payload = {"type": "user.created", "data": {"id": "user_FAKE_1"}}
    body, headers = _signed(payload)

    assert verify_signature(FAKE_SECRET, body, headers) == payload


def test_a_forged_signature_is_rejected() -> None:
    body, headers = _signed({"type": "user.created", "data": {"id": "user_FAKE_1"}})
    headers["svix-signature"] = "v1,Zm9yZ2VkIHNpZ25hdHVyZQ=="

    with pytest.raises(WebhookSignatureError):
        verify_signature(FAKE_SECRET, body, headers)


def test_a_body_tampered_with_after_signing_is_rejected() -> None:
    body, headers = _signed({"type": "user.created", "data": {"id": "user_FAKE_1"}})
    tampered = body.replace(b"user_FAKE_1", b"user_FAKE_2")

    with pytest.raises(WebhookSignatureError):
        verify_signature(FAKE_SECRET, tampered, headers)


def test_a_signature_from_a_different_secret_is_rejected() -> None:
    other = "whsec_" + base64.b64encode(secrets.token_bytes(24)).decode()
    body, headers = _signed({"type": "user.created", "data": {}}, secret=other)

    with pytest.raises(WebhookSignatureError):
        verify_signature(FAKE_SECRET, body, headers)


def test_an_old_delivery_is_rejected() -> None:
    # Svix bounds the timestamp; an attacker who captured a valid delivery
    # cannot replay it days later even before our own svix-id guard sees it
    stale = datetime.now(UTC) - timedelta(hours=2)
    body, headers = _signed({"type": "user.created", "data": {}}, timestamp=stale)

    with pytest.raises(WebhookSignatureError):
        verify_signature(FAKE_SECRET, body, headers)


@pytest.mark.parametrize("missing", ["svix-id", "svix-timestamp", "svix-signature"])
def test_a_missing_svix_header_is_rejected(missing: str) -> None:
    body, headers = _signed({"type": "user.created", "data": {}})
    headers.pop(missing)

    with pytest.raises(WebhookSignatureError):
        verify_signature(FAKE_SECRET, body, headers)


def test_an_unconfigured_secret_is_a_503_never_a_bypass() -> None:
    body, headers = _signed({"type": "user.created", "data": {}})

    with pytest.raises(WebhookNotConfiguredError) as exc_info:
        verify_signature("", body, headers)

    assert exc_info.value.status_code == 503


def test_an_oversized_body_is_rejected_before_verification() -> None:
    huge = b"x" * (MAX_BODY_BYTES + 1)
    _, headers = _signed({"type": "user.created", "data": {}})

    with pytest.raises(WebhookSignatureError):
        verify_signature(FAKE_SECRET, huge, headers)


def test_a_signed_but_non_json_body_is_rejected() -> None:
    body = b"not json"
    moment = datetime.now(UTC)
    signature = Webhook(FAKE_SECRET).sign(DELIVERY_ID, moment, body.decode())
    headers = {
        "svix-id": DELIVERY_ID,
        "svix-timestamp": str(int(moment.timestamp())),
        "svix-signature": signature,
    }

    with pytest.raises(WebhookSignatureError):
        verify_signature(FAKE_SECRET, body, headers)


def test_a_signed_json_array_yields_an_empty_mapping() -> None:
    # valid JSON, wrong shape: handled as "nothing to do" rather than crashing
    body = b'["not", "an", "object"]'
    moment = datetime.now(UTC)
    headers = {
        "svix-id": DELIVERY_ID,
        "svix-timestamp": str(int(moment.timestamp())),
        "svix-signature": Webhook(FAKE_SECRET).sign(DELIVERY_ID, moment, body.decode()),
    }

    assert verify_signature(FAKE_SECRET, body, headers) == {}
