"""T4.74-4 — ``spot_entries.spot_entries_once`` with fakes only
(``spot_entries_rig.py``): disabled ⇒ not one query; ``refuted``/``cooldown``
⇒ no candidate query; a refused decision ⇒ a refused row and **zero** signer
calls; an approved one ⇒ **exactly one** signature (the real ``spot_leg`` over
the synthetic transaction) and a position with the signal's geometry; a switch
that moves after the admission refuses the admitted row;
``submitted_unconfirmed`` opens no position; a tick that raises is counted,
never propagated."""

from __future__ import annotations

import base64
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest

from hunter_core.domain.enums import KillSwitchState
from hunter_meme_executor import spot_entries
from hunter_meme_executor.spot_config import SpotConfig
from hunter_meme_executor.spot_repo import ClosedStats

from .spot_entries_rig import NOW, UNI_OUT, Store, candidate, entries_rig
from .spot_tx_fixtures import SIGNATURE, TICKET, WIF

pytestmark = pytest.mark.unit


# ---- the flag ---------------------------------------------------------------------
async def test_disabled_makes_no_query_no_quote_no_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = Store(candidates=[candidate()])
    rig = entries_rig(monkeypatch, store, spot=SpotConfig())
    await spot_entries.spot_entries_once(rig.ctx)  # type: ignore[arg-type]
    assert store.queries == [] and store.orders == []
    assert rig.ctx.treasury_client.quote_calls == 0 and rig.signer.log == []
    assert cast(Any, rig.ctx).kill.refreshes == 0


@pytest.mark.parametrize(
    "closed,state",
    [
        (ClosedStats(20, Decimal("-0.01"), Decimal("-0.5"), Decimal("-0.025"), 0, NOW), "refuted"),
        (ClosedStats(5, Decimal("-0.15"), Decimal("-9"), Decimal("-1.8"), 0, NOW), "refuted"),
        (
            ClosedStats(
                4, Decimal("-0.004"), Decimal("-4"), Decimal("-1"), 3, NOW - timedelta(hours=1)
            ),
            "cooldown",
        ),
    ],
)
async def test_a_refuted_or_cooling_lane_never_fetches_a_candidate(
    monkeypatch: pytest.MonkeyPatch, closed: ClosedStats, state: str
) -> None:
    store = Store(closed=closed, candidates=[candidate()])
    rig = entries_rig(monkeypatch, store)
    await spot_entries.spot_entries_once(rig.ctx)  # type: ignore[arg-type]
    stats = cast(Any, rig.ctx).spot
    assert store.queries == ["closed_stats"]
    assert stats.lane.state == state and stats.last_refusal == f"spot1_{state}"
    assert store.orders == [] and rig.signer.log == []


async def test_nineteen_losing_trades_do_not_refute_the_twentieth_does(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = Store(closed=ClosedStats(19, Decimal("-0.01"), Decimal("-1"), Decimal("-0.05"), 0, NOW))
    rig = entries_rig(monkeypatch, store)
    await spot_entries.spot_entries_once(rig.ctx)  # type: ignore[arg-type]
    assert store.queries == ["closed_stats", "candidates"]
    assert cast(Any, rig.ctx).spot.lane.state == "on"


# ---- the decision -----------------------------------------------------------------
async def test_a_refused_decision_writes_a_refused_row_and_never_touches_the_signer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = Store(candidates=[candidate()])
    store.closes["SOLUSDT"] = None  # parity unavailable -> the engine refuses
    rig = entries_rig(monkeypatch, store)
    await spot_entries.spot_entries_once(rig.ctx)  # type: ignore[arg-type]
    assert len(store.orders) == 1
    row = store.orders[0]
    assert row["status"] == "refused" and row["reason"] == "parity_unavailable"
    parity = next(c for c in row["admission"]["checks"] if c["name"] == "parity")
    assert parity["state"] == "unavailable" and parity["message"] == "sol_usd_unavailable"
    assert row["client_order_id"] == "spot:buy:" + row["signal_id"]
    assert row["admission"]["decided_by"] == "executor:spot1_auto"
    assert row["admission"]["profile"] == "spot"
    names = [c["name"] for c in row["admission"]["checks"]]
    assert "parity" in names and "sizing" in names, "every check recorded, sizing included"
    assert row["admission"]["sizing"]["binding_constraint"]
    assert row["admission"]["spot1"]["candles"]["sol_close_time"] is None
    assert row["intent"]["lane"] == "spot" and row["intent"]["max_sol_cost_sol"] == "0.05"
    assert rig.signer.log == [] and rig.ctx.treasury_client.swap_calls == []
    assert store.positions == []
    assert cast(Any, rig.ctx).spot.refused_by_reason == {"parity_unavailable": 1}


async def test_a_blocking_switch_refuses_before_any_quote(monkeypatch: pytest.MonkeyPatch) -> None:
    store = Store(candidates=[candidate()])
    rig = entries_rig(monkeypatch, store)
    cast(Any, rig.ctx).kill.effective = KillSwitchState.TRADING_DISABLED
    await spot_entries.spot_entries_once(rig.ctx)  # type: ignore[arg-type]
    assert [o["reason"] for o in store.orders] == ["kill_switch_blocked"]
    assert rig.ctx.treasury_client.quote_calls == 0 and rig.signer.log == []


async def test_an_approved_decision_signs_exactly_once_and_opens_the_position(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = Store(candidates=[candidate(decimals=None)])
    rig = entries_rig(monkeypatch, store)
    mint_account = base64.b64encode(bytes(44) + bytes([8])).decode()  # decimals at offset 44

    def get_account(mint: str, *, commitment: str) -> Any:
        return SimpleNamespace(data_base64=mint_account)

    rig.ctx.chain.rpc.__dict__["get_account"] = get_account
    await spot_entries.spot_entries_once(rig.ctx)  # type: ignore[arg-type]
    assert store.decimals_written == [8], "read once by RPC, written back to the map"
    assert len(store.orders) == 1 and store.orders[0]["status"] == "admitted"
    assert store.orders[0]["reason"] is None
    assert store.orders[0]["admission"]["approved"] is True
    assert rig.signer.log.count("sign") == 1
    assert rig.db.statuses() == ["simulated", "submitted", "confirmed"]
    assert len(store.positions) == 1
    pos = store.positions[0]
    assert pos["entry_order_id"] == "order-1" and pos["mint"] == WIF
    assert pos["tokens"] == UNI_OUT
    assert pos["sol_spent_lamports"] == TICKET + 5_050, "the signature's delta, rent out"
    assert pos["ata_rent_lamports"] == 2_039_280
    assert pos["initial_risk_sol"] == Decimal("0.05") * Decimal("0.015")
    params = pos["params"]
    assert params["ref"] == "7.5" and params["horizon_s"] == 14_400
    assert Decimal(params["stop_frac"]) == Decimal("0.015")
    assert Decimal(params["target_frac"]) == Decimal("0.0225")
    assert Decimal(params["r_unit_sol"]) == Decimal("0.00075")
    assert params["sol_usd_at_entry"] == "200" and params["bin_usd_at_entry"] == "7.5"
    assert Decimal(params["jup_usd_at_entry"]).quantize(Decimal("0.01")) == Decimal("7.50")
    assert params["entry_sol_per_atom"] == str(
        Decimal(pos["sol_spent_lamports"]) / Decimal(1_000_000_000) / Decimal(UNI_OUT)
    )
    stats = cast(Any, rig.ctx).spot
    assert (stats.signals_seen, stats.admitted, stats.buys_confirmed) == (1, 1, 1)
    assert stats.last_signature == SIGNATURE
    assert cast(Any, rig.ctx).kill.refreshes == 3, (
        "top of tick, after the admission, before signing"
    )
    assert rig.ctx.chain.reads == 2, "the admission's balance and the simulation's pre-state"


async def test_a_switch_that_moves_after_the_admission_refuses_the_admitted_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = Store(candidates=[candidate()])
    rig = entries_rig(monkeypatch, store)
    kill = cast(Any, rig.ctx).kill
    kill.flip_on_refresh, kill.flip_after = KillSwitchState.TRADING_DISABLED, 2
    await spot_entries.spot_entries_once(rig.ctx)  # type: ignore[arg-type]
    assert store.orders[0]["status"] == "admitted"
    assert store.refused_admitted == ["kill_switch_blocked_before_signing"]
    assert rig.signer.log == [] and store.positions == []


async def test_a_buy_left_unconfirmed_opens_no_position(monkeypatch: pytest.MonkeyPatch) -> None:
    store = Store(candidates=[candidate()])
    rig = entries_rig(monkeypatch, store)
    rig.ctx.chain.rpc.statuses = [None]
    await spot_entries.spot_entries_once(rig.ctx)  # type: ignore[arg-type]
    assert rig.signer.log.count("sign") == 1
    assert rig.db.statuses() == ["simulated", "submitted"]
    assert store.positions == []
    stats = cast(Any, rig.ctx).spot
    assert stats.buys_unconfirmed == 1 and stats.buys_confirmed == 0


async def test_a_tick_that_raises_is_counted_never_propagated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = Store(candidates=[candidate()])
    rig = entries_rig(monkeypatch, store)

    async def boom(_s: Any, **kw: Any) -> list[Any]:
        raise RuntimeError("postgres away")

    monkeypatch.setattr(spot_entries, "candidate_signals", boom)
    await spot_entries.spot_entries_once(rig.ctx)  # type: ignore[arg-type]
    assert cast(Any, rig.ctx).spot.tick_failures == 1 and rig.ctx.state.rpc_errors == 1


async def test_a_transient_quote_failure_writes_no_row_so_the_signal_is_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hunter_exchanges.base import ExchangeUnavailable

    store = Store(candidates=[candidate()])
    rig = entries_rig(monkeypatch, store)

    def unavailable(**_k: Any) -> Any:
        raise ExchangeUnavailable("429", exchange="jupiter")

    rig.ctx.treasury_client.__dict__["quote"] = unavailable
    await spot_entries.spot_entries_once(rig.ctx)  # type: ignore[arg-type]
    assert store.orders == [] and rig.signer.log == []
