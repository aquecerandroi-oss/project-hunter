"""KB-0165 — every builder of the decision wallet feeds §3.2's check 17 from
the holdings verdict (fakes only). Two lanes here (launch, ``spot/1``); the
desk's ``entries.py`` is proven end to end on Postgres
(``test_wallet_holdings_integration.py``).

For each lane: a foreign mint refuses ``wallet_unrecognized_holdings`` by name
with the mint in the check and nothing signed; no verdict **defers** (no row,
nothing signed — §8.2); a clean verdict approves as before and the admission
records the verdict it decided on."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest

import hunter_meme_executor.launch_entries as le
from hunter_meme_executor import spot_entries
from hunter_meme_executor.admission import wallet_from
from hunter_meme_executor.chain import WalletRead
from hunter_meme_executor.kill_switch import DayAnchor
from hunter_meme_executor.wallet_holdings import HoldingsVerdict
from hunter_risk_meme import MEME_PAPER_V0

from .spot_entries_rig import NOW, Store, candidate, entries_rig
from .test_launch_entries import Db, FakeContext, FakeSubmitter, _config, _fresh_candidate, _wire

pytestmark = pytest.mark.unit

FOREIGN = "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn"


def _foreign(at: datetime) -> HoldingsVerdict:
    return HoldingsVerdict((FOREIGN,), 3, (9, 9), at)


def _pinned(monkeypatch: pytest.MonkeyPatch) -> Any:
    """A launch candidate whose age is 0.6 s by construction (Astra, F5 review): the
    lane refuses ``launch_proposal_stale`` past 5 s of **its** clock, so a paused
    runner must never turn a clean-wallet test into a staleness refusal."""
    fresh = _fresh_candidate()
    now = fresh.candidate.proposed_at + timedelta(seconds=0.6)
    monkeypatch.setattr(le, "utcnow", lambda: now)
    return fresh


def _wallet_cap(admission: dict[str, Any]) -> dict[str, Any]:
    return next(c for c in admission["checks"] if c["name"] == "wallet_cap")


# ---- launch lane ----------------------------------------------------------------------
async def test_launch_a_foreign_mint_refuses_by_name_and_signs_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, submitter = Db(candidates=[_pinned(monkeypatch)]), FakeSubmitter()
    db.holdings = _foreign(le.utcnow())
    _wire(monkeypatch, db, submitter)
    ctx = FakeContext(config=_config())
    await le.launch_entries_once(ctx)  # type: ignore[arg-type]
    assert len(db.orders) == 1 and db.orders[0]["status"] == "refused"
    assert db.orders[0]["reason"] == "wallet_unrecognized_holdings"
    check = _wallet_cap(db.orders[0]["admission"])
    assert check["state"] == "failed" and FOREIGN in check["message"]
    assert db.orders[0]["admission"]["wallet_holdings"]["unrecognized"] == [FOREIGN]
    assert submitter.calls == [] and db.positions == []


async def test_launch_without_a_verdict_defers_writes_nothing_signs_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, submitter = Db(candidates=[_pinned(monkeypatch)]), FakeSubmitter()
    db.holdings = None
    _wire(monkeypatch, db, submitter)
    ctx = FakeContext(config=_config())
    await le.launch_entries_once(ctx)  # type: ignore[arg-type]
    assert db.orders == [] and db.claims == [] and submitter.calls == []


async def test_launch_a_clean_wallet_approves_and_records_the_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, submitter = Db(candidates=[_pinned(monkeypatch)]), FakeSubmitter()
    _wire(monkeypatch, db, submitter)
    ctx = FakeContext(config=_config())
    await le.launch_entries_once(ctx)  # type: ignore[arg-type]
    assert len(db.orders) == 1 and db.orders[0]["status"] == "admitted"
    admission = db.orders[0]["admission"]
    assert _wallet_cap(admission)["state"] == "passed"
    assert admission["wallet_holdings"]["unrecognized_count"] == 0
    assert len(submitter.calls) == 1


# ---- spot/1 ---------------------------------------------------------------------------
async def test_spot_a_foreign_mint_refuses_by_name_and_signs_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = Store(candidates=[candidate()])
    store.holdings = _foreign(NOW)
    rig = entries_rig(monkeypatch, store)
    await spot_entries.spot_entries_once(rig.ctx)  # type: ignore[arg-type]
    assert len(store.orders) == 1
    row = store.orders[0]
    assert row["status"] == "refused" and row["reason"] == "wallet_unrecognized_holdings"
    assert FOREIGN in _wallet_cap(row["admission"])["message"]
    assert row["admission"]["wallet_holdings"]["unrecognized"] == [FOREIGN]
    assert rig.signer.log == [] and store.positions == []


async def test_spot_without_a_verdict_defers_writes_nothing_signs_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = Store(candidates=[candidate()])
    store.holdings = None
    rig = entries_rig(monkeypatch, store)
    await spot_entries.spot_entries_once(rig.ctx)  # type: ignore[arg-type]
    assert store.orders == [] and rig.signer.log == [] and store.positions == []
    assert cast(Any, rig.ctx).spot.tick_failures == 0, "a deferral, not a crashed tick"


async def test_spot_a_clean_wallet_approves_and_records_the_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = Store(candidates=[candidate()])
    rig = entries_rig(monkeypatch, store)
    await spot_entries.spot_entries_once(rig.ctx)  # type: ignore[arg-type]
    assert len(store.orders) == 1 and store.orders[0]["status"] == "admitted"
    admission = store.orders[0]["admission"]
    assert _wallet_cap(admission)["state"] == "passed"
    assert admission["wallet_holdings"]["unrecognized_count"] == 0
    assert cast(Any, rig.signer).log.count("sign") == 1


# ---- guardian F4: no builder can forget the input ------------------------------------
def test_the_decision_wallet_cannot_be_built_without_the_holdings_verdict() -> None:
    """A default of ``()`` is how check 17 stayed dead for every lane (KB-0165): a
    fourth builder that forgot the argument would have compiled and read "clean"."""
    param = inspect.signature(wallet_from).parameters["unrecognized"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY
    assert param.default is inspect.Parameter.empty
    now = datetime(2026, 9, 28, tzinfo=UTC)
    with pytest.raises(TypeError, match="unrecognized"):
        wallet_from(  # pyright: ignore[reportCallIssue] - the omission under test
            wallet_id="wallet",
            now=now,
            balance=WalletRead(pubkey="wallet", lamports=300_000_000, slot=1, observed_at=now),
            positions=[],
            pending=[],
            anchor=DayAnchor(now, Decimal("0.3"), Decimal("0.3"), now),
            limits=MEME_PAPER_V0,
        )
