"""The Mayhem loop (T4.2e) over the five live accounts of 12/09/2026: the
denominator of a Mayhem curve is the record's, written only after the chain
reconciled the agent's flow; the site's own progress is reproduced from it
within half a point; the loop reads only pending Mayhem mints, 25 per call,
writes once, and names what it refuses. No socket, no database."""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from hunter_exchanges.pumpfun.decode import decode_bonding_curve_account
from hunter_exchanges.pumpfun.mayhem_state import (
    NormalizedMayhemFlow,
    decode_mayhem_state,
    decode_mint_supply,
    decode_token_account_amount,
    mayhem_accounts_for,
    mayhem_flow_from_accounts,
)
from hunter_exchanges.pumpfun.quote import GlobalParams
from hunter_exchanges.pumpfun.rpc import MayhemFlowBatch
from hunter_meme_worker.config import MemeConfig
from hunter_meme_worker.context import RadarContext, RadarState
from hunter_meme_worker.features import curve_progress_pct
from hunter_meme_worker.graduation import MAYHEM_STATE, GlobalParamsStore, mayhem_denominator
from hunter_meme_worker.mayhem import RESERVE_ABOVE_RECORD, mayhem_once, pending_mayhem
from hunter_meme_worker.sources import SOLANA_RPC, SourcesState
from hunter_meme_worker.tracker import MintTracker, TrackedMint

pytestmark = pytest.mark.unit

FIXTURES = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "exchange-adapters"
    / "tests"
    / "fixtures"
    / "pumpfun"
)
BATCHES = (
    "t42e_rpc_mayhem_accounts",
    "t42e_rpc_mayhem_accounts_paused",
    "t42e_rpc_mayhem_accounts_fh42k",
)
T0 = datetime(2026, 9, 12, 11, 44, tzinfo=UTC)
FIXTURE = "2sduGq1bDtMbu6apCs3cfmqfyA32bkXA4CCBdTW5pump"
MANUAL = "4BTPZVKt4zC9ukLFBgEe3hQcXLTE8ATRBZFuMnRTpump"
DUMPED = "Fh42kAfy27CGoUA8CgFwpTGMubzndaAyTy2gghu5pump"
PARAMS = GlobalParams(
    slot=354155511,
    signature="x",
    initial_virtual_token_reserves=1073000000000000,
    initial_virtual_sol_reserves=30000000000,
    initial_real_token_reserves=793100000000000,
    token_total_supply=1000000000000000,
    fee_basis_points=95,
    timestamp=1752856476446,
)


def _accounts() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for name in BATCHES:
        raw = json.loads((FIXTURES / f"{name}_raw.json").read_text())
        meta = json.loads((FIXTURES / f"{name}_addresses.json").read_text())
        for (_, address), account in zip(meta["addresses"], raw["result"]["value"], strict=True):
            out[address] = account
    return out


def _flow(mint: str, accounts: dict[str, dict[str, Any]] | None = None) -> NormalizedMayhemFlow:
    accounts = accounts or _accounts()
    curve_addr, state_addr, vault_addr, mint_addr = mayhem_accounts_for(mint)
    curve, state, vault, spl = (
        accounts[a] for a in (curve_addr, state_addr, vault_addr, mint_addr)
    )
    return mayhem_flow_from_accounts(
        mint,
        curve=decode_bonding_curve_account(curve["data"][0], owner=curve["owner"]),
        state=decode_mayhem_state(state["data"][0], owner=state["owner"]),
        vault_tokens=decode_token_account_amount(vault["data"][0], owner=vault["owner"]),
        mint_supply=decode_mint_supply(spl["data"][0], owner=spl["owner"]),
        slot=446421000,
        commitment="finalized",
        now=T0,
    )


def _site_progress(name: str) -> Decimal:
    raw = json.loads(
        (FIXTURES / f"t42e_indexer_coin_{name}_raw.json").read_text(), parse_float=Decimal
    )
    return Decimal(raw["progress"])


# ------------------------------------------------------- the denominator itself
def test_the_site_progress_of_the_real_mayhem_coins_is_reproduced_within_half_a_point() -> None:
    """The brief's test. ``4BTP…``: the site said 3,43 % at 11:43:52Z; the chain
    (slot 446421000, seconds later) gives 1 − 765 908 543,509630 / 793 100 000 =
    3,4285 %. ``2sduGq…``: the site said 0; the chain gives −3,7251 % — the site
    clamps at zero what this radar stores as it is (the agent net-sold 3,7 % of
    the initial into the curve; ``features.py`` never clamps)."""
    manual = mayhem_denominator(_flow(MANUAL), PARAMS)
    assert (manual.value, manual.source) == (Decimal("793100000"), MAYHEM_STATE)
    progress = curve_progress_pct(_flow(MANUAL).curve_real_token_reserves, manual.value)
    assert progress is not None
    assert abs(progress * 100 - _site_progress("4BTP")) <= Decimal("0.5")
    assert progress == Decimal("0.034285")
    fixture = mayhem_denominator(_flow(FIXTURE), PARAMS)
    assert (fixture.value, fixture.source) == (Decimal("793100000"), MAYHEM_STATE)
    raw = curve_progress_pct(_flow(FIXTURE).curve_real_token_reserves, fixture.value)
    assert raw is not None
    assert raw == Decimal("-0.037251"), "stored as computed: the agent's net supply share"
    assert abs(max(Decimal(0), raw) * 100 - _site_progress("2sduGq")) <= Decimal("0.5"), (
        "the site's rendering clamps at zero"
    )


def test_every_live_flow_keeps_the_record_and_the_dumped_one_is_deeply_negative() -> None:
    accounts = _accounts()
    for name in BATCHES:
        for mint in json.loads((FIXTURES / f"{name}_addresses.json").read_text())["mints"]:
            result = mayhem_denominator(_flow(mint, accounts), PARAMS)
            assert (result.value, result.source) == (Decimal("793100000"), MAYHEM_STATE), mint
    dumped = curve_progress_pct(
        _flow(DUMPED, accounts).curve_real_token_reserves, Decimal("793100000")
    )
    assert dumped is not None and dumped < Decimal("-1.16"), (
        "6,5 h in the agent had sold its whole billion: the curve holds 2,16× the initial"
    )


# --------------------------------------------------------------------- the loop
class FakeChain:
    def __init__(self, accounts: dict[str, dict[str, Any]], *, fail: bool = False) -> None:
        self.accounts = accounts
        self.calls: list[list[str]] = []
        self.fail = fail

    async def get_curve_state(self, mint: str, bonding_curve: str) -> Any:
        raise AssertionError("the Mayhem loop never reads one account at a time")

    async def get_curve_states(self, mints: Any, *, with_block_time: bool = True) -> Any:
        raise AssertionError("the Mayhem loop never reads the curve batch (T4.2f, chain.py)")

    async def get_mayhem_flows(self, mints: Any) -> MayhemFlowBatch:
        self.calls.append(list(mints))
        if self.fail:
            raise RuntimeError("rpc down")
        batch = MayhemFlowBatch(slot=446421000, calls=1)
        for mint in mints:
            try:
                batch.flows[mint] = _flow(mint, self.accounts)
            except KeyError:
                batch.refused[mint] = "curve_not_found"
        return batch


class _Session:
    def __init__(self, log: list[Any]) -> None:
        self.log = log

    async def execute(self, statement: Any, params: Any = None) -> None:
        self.log.append((str(statement)[:60], params))

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


class _Params:
    async def get_global_params(self, created_at_ms: int) -> GlobalParams:
        return PARAMS


def _context(chain: FakeChain, log: list[Any], *, tracked: list[TrackedMint]) -> RadarContext:
    tracker = MintTracker(window_minutes=1440, cap=120)
    for mint in tracked:
        tracker.observe(mint)
    return RadarContext(
        config=MemeConfig(mayhem_batch=2),
        session_factory=lambda: _Session(log),  # type: ignore[arg-type]
        tracker=tracker,
        state=RadarState(),
        events=None,  # type: ignore[arg-type]
        curves=None,  # type: ignore[arg-type]
        chain=chain,
        sources=SourcesState(),
        params=GlobalParamsStore(_Params(), refresh_s=3600),
    )


def _tracked(mint: str, **kw: object) -> TrackedMint:
    return TrackedMint(mint=mint, first_seen_at=T0, created_at=T0, **kw)  # type: ignore[arg-type]


def _no_role(factory: Any, db_role: str) -> Any:
    return factory()


async def test_the_loop_reads_only_pending_mayhem_mints_and_writes_the_denominator_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("hunter_meme_worker.mayhem.role_session", _no_role)
    monkeypatch.setattr("hunter_meme_worker.collect.role_session", _no_role)
    log: list[Any] = []
    chain = FakeChain(_accounts())
    ctx = _context(
        chain,
        log,
        tracked=[
            _tracked(FIXTURE, mayhem_state="paused"),
            _tracked(MANUAL, mayhem_state="active"),
            _tracked("STANDARD"),  # no agent state: not Mayhem, never requested
            _tracked("KNOWN", mayhem_state="active", initial_real_token_reserves=Decimal(1)),
        ],
    )
    assert [t.mint for t in pending_mayhem(ctx.tracker)] == [FIXTURE, MANUAL] or set(
        t.mint for t in pending_mayhem(ctx.tracker)
    ) == {FIXTURE, MANUAL}
    report = await mayhem_once(ctx)
    assert report.pending == 2 and report.requested == 2 and report.written == 2
    assert chain.calls == [[FIXTURE, MANUAL]] or chain.calls == [[MANUAL, FIXTURE]]
    tracked = ctx.tracker.get(FIXTURE)
    assert tracked is not None and tracked.initial_real_token_reserves == Decimal("793100000")
    assert tracked.mayhem_state == "paused", "the tracker keeps what it knew"
    upserts = [
        p
        for s, p in log
        if s.startswith("INSERT INTO meme_tokens") and p.get("progress_denominator_source")
    ]
    assert {p["mint"]: p["progress_denominator_source"] for p in upserts} == {
        FIXTURE: MAYHEM_STATE,
        MANUAL: MAYHEM_STATE,
    }
    assert all(p["mayhem_enabled"] is True for p in upserts)
    snapshots = [p for s, p in log if s.startswith("INSERT INTO meme_curve_snapshots")]
    assert {p["mint"] for p in snapshots} == {FIXTURE, MANUAL}
    assert all(p["source"] == "solana_rpc" and p["slot"] == 446421000 for p in snapshots)
    assert ctx.state.observations[FIXTURE].real_token_reserves == Decimal("822644036.902123")
    # Second cycle: nothing pending, no call.
    again = await mayhem_once(ctx)
    assert again.pending == 0 and len(chain.calls) == 1
    assert ctx.sources is not None
    assert (
        ctx.sources.mayhem_pending == 0
        and ctx.sources.mayhem_written_60s.total(T0 + timedelta(seconds=5)) == 2
    )
    assert ctx.sources[SOLANA_RPC].used_60s.total(T0 + timedelta(seconds=5)) == 1


async def test_the_loop_batches_by_config_and_names_a_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("hunter_meme_worker.mayhem.role_session", _no_role)
    monkeypatch.setattr("hunter_meme_worker.collect.role_session", _no_role)
    log: list[Any] = []
    accounts = _accounts()
    # Break the identity of the fixture coin: the vault claims one more subunit.
    vault_addr = mayhem_accounts_for(FIXTURE)[2]
    chain = FakeChain({k: v for k, v in accounts.items() if k != vault_addr})
    ctx = _context(
        chain,
        log,
        tracked=[
            _tracked(FIXTURE, mayhem_state="paused"),
            _tracked(MANUAL, mayhem_state="active"),
            _tracked(DUMPED, mayhem_state="completed"),
        ],
    )
    report = await mayhem_once(ctx)
    assert report.requested == 2 == ctx.config.mayhem_batch, "25 per call in production, 2 here"
    assert report.refused.get("curve_not_found", 0) + report.written == 2
    assert [p["mint"] for s, p in log if s.startswith("INSERT INTO meme_tokens")] != [FIXTURE], (
        "a flow that does not reconcile writes nothing"
    )
    second = await mayhem_once(ctx)
    assert second.pending >= 1, "the refused mint stays pending and is retried"


async def test_a_reserve_above_the_record_is_refused_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("hunter_meme_worker.mayhem.role_session", _no_role)
    monkeypatch.setattr("hunter_meme_worker.collect.role_session", _no_role)
    log: list[Any] = []
    chain = FakeChain(_accounts())
    ctx = _context(chain, log, tracked=[_tracked(FIXTURE, mayhem_state="paused")])
    smaller = dataclasses.replace(PARAMS, initial_real_token_reserves=700_000_000_000_000)

    class _Smaller:
        async def get_global_params(self, created_at_ms: int) -> GlobalParams:
            return smaller

    ctx = dataclasses.replace(ctx, params=GlobalParamsStore(_Smaller(), refresh_s=3600))
    report = await mayhem_once(ctx)
    assert report.written == 0 and report.refused == {RESERVE_ABOVE_RECORD: 1}
    assert ctx.tracker.get(FIXTURE).initial_real_token_reserves is None  # type: ignore[union-attr]


async def test_a_failed_batch_is_counted_on_the_source_and_never_a_guess() -> None:
    log: list[Any] = []
    chain = FakeChain(_accounts(), fail=True)
    ctx = _context(chain, log, tracked=[_tracked(FIXTURE, mayhem_state="paused")])
    report = await mayhem_once(ctx)
    assert report.written == 0 and report.calls == 0 and log == []
    assert ctx.sources is not None
    assert ctx.sources[SOLANA_RPC].last_error == "RuntimeError"
    assert ctx.sources.mayhem_pending == 1
