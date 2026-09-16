"""Dependency-free pieces the ``meme_rule_set.py`` family shares (T4.35 split):
the connection protocol, the one exception every act of every sibling module
raises and ``meme_rule_set.py``'s own CLI catches, the audit component name and
the by-label lookup. Kept apart so ``meme_rule_set.py`` and
``meme_rule_set_params.py`` can each import functions from the other's
direction without a straight import cycle — both of them import *this*
module at the top, byte for byte the same object either way.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

    from meme_rule_set import RuleSetRow

__all__ = ["COMPONENT", "Connection", "Refused", "load"]

COMPONENT = "meme_rule_set"


class Connection(Protocol):
    async def execute(self, statement: Any, parameters: Any = None, /) -> Any: ...


class Refused(Exception):
    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason


def load(rows: Sequence[RuleSetRow], label: str) -> RuleSetRow:
    """The row ``name/version`` names, or ``rule_set_missing``."""
    name, _, version = label.partition("/")
    for row in rows:
        if row.name == name and row.version == version:
            return row
    raise Refused("rule_set_missing", label)
