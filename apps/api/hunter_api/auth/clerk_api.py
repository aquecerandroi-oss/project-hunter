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

from typing import TYPE_CHECKING, Any, Protocol, cast

import httpx
from pydantic import BaseModel

from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hunter_api.settings import ApiSettings

logger = get_logger(__name__)

CLERK_API_BASE = "https://api.clerk.com/v1"
REQUEST_TIMEOUT_S = 5.0


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
        url = f"{CLERK_API_BASE}/users/{external_auth_id}"
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
    carry the same object. The primary address is the one Clerk marks as such;
    when it names none, the first address is used rather than dropping the user
    on the floor (``users.email`` is ``NOT NULL``).
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
    addresses = _addresses(payload.get("email_addresses"))
    if not addresses:
        return None
    primary_id = payload.get("primary_email_address_id")
    for address in addresses:
        if primary_id is not None and address.get("id") == primary_id:
            return _optional_str(address.get("email_address"))
    return _optional_str(addresses[0].get("email_address"))


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
