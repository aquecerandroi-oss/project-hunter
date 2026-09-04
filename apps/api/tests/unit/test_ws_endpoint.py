"""``/ws`` closes with 4401: auth verification is T06's job, never faked here.

Uses ``starlette.testclient.TestClient`` specifically for its
``websocket_connect()`` — ``httpx`` (used elsewhere in this suite) has no
WebSocket support at all.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

if TYPE_CHECKING:
    from fastapi import FastAPI

pytestmark = pytest.mark.unit


def test_closes_with_4401_after_an_auth_message(app: FastAPI) -> None:
    with TestClient(app) as client, client.websocket_connect("/ws") as websocket:
        websocket.send_text(json.dumps({"type": "auth", "token": "whatever"}))
        with pytest.raises(WebSocketDisconnect) as exc_info:
            websocket.receive_text()

    assert exc_info.value.code == 4401


def test_closes_with_4401_given_a_non_auth_message(app: FastAPI) -> None:
    with TestClient(app) as client, client.websocket_connect("/ws") as websocket:
        websocket.send_text("not an auth message")
        with pytest.raises(WebSocketDisconnect) as exc_info:
            websocket.receive_text()

    assert exc_info.value.code == 4401
