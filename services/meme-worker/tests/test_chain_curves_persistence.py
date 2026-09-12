"""T4.2f against a real Postgres at ``head`` — one file, one container, run alone
(``timeout 590``).

What only a database can prove: the live capture of 13:07:58 UTC goes through
the **real** ``SolanaRpcClient`` (``httpx.MockTransport`` serving the fixture's
bytes for the addresses the client derives), the real decoder and the real
upsert — one ``solana_rpc`` snapshot per SOL curve stamped with the slot's block
time and finality; the denominator with its provenance in ``meme_tokens``
(``global_params`` for a mid-life standard curve, ``observed_virgin`` for a
virgin one, none for a Mayhem coin); the same slot read twice is one row; the
minute folds with a progress for the standard curves and a named reason for
every other; and a restart rebuilds the set from the rows.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from hunter_meme_worker.chain import chain_once
from hunter_meme_worker.config import MemeConfig
from hunter_meme_worker.context import RadarContext, RadarState
from hunter_meme_worker.features import (
    DENOMINATOR_UNKNOWN,
    INSUFFICIENT_COVERAGE,
    UNSUPPORTED_QUOTE,
)
from hunter_meme_worker.fold import fold_minute
from hunter_meme_worker.graduation import GLOBAL_PARAMS, GlobalParamsStore
from hunter_meme_worker.repo import load_tracked
from hunter_meme_worker.sources import SourcesState
from hunter_meme_worker.tracker import MintTracker, TrackedMint
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_exchanges.pumpfun.quote import GlobalParams
from hunter_exchanges.pumpfun.rpc import SolanaRpcClient
from hunter_exchanges.pumpfun.rpc_curves import CURVE_EMPTIED, decode_curve_batch
from hunter_exchanges.pumpfun.rpc_curves import UNSUPPORTED_QUOTE as CHAIN_UNSUPPORTED

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

WORKER = "hunter_worker"
FIXTURES = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "exchange-adapters"
    / "tests"
    / "fixtures"
    / "pumpfun"
)
SLOT = 446436963
BLOCK_TIME = datetime(2026, 9, 12, 13, 7, 47, tzinfo=UTC)
MINUTE = datetime(2026, 9, 12, 13, 8, tzinfo=UTC)
T0 = BLOCK_TIME - timedelta(minutes=5)
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
_SNAPSHOTS = text(
    "SELECT mint, source, slot, commitment, observed_at, received_at, real_token_reserves "
    "FROM meme_curve_snapshots WHERE mint = ANY(:mints) ORDER BY mint"
)
_TOKENS = text(
    "SELECT mint, first_seen_source, initial_real_token_reserves, progress_denominator_source, "
    "mayhem_enabled FROM meme_tokens WHERE mint = ANY(:mints)"
)
_FEATURES = text(
    "SELECT mint, curve_progress_pct, progress_reason, snapshot_source, coverage "
    "FROM meme_features_1m WHERE mint = ANY(:mints) AND end_time = :end_time "
    "AND features_version = :version"
)


def _fixture() -> tuple[dict[str, Any], dict[str, str], dict[str, list[str]]]:
    """Accounts by address, address by mint, and the mints by what the chain says."""
    meta = json.loads((FIXTURES / "t42f_rpc_curves_batch1_addresses.json").read_text())
    raw = json.loads((FIXTURES / "t42f_rpc_curves_batch1_raw.json").read_text())
    by_address: dict[str, Any] = {}
    address_of: dict[str, str] = {}
    mints: list[str] = []
    for (mint, address), account in zip(meta["addresses"], raw["result"]["value"], strict=True):
        by_address[address] = account
        address_of[mint] = address
        mints.append(mint)
    states, refused, _ = decode_curve_batch(
        mints, raw["result"], block_time=BLOCK_TIME, received_at=BLOCK_TIME
    )
    kinds: dict[str, list[str]] = {"mayhem": [], "virgin": [], "midlife": []}
    for mint, state in states.items():
        if state.mayhem_enabled:
            kinds["mayhem"].append(mint)
        elif state.real_sol_reserves == 0:
            kinds["virgin"].append(mint)
        else:
            kinds["midlife"].append(mint)
    for mint, why in refused.items():
        kinds.setdefault(why, []).append(mint)
    return by_address, address_of, kinds


def _transport(by_address: dict[str, Any]) -> httpx.MockTransport:
    times = json.loads((FIXTURES / "t42f_rpc_block_time_raw.json").read_text())

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["method"] == "getBlockTime":
            return httpx.Response(200, json=times[str(body["params"][0])])
        assert body["method"] == "getMultipleAccounts"
        addresses = body["params"][0]
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "context": {"slot": SLOT},
                    "value": [by_address.get(address) for address in addresses],
                },
            },
        )

    return httpx.MockTransport(respond)


class _Params:
    async def get_global_params(self, created_at_ms: int) -> GlobalParams:
        return PARAMS


def _chosen(kinds: dict[str, list[str]]) -> dict[str, str]:
    """Two mid-life standard curves, a Mayhem one, an emptied one, a non-SOL one.
    No virgin curve: none of the 79 SOL curves of the capture had
    ``real_sol_reserves = 0`` — a fresh coin carries its creator's buy."""
    assert kinds["virgin"] == []
    return {
        "midlife_a": kinds["midlife"][0],
        "midlife_b": kinds["midlife"][1],
        "mayhem": kinds["mayhem"][0],
        "emptied": kinds[CURVE_EMPTIED][0],
        "unsupported": kinds[CHAIN_UNSUPPORTED][0],
    }


async def _rows(
    factory: async_sessionmaker[AsyncSession], statement: Any, params: dict[str, Any]
) -> list[dict[str, Any]]:
    async with role_session(factory, db_role=WORKER) as session:
        return [dict(r) for r in (await session.execute(statement, params)).mappings()]


async def test_the_chains_photo_lands_through_the_real_client_decoder_and_upsert(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    by_address, _, kinds = _fixture()
    chosen = _chosen(kinds)
    mints = list(chosen.values())
    tracker = MintTracker(window_minutes=1440, cap=50)
    for mint in mints:
        tracker.observe(TrackedMint(mint=mint, first_seen_at=T0, created_at=T0, creator="C"))
    sources = SourcesState()
    async with httpx.AsyncClient(transport=_transport(by_address)) as http:
        ctx = RadarContext(
            config=MemeConfig(),
            session_factory=db_session_factory,
            tracker=tracker,
            state=RadarState(),
            events=None,  # type: ignore[arg-type]
            curves=None,  # type: ignore[arg-type]
            chain=SolanaRpcClient(http_client=http, rpc_url="https://rpc.test"),
            sources=sources,
            params=GlobalParamsStore(_Params(), refresh_s=3600),
        )
        report = await chain_once(ctx)
        assert report.read == 3 and report.calls == 2 and not report.failed
        assert report.refused == {CURVE_EMPTIED: 1, CHAIN_UNSUPPORTED: 1}
        snapshots = await _rows(db_session_factory, _SNAPSHOTS, {"mints": mints})
        assert {r["mint"] for r in snapshots} == {
            chosen["midlife_a"],
            chosen["midlife_b"],
            chosen["mayhem"],
        }
        for row in snapshots:
            assert row["source"] == "solana_rpc" and row["slot"] == SLOT
            assert row["commitment"] == "finalized" and row["observed_at"] == BLOCK_TIME
            assert row["received_at"] > row["observed_at"], "the block time, not the arrival"
        tokens = {r["mint"]: r for r in await _rows(db_session_factory, _TOKENS, {"mints": mints})}
        for key in ("midlife_a", "midlife_b"):
            assert tokens[chosen[key]]["progress_denominator_source"] == GLOBAL_PARAMS
            assert tokens[chosen[key]]["initial_real_token_reserves"] == Decimal("793100000")
            assert tokens[chosen[key]]["first_seen_source"] == "solana_rpc"
        assert tokens[chosen["mayhem"]]["progress_denominator_source"] is None
        assert tokens[chosen["mayhem"]]["mayhem_enabled"] is True
        assert chosen["emptied"] not in tokens and chosen["unsupported"] not in tokens
        # The same slot again: the same instant from the same source is one row.
        again = await chain_once(ctx)
        assert again.read == 3
        assert len(await _rows(db_session_factory, _SNAPSHOTS, {"mints": mints})) == 3
        # The minute folds from the chain's photo, with its reasons.
        ctx.state.last_folded_minute = MINUTE - timedelta(minutes=1)
        rows = await fold_minute(ctx, MINUTE)
        assert len(rows) == 5
        folded = {
            r["mint"]: r
            for r in await _rows(
                db_session_factory,
                _FEATURES,
                {"mints": mints, "end_time": MINUTE, "version": ctx.config.features_version},
            )
        }
        for key in ("midlife_a", "midlife_b"):
            row = folded[chosen[key]]
            assert row["progress_reason"] is None and row["snapshot_source"] == "solana_rpc"
            reserve = next(s["real_token_reserves"] for s in snapshots if s["mint"] == chosen[key])
            expected = (Decimal(1) - reserve / Decimal("793100000")).quantize(Decimal("0.000001"))
            assert row["curve_progress_pct"] == expected and row["coverage"] == 1
        assert folded[chosen["mayhem"]]["progress_reason"] == DENOMINATOR_UNKNOWN
        assert folded[chosen["emptied"]]["progress_reason"] == INSUFFICIENT_COVERAGE
        assert folded[chosen["unsupported"]]["progress_reason"] == UNSUPPORTED_QUOTE
        fields = sources.heartbeat_fields(MINUTE, tracked=5)
        assert fields["progress_coverage_pct"] == "40.0", "2 of 5 rows carry a progress"
        assert fields["chain_read_mints"] == "3" and fields["chain_tracked_mints"] == "4", (
            "the second cycle no longer asks the chain for the coin not quoted in SOL"
        )


async def test_a_restart_rebuilds_the_set_with_the_chains_denominators(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _, _, kinds = _fixture()
    chosen = _chosen(kinds)
    async with role_session(db_session_factory, db_role=WORKER) as session:
        tracked = {
            t.mint: t for t in await load_tracked(session, cutoff=T0 - timedelta(hours=1), cap=500)
        }
    for key in ("midlife_a", "midlife_b"):
        assert chosen[key] in tracked, "the chain's first photo is the row that survives a restart"
        assert tracked[chosen[key]].initial_real_token_reserves == Decimal("793100000")
    assert chosen["mayhem"] in tracked
    assert tracked[chosen["mayhem"]].initial_real_token_reserves is None
