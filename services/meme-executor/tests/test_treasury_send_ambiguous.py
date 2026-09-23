"""T4.84 — the treasury send that neither confirmed nor refused, and the
signer that raises between the simulation and the broadcast.

Two defects the T4.83 audit found in ``treasury_send`` (both already fixed on
the ``spot/1`` lane in T4.73b/T4.74-4):

1. any exception from ``sendTransaction`` marked the row ``failed`` **without
   a signature** — the RPC may have relayed it before the answer was lost, so
   the swap can land while the row says it never happened: it leaves the daily
   USDC ceiling (``usdc_committed_last_24h`` counts ``submitted|confirmed``)
   and leaves the reconcile (which reads ``submitted`` rows with a signature).
   Now the signature is derived locally from the signed bytes and recorded
   **before** the broadcast; only ``SendDisabled`` (nothing ever left the
   process) is ``failed``.
2. ``signer.sign`` sat outside any ``try``: a rotated or corrupt key left the
   row ``simulated`` forever, never sent, never refused, with nothing in
   ``treasury_last_attempt_reason``. Now it is a named refusal.

Fakes only (``treasury_send_rig.py``): no Postgres, no network, no key.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

import pytest

from hunter_core.domain.types import utcnow
from hunter_exchanges.pumpfun.tx_rpc import SendDisabled
from hunter_meme_executor import treasury_db

from .spot_tx_fixtures import table_addresses
from .treasury_send_rig import (
    LOCAL_SIGNATURE,
    MINT_SLOT,
    WSOL,
    confirmed_tx,
    rig,
    run_attempt,
    served,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.unit


def _rig(monkeypatch: pytest.MonkeyPatch) -> Any:
    return rig(monkeypatch, served(table_addresses(256, {MINT_SLOT: WSOL})))


# --------------------------------------------------------- (1) the ambiguous send
@pytest.mark.parametrize(
    "error", [TimeoutError("read timed out"), ConnectionError("connection reset")]
)
async def test_a_send_that_raises_leaves_the_row_submitted_with_its_signature(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    """The RPC accepted the transaction and the answer was lost: the swap may
    be on chain. The row must stay ``submitted`` **with** the signature, so it
    keeps counting against the daily ceiling and the reconcile can settle it."""
    target = _rig(monkeypatch)
    target.ctx.chain.rpc.send_error = error
    await run_attempt(target)
    assert target.statuses == ["quoted", "simulated", "submitted"]
    assert target.signatures == [LOCAL_SIGNATURE]
    assert target.ctx.state.treasury_last_attempt_reason == f"send_unknown:{type(error).__name__}"
    assert target.ctx.state.last_signature == LOCAL_SIGNATURE
    assert target.ctx.state.rpc_errors == 1


async def test_the_signature_is_recorded_before_the_broadcast_and_is_the_local_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Derived from the signed bytes, not from the RPC's answer — that answer
    may never arrive, and the first signature of the transaction *is* its id."""
    target = _rig(monkeypatch)
    seen: list[list[str]] = []

    def send(tx: bytes, *, max_retries: int = 0) -> str:
        seen.append(list(target.statuses))
        target.log.append("send")
        return "5" * 88  # an RPC that answers something else

    monkeypatch.setattr(target.ctx.chain.rpc, "send_transaction", send)
    await run_attempt(target)
    assert seen == [["quoted", "simulated", "submitted"]]
    assert target.signatures == [LOCAL_SIGNATURE]
    assert target.ctx.state.treasury_last_attempt_reason == f"ok:{LOCAL_SIGNATURE}"


async def test_send_disabled_is_the_only_unambiguous_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The client was built without ``allow_send``: nothing was relayed by
    construction, so ``failed`` is a fact, not a guess."""
    target = _rig(monkeypatch)
    target.ctx.chain.rpc.send_error = SendDisabled()
    await run_attempt(target)
    assert target.statuses == ["quoted", "simulated", "submitted", "failed"]
    assert target.ctx.state.treasury_last_attempt_reason == "send_disabled"


# ------------------------------------- (1b) the fill of the immediate confirm
async def test_the_confirmed_fill_is_the_meta_of_this_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Astra, review of this diff: the confirm read the **live** wallet, which
    the spot lane moves. The fill is the fee payer's lamport delta of this
    signature, and ``wallet_sol_after`` follows from it."""
    target = _rig(monkeypatch)
    target.ctx.chain.rpc.tx = confirmed_tx(9_400_000)
    await run_attempt(target)
    assert target.statuses == ["quoted", "simulated", "submitted", "confirmed"]
    assert target.fills == [(Decimal("0.0094"), Decimal("0.6894"))]


@pytest.mark.parametrize("failure", ["not_served", "rpc_error"], ids=["not-served", "rpc-error"])
async def test_a_confirm_whose_fill_cannot_be_read_stays_submitted(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    """The old path fell back to ``wallet_sol_before`` and wrote ``confirmed``
    with a fill of **zero**: the swap's SOL then never reached the daily-loss
    brake (§16.3) and the row left the reconcile for good. Now it stays
    ``submitted`` and the reconcile settles it."""
    target = _rig(monkeypatch)
    if failure == "rpc_error":
        target.ctx.chain.rpc.tx_error = TimeoutError("rpc down")
    else:
        target.ctx.chain.rpc.tx = None
    await run_attempt(target)
    assert target.statuses == ["quoted", "simulated", "submitted"]
    assert target.fills == []
    assert target.ctx.state.treasury_last_attempt_reason == "confirm_fill_unreadable"


async def test_the_daily_ceiling_counts_the_status_an_ambiguous_send_leaves() -> None:
    """The pairing that makes the fix above safe: what the cap counts and what
    the send leaves are the same word, read off the query itself."""
    captured: list[str] = []

    class _Session:
        async def scalar(self, statement: object, params: object = None) -> int:
            captured.append(str(statement))
            return 0

    await treasury_db.usdc_committed_last_24h(cast("AsyncSession", _Session()), now=utcnow())
    assert "'submitted'" in captured[0] and "'confirmed'" in captured[0]


# ------------------------------------------------------------- (2) the signer
@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (RuntimeError("key rotated under us"), "signer_failed:RuntimeError"),
        (ValueError("corrupt secret"), "signer_failed:ValueError"),
    ],
    ids=["rotated", "corrupt"],
)
async def test_a_signer_that_raises_refuses_by_name_and_sends_nothing(
    monkeypatch: pytest.MonkeyPatch, error: Exception, reason: str
) -> None:
    """Fails closed *and* says so: the row ends ``refused`` by name instead of
    sitting ``simulated`` forever with an empty last-attempt field."""
    target = _rig(monkeypatch)
    target.ctx.signer.error = error
    await run_attempt(target)
    assert target.statuses == ["quoted", "simulated", "refused"]
    assert target.ctx.state.treasury_last_attempt_reason == reason
    assert "send" not in target.log
    assert target.ctx.state.last_signature is None


async def test_a_signature_of_the_wrong_size_is_refused_before_the_broadcast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``serialize_transaction`` is the last local check: a 32-byte signature
    would make a malformed transaction, never a sent one."""
    target = _rig(monkeypatch)

    def sign(_message_bytes: bytes) -> bytes:
        return bytes(32)

    monkeypatch.setattr(target.ctx.signer, "sign", sign)
    await run_attempt(target)
    assert target.statuses == ["quoted", "simulated", "refused"]
    assert target.ctx.state.treasury_last_attempt_reason == "signer_failed:ValueError"
    assert "send" not in target.log
