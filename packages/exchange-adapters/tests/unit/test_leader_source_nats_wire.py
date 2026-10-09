"""Copy-trade pilot (H-037): the NATS wire side of the leader source, offline and pure.

Frames follow the shape of the 4 real balance samples of the 06/10 probe (KB-0186); the values in
``fixtures/pumpfun/leader_nats_frames.json`` are invented placeholders (see its ``_provenance``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from hunter_exchanges.pumpfun.leader_source_nats_wire import (
    BalanceLeg,
    NatsAuthError,
    NatsConfig,
    NatsParser,
    classify_err,
    connect_line,
    decode_payload,
    home_nats_config,
    parse_balance_leg,
    refused_for_scale,
    to_atoms,
)

pytestmark = pytest.mark.unit

FX = json.loads(
    (Path(__file__).parents[1] / "fixtures/pumpfun/leader_nats_frames.json").read_text()
)
WALLET: str = FX["wallet"]
MINT: str = FX["mint"]
SOL_FRAME: dict[str, Any] = FX["frames"]["sol_leg"]
TOKEN_FRAME: dict[str, Any] = FX["frames"]["token_leg"]
SUBJECT = f"account_balance_change.{WALLET}.{MINT}"


def test_credential_is_read_from_the_home_page_props_and_never_printed() -> None:
    cfg = home_nats_config(FX["home_page_props_escaped"])
    assert (cfg.servers, cfg.user) == ("wss://core.nats.invalid", "subscriber")
    assert cfg.password == "TEST-ONLY-NOT-A-REAL-PASSWORD"
    assert "TEST-ONLY" not in repr(cfg) and "TEST-ONLY" not in str(cfg)


def test_a_home_page_without_the_configs_is_an_auth_error_not_a_crash() -> None:
    with pytest.raises(NatsAuthError):
        home_nats_config("<html>login required</html>")
    with pytest.raises(NatsAuthError):
        home_nats_config('"configs":{"UNIFIED":{"servers":"w","user":"u","pass":"p"}}')  # no CORE
    with pytest.raises(NatsAuthError):
        home_nats_config('"configs":{"CORE":{"servers":"w"')  # truncated


def test_the_error_message_of_a_failed_credential_never_carries_the_page() -> None:
    with pytest.raises(NatsAuthError) as err:
        home_nats_config('"configs":{"CORE":{"servers":"w","user":"u","pass":"SECRET-PW"')
    assert "SECRET-PW" not in str(err.value)


def test_connect_line_is_the_plain_client_handshake() -> None:
    line = connect_line(NatsConfig("wss://x", "subscriber", "pw"))
    head, body = line.split(" ", 1)
    assert head == "CONNECT" and line.endswith("\r\nPING\r\n")
    obj = json.loads(body.split("\r\n")[0])
    assert (obj["user"], obj["pass"], obj["verbose"], obj["headers"]) == (
        "subscriber",
        "pw",
        False,
        True,
    )


def test_parser_reassembles_a_message_split_across_frames_and_handles_hmsg() -> None:
    payload = json.dumps(TOKEN_FRAME).encode()
    msg = b"MSG %s 7 %d\r\n%s\r\n" % (SUBJECT.encode(), len(payload), payload)
    parser = NatsParser()
    assert parser.push(b"INFO {}\r\n")[0].kind == "info"
    assert parser.push(msg[:40]) == []
    (op,) = parser.push(msg[40:])
    assert (op.kind, op.subject, op.sid) == ("msg", SUBJECT, 7) and decode_payload(op.payload)
    header = b"NATS/1.0\r\n\r\n"
    hmsg = b"HMSG %s 7 %d %d\r\n%s%s\r\n" % (
        SUBJECT.encode(),
        len(header),
        len(header) + len(payload),
        header,
        payload,
    )
    (hop,) = parser.push(hmsg)
    assert hop.payload == payload
    assert [o.kind for o in parser.push(b"PING\r\nPONG\r\n+OK\r\n")] == ["ping", "pong", "ok"]


def test_error_classification() -> None:
    assert classify_err("'Authorization Violation'") == "auth"
    assert classify_err("'Permissions Violation for Subscription to \"x\"'") == "permissions"
    assert classify_err("'Maximum Subscriptions Exceeded'") == "subscription_limit"
    assert classify_err("'Slow Consumer'") == "other"


def test_decode_payload_unwraps_double_encoding_and_refuses_the_rest() -> None:
    inner = json.dumps(SOL_FRAME)
    assert decode_payload(json.dumps(inner).encode()) == SOL_FRAME
    assert decode_payload(b"not json") is None
    assert decode_payload(b"[1,2]") is None
    assert decode_payload(b"\xff\xfe") is None


@pytest.mark.parametrize(
    ("text", "decimals", "atoms"),
    [
        ("59760.972304279", 9, 59_760_972_304_279),
        ("795761175.792087", 6, 795_761_175_792_087),
        ("0", 6, 0),
        ("1.5", 6, 1_500_000),
        ("1E+3", 6, 1_000_000_000),
        ("0.0000001", 6, None),  # finer than the mint's decimals: not this mint's scale
        ("-1", 6, None),
        ("abc", 6, None),
        ("NaN", 6, None),
        ("Infinity", 6, None),
    ],
)
def test_balances_become_integer_atoms_or_nothing(
    text: str, decimals: int, atoms: int | None
) -> None:
    assert to_atoms(text, decimals) == atoms


def test_a_token_leg_parses_into_integer_atoms_with_its_order_key() -> None:
    leg = parse_balance_leg(SUBJECT, TOKEN_FRAME)
    assert isinstance(leg, BalanceLeg)
    assert (leg.wallet, leg.mint, leg.balance_atoms) == (WALLET, MINT, 795_761_175_792_087)
    assert (leg.slot, leg.tx_index, leg.signature) == (453890603, 512, TOKEN_FRAME["txSignature"])
    assert leg.order == (453890603, 512) and not leg.is_sol
    assert leg.server_ts is not None
    assert leg.server_ts.utcoffset() is not None and leg.server_ts.utcoffset().total_seconds() == 0  # type: ignore[union-attr]


def test_the_sol_leg_is_lamports() -> None:
    leg = parse_balance_leg(SUBJECT, SOL_FRAME)
    assert leg is not None and leg.is_sol and leg.balance_atoms == 59_760_972_304_279


_MISSING = object()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("txSignature", _MISSING),
        ("balance", "1.2.3"),
        ("balance", 12.5),  # a float on the wire is never trusted
        ("slot", "x"),
        ("slot", -1),
        ("txIndex", "abc"),
        ("walletAddress", "SomeoneElse"),  # not the wallet in the subject
        ("tokenMint", None),
    ],
)
def test_malformed_legs_are_refused_not_guessed(field: str, value: object) -> None:
    frame = dict(TOKEN_FRAME)
    if value is _MISSING:
        del frame[field]
    else:
        frame[field] = value
    assert parse_balance_leg(SUBJECT, frame) is None


def test_a_naive_server_stamp_only_loses_the_optional_stamp() -> None:
    frame = {**TOKEN_FRAME, "timestamp": "2026-10-06T11:39:09.855"}
    leg = parse_balance_leg(SUBJECT, frame)
    assert leg is not None and leg.server_ts is None


def test_other_subjects_are_not_balance_legs() -> None:
    assert parse_balance_leg("unifiedTradeEvent.lite.X", TOKEN_FRAME) is None


WSOL = "So11111111111111111111111111111111111111112"


def test_wrapped_sol_is_a_nine_decimal_leg_not_a_malformed_one() -> None:
    frame = {**TOKEN_FRAME, "tokenMint": WSOL, "balance": "2242.493650673"}
    leg = parse_balance_leg(f"account_balance_change.{WALLET}.{WSOL}", frame)
    assert leg is not None and leg.mint == WSOL and leg.balance_atoms == 2_242_493_650_673


def test_a_mint_on_another_scale_is_told_apart_from_a_malformed_frame() -> None:
    other = {**TOKEN_FRAME, "balance": "1.123456789"}  # nine decimals on an unknown mint
    assert parse_balance_leg(SUBJECT, other) is None
    assert refused_for_scale(SUBJECT, other)
    assert not refused_for_scale(SUBJECT, {**TOKEN_FRAME, "balance": "nonsense"})
    assert not refused_for_scale(SUBJECT, {**TOKEN_FRAME, "txSignature": None})
