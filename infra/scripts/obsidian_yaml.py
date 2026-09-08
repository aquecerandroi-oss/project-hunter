"""Two YAML flow-scalar helpers shared by every Obsidian frontmatter renderer
in this task — no PyYAML dependency for a dozen lines of frontmatter.

A JSON string literal is also a valid YAML double-quoted scalar, and
``json.dumps`` of a list of strings is also a valid YAML flow sequence, so
that one function covers both quoting and list-rendering needs.
"""

from __future__ import annotations

import json

__all__ = ["yaml_list", "yaml_scalar"]

_UNSAFE_CHARS = set(":#{}[]&*!|>'\"%@`,")


def yaml_scalar(value: str | None) -> str:
    """Bare when safe, JSON-quoted otherwise; ``""`` for ``None``/empty."""
    if value is None or value == "":
        return '""'
    if _UNSAFE_CHARS.intersection(value) or value != value.strip():
        return json.dumps(value)
    return value


def yaml_list(values: tuple[str, ...] | list[str]) -> str:
    return json.dumps(list(values))
