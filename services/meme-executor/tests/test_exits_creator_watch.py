"""T4.2h-b — the real position and the creator's sale **seen on the chain**,
without a database.

The exit loop used to learn of a dump only from ``meme_features_1m.creator_sold``
— the minute tape, which on 12/09/2026 was on average 14 minutes late and cost
22 of the 35 measured paper closes. Since ``0038`` the radar's 15-second watch
stamps ``meme_live_positions.creator_sold_seen_at`` and the loop reads it on its
own 5 s tick. What this file pins down, one case each way:

- either source is enough (the chain-seen sale, or the tape's flag);
- **silence is not a sale**: no stamp and a tape that measured nothing
  (``None``) is not a dump — the position keeps running on its other rules;
- the precedence above the dump does not move: the operator's ``sell_now`` and
  the owner-enabled emergency close still outrank it (``RISK_ENGINE_MEME`` §6),
  so the kill switch is never overtaken by a radar observation;
- a row written **before** ``0038`` reads as "not seen", never as "sold": the
  column defaults to ``None`` on the dataclass, so a restart against an older
  row cannot fabricate an exit.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from hunter_meme_executor.repo_positions import OpenPosition
from hunter_risk_meme import ExitParams, PositionForExit, decide_exit

MINT = "25xPUKHqporrJqzKgdShSuckPPPmTMdyVp5Ue256pump"
ENTRY_AT = datetime(2026, 9, 15, 19, 0, tzinfo=UTC)
SEEN_AT = ENTRY_AT + timedelta(seconds=90)
PARAMS = ExitParams(
    target_multiple=Decimal(3),
    trailing_from_peak_pct=Decimal("0.35"),
    time_stop_s=1800,
)


def _position(**overrides: Any) -> OpenPosition:
    fields: dict[str, Any] = {
        "id": "01994d00-6c1a-7000-8000-000000000101",
        "proposal_id": "01994d00-6c1a-7000-8000-000000000102",
        "mint": MINT,
        "entry_at": ENTRY_AT,
        "tokens": 1_000_000,
        "sol_spent_lamports": 50_000_000,
        "initial_risk_sol": Decimal("0.05"),
        "params": {},
        "mark_sol": Decimal("0.04"),
        "high_water_sol": Decimal("0.06"),
        "exit_intent": None,
        "sell_requested_at": None,
        "sell_requested_by": None,
        "migrated": False,
    }
    fields.update(overrides)
    return OpenPosition(**fields)


def _reason(position: OpenPosition, tape_creator_sold: bool | None, **kwargs: Any) -> str | None:
    """The loop's own call (``exits.manage_position``), with the mark unchanged."""
    return decide_exit(
        PositionForExit(
            position_id=position.id,
            mint=position.mint,
            entry_at=position.entry_at,
            sol_spent=Decimal(position.sol_spent_lamports) / Decimal(1_000_000_000),
            token_amount=max(1, position.tokens),
            peak_mark_sol=position.high_water_sol or Decimal(0),
            migrated=position.migrated,
            curve_complete=False,
        ),
        position.mark_sol,
        ENTRY_AT + timedelta(seconds=120),
        PARAMS,
        sell_now=position.sell_requested_at is not None,
        creator_dump=position.creator_dump_seen(tape_creator_sold),
        **kwargs,
    )


def test_a_sale_seen_on_the_chain_is_a_dump_even_while_the_tape_says_nothing() -> None:
    position = _position(creator_sold_seen_at=SEEN_AT)
    assert position.creator_dump_seen(None) is True
    assert position.creator_dump_seen(False) is True, "the chain saw it; the tape is late"
    assert _reason(position, None) == "creator_dump"


def test_no_stamp_and_a_tape_that_measured_nothing_is_not_a_dump() -> None:
    position = _position()
    assert position.creator_dump_seen(None) is False
    assert position.creator_dump_seen(False) is False
    assert _reason(position, None) is None, "silence is not a sale — the position keeps running"


def test_the_minute_tape_still_fires_the_dump_on_its_own() -> None:
    """The T4.2h path is kept: ``0038`` adds a faster source, it replaces none."""
    position = _position()
    assert position.creator_dump_seen(True) is True
    assert _reason(position, True) == "creator_dump"


def test_the_operator_and_the_emergency_close_still_outrank_a_seen_sale() -> None:
    """§6's precedence: a radar observation never gets ahead of the kill switch."""
    position = _position(creator_sold_seen_at=SEEN_AT, sell_requested_at=SEEN_AT)
    assert _reason(position, None) == "sell_now"
    assert (
        _reason(_position(creator_sold_seen_at=SEEN_AT), None, emergency_auto_close=True)
        == "emergency_auto_close"
    )


def test_a_position_row_written_before_0038_reads_as_not_seen() -> None:
    """A restart against a pre-``0038`` row must not fabricate an exit."""
    assert _position().creator_sold_seen_at is None
    assert _position().creator_dump_seen(None) is False
