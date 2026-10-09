"""pump.fun NATS-over-WebSocket, the client side the leader source needs (H-037) — pure, no IO, no clock.

The anonymous site opens ``wss://prod-v2.nats.realtime.pump.fun`` (instance ``CORE``) with a static
``subscriber`` credential that ships in the props of the public home page (KB-0186, decision
2026-10-06). :func:`home_nats_config` reads it **from that page text at run time**; the caller keeps
it in memory only. Nothing here writes it, logs it or puts it in an exception message
(:attr:`NatsConfig.password` is ``repr=False`` and ``__str__`` omits it). No login, no cookie, no
``/nats/token`` (the user-scoped path).

The framing is the plain NATS client protocol the site's worker speaks (``INFO``/``CONNECT``/``SUB``/
``MSG``/``HMSG``/``PING``/``-ERR``); payloads are JSON, sometimes double-encoded as a string. The
balance channel ``account_balance_change.<wallet>.*`` sends **absolute balances in UI decimals as
strings**, one frame per balance leg (SOL, and each token) of a transaction, sharing ``txSignature``
and ``slot``; :func:`parse_balance_leg` turns one into exact integer atoms/lamports.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Final, Literal, cast

HOME_URL: Final = "https://pump.fun/"
BALANCE_SUBJECT: Final = "account_balance_change"
SOL_DECIMALS: Final = 9
TOKEN_DECIMALS: Final = 6
"""Pump bonding-curve and PumpSwap-launched mints have 6 decimals; a balance finer than that is not
this scale and is refused (the chain confirmation reads the real decimals)."""

WSOL_MINT: Final = "So11111111111111111111111111111111111111112"
_KNOWN_DECIMALS: Final = {WSOL_MINT: SOL_DECIMALS}

OpKind = Literal["info", "msg", "ping", "pong", "ok", "err"]

_ERR_KINDS: Final = (
    (re.compile(r"authorization violation|authentication", re.I), "auth"),
    (re.compile(r"permissions violation", re.I), "permissions"),
    (re.compile(r"maximum subscriptions exceeded", re.I), "subscription_limit"),
)


class NatsAuthError(Exception):
    """The credential is gone or refused (the page no longer carries it, or the server said so).
    Fixed messages only: never the page, never the password."""


class NatsRefused(Exception):
    """The page or the socket said no with an HTTP status (401/403/418/429): a rate limit or a block.
    Never retried in a tight loop and never evaded; it is a ``system_event`` and a named gap."""

    def __init__(self, status: int) -> None:
        super().__init__(f"HTTP {status}")
        self.status = status


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


def home_nats_config(home_html: str, instance: str = "CORE") -> NatsConfig:
    """The ``configs.<instance>`` prop of the site's ``NatsProvider``; :class:`NatsAuthError` when the
    page no longer carries it (then the honest result is "requires auth")."""
    text = home_html.replace('\\"', '"')
    at = text.find('"configs":{')
    if at < 0:
        raise NatsAuthError("home page carries no NatsProvider configs")
    try:
        raw: Any
        raw, _ = json.JSONDecoder().raw_decode(text, at + len('"configs":'))
    except json.JSONDecodeError:
        raise NatsAuthError("NatsProvider configs unreadable") from None
    cfg = cast("dict[str, Any]", raw).get(instance) if isinstance(raw, dict) else None
    if isinstance(cfg, dict):
        c = cast("dict[str, Any]", cfg)
        if c.get("servers") and c.get("user") and c.get("pass"):
            return NatsConfig(str(c["servers"]), str(c["user"]), str(c["pass"]))
    raise NatsAuthError(f"NatsProvider configs carry no usable {instance} entry")


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
        pos = 0
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
        try:
            if head.startswith("MSG ") and len(parts) in (4, 5):
                self._want = (parts[1], int(parts[2]), 0, int(parts[-1]))
                return None
            if head.startswith("HMSG ") and len(parts) in (5, 6):
                self._want = (parts[1], int(parts[2]), int(parts[-2]), int(parts[-1]))
                return None
        except ValueError:
            return Op("err", text="malformed MSG line")
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


def classify_err(text: str) -> str:
    for pattern, kind in _ERR_KINDS:
        if pattern.search(text):
            return kind
    return "other"


def to_atoms(text: str, decimals: int) -> int | None:
    """A UI-decimal balance string -> exact integer atoms; ``None`` when it is not a finite,
    non-negative number representable at ``decimals`` (a finer value is another mint's scale)."""
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    if not value.is_finite() or value < 0:
        return None
    scaled = value.scaleb(decimals)
    if scaled != scaled.to_integral_value():
        return None
    return int(scaled)


@dataclass(frozen=True, slots=True)
class BalanceLeg:
    """One ``account_balance_change`` frame: the wallet's absolute balance of ``mint`` after the
    transaction ``signature`` (``mint == "SOL"`` is the native balance, in lamports)."""

    wallet: str
    mint: str
    balance_atoms: int
    slot: int
    tx_index: int
    signature: str
    server_ts: datetime | None

    @property
    def is_sol(self) -> bool:
        return self.mint == "SOL"

    @property
    def order(self) -> tuple[int, int]:
        """Chain order of the leg: later transactions compare greater."""
        return (self.slot, self.tx_index)


def _server_ts(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo is not None else None


def _int_field(value: object, *, default: int | None = None) -> int | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _decimals(mint: str) -> int:
    return SOL_DECIMALS if mint == "SOL" else _KNOWN_DECIMALS.get(mint, TOKEN_DECIMALS)


def refused_for_scale(subject: str, payload: dict[str, Any]) -> bool:
    """True when :func:`parse_balance_leg` refused only because the balance is finer than the mint's
    assumed decimals (another scale: not a pump mint) — counted apart from a malformed frame."""
    mint, balance = payload.get("tokenMint"), payload.get("balance")
    if not isinstance(mint, str) or not isinstance(balance, str):
        return False
    try:
        finite = Decimal(balance).is_finite()
    except InvalidOperation:
        return False
    parts = subject.split(".")
    return (
        finite
        and len(parts) >= 3
        and payload.get("txSignature") is not None
        and payload.get("walletAddress") == parts[1]
        and to_atoms(balance, _decimals(mint)) is None
    )


def parse_balance_leg(subject: str, payload: dict[str, Any]) -> BalanceLeg | None:
    """A frame of ``account_balance_change.<wallet>.*`` -> :class:`BalanceLeg`; ``None`` for another
    subject or anything malformed (never guessed). The wallet in the body must be the one in the
    subject."""
    parts = subject.split(".")
    if len(parts) < 3 or parts[0] != BALANCE_SUBJECT:
        return None
    wallet, signature, mint = parts[1], payload.get("txSignature"), payload.get("tokenMint")
    balance = payload.get("balance")
    slot = payload.get("slot")
    if payload.get("walletAddress") != wallet:
        return None
    if not (isinstance(signature, str) and signature and isinstance(mint, str) and mint):
        return None
    if not isinstance(balance, str) or isinstance(slot, bool) or not isinstance(slot, int):
        return None  # a JSON number for a balance would be a float: never trusted
    tx_index = _int_field(payload.get("txIndex"), default=0)
    atoms = to_atoms(balance, _decimals(mint))
    if atoms is None or tx_index is None or slot < 0:
        return None
    return BalanceLeg(
        wallet, mint, atoms, slot, tx_index, signature, _server_ts(payload.get("timestamp"))
    )
