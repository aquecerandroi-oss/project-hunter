"""Unit tests for hunter_core.logging."""

import pytest

from hunter_core.logging import (
    bind_context,
    clear_context,
    configure_logging,
    get_logger,
    redact_processor,
)
from hunter_core.settings import Environment, Settings

pytestmark = pytest.mark.unit


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


@pytest.mark.parametrize("hunter_env", ["dev", "prod"])
def test_configure_logging_does_not_raise(hunter_env: Environment) -> None:
    settings = Settings(hunter_env=hunter_env)
    configure_logging(settings, role="api")
    get_logger(__name__).info("smoke", password="should-not-appear-in-output")
