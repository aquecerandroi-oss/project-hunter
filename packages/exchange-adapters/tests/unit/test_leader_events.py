"""Copy-trade pilot (H-037), task 0b: the invariants of the amended leader contract
(docs/design/copiar-carteiras-papel.md section 2.3). Pure, no IO."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from hunter_exchanges.pumpfun.leader_events import (
    LeaderConfirmation,
    LeaderEvent,
    LeaderGap,
    PostReserves,
)

pytestmark = pytest.mark.unit

T0 = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)
NAIVE = datetime(2026, 10, 9, 12, 0, 0)  # noqa: DTZ001 - naive on purpose
BRT = timezone(timedelta(hours=-3))


def event(**kw: object) -> LeaderEvent:
    base: dict[str, object] = {
        "wallet": "W",
        "mint": "M",
        "side": "buy",
        "token_delta_atoms": 5,
        "sol_delta_lamports": -7,
        "position_after_atoms": 5,
        "signature": "S",
        "slot": 10,
        "block_time": None,
        "first_seen_at": T0,
        "fields_complete_at": T0 + timedelta(milliseconds=2),
        "source": "nats",
        "confirmed": False,
    }
    base.update(kw)
    return LeaderEvent(**base)  # type: ignore[arg-type]


def confirmation(**kw: object) -> LeaderConfirmation:
    base: dict[str, object] = {
        "wallet": "W",
        "mint": "M",
        "signature": "S",
        "slot": 10,
        "status": "confirmed",
        "reason": None,
        "confirmed_at": T0 + timedelta(milliseconds=400),
        "block_time": T0 - timedelta(seconds=1),
    }
    base.update(kw)
    return LeaderConfirmation(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- LeaderEvent
def test_a_provisional_event_carries_separate_stamps_and_defaults_are_the_honest_ones() -> None:
    e = event()
    assert (e.server_ts, e.multi_mint, e.kind) == (None, False, "unknown")
    assert e.first_seen_at < e.fields_complete_at and e.block_time is None


@pytest.mark.parametrize("name", ["first_seen_at", "fields_complete_at", "server_ts", "block_time"])
@pytest.mark.parametrize("bad", [NAIVE, T0.astimezone(BRT)])
def test_every_stamp_must_be_utc_aware(name: str, bad: datetime) -> None:
    kw: dict[str, object] = {name: bad}
    if name == "fields_complete_at":
        kw[name] = bad + timedelta(seconds=1) if bad.tzinfo else bad
    with pytest.raises(ValueError, match=name):
        event(**kw)


def test_fields_cannot_be_complete_before_the_first_leg_was_seen() -> None:
    with pytest.raises(ValueError, match="fields_complete_at"):
        event(fields_complete_at=T0 - timedelta(milliseconds=1))
    event(fields_complete_at=T0)  # the same instant is the single-leg case


def test_the_sol_leg_may_be_unknown_but_never_a_float_or_a_guessed_zero() -> None:
    assert event(sol_delta_lamports=None).sol_delta_lamports is None
    with pytest.raises(ValueError, match="sol_delta_lamports"):
        event(sol_delta_lamports=1.5)
    with pytest.raises(ValueError, match="sol_delta_lamports"):
        event(sol_delta_lamports=True)


def test_a_multi_mint_event_has_no_sol_leg_because_it_cannot_be_attributed() -> None:
    assert event(multi_mint=True, sol_delta_lamports=None).multi_mint is True
    with pytest.raises(ValueError, match="multi_mint"):
        event(multi_mint=True, sol_delta_lamports=-7)


def test_kind_is_one_of_the_named_values() -> None:
    for kind in ("unknown", "swap", "transfer"):
        assert event(kind=kind).kind == kind
    with pytest.raises(ValueError, match="kind"):
        event(kind="airdrop")


def test_the_original_side_slot_and_position_invariants_still_hold() -> None:
    with pytest.raises(ValueError, match="buy"):
        event(side="buy", token_delta_atoms=-1)
    with pytest.raises(ValueError, match="sell"):
        event(side="sell", token_delta_atoms=1)
    with pytest.raises(ValueError, match="negative"):
        event(position_after_atoms=-1)
    with pytest.raises(ValueError, match="negative"):
        event(slot=-1)
    with pytest.raises(ValueError, match="atoms"):
        event(token_delta_atoms=1.5)


def test_integers_are_checked_everywhere_and_the_closed_vocabularies_are_closed() -> None:
    with pytest.raises(ValueError, match="position_after_atoms"):
        event(position_after_atoms=1.5)
    with pytest.raises(ValueError, match="slot"):
        event(slot=True)
    with pytest.raises(ValueError, match="side"):
        event(side="hold")
    with pytest.raises(ValueError, match="source"):
        event(source="pumpportal")


def test_observed_at_is_the_deprecated_alias_of_first_seen_at() -> None:
    assert event().observed_at == T0


def test_the_event_is_frozen() -> None:
    with pytest.raises(AttributeError):
        event().confirmed = True  # type: ignore[misc]
    assert replace(event(), confirmed=True).confirmed


# --------------------------------------------------------------------------- LeaderConfirmation
def test_a_confirmed_confirmation_needs_no_reason() -> None:
    c = confirmation()
    assert (c.status, c.reason, c.post_reserves) == ("confirmed", None, None)


@pytest.mark.parametrize("status", ["divergent", "failed_tx", "not_found", "rpc_error"])
def test_every_other_state_must_say_why(status: str) -> None:
    confirmation(status=status, reason="the field that disagreed")
    with pytest.raises(ValueError, match="reason"):
        confirmation(status=status, reason=None)
    with pytest.raises(ValueError, match="reason"):
        confirmation(status=status, reason="")


def test_a_confirmed_state_cannot_carry_a_reason_and_the_status_is_closed() -> None:
    with pytest.raises(ValueError, match="reason"):
        confirmation(status="confirmed", reason="because")
    with pytest.raises(ValueError, match="status"):
        confirmation(status="maybe", reason="x")


@pytest.mark.parametrize("name", ["confirmed_at", "block_time"])
def test_confirmation_stamps_are_utc_aware(name: str) -> None:
    with pytest.raises(ValueError, match=name):
        confirmation(**{name: NAIVE})


def test_confirmed_at_is_local_reception_and_block_time_is_the_chains_and_may_be_absent() -> None:
    assert confirmation(block_time=None).block_time is None


def test_reserves_come_only_with_a_read_transaction() -> None:
    reserves = PostReserves(
        venue="curve", sol_reserves=30, token_reserves=1000, virtual_quote_reserves=None,
        real_sol_reserves=5,
    )  # fmt: skip
    assert confirmation(post_reserves=reserves).post_reserves == reserves
    confirmation(status="divergent", reason="amount", post_reserves=reserves)
    for status in ("failed_tx", "not_found", "rpc_error"):
        with pytest.raises(ValueError, match="post_reserves"):
            confirmation(status=status, reason="x", post_reserves=reserves)


def test_reserves_are_non_negative_integers() -> None:
    with pytest.raises(ValueError, match="reserves"):
        PostReserves("pool", -1, 1, None, None)
    with pytest.raises(ValueError, match="reserves"):
        PostReserves("pool", 1.5, 1, None, None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="venue"):
        PostReserves("amm", 1, 1, None, None)  # type: ignore[arg-type]


def test_the_chains_own_numbers_ride_on_a_divergent_confirmation() -> None:
    c = confirmation(
        status="divergent",
        reason="token_delta",
        chain_token_delta_atoms=9,
        chain_position_after_atoms=9,
    )
    assert (c.chain_token_delta_atoms, c.chain_position_after_atoms) == (9, 9)
    with pytest.raises(ValueError, match="chain_position_after_atoms"):
        confirmation(chain_position_after_atoms=-1)


# --------------------------------------------------------------------------- LeaderGap (unchanged)
def test_the_gap_contract_is_unchanged() -> None:
    LeaderGap(None, T0, None, "x")
    with pytest.raises(ValueError, match="reason"):
        LeaderGap(None, T0, None, "")
    with pytest.raises(ValueError, match="before"):
        LeaderGap(None, T0, T0 - timedelta(seconds=1), "x")


def test_a_signed_virtual_quote_reserve_is_valid_while_the_physical_ones_are_not_negative() -> None:
    """PumpSwap's virtual quote is an i128: negative with a positive effective reserve is legal."""
    ok = PostReserves(
        "pool",
        sol_reserves=100,
        token_reserves=5,
        virtual_quote_reserves=-90,
        real_sol_reserves=None,
    )
    assert ok.virtual_quote_reserves == -90
    with pytest.raises(ValueError, match="sol_reserves"):
        PostReserves("pool", -1, 5, -90, None)
    with pytest.raises(ValueError, match="virtual_quote_reserves"):
        PostReserves("pool", 1, 5, 1.5, None)  # type: ignore[arg-type]
