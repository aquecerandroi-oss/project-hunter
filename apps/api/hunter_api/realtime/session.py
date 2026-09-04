"""What a live WebSocket keeps, and the task that keeps checking it.

Authorization on an HTTP request is decided once and lasts for one request. A
WebSocket is authorized once and then lasts for hours, which makes "still a
member?" a question with a shelf life: remove someone from an organization, or
let the Clerk webhook suspend them, and their open socket keeps receiving that
organization's risk events and positions until they close the tab.

:func:`watch_session` is the answer — one task per connection that, every
``ws_revalidate_interval_s``, re-resolves the principal from the same claims
the handshake verified and compares the result against what the socket is
subscribed to. It also closes a socket that has sent nothing at all for
:data:`IDLE_TIMEOUT_SECONDS`; the pong timeout in ``endpoint`` catches a client
that stopped answering, this catches one that answers and does nothing else.

Close codes live here rather than in ``endpoint`` so the watchdog and the
endpoint can share them without importing each other.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import TYPE_CHECKING, Protocol

from hunter_api.auth.clerk import InvalidTokenError
from hunter_api.auth.principal import Principal, ProvisioningError
from hunter_api.realtime.channels import is_authorized
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from fastapi import WebSocket

    from hunter_api.auth.clerk import TokenClaims

logger = get_logger(__name__)

WS_MEMBERSHIP_REVOKED_CODE = 4403
WS_IDLE_TIMEOUT_CODE = 4409

IDLE_TIMEOUT_SECONDS = 15 * 60
DEFAULT_REVALIDATE_INTERVAL_S = 60.0


class ChannelSink(Protocol):
    """The one thing the watchdog needs from the hub — named as a Protocol so
    this module does not import ``endpoint`` (which imports this one).
    """

    async def unsubscribe(self, connection: WebSocket, channel: str) -> None: ...


class WsSession:
    """One connection's mutable state: who it is, what it listens to, when it
    last said anything.

    ``claims`` is kept because revalidation needs to re-resolve the *same*
    verified identity without re-reading a token from the wire — the token is
    never stored, and nothing the client sends later is trusted to name who
    they are.
    """

    __slots__ = ("claims", "last_frame_at", "principal", "subscribed")

    def __init__(self, principal: Principal, claims: TokenClaims) -> None:
        self.principal = principal
        self.claims = claims
        self.subscribed: set[str] = set()
        self.last_frame_at = time.monotonic()

    def mark_frame(self) -> None:
        self.last_frame_at = time.monotonic()

    @property
    def idle_for(self) -> float:
        return time.monotonic() - self.last_frame_at


async def watch_session(websocket: WebSocket, session: WsSession, hub: ChannelSink) -> None:
    """Revalidate membership and enforce the idle timeout until cancelled."""
    interval = _interval(websocket)
    while True:
        await asyncio.sleep(interval)
        if session.idle_for >= IDLE_TIMEOUT_SECONDS:
            logger.info("ws_idle_timeout", principal_id=str(session.principal.user_id))
            await close_socket(websocket, WS_IDLE_TIMEOUT_CODE, "idle timeout")
            return
        if await _revalidate(websocket, session, hub):
            return


async def _revalidate(websocket: WebSocket, session: WsSession, hub: ChannelSink) -> bool:
    """``True`` when the socket was closed.

    The channels a lost membership covered are dropped *before* the close, so
    the hub releases its Redis subscription even if the close races the client
    disappearing on its own.
    """
    updated = await _resolve(websocket, session)
    if updated is None:
        return False
    session.principal = updated
    lost = [channel for channel in session.subscribed if not is_authorized(channel, updated)]
    if not lost:
        return False
    logger.info("ws_membership_revoked", principal_id=str(updated.user_id), channels=len(lost))
    for channel in lost:
        session.subscribed.discard(channel)
        await hub.unsubscribe(websocket, channel)
    await close_socket(websocket, WS_MEMBERSHIP_REVOKED_CODE, "membership revoked")
    return True


async def _resolve(websocket: WebSocket, session: WsSession) -> Principal | None:
    """Re-resolve the principal, or ``None`` when this round should be skipped.

    A resolver failure that is *not* about identity (the database briefly
    unreachable) leaves the socket alone: dropping every live connection on a
    transient error turns a blip into an outage, and the next round is a
    minute away. An identity failure — the account no longer resolves — is
    treated as total membership loss, which closes the socket.
    """
    resolver = websocket.app.state.principal_resolver
    try:
        principal: Principal = await resolver.resolve(session.claims)
    except (InvalidTokenError, ProvisioningError):
        logger.info("ws_principal_gone")
        return _without_memberships(session.principal)
    except Exception:
        logger.warning("ws_revalidation_failed")
        return None
    return principal


def _without_memberships(principal: Principal) -> Principal:
    return Principal(
        user_id=principal.user_id,
        external_auth_id=principal.external_auth_id,
        email=principal.email,
        memberships=(),
    )


def _interval(websocket: WebSocket) -> float:
    settings = getattr(websocket.app.state, "settings", None)
    interval = getattr(settings, "ws_revalidate_interval_s", DEFAULT_REVALIDATE_INTERVAL_S)
    return float(interval)


async def close_socket(websocket: WebSocket, code: int, reason: str) -> None:
    """Close, swallowing whatever the transport says about a socket that may
    already be gone — the caller is on its way out either way.
    """
    with contextlib.suppress(Exception):
        await websocket.close(code=code, reason=reason)
