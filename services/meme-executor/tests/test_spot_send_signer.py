"""T4.86 (1) — the last local step before the ``spot/1`` lane broadcasts: the
signature. Mirrors what T4.84 closed in the treasury (``test_treasury_send_ambiguous.py``
§ "the signer"): a key rotated or corrupt in flight, and a signature of the
wrong length, are **local** failures — nothing left the process — and must end
as a refusal **by name** over the row, never as an exception climbing to the
loop's generic ``except``.

The hole this file pins: with ``ctx.signer.sign(...)`` outside the ``try``, the
exception reached ``spot_entries._tick``'s ``except Exception`` (which only
counts ``tick_failures``/``rpc_errors``); the ``spot_orders`` row stayed
``simulated`` — never sent, never refused, no named reason — holding its
reservation (a buy's ``pending_spot_markets``, a sell's ``exit_order_id`` on
the position, which parks the stop) until the reconcile's 300 s rescue closed
it as ``abandoned_before_signing``. Five minutes of a held reservation, a
parked protection exit, and the real reason lost (RISK_ENGINE §10: an exit
must not be blocked by an entry-path accident).
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from hunter_meme_executor import spot_entries, spot_exits

from .spot_entries_rig import Store, candidate, entries_rig
from .spot_exits_rig import POSITION_ID, exits_rig, position
from .spot_fakes import buy_rig, run_buy

pytestmark = pytest.mark.unit

STOP_OUT = 49_000_000
"""``test_spot_exits.STOP_OUT``: a mark of 0,049 SOL over 0,05 spent is −1,33 R."""


# ------------------------------------------------------------------- the leg
@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (RuntimeError("key rotated under us"), "signer_failed:RuntimeError"),
        (ValueError("corrupt secret"), "signer_failed:ValueError"),
    ],
    ids=["rotated", "corrupt"],
)
async def test_a_signer_that_raises_refuses_the_row_by_name_and_sends_nothing(
    monkeypatch: pytest.MonkeyPatch, error: Exception, reason: str
) -> None:
    """Fails closed *and* says so: the row ends ``refused`` by name instead of
    sitting ``simulated`` forever with its reservation still held."""
    rig = buy_rig(monkeypatch)
    rig.signer.error = error
    result = await run_buy(rig)
    assert (result.status, result.reason) == ("refused", reason)
    assert rig.db.statuses() == ["simulated", "refused"], "never left ``simulated``"
    assert "send" not in rig.log and rig.ctx.chain.rpc.sent == []
    assert rig.ctx.state.last_signature is None
    assert result.signature is None


async def test_a_signature_of_the_wrong_size_is_refused_before_the_broadcast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``serialize_transaction`` is the last local check (it raises ``ValueError``
    below 64 bytes): a malformed transaction is refused, never sent."""
    rig = buy_rig(monkeypatch)
    rig.signer.signature = bytes(32)
    result = await run_buy(rig)
    assert (result.status, result.reason) == ("refused", "signer_failed:ValueError")
    assert rig.db.statuses() == ["simulated", "refused"]
    assert "send" not in rig.log


# ------------------------------------------------------- the buy's reservation
async def test_the_entries_loop_releases_the_reservation_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The caller's side of the same accident: the tick does not raise, the
    refusal is counted under its own name, and no position is opened."""
    store = Store(candidates=[candidate()])
    rig = entries_rig(monkeypatch, store)
    rig.signer.error = RuntimeError("key rotated under us")
    await spot_entries.spot_entries_once(cast(Any, rig.ctx))
    stats = cast(Any, rig.ctx).spot
    assert rig.db.statuses() == ["simulated", "refused"]
    assert stats.tick_failures == 0, "not an unexplained tick failure any more"
    assert stats.refused_by_reason == {"signer_failed:RuntimeError": 1}
    assert stats.last_refusal == "signer_failed:RuntimeError"
    assert rig.ctx.state.entries_refused == 1
    assert store.positions == [], "no position, and the row is terminal"


# ------------------------------------------------------ the sell's reservation
async def test_a_sell_whose_signer_raises_releases_the_position_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The worst side of the hole: ``set_exit_pending`` pinned the position
    before the leg, so a signer that raised left ``exit_order_id`` set and the
    exits loop never sold that position again."""
    rig = exits_rig(monkeypatch, sol_out=STOP_OUT)
    rig.store.positions = [position()]
    rig.ctx.signer.error = RuntimeError("key rotated under us")
    await spot_exits.spot_exits_once(rig.ctx)
    assert rig.db.statuses() == ["simulated", "refused"]
    assert rig.stats.tick_failures == 0
    cleared = rig.store.pending_cleared
    assert [c["position_id"] for c in cleared] == [POSITION_ID]
    assert cleared[0]["outcome"] == "refused:signer_failed:RuntimeError"
    assert POSITION_ID in rig.stats.exit_backoff_until, "retried after the backoff"
    assert rig.stats.exit_hard_failures[POSITION_ID] == 0, (
        "a signer out of service is not a statement about this trade: it must not spend the "
        "MAX_EXIT_ATTEMPTS budget that blocks a protection exit for good (RISK_ENGINE meme §10)"
    )
    assert rig.stats.exit_transient_streak[POSITION_ID] == 1, "visible as a streak instead"
