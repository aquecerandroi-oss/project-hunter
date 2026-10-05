"""T4.8f (Astra, 05/10): the program-identity block is re-read at the **signature boundary**,
exactly like the kill switch — a block that appears while an admitted entry awaits the RPC or the
database must refuse the row before anything is signed. ``signing_block`` is the one decision both
entry paths (``entries.py``, ``launch_entries.py``) now take there."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from hunter_meme_executor.context import ExecutorState
from hunter_meme_executor.signing_gate import signing_block

pytestmark = pytest.mark.unit


def _ctx(*, kill: bool = False, state: ExecutorState | None = None) -> Any:
    return SimpleNamespace(
        kill=SimpleNamespace(blocks_entries=kill, effective=SimpleNamespace(value="LATCHED")),
        state=state or ExecutorState(program_identity_verified=True),
    )


def test_nothing_blocks_a_clean_desk() -> None:
    assert signing_block(_ctx()) is None


def test_the_kill_switch_keeps_its_name_and_its_log_detail() -> None:
    assert signing_block(_ctx(kill=True)) == (
        "kill_switch_blocked_before_signing",
        {"kill_switch": "LATCHED"},
    )


def test_an_upgrade_that_lands_after_admission_refuses_before_signing() -> None:
    state = ExecutorState(program_identity_verified=True)
    assert signing_block(_ctx(state=state)) is None  # the admission passed
    state.program_divergence = "pumpswap last_deploy_slot 9 != 8"  # the tick found it meanwhile
    assert signing_block(_ctx(state=state)) == (
        "program_upgraded_before_signing",
        {"detail": "pumpswap last_deploy_slot 9 != 8"},
    )


def test_an_identity_that_became_unreadable_after_admission_refuses_before_signing() -> None:
    state = ExecutorState(program_identity_verified=True)
    state.program_unreadable = "3 consecutive program identity reads failed"
    reason, detail = signing_block(_ctx(state=state)) or ("", {})
    assert reason == "program_identity_unreadable_before_signing"
    assert "3 consecutive" in detail["detail"]


def test_the_kill_switch_outranks_the_program_block() -> None:
    state = ExecutorState(program_identity_verified=True)
    state.program_divergence = "x"
    block = signing_block(_ctx(kill=True, state=state))
    assert block is not None and block[0] == "kill_switch_blocked_before_signing"


def test_a_state_that_never_verified_the_identity_refuses_before_signing() -> None:
    """Born unverified (exits-only boot): an entry admitted in that state is refused, by name."""
    state = ExecutorState()
    reason, detail = signing_block(_ctx(state=state)) or ("", {})
    assert reason == "program_identity_unverified_before_signing"
    assert "exits-only" in detail["detail"]
