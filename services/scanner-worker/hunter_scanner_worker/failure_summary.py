"""A failed cycle in a few hundred bytes, not tens of kilobytes.

``logger.exception`` on a SQLAlchemy ``DBAPIError`` writes the whole statement
and every bound parameter: a 200-market flush is ~60 KB per failure, once every
~10 s, and the Docker log rotated in 30 minutes -- which is what erased the first
error of the 30/09 and the 02/10 stops. What an operator needs is five facts:
what class of error, the database's own sentence, the constraint and key when it
is a violation, and where in *our* code it surfaced.

Nothing here reads the statement or the parameters, and the two fields that can
echo data are allow-listed rather than trimmed (Astra, 05/10): ``detail`` only
survives as the ``Key (columns)=(uuids)`` of a unique violation, and the server's
message only for the SQLSTATE classes whose text never carries a value. A
``DETAIL: Failing row contains (...)`` or an ``invalid input syntax ... "value"``
is replaced by a fixed sentence.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["MESSAGE_LIMIT", "summarize_exception"]

MESSAGE_LIMIT = 240
FRAME_LIMIT = 3
_CHAIN_LIMIT = 6
_SAFE_MESSAGE_CLASSES = ("08", "23", "40", "53", "55", "57")
"""Connection, integrity, rollback/deadlock, resources, object state and operator
intervention (``statement timeout`` is 57014). Their messages name constraints,
tables and states, never a row value; class 22 (data exception) and the rest do."""
_UNIQUE_KEY = re.compile(
    r"^Key \([a-z_]+(?:, [a-z_]+)*\)=\([0-9a-fA-F-]{36}(?:, [0-9a-fA-F-]{36})*\) already exists\.$"
)
_PROJECT_FRAME = re.compile(r"hunter_[a-z_]+[/\\](?P<file>[\w.]+)$")
"""A frame from our packages (``hunter_scanner_worker``, ``hunter_core``...), in
Docker's ``/app/services/...`` and in a checkout alike; ``site-packages`` never
matches because the file there is not under a ``hunter_*`` directory."""


def _qualified(error: BaseException) -> str:
    kind = type(error)
    if kind.__module__ == "builtins":
        return kind.__qualname__
    return f"{kind.__module__}.{kind.__qualname__}"


def _chain(error: BaseException) -> list[BaseException]:
    """``error`` and what it wraps: SQLAlchemy's ``orig``, then ``__cause__``/``__context__``."""
    seen: list[BaseException] = []
    current: BaseException | None = error
    while current is not None and current not in seen and len(seen) < _CHAIN_LIMIT:
        seen.append(current)
        nested = getattr(current, "orig", None)
        current = (
            nested
            if isinstance(nested, BaseException)
            else current.__cause__ or current.__context__
        )
    return seen


def _first_line(text: str) -> str:
    line = text.strip().splitlines()[0] if text.strip() else ""
    return line[:MESSAGE_LIMIT]


def _attribute(chain: list[BaseException], name: str) -> str | None:
    for error in chain:
        value = getattr(error, name, None)
        if isinstance(value, str) and value:
            return value
    return None


def _message(root: BaseException) -> str:
    state = getattr(root, "sqlstate", None)
    if isinstance(state, str) and not state.startswith(_SAFE_MESSAGE_CLASSES):
        return f"database error {state} (message withheld: it can echo a value)"
    sentence = getattr(root, "message", None)
    return _first_line(sentence if isinstance(sentence, str) else str(root))


def _frames(error: BaseException) -> list[str]:
    frames: list[str] = []
    traceback = error.__traceback__
    while traceback is not None:
        code = traceback.tb_frame.f_code
        found = _PROJECT_FRAME.search(code.co_filename)
        if found:
            frames.append(f"{found['file']}:{traceback.tb_lineno} {code.co_name}")
        traceback = traceback.tb_next
    return frames[-FRAME_LIMIT:]


def summarize_exception(error: BaseException) -> dict[str, Any]:
    """The structured fields to log for ``error``; never the SQL, never a parameter."""
    chain = _chain(error)
    root = chain[-1]
    summary: dict[str, Any] = {
        "error_type": _qualified(error),
        "root_type": _qualified(root),
        "message": _message(root),
    }
    constraint = _attribute(chain, "constraint_name")
    if constraint:
        summary["constraint"] = constraint[:MESSAGE_LIMIT]
    detail = _attribute(chain, "detail")
    if detail and _UNIQUE_KEY.match(detail):
        summary["detail"] = detail
    summary["frames"] = _frames(error)
    return summary
