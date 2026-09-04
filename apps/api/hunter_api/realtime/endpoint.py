"""``/ws`` — the WebSocket gateway entrypoint.

SECURITY.md §1: "token enviado na primeira mensagem (auth), nunca na query
string. Conexao fechada se nao autenticar em 5 s." Verifying that token
(Clerk JWT) is T06's job. Until then, every connection is accepted, given up
to 5 s to send an ``{"type": "auth", ...}`` message, and then closed with
``4401`` regardless of what (if anything) it sent — this endpoint never
fakes a successful authentication.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, cast

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from hunter_core.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)

AUTH_TIMEOUT_SECONDS = 5
WS_AUTH_REQUIRED_CODE = 4401


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=AUTH_TIMEOUT_SECONDS)
    except TimeoutError:
        await websocket.close(code=WS_AUTH_REQUIRED_CODE, reason="authentication timeout")
        return
    except WebSocketDisconnect:
        return

    sent_auth_message = _looks_like_auth_message(raw)
    logger.info("ws_auth_not_implemented", sent_auth_message=sent_auth_message)
    # Verification (Clerk JWT) lands in T06; every connection is closed here
    # whether or not it sent a well-formed auth message.
    await websocket.close(code=WS_AUTH_REQUIRED_CODE, reason="authentication not implemented (T06)")


def _looks_like_auth_message(raw: str) -> bool:
    try:
        data: object = json.loads(raw)
    except ValueError:
        return False
    if not isinstance(data, dict):
        return False
    message = cast("dict[str, Any]", data)
    return message.get("type") == "auth"
