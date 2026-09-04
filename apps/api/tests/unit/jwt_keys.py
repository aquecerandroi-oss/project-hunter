"""An RSA keypair and a JWKS built from it, for signing FAKE tokens in tests.

Generated per process, never read from disk and never written anywhere: there
is no key material in the repository, and nothing here resembles a Clerk
credential. ``apps/api/tests/integration/conftest.py`` imports this too, so the
unit and integration suites exercise the same ``StaticKeyAuthProvider`` path.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

FAKE_KID = "FAKE-test-key-1"
FAKE_ISSUER = "https://fake-instance.clerk.test"
FAKE_AZP = "http://web.test"


def generate_keypair() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def jwks_for(private_key: rsa.RSAPrivateKey, *, kid: str = FAKE_KID) -> dict[str, Any]:
    """The public half of ``private_key`` as a one-key JWKS document."""
    jwk: dict[str, Any] = dict(RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True))
    jwk.update({"kid": kid, "alg": "RS256", "use": "sig"})
    return {"keys": [jwk]}


def sign(
    private_key: rsa.RSAPrivateKey,
    *,
    subject: str = "user_FAKE_clerk_id",
    issuer: str = FAKE_ISSUER,
    azp: str | None = FAKE_AZP,
    email: str | None = None,
    kid: str = FAKE_KID,
    expires_in_s: int = 300,
    issued_at: datetime | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """A FAKE RS256 session token, shaped like the ones Clerk issues."""
    now = issued_at or datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": subject,
        "iss": issuer,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(seconds=expires_in_s),
    }
    if azp is not None:
        claims["azp"] = azp
    if email is not None:
        claims["email"] = email
    if extra:
        claims.update(extra)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})
