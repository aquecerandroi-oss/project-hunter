"""Mapping a Clerk ``User`` object onto the local mirror — SECURITY.md §1.

The subject of this file is one rule: **only a verified primary address counts
as the user's email**. `users.email` is what an invitation is matched against
(``services/invitations.accept_invitation``), so an address Clerk has not
verified is an address anybody can claim — add ``owner@customer.test`` to a
throwaway Clerk account, never confirm it, and the pending invitation to that
customer's organization becomes acceptable. Clerk exposes the verification
state on each address; the mapper refuses to look away from it.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import SecretStr

from hunter_api.auth.clerk_api import ClerkBackendApi, profile_from_clerk_user
from hunter_api.settings import ApiSettings

pytestmark = pytest.mark.unit


def _address(identifier: str, email: str, status: str | None = "verified") -> dict[str, Any]:
    entry: dict[str, Any] = {"id": identifier, "email_address": email}
    if status is not None:
        entry["verification"] = {"status": status}
    return entry


def _user(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": "user_FAKE_1",
        "email_addresses": [_address("idn_FAKE_1", "primary@example.test")],
        "primary_email_address_id": "idn_FAKE_1",
        "first_name": "Ada",
        "last_name": "Lovelace",
    }
    payload.update(overrides)
    return payload


def test_a_verified_primary_address_is_the_email() -> None:
    profile = profile_from_clerk_user(_user())

    assert profile is not None
    assert profile.email == "primary@example.test"
    assert profile.display_name == "Ada Lovelace"


@pytest.mark.parametrize("status", ["unverified", "failed", "expired", None])
def test_an_unverified_primary_address_yields_no_email(status: str | None) -> None:
    payload = _user(
        email_addresses=[_address("idn_FAKE_1", "primary@example.test", status)],
    )

    profile = profile_from_clerk_user(payload)

    assert profile is not None
    assert profile.email is None


def test_a_verified_secondary_address_is_not_used_as_a_fallback() -> None:
    """The old fallback took ``addresses[0]`` when no primary was named.

    An attacker who adds a second address to their own Clerk account chooses
    which row lands in ``users.email``; the primary is the one Clerk itself
    considers authoritative, so it is the only one read here.
    """
    payload = _user(
        email_addresses=[
            _address("idn_FAKE_other", "someone.elses@example.test"),
            _address("idn_FAKE_1", "primary@example.test"),
        ],
        primary_email_address_id=None,
    )

    profile = profile_from_clerk_user(payload)

    assert profile is not None
    assert profile.email is None


def test_a_primary_id_pointing_at_a_missing_address_yields_no_email() -> None:
    payload = _user(primary_email_address_id="idn_FAKE_gone")

    profile = profile_from_clerk_user(payload)

    assert profile is not None
    assert profile.email is None


def test_a_payload_without_an_id_is_not_a_profile() -> None:
    assert profile_from_clerk_user({"email_addresses": []}) is None


async def test_the_clerk_user_id_is_percent_encoded_into_the_path() -> None:
    """``sub`` is attacker-shaped text that becomes part of a URL path.

    Unencoded, ``user_x/../../organizations`` would address a different Clerk
    endpoint entirely with our secret key attached to the request.
    """
    requested: list[str] = []

    class _Client:
        async def get(self, url: str, **_kwargs: Any) -> Any:
            requested.append(url)
            raise ConnectionError("not reached")

    settings = ApiSettings(hunter_env="test", clerk_secret_key=SecretStr("sk_FAKE_test"))
    api = ClerkBackendApi(settings, client=_Client())  # pyright: ignore[reportArgumentType]

    await api.fetch("user_FAKE/../organizations?x=1")

    assert requested == ["https://api.clerk.com/v1/users/user_FAKE%2F..%2Forganizations%3Fx%3D1"]
