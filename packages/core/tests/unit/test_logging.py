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
)
from hunter_core.settings import Environment, Settings

pytestmark = pytest.mark.unit


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
