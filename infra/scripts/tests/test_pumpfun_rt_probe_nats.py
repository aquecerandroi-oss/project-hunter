"""Unit tests for ``infra/scripts/pumpfun_rt_probe_nats.py`` (the NATS-over-WebSocket client side of the
pump.fun realtime latency probe, 2026-10-06). Offline: synthetic frames and a synthetic home page; the
password in the fake page is a placeholder, never a real credential.

Run:
    uv run --no-sync pytest infra/scripts/tests/test_pumpfun_rt_probe_nats.py -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:  # the layout every script in this folder uses
    sys.path.insert(0, str(SCRIPTS_DIR))

from pumpfun_rt_probe_nats import (  # noqa: E402  (path surgery must come first)
    NatsConfig,
    NatsParser,
    classify_err,
    connect_line,
    decode_payload,
    site_nats_configs,
    slot_of,
)

FAKE_HOME = (
    'garbage<script>self.__next_f.push([1,"x"])</script>["$","$L9d",null,{\\"configs\\":{'
    '\\"ADVANCED\\":{\\"timeout\\":5000,\\"servers\\":\\"wss://adv.example\\",\\"user\\":\\"subscriber\\",'
    '\\"pass\\":\\"FAKE-A\\"},'
    '\\"CORE\\":{\\"timeout\\":5000,\\"servers\\":\\"wss://core.example\\",\\"user\\":\\"subscriber\\",'
    '\\"pass\\":\\"FAKE-C\\"},'
    '\\"UNIFIED\\":{\\"timeout\\":5000,\\"servers\\":\\"wss://uni.example\\",\\"user\\":\\"subscriber\\",'
    '\\"pass\\":\\"FAKE-U\\"}},\\"instances\\":[\\"UNIFIED\\",\\"CORE\\"],\\"children\\":1}]'
)


def test_site_configs_come_from_the_props_the_anonymous_page_ships() -> None:
    configs = site_nats_configs(FAKE_HOME)
    assert set(configs) == {"ADVANCED", "CORE", "UNIFIED"}
    assert configs["UNIFIED"] == NatsConfig("wss://uni.example", "subscriber", "FAKE-U")


def test_config_repr_never_prints_the_password() -> None:
    cfg = NatsConfig("wss://uni.example", "subscriber", "FAKE-U")
    assert "FAKE-U" not in repr(cfg)
    assert "FAKE-U" not in str(cfg)


def test_missing_configs_is_an_error_not_a_guess() -> None:
    with pytest.raises(ValueError, match="configs"):
        site_nats_configs("<html>no nats here</html>")


def test_connect_line_mirrors_the_site_client_without_a_token() -> None:
    line = connect_line(NatsConfig("wss://x", "subscriber", "FAKE-U"))
    assert line.startswith("CONNECT {") and line.endswith("}\r\nPING\r\n")
    body = json.loads(line[len("CONNECT ") : line.index("\r\n")])
    assert body["user"] == "subscriber" and body["pass"] == "FAKE-U"
    assert body["verbose"] is False and body["headers"] is True and body["protocol"] == 1
    assert "auth_token" not in body and "jwt" not in body


def test_parser_handles_a_message_split_across_websocket_frames() -> None:
    p = NatsParser()
    first = p.push(b'INFO {"a":1}\r\nMSG subj.x 7 5\r\nhel')
    assert [(o.kind, o.text) for o in first] == [("info", '{"a":1}')]
    second = p.push(b"lo\r\nPING\r\n")
    assert [o.kind for o in second] == ["msg", "ping"]
    assert (second[0].subject, second[0].sid, second[0].payload) == ("subj.x", 7, b"hello")


def test_parser_reads_hmsg_headers_off_the_payload() -> None:
    p = NatsParser()
    hdr = b"NATS/1.0\r\n\r\n"
    ops = p.push(b"HMSG s 3 %d %d\r\n" % (len(hdr), len(hdr) + 2) + hdr + b"ok\r\n")
    assert ops[0].kind == "msg" and ops[0].payload == b"ok"


def test_parser_reports_err_and_pong_and_ok() -> None:
    ops = NatsParser().push(
        b"+OK\r\nPONG\r\n-ERR 'Permissions Violation for Subscription to \"a.b\"'\r\n"
    )
    assert [o.kind for o in ops] == ["ok", "pong", "err"]
    assert "Permissions Violation" in ops[2].text


def test_parser_keeps_two_messages_in_one_frame() -> None:
    ops = NatsParser().push(b"MSG a 1 2\r\nhi\r\nMSG b 2 3\r\nyou\r\n")
    assert [(o.subject, o.payload) for o in ops] == [("a", b"hi"), ("b", b"you")]


def test_decode_payload_unwraps_a_double_encoded_json_string() -> None:
    inner = json.dumps({"tx": "sig1", "mint": "m"})
    assert decode_payload(json.dumps(inner).encode()) == {"tx": "sig1", "mint": "m"}
    assert decode_payload(inner.encode()) == {"tx": "sig1", "mint": "m"}


def test_decode_payload_returns_none_on_garbage_instead_of_raising() -> None:
    assert decode_payload(b"\xff\xfe not json") is None
    assert decode_payload(b"123") is None  # not an object


def test_slot_of_reads_the_first_twelve_digits_of_the_slot_index_id() -> None:
    # verified in docs/PUMPFUN.md section 3.1: ``slotIndexId`` = 12-digit slot + the in-slot index
    assert slot_of("00045377553700023900000002") == 453775537
    assert slot_of("not-digits") is None
    assert slot_of(None) is None


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("'Authorization Violation'", "auth"),
        ("'User Authentication Expired'", "auth"),
        ("'Permissions Violation for Subscription to \"x\"'", "permissions"),
        ("'Maximum Subscriptions Exceeded'", "subscription_limit"),
        ("'Stale Connection'", "other"),
    ],
)
def test_classify_err_names_the_refusal(text: str, kind: str) -> None:
    assert classify_err(text) == kind
