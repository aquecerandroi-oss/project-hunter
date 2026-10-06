"""pump.fun realtime latency probe (2026-10-06) — the NATS-over-WebSocket client side, no IO.

The site opens ``wss://unified-prod.nats.realtime.pump.fun`` and ``wss://prod-v2.nats.realtime.pump.fun``
for every anonymous visitor. The static ``subscriber`` credential it uses ships in the props of the
anonymous home page (``configs`` of the ``NatsProvider``, read from the public bundle on 06/10/2026), so
this module reads it **at run time from that page** and keeps it in memory: nothing is written to disk,
nothing is printed (``NatsConfig.password`` is ``repr=False``). No login, no cookie, no ``/nats/token``
(the user-scoped JWT path), no ``Origin`` header the site did not send.

The framing below is the plain NATS client protocol the site's worker speaks (``INFO``/``CONNECT``/
``SUB``/``MSG``/``HMSG``/``PING``/``-ERR``); payloads are JSON, sometimes double-encoded as a string.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Final, Literal, cast

HOME_URL: Final = "https://pump.fun/"
OpKind = Literal["info", "msg", "ping", "pong", "ok", "err"]

_ERR_KINDS: Final = (
    (re.compile(r"authorization violation|authentication", re.I), "auth"),
    (re.compile(r"permissions violation", re.I), "permissions"),
    (re.compile(r"maximum subscriptions exceeded", re.I), "subscription_limit"),
)


@dataclass(frozen=True, slots=True)
class NatsConfig:
    servers: str
    user: str
    password: str = field(repr=False)

    def __str__(self) -> str:
        return f"NatsConfig(servers={self.servers!r}, user={self.user!r})"


@dataclass(frozen=True, slots=True)
class Op:
    kind: OpKind
    subject: str = ""
    sid: int = 0
    payload: bytes = b""
    text: str = ""


def site_nats_configs(home_html: str) -> dict[str, NatsConfig]:
    """The ``configs`` prop of the site's ``NatsProvider`` (``ADVANCED``/``CORE``/``UNIFIED``/...).

    Raises ``ValueError`` when the page no longer carries it (then the honest result is "requires auth")."""
    text = home_html.replace('\\"', '"')
    at = text.find('"configs":{')
    if at < 0:
        raise ValueError("home page carries no NatsProvider configs")
    try:
        raw: Any
        raw, _ = json.JSONDecoder().raw_decode(text, at + len('"configs":'))
    except json.JSONDecodeError as exc:
        raise ValueError(f"NatsProvider configs unreadable: {exc.msg}") from exc
    out: dict[str, NatsConfig] = {}
    for name, cfg in cast("dict[str, Any]", raw).items():
        if isinstance(cfg, dict):
            c = cast("dict[str, Any]", cfg)
            if c.get("servers") and c.get("user") and c.get("pass"):
                out[name] = NatsConfig(str(c["servers"]), str(c["user"]), str(c["pass"]))
    if not out:
        raise ValueError("NatsProvider configs carry no user/pass entries")
    return out


def connect_line(cfg: NatsConfig) -> str:
    """``CONNECT`` + ``PING`` exactly as a plain client sends them (the PONG confirms acceptance)."""
    body = {
        "verbose": False,
        "pedantic": False,
        "user": cfg.user,
        "pass": cfg.password,
        "lang": "js",
        "version": "0",
        "protocol": 1,
        "headers": True,
        "no_responders": True,
    }
    return "CONNECT " + json.dumps(body, separators=(",", ":")) + "\r\nPING\r\n"


class NatsParser:
    """Incremental parser: feed WebSocket frames, get complete operations (a frame may split a message)."""

    def __init__(self) -> None:
        self._rest: bytes = b""
        # subject, sid, header bytes, total bytes of the message whose body is still to come
        self._want: tuple[str, int, int, int] | None = None

    def push(self, data: bytes) -> list[Op]:
        buf = self._rest + data
        pos: int = 0
        ops: list[Op] = []
        while True:
            want = self._want
            if want is not None:
                subject, sid, hdr, size = want
                if len(buf) - pos < size + 2:
                    break
                ops.append(Op("msg", subject, sid, buf[pos + hdr : pos + size]))
                pos += size + 2
                self._want = None
                continue
            end = buf.find(b"\r\n", pos)
            if end < 0:
                break
            line = buf[pos:end].decode("utf-8", "replace")
            pos = end + 2
            op = self._control(line)
            if op is not None:
                ops.append(op)
        self._rest = buf[pos:]
        return ops

    def _control(self, line: str) -> Op | None:
        head = line[:5].upper()
        parts = line.split()
        if head.startswith("MSG ") and len(parts) in (4, 5):
            self._want = (parts[1], int(parts[2]), 0, int(parts[-1]))
            return None
        if head.startswith("HMSG ") and len(parts) in (5, 6):
            self._want = (parts[1], int(parts[2]), int(parts[-2]), int(parts[-1]))
            return None
        if head.startswith("INFO"):
            return Op("info", text=line[5:])
        if head.startswith("PING"):
            return Op("ping")
        if head.startswith("PONG"):
            return Op("pong")
        if line.startswith("+OK"):
            return Op("ok")
        if line.startswith("-ERR"):
            return Op("err", text=line[4:].strip())
        return None


def decode_payload(payload: bytes) -> dict[str, Any] | None:
    """JSON object of a message; unwraps one level of double encoding; ``None`` on anything else."""
    try:
        value: Any = json.loads(payload.decode("utf-8"))
        if isinstance(value, str):
            value = json.loads(value)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return cast("dict[str, Any]", value) if isinstance(value, dict) else None


def slot_of(slot_index_id: object) -> int | None:
    """Solana slot inside ``slotIndexId`` (12 digits + in-slot index; docs/PUMPFUN.md section 3.1)."""
    if isinstance(slot_index_id, str) and len(slot_index_id) >= 12 and slot_index_id[:12].isdigit():
        return int(slot_index_id[:12])
    return None


def classify_err(text: str) -> str:
    for pattern, kind in _ERR_KINDS:
        if pattern.search(text):
            return kind
    return "other"
