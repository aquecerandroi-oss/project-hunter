"""Retcode classification: a closed list per action (``docs/RISK_ENGINE_B3.md`` §3.6).

A retcode that is not on a *terminal* row **of the action that was sent** is uncertain.
Acceptance is not completion:

* entry: ``DONE`` / ``DONE_PARTIAL`` / ``PLACED`` are terminal with effect — the caller still
  reads the broker to confirm volume and ticket;
* cancel: only ``DONE``, and the caller still needs the order in a final state in the history
  before it may call it cancelled;
* SLTP: only ``DONE`` and ``NO_CHANGES`` conclude. ``PLACED`` and ``DONE_PARTIAL`` do not.

The table is built for **every** ``Retcode`` x ``Action`` pair, so a retcode added to
:class:`~hunter_exchanges.mt5.constants.Retcode` without a class cannot exist; a code the
terminal returns that we do not know is :data:`Verdict.UNCERTAIN` named ``UNKNOWN_<n>`` and logged.
``tests/mt5/test_retcodes.py`` fails if the table and the contract's three rows ever diverge.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import structlog

from .constants import Retcode

log = structlog.get_logger(__name__)


class Action(StrEnum):
    ENTRY = "entry"  # TRADE_ACTION_DEAL or TRADE_ACTION_PENDING
    CANCEL = "cancel"  # TRADE_ACTION_REMOVE
    SLTP = "sltp"  # TRADE_ACTION_SLTP


class Verdict(StrEnum):
    DONE = "done"  # terminal with effect (entry filled / cancel accepted / SLTP applied)
    PARTIAL = "partial"  # entry only: filled in part
    PLACED = "placed"  # entry only: resting in the book
    REJECTED = "rejected"  # terminal without effect
    UNCERTAIN = "uncertain"  # may or may not have taken effect: never resend, resolve


@dataclass(frozen=True)
class Classification:
    verdict: Verdict
    retcode: int | None
    name: str


_R = Retcode
_WITH_EFFECT: dict[Action, dict[Retcode, Verdict]] = {
    Action.ENTRY: {
        _R.DONE: Verdict.DONE,
        _R.DONE_PARTIAL: Verdict.PARTIAL,
        _R.PLACED: Verdict.PLACED,
    },
    Action.CANCEL: {_R.DONE: Verdict.DONE},
    Action.SLTP: {_R.DONE: Verdict.DONE, _R.NO_CHANGES: Verdict.DONE},
}

# Contract row "terminal sem efeito": identical for all three actions.
_NO_EFFECT: frozenset[Retcode] = frozenset(
    {
        _R.REQUOTE, _R.REJECT, _R.CANCEL, _R.INVALID, _R.INVALID_VOLUME, _R.INVALID_PRICE,
        _R.INVALID_STOPS, _R.TRADE_DISABLED, _R.MARKET_CLOSED, _R.NO_MONEY, _R.PRICE_CHANGED,
        _R.PRICE_OFF, _R.INVALID_EXPIRATION, _R.INVALID_FILL, _R.INVALID_ORDER,
        _R.CLIENT_DISABLES_AT, _R.SERVER_DISABLES_AT, _R.LIMIT_ORDERS, _R.LIMIT_VOLUME,
        _R.LIMIT_POSITIONS, _R.LONG_ONLY, _R.SHORT_ONLY, _R.CLOSE_ONLY, _R.POSITION_CLOSED,
        _R.FROZEN, _R.TOO_MANY_REQUESTS, _R.ONLY_REAL, _R.HEDGE_PROHIBITED, _R.FIFO_CLOSE,
        _R.INVALID_CLOSE_VOLUME, _R.CLOSE_ORDER_EXIST, _R.REJECT_CANCEL,
    }
)  # fmt: skip


def _verdict(action: Action, code: Retcode) -> Verdict:
    effect = _WITH_EFFECT[action].get(code)
    if effect is not None:
        return effect
    return Verdict.REJECTED if code in _NO_EFFECT else Verdict.UNCERTAIN


CLASSIFICATION: dict[tuple[Action, int], Verdict] = {
    (action, int(code)): _verdict(action, code) for action in Action for code in Retcode
}


def classify(action: Action, retcode: int | None) -> Classification:
    """Class of ``retcode`` for ``action``. ``None`` (no result object) is uncertain."""
    if retcode is None:
        return Classification(Verdict.UNCERTAIN, None, "NO_RESULT")
    verdict = CLASSIFICATION.get((action, retcode))
    if verdict is None:
        log.warning("mt5_unclassified_retcode", action=action.value, retcode=retcode)
        return Classification(Verdict.UNCERTAIN, retcode, f"UNKNOWN_{retcode}")
    return Classification(verdict, retcode, Retcode(retcode).name)
