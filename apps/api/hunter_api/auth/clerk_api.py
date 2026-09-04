"""Reading a user's profile from Clerk's Backend API.

Only used on the two paths where the local mirror is missing or stale:
just-in-time provisioning (:mod:`hunter_api.auth.principal`) and the
``user.created``/``user.updated`` webhook, which brings the payload with it
and therefore never calls out.

``CLERK_SECRET_KEY`` is read straight from settings and used as a bearer
credential; it is never logged, never returned, and never reaches a response
body (SECURITY.md §4).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Protocol, cast
from urllib.parse import quote

import httpx
from pydantic import BaseModel

from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from hunter_api.settings import ApiSettings

logger = get_logger(__name__)

CLERK_API_BASE = "https://api.clerk.com/v1"
REQUEST_TIMEOUT_S = 5.0
VERIFIED_STATUS = "verified"
"""The only ``email_addresses[].verification.status`` we accept."""


class UserProfile(BaseModel):
    """What the local ``users`` mirror needs from Clerk."""

    external_auth_id: str
    email: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None


class ProfileSource(Protocol):
    """Fetches a profile by Clerk user id, or ``None`` when unavailable."""

    async def fetch(self, external_auth_id: str) -> UserProfile | None: ...


class ClerkBackendApi:
    """``GET /v1/users/{id}`` against Clerk, authenticated with the secret key."""

    def __init__(self, settings: ApiSettings, *, client: httpx.AsyncClient | None = None) -> None:
        self._secret_key = settings.clerk_secret_key
        self._client = client

    async def fetch(self, external_auth_id: str) -> UserProfile | None:
        secret = self._secret_key.get_secret_value()
        if not secret:
            logger.warning("clerk_secret_key_unset")
            return None
        # the id comes from a token's ``sub``: percent-encoded so it stays one
        # path segment and cannot address a different Clerk endpoint with our
        # secret key attached
        url = f"{CLERK_API_BASE}/users/{quote(external_auth_id, safe='')}"
        headers = {"Authorization": f"Bearer {secret}"}
        try:
            payload = await self._get(url, headers)
        except Exception:
            # never include the exception text: an httpx error renders the
            # request, and the request carries the Authorization header
            logger.warning("clerk_profile_fetch_failed")
            return None
        return profile_from_clerk_user(payload)

    async def _get(self, url: str, headers: Mapping[str, str]) -> dict[str, Any]:
        if self._client is not None:
            response = await self._client.get(url, headers=headers, timeout=REQUEST_TIMEOUT_S)
        else:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S) as client:
                response = await client.get(url, headers=headers)
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        return payload


class StaticProfileSource:
    """A fixed set of profiles — tests and the offline dev path. Never hits the
    network, so a suite that forgets to stub Clerk fails loudly instead of
    silently reaching out.
    """

    def __init__(self, profiles: Mapping[str, UserProfile] | None = None) -> None:
        self._profiles = dict(profiles or {})

    def add(self, profile: UserProfile) -> None:
        self._profiles[profile.external_auth_id] = profile

    async def fetch(self, external_auth_id: str) -> UserProfile | None:
        return self._profiles.get(external_auth_id)


def profile_from_clerk_user(payload: Mapping[str, Any]) -> UserProfile | None:
    """Map a Clerk ``User`` object onto :class:`UserProfile`.

    Shared with the webhook, whose ``user.created``/``user.updated`` payloads
    carry the same object. ``email`` is ``None`` unless Clerk names a primary
    address *and* reports it verified — callers decide what to do with that
    (JIT provisioning fails closed with a 503, the webhook acknowledges and
    records an audit row), because ``users.email`` is ``NOT NULL`` and is what
    invitations are matched against.
    """
    external_auth_id = payload.get("id")
    if not isinstance(external_auth_id, str) or not external_auth_id:
        return None
    return UserProfile(
        external_auth_id=external_auth_id,
        email=_primary_email(payload),
        display_name=_display_name(payload),
        avatar_url=_optional_str(payload.get("image_url")),
    )


def _primary_email(payload: Mapping[str, Any]) -> str | None:
    """The primary address, and only if Clerk has verified it.

    Both halves are load-bearing. ``users.email`` is what
    ``accept_invitation`` matches an invitation against, so an *unverified*
    address is an address anyone can type: claim ``owner@customer.test`` on a
    throwaway Clerk account, never confirm it, and the pending invitation to
    that organization becomes acceptable. And the *primary* is Clerk's own
    answer to "which one is this person" — falling back to the first address
    in the list would let the caller choose it by adding one.
    """
    primary_id = payload.get("primary_email_address_id")
    if not isinstance(primary_id, str) or not primary_id:
        return None
    for address in _addresses(payload.get("email_addresses")):
        if address.get("id") != primary_id:
            continue
        return _optional_str(address.get("email_address")) if _is_verified(address) else None
    return None


def _is_verified(address: Mapping[str, Any]) -> bool:
    verification = address.get("verification")
    if not isinstance(verification, Mapping):
        return False
    status_value = cast("Mapping[str, Any]", verification).get("status")
    return status_value == VERIFIED_STATUS


def _addresses(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    entries = cast("list[object]", value)
    return [cast("dict[str, Any]", entry) for entry in entries if isinstance(entry, dict)]


def _display_name(payload: Mapping[str, Any]) -> str | None:
    parts = [_optional_str(payload.get("first_name")), _optional_str(payload.get("last_name"))]
    joined = " ".join(part for part in parts if part)
    return joined or _optional_str(payload.get("username"))


def _optional_str(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def create_profile_source(settings: ApiSettings) -> ProfileSource:
    """Clerk in every environment; an empty static source when no secret key is
    configured, so a local run without Clerk credentials fails at the point of
    provisioning with a clear 503 instead of a network error per request.
    """
    if not settings.clerk_secret_key.get_secret_value():
        return StaticProfileSource()
    return ClerkBackendApi(settings)
