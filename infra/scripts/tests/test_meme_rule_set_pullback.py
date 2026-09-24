"""T4.91: turning the entry at the pullback on through ``meme_rule_set.py
--set-param`` — one key per call, and the tool refuses any document the Lab
cannot load (T4.64). So ``entry_pullback_pct`` is the switch and the window
goes first: the window alone loads (inert), the percent alone does not; the
percent is a decimal **string** and only a ``15s`` set can wait for a
pullback; ``entry_pullback_pct=null`` turns it off. The exact commands the
T4.91 report prints, against a fake connection — nothing is written anywhere.

No database. Run: ``uv run pytest infra/scripts/tests/test_meme_rule_set_pullback.py -q``
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from typing import Any

import pytest

from .test_meme_rule_set_validate import (
    FakeConn,
    _load,
    _set,
)

pytestmark = pytest.mark.unit

REASON = "T4.91: EXP-M24, entrada no recuo"


async def _set_param(row: dict[str, Any], set_param: str, *, apply: bool) -> tuple[int, str]:
    script = _load("meme_rule_set")
    conn = FakeConn([row])
    result: tuple[int, str] = await script.run(
        conn,
        deprecate=None,
        apply=apply,
        reason=REASON,
        set_param=set_param,
        rule_sets=[f"{row['name']}/{row['version']}"],
    )
    return result


@pytest.mark.parametrize("apply", [False, True])
async def test_the_window_goes_first_and_loads_on_its_own(apply: bool) -> None:
    code, _report = await _set_param(
        _set("paper", "1", clock="15s"), "entry_pullback_window_s=60", apply=apply
    )
    assert code == 0


async def test_the_percent_without_its_window_never_loads() -> None:
    script = _load("meme_rule_set")
    with pytest.raises(script.WouldNotLoad, match="needs entry_pullback_window_s"):
        await _set_param(_set("paper", "1", clock="15s"), 'entry_pullback_pct="3"', apply=False)


@pytest.mark.parametrize("apply", [False, True])
async def test_the_percent_after_the_window_turns_it_on(apply: bool) -> None:
    row = _set("paper", "1", clock="15s", entry_pullback_window_s=60)
    code, _report = await _set_param(row, 'entry_pullback_pct="3"', apply=apply)
    assert code == 0


async def test_a_bare_number_percent_is_refused() -> None:
    script = _load("meme_rule_set")
    row = _set("paper", "1", clock="15s", entry_pullback_window_s=60)
    with pytest.raises(script.WouldNotLoad, match="decimal string"):
        await _set_param(row, "entry_pullback_pct=3", apply=True)


async def test_only_a_fifteen_second_set_can_wait_for_a_pullback() -> None:
    script = _load("meme_rule_set")
    row = _set("paper", "1", entry_pullback_window_s=60)  # the minute clock by default
    with pytest.raises(script.WouldNotLoad, match="15s"):
        await _set_param(row, 'entry_pullback_pct="3"', apply=True)


async def test_null_turns_it_off() -> None:
    row = _set("paper", "1", clock="15s", entry_pullback_window_s=60, entry_pullback_pct="3")
    code, _report = await _set_param(row, "entry_pullback_pct=null", apply=True)
    assert code == 0
