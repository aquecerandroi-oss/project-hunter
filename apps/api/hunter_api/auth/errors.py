"""The two answers a failed authentication can give, and why they differ.

They live in their own module because both the token verifier
(:mod:`hunter_api.auth.clerk`) and the key cache (:mod:`hunter_api.auth.jwks`)
raise them, and neither should have to import the other to do it.
"""

from __future__ import annotations

from fastapi import status

from hunter_api.errors import HunterError


class InvalidTokenError(HunterError):
    """401 for anything wrong with a bearer token — bad signature, expired,
    wrong issuer, unknown key. The reason is deliberately coarse: telling a
    caller *which* check failed helps an attacker tune the next attempt more
    than it helps a legitimate client, which can only do one thing either way
    (re-authenticate).
    """

    def __init__(self, detail: str = "The access token is missing or invalid.") -> None:
        super().__init__(
            type_slug="invalid-token",
            title="Unauthorized",
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
        )


class AuthUnavailableError(HunterError):
    """503 for "we cannot verify anything right now" — the JWKS document could
    not be fetched and nothing usable is cached.

    Deliberately *not* an :class:`InvalidTokenError`. A 401 tells the browser
    its session is dead and sends the user back to Clerk to sign in again; a
    JWKS outage would then log out every signed-in user of the platform for a
    fault on our side, and the sign-in they attempt goes through the same
    unreachable provider. 503 + ``Retry-After`` says what is actually true.
    """

    def __init__(self, retry_after_s: int = 30) -> None:
        super().__init__(
            type_slug="auth-unavailable",
            title="Service Unavailable",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is temporarily unavailable. Try again shortly.",
            headers={"Retry-After": str(retry_after_s)},
        )
