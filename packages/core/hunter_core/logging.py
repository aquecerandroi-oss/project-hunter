"""structlog configuration: JSON in prod, pretty console in dev/test.

ARCHITECTURE.md §11: "Logs JSON com request_id, org_id, role, event_id."
SECURITY.md §4: no secret ever reaches a log. The redaction processor below
masks the *value* of any key whose name looks like a secret, recursively,
so a nested payload (e.g. an event envelope) is covered too.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, cast

import structlog

if TYPE_CHECKING:
    from hunter_core.settings import Settings

_REDACT_KEY_RE = re.compile(r"(?i)(secret|token|password|api_key|authorization|cookie)")
_REDACTED = "***REDACTED***"


def _redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        mapping = cast("dict[Any, Any]", value)
        return {key: _redact(str(key), val) for key, val in mapping.items()}
    if isinstance(value, (list, tuple)):
        items = cast("list[Any] | tuple[Any, ...]", value)
        return [_redact_value(item) for item in items]
    return value


def _redact(key: str, value: Any) -> Any:
    if _REDACT_KEY_RE.search(key):
        return _REDACTED
    return _redact_value(value)


def redact_processor(
    logger: structlog.typing.WrappedLogger, method_name: str, event_dict: structlog.typing.EventDict
) -> structlog.typing.EventDict:
    """structlog processor: mask values of keys matching secret/token/password/... ."""
    return {key: _redact(key, value) for key, value in event_dict.items()}


def configure_logging(settings: Settings, role: str) -> None:
    """Configure structlog + stdlib logging for this process.

    JSON renderer in prod (machine-readable, one line per event); a readable
    console renderer otherwise. Every event is bound with ``role``.
    """
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        redact_processor,
    ]
    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if settings.hunter_env == "prod"
        else structlog.dev.ConsoleRenderer()
    )

    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
    )
    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
    )
    root_handler = logging.getLogger().handlers[0]
    root_handler.setFormatter(formatter)

    structlog.contextvars.bind_contextvars(role=role)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """A bound structlog logger for ``name`` (module or component)."""
    return structlog.get_logger(name)


def bind_context(**kv: Any) -> None:
    """Bind key/values (e.g. ``request_id``, ``org_id``) to every subsequent log call."""
    structlog.contextvars.bind_contextvars(**kv)


def clear_context() -> None:
    """Clear all context bound with :func:`bind_context`."""
    structlog.contextvars.clear_contextvars()
