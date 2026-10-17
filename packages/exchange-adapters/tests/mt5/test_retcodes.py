"""The retcode classification table (contract RISK_ENGINE_B3 §3.6): closed list per action."""

from __future__ import annotations

import pytest

from hunter_exchanges.mt5.constants import Retcode
from hunter_exchanges.mt5.retcodes import CLASSIFICATION, Action, Verdict, classify

pytestmark = pytest.mark.unit

# Copied by hand from the contract's "terminal sem efeito" row (not derived from the code).
NO_EFFECT = {
    "REQUOTE", "REJECT", "CANCEL", "INVALID", "INVALID_VOLUME", "INVALID_PRICE",
    "INVALID_STOPS", "TRADE_DISABLED", "MARKET_CLOSED", "NO_MONEY", "PRICE_CHANGED",
    "PRICE_OFF", "INVALID_EXPIRATION", "INVALID_FILL", "INVALID_ORDER",
    "CLIENT_DISABLES_AT", "SERVER_DISABLES_AT", "LIMIT_ORDERS", "LIMIT_VOLUME",
    "LIMIT_POSITIONS", "LONG_ONLY", "SHORT_ONLY", "CLOSE_ONLY", "POSITION_CLOSED",
    "FROZEN", "TOO_MANY_REQUESTS", "ONLY_REAL", "HEDGE_PROHIBITED", "FIFO_CLOSE",
    "INVALID_CLOSE_VOLUME", "CLOSE_ORDER_EXIST", "REJECT_CANCEL",
}  # fmt: skip
UNCERTAIN = {"TIMEOUT", "CONNECTION", "ERROR", "ORDER_CHANGED", "LOCKED"}
WITH_EFFECT = {"DONE", "DONE_PARTIAL", "PLACED", "NO_CHANGES"}


def test_every_known_retcode_is_in_exactly_one_of_the_contract_rows() -> None:
    names = {r.name for r in Retcode}
    assert names == NO_EFFECT | UNCERTAIN | WITH_EFFECT
    assert not (NO_EFFECT & UNCERTAIN) and not (NO_EFFECT & WITH_EFFECT)


@pytest.mark.parametrize("action", list(Action))
def test_the_table_has_a_class_for_every_action_and_every_known_retcode(action: Action) -> None:
    for code in Retcode:
        assert (action, int(code)) in CLASSIFICATION, (action, code.name)


@pytest.mark.parametrize("action", list(Action))
@pytest.mark.parametrize("name", sorted(NO_EFFECT))
def test_terminal_without_effect_is_rejected_for_every_action(action: Action, name: str) -> None:
    result = classify(action, int(Retcode[name]))
    assert result.verdict is Verdict.REJECTED
    assert result.name == name


@pytest.mark.parametrize("action", list(Action))
@pytest.mark.parametrize("name", sorted(UNCERTAIN))
def test_uncertain_retcodes_are_uncertain_for_every_action(action: Action, name: str) -> None:
    assert classify(action, int(Retcode[name])).verdict is Verdict.UNCERTAIN


def test_entry_terminal_with_effect() -> None:
    assert classify(Action.ENTRY, int(Retcode.DONE)).verdict is Verdict.DONE
    assert classify(Action.ENTRY, int(Retcode.DONE_PARTIAL)).verdict is Verdict.PARTIAL
    assert classify(Action.ENTRY, int(Retcode.PLACED)).verdict is Verdict.PLACED
    assert classify(Action.ENTRY, int(Retcode.NO_CHANGES)).verdict is Verdict.UNCERTAIN


def test_cancel_only_done_is_accepted_and_it_is_not_yet_a_cancellation() -> None:
    assert classify(Action.CANCEL, int(Retcode.DONE)).verdict is Verdict.DONE
    for name in ("DONE_PARTIAL", "PLACED", "NO_CHANGES"):
        assert classify(Action.CANCEL, int(Retcode[name])).verdict is Verdict.UNCERTAIN


def test_sltp_done_and_no_changes_conclude_but_placed_and_partial_do_not() -> None:
    assert classify(Action.SLTP, int(Retcode.DONE)).verdict is Verdict.DONE
    assert classify(Action.SLTP, int(Retcode.NO_CHANGES)).verdict is Verdict.DONE
    assert classify(Action.SLTP, int(Retcode.PLACED)).verdict is Verdict.UNCERTAIN
    assert classify(Action.SLTP, int(Retcode.DONE_PARTIAL)).verdict is Verdict.UNCERTAIN


@pytest.mark.parametrize("action", list(Action))
def test_a_retcode_outside_the_table_is_uncertain_and_named_unknown(action: Action) -> None:
    result = classify(action, 99999)
    assert result.verdict is Verdict.UNCERTAIN
    assert result.name == "UNKNOWN_99999"
    assert result.retcode == 99999


@pytest.mark.parametrize("action", list(Action))
def test_no_result_at_all_is_uncertain(action: Action) -> None:
    result = classify(action, None)
    assert result.verdict is Verdict.UNCERTAIN
    assert result.retcode is None
    assert result.name == "NO_RESULT"
