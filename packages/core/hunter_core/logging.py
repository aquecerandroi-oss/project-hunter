"""structlog configuration: JSON in staging/production, pretty console in dev/test.

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


# HIGH-1 (security review T4.62): the processor above only looks at *key
# names* — a value that merely *contains* ``...?api-key=SECRET`` inside an
# arbitrary string (``event``, ``exception`` after ``format_exc_info``,
# ``error``, a URL embedded in either) sails through untouched. This second,
# value-level pass scans every string field recursively for a small set of
# ``name=value`` secret markers and masks the *value* only, keeping the first
# four characters so a masked log line is still useful for correlation
# (``FAKE1234abcd`` -> ``FAKE***``). It must run last in the processor chain,
# after ``format_exc_info`` has already rendered ``exception`` into a string
# (docstring of :func:`configure_logging`).
_SECRET_VALUE_RE = re.compile(r"(?i)\b(api[-_]?key|token|key|secret|password)=([^\s&\"'<>]+)")


def _mask_secret_value(value: str) -> str:
    return value if len(value) <= 4 else f"{value[:4]}***"


def _redact_secret_string(text: str) -> str:
    return _SECRET_VALUE_RE.sub(lambda m: f"{m.group(1)}={_mask_secret_value(m.group(2))}", text)


def _redact_secret_values_deep(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_secret_string(value)
    if isinstance(value, dict):
        mapping = cast("dict[Any, Any]", value)
        return {key: _redact_secret_values_deep(val) for key, val in mapping.items()}
    if isinstance(value, (list, tuple)):
        items = cast("list[Any] | tuple[Any, ...]", value)
        return [_redact_secret_values_deep(item) for item in items]
    return value


def redact_secret_values_processor(
    logger: structlog.typing.WrappedLogger, method_name: str, event_dict: structlog.typing.EventDict
) -> structlog.typing.EventDict:
    """structlog processor: mask ``name=value`` secret markers found inside
    any string field (recursively) — ``event``, ``exception``, ``error``, or
    a nested dict/list. Complements :func:`redact_processor`'s key-based
    masking; must be the last processor in ``shared_processors`` (HIGH-1)."""
    return {key: _redact_secret_values_deep(value) for key, value in event_dict.items()}


def redact_url(url: str) -> str:
    """Mask secret-looking query values (``api-key=``, ``token=``, ...) in a
    URL string before an adapter logs it directly (e.g. ``error=str(exc)``
    where ``exc`` is a ``websockets`` connect failure whose message embeds the
    keyed URI) — the same masking :func:`redact_secret_values_processor`
    applies to every log field, exposed standalone for call sites that build
    their own message text outside the logging pipeline."""
    return _redact_secret_string(url)


def is_json_logging(settings: Settings) -> bool:
    """``True`` when logs should render as JSON (``staging`` and ``production``)."""
    return settings.hunter_env in ("staging", "production")


def configure_logging(settings: Settings, role: str) -> None:
    """Configure structlog + stdlib logging for this process.

    JSON renderer in staging/production (machine-readable, one line per
    event); a readable console renderer otherwise. Every event is bound with
    ``role``.
    """
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        redact_processor,
        redact_secret_values_processor,
    ]
    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if is_json_logging(settings)
        else structlog.dev.ConsoleRenderer()
    )

    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
    )
    # HIGH-2: the stdlib default level (INFO) makes httpx/httpcore's own
    # ``HTTP Request: POST https://...?api-key=...`` line print at every
    # request; those two loggers are noise below WARNING regardless of
    # ``LOG_LEVEL``, and it's also the URL leak's only route into stdlib
    # logging (the shared ``redact_secret_values_processor`` above catches it
    # too, but there's no reason to compute the line at all).
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
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
