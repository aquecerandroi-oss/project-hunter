"""Unit tests for hunter_core.logging."""

import logging as stdlib_logging

import pytest
import structlog
from pydantic import SecretStr

from hunter_core.logging import (
    bind_context,
    clear_context,
    configure_logging,
    get_logger,
    is_json_logging,
    redact_processor,
    redact_secret_values_processor,
    redact_url,
)
from hunter_core.settings import Environment, Settings

pytestmark = pytest.mark.unit

FAKE_KEYED_URL = "https://example.invalid/?api-key=FAKE1234abcd"


def _settings(hunter_env: Environment) -> Settings:
    """``Settings`` for ``hunter_env``, carrying the credentials staging and
    production refuse to start without (SECURITY.md §8). Logging does not read
    any of them; the constructor validates them.
    """
    return Settings(
        hunter_env=hunter_env,
        clerk_issuer="https://clerk.hunter.example",
        clerk_jwks_url=SecretStr("https://clerk.hunter.example/.well-known/jwks.json"),
        clerk_secret_key=SecretStr("sk_FAKE_not_a_real_key"),
        clerk_webhook_secret=SecretStr("whsec_FAKE_not_a_real_secret"),
    )


def test_redact_processor_masks_top_level_secret_keys() -> None:
    event = {"event": "login", "password": "hunter2", "api_key": "sk-abc", "user": "alice"}
    result = redact_processor(None, "info", event)
    assert result["password"] == "***REDACTED***"
    assert result["api_key"] == "***REDACTED***"
    assert result["user"] == "alice"
    assert result["event"] == "login"


def test_redact_processor_masks_nested_secret_keys() -> None:
    event = {
        "event": "webhook.received",
        "payload": {"headers": {"Authorization": "Bearer xyz"}, "body": {"ok": True}},
    }
    result = redact_processor(None, "info", event)
    assert result["payload"]["headers"]["Authorization"] == "***REDACTED***"
    assert result["payload"]["body"]["ok"] is True


def test_redact_processor_masks_secret_keys_inside_lists() -> None:
    event = {"credentials": [{"token": "abc123"}, {"token": "def456"}]}
    result = redact_processor(None, "info", event)
    assert result["credentials"] == [
        {"token": "***REDACTED***"},
        {"token": "***REDACTED***"},
    ]


def test_redact_processor_is_case_insensitive() -> None:
    event = {"SECRET_KEY": "abc", "Cookie": "session=1"}
    result = redact_processor(None, "info", event)
    assert result["SECRET_KEY"] == "***REDACTED***"
    assert result["Cookie"] == "***REDACTED***"


def test_get_logger_returns_a_bound_logger() -> None:
    logger = get_logger(__name__)
    assert hasattr(logger, "info")
    assert hasattr(logger, "bind")


def test_bind_and_clear_context_round_trip() -> None:
    bind_context(request_id="req-1")
    clear_context()


@pytest.mark.parametrize("hunter_env", ["development", "test", "staging", "production"])
def test_configure_logging_does_not_raise(hunter_env: Environment) -> None:
    settings = _settings(hunter_env)
    configure_logging(settings, role="api")
    get_logger(__name__).info("smoke", password="should-not-appear-in-output")


@pytest.mark.parametrize(
    ("hunter_env", "expected"),
    [
        ("development", False),
        ("test", False),
        ("staging", True),
        ("production", True),
    ],
)
def test_is_json_logging_true_for_staging_and_production(
    hunter_env: Environment, expected: bool
) -> None:
    settings = _settings(hunter_env)
    assert is_json_logging(settings) is expected


@pytest.mark.parametrize(
    ("hunter_env", "renderer_type"),
    [
        ("development", structlog.dev.ConsoleRenderer),
        ("test", structlog.dev.ConsoleRenderer),
        ("staging", structlog.processors.JSONRenderer),
        ("production", structlog.processors.JSONRenderer),
    ],
)
def test_configure_logging_selects_renderer_by_env(
    hunter_env: Environment, renderer_type: type
) -> None:
    settings = _settings(hunter_env)
    configure_logging(settings, role="api")
    root_handler = stdlib_logging.getLogger().handlers[0]
    formatter = root_handler.formatter
    assert isinstance(formatter, structlog.stdlib.ProcessorFormatter)
    renderer = formatter.processors[-1]
    assert isinstance(renderer, renderer_type)


# ---- HIGH-1/HIGH-2 (security review T4.62): value-level redaction ---------------------


@pytest.mark.parametrize(
    "key_name", ["api-key", "apikey", "api_key", "token", "key", "secret", "password"]
)
def test_redact_secret_values_processor_masks_event_string(key_name: str) -> None:
    url = f"https://example.invalid/?{key_name}=FAKE1234abcd"
    result = redact_secret_values_processor(None, "info", {"event": f"GET {url}"})
    assert "FAKE1234abcd" not in result["event"]
    assert f"{key_name}=FAKE***" in result["event"]


@pytest.mark.parametrize(
    "key_name", ["api-key", "apikey", "api_key", "token", "key", "secret", "password"]
)
def test_redact_secret_values_processor_masks_exception_string(key_name: str) -> None:
    """``exception`` is already a rendered string by the time this processor
    runs (``format_exc_info`` ran earlier in ``shared_processors``) — a
    keyed URL inside a traceback line must be masked exactly like ``event``."""
    traceback_text = (
        f"Traceback (most recent call last):\n"
        f"httpx.ConnectError: https://example.invalid/?{key_name}=FAKE1234abcd\n"
        f"\nThe above exception was the direct cause of the following exception:\n"
        f"\nExchangeUnavailable: solana rpc failed"
    )
    result = redact_secret_values_processor(None, "info", {"exception": traceback_text})
    assert "FAKE1234abcd" not in result["exception"]
    assert f"{key_name}=FAKE***" in result["exception"]


def test_redact_secret_values_processor_masks_a_nested_dict_value() -> None:
    event = {"context": {"url": FAKE_KEYED_URL}}
    result = redact_secret_values_processor(None, "info", event)
    assert "FAKE1234abcd" not in result["context"]["url"]
    assert "api-key=FAKE***" in result["context"]["url"]


def test_redact_secret_values_processor_leaves_unrelated_text_alone() -> None:
    result = redact_secret_values_processor(None, "info", {"event": "mint graduated"})
    assert result["event"] == "mint graduated"


def test_redact_url_masks_the_keyed_query_value() -> None:
    masked = redact_url(FAKE_KEYED_URL)
    assert "FAKE1234abcd" not in masked
    assert masked == "https://example.invalid/?api-key=FAKE***"


def test_configure_logging_sets_httpx_and_httpcore_loggers_to_warning() -> None:
    settings = _settings("development")
    configure_logging(settings, role="api")
    assert stdlib_logging.getLogger("httpx").getEffectiveLevel() == stdlib_logging.WARNING
    assert stdlib_logging.getLogger("httpcore").getEffectiveLevel() == stdlib_logging.WARNING


def test_httpx_info_record_does_not_pass_the_default_level(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = _settings("development")
    configure_logging(settings, role="api")
    httpx_logger = stdlib_logging.getLogger("httpx")
    with caplog.at_level(stdlib_logging.DEBUG):
        httpx_logger.info(f"HTTP Request: POST {FAKE_KEYED_URL}")
    assert not any(record.name == "httpx" for record in caplog.records)


SYNTH_PASSWORD = "SYNTHETIC-PASSWORD-1234"


def test_a_json_pass_value_is_masked_in_any_string_field() -> None:
    out = redact_secret_values_processor(
        None,  # type: ignore[arg-type]
        "info",
        {"event": 'sent CONNECT {"user":"subscriber","pass":"' + SYNTH_PASSWORD + '","lang":"js"}'},
    )
    assert SYNTH_PASSWORD not in out["event"] and '"user":"subscriber"' in out["event"]


def test_a_python_repr_pass_value_is_masked_too() -> None:
    out = redact_secret_values_processor(
        None,  # type: ignore[arg-type]
        "info",
        {"error": f"bad CONNECT {{'pass': '{SYNTH_PASSWORD}'}}"},
    )
    assert SYNTH_PASSWORD not in out["error"]


def test_redact_url_masks_userinfo_passwords() -> None:
    masked = redact_url(f"wss://subscriber:{SYNTH_PASSWORD}@core.nats.invalid/path")
    assert SYNTH_PASSWORD not in masked and "subscriber" in masked and "core.nats.invalid" in masked


def test_userinfo_masking_leaves_a_plain_url_alone() -> None:
    assert redact_url("https://example.invalid:8080/a?b=c") == "https://example.invalid:8080/a?b=c"


def test_configure_logging_pins_websockets_to_warning_even_at_debug(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """websockets logs every frame at DEBUG (``> TEXT 'CONNECT {...pass...}'``); LOG_LEVEL=DEBUG must not
    turn that on — the NATS credential travels in the first frame we send."""
    monkeypatch.setenv("WEBSOCKETS_MAX_LOG_SIZE", "1000")
    settings = _settings("development").model_copy(update={"log_level": "DEBUG"})
    configure_logging(settings, role="api")
    assert stdlib_logging.getLogger("websockets").getEffectiveLevel() >= stdlib_logging.WARNING
    frame = f'> TEXT \'CONNECT {{"user":"subscriber","pass":"{SYNTH_PASSWORD}"}}\''
    with caplog.at_level(stdlib_logging.DEBUG):
        stdlib_logging.getLogger("websockets.client").debug(frame)
    assert SYNTH_PASSWORD not in caplog.text


@pytest.mark.parametrize("short", ["xy12", "a", "1234"])
def test_short_passwords_are_masked_whole_not_left_clear(short: str) -> None:
    out = redact_secret_values_processor(
        None,  # type: ignore[arg-type]
        "info",
        {"event": f'{{"pass":"{short}"}} and wss://u:{short}@host'},
    )
    assert f'"{short}"' not in out["event"] and f":{short}@" not in out["event"]


def test_a_json_password_with_a_single_quote_inside_is_masked_whole() -> None:
    out = redact_secret_values_processor(
        None,  # type: ignore[arg-type]
        "info",
        {"event": '{"pass":"TEST\'TAIL-SYNTHETIC","user":"u"}'},
    )
    assert "TAIL-SYNTHETIC" not in out["event"] and '"user":"u"' in out["event"]


def test_the_exact_key_pass_is_masked_in_structured_fields() -> None:
    out = redact_processor(
        None, "info", {"pass": SYNTH_PASSWORD, "passed": "yes", "nested": {"pass": "x"}}
    )  # type: ignore[arg-type]
    assert out["pass"] == "***REDACTED***" and out["nested"]["pass"] == "***REDACTED***"
    assert out["passed"] == "yes"  # only the exact key, not every word that starts with it


def test_redacting_a_long_hostile_string_is_linear_not_quadratic() -> None:
    import time

    start = time.perf_counter()
    redact_url("a." * 20_000)
    redact_secret_values_processor(None, "info", {"event": "a." * 20_000})  # type: ignore[arg-type]
    assert time.perf_counter() - start < 1.0  # was 3.6 s for 16 000 characters with the old pattern
