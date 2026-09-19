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

__all__ = ["COMPONENT", "Connection", "Refused", "WouldNotLoad", "load"]

COMPONENT = "meme_rule_set"


class Connection(Protocol):
    async def execute(self, statement: Any, parameters: Any = None, /) -> Any: ...


class Refused(Exception):
    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason


class WouldNotLoad(Exception):
    """T4.64: the params document ``--set-param``/``--validate`` is about to
    write (or already carries) would crash-loop the meme worker —
    ``hunter_meme_worker.lab_models.RuleSetSpec.from_params``, its entry gate
    or its exit rules refuse it. Raised by ``meme_rule_set_validate``, caught
    only by ``meme_rule_set.py``'s own CLI (exit 2, nothing written)."""


def load(rows: Sequence[RuleSetRow], label: str) -> RuleSetRow:
    """The row ``name/version`` names, or ``rule_set_missing``."""
    name, _, version = label.partition("/")
    for row in rows:
        if row.name == name and row.version == version:
            return row
    raise Refused("rule_set_missing", label)
