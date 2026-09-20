"""``spot_desk_markets.py --close-manual`` (T4.74-7, A1): closing a
``spot_positions`` row that was sold outside the lane (``meme_spot_swap.py``,
another DEX), audited. Against a fake connection and a fake RPC: the sell
transaction's own meta fills ``sol_received_lamports``/``pnl_sol``; a token
delta that is not the position's whole lot refuses; dry-run writes nothing;
``--apply`` inserts the ``spot_orders`` sell row (one signature per row),
closes the position and leaves one ``system_events`` row.

Run: ``uv run pytest infra/scripts/tests/test_spot_desk_close_manual.py -q``
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import UUID

import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
WALLET = "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"
OTHER = "9yLYuh3DX98e08UYKTEqcE6kCljfUrB94UASvKptxBtV"
MINT = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"
SIG = "5VERv8NMvzbJMEkV8xnrLkEaWRtSz9CosKDYjCJjBRnbJLgp8uirBgmQpjKhoR4tjF3ZpRzrFmBV6UjKdiSZkQUW"
ENTRY_AT = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
BLOCK_TIME = int((ENTRY_AT + timedelta(hours=2)).timestamp())
TOKENS = 660_000_000
SPENT = 50_000_000
REASON = "vendida na mão pelo meme_spot_swap.py, Jupiter sem rota na pista"


def _load(name: str) -> ModuleType:
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(
        f"hunter_infra_{name}_cm", SCRIPTS_DIR / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def tx(
    *,
    token_pre: int = TOKENS,
    token_post: int = 0,
    sol_delta: int = 48_900_000,
    payer: str = WALLET,
    block_time: int | None = BLOCK_TIME,
    err: Any = None,
) -> dict[str, Any]:
    def entry(amount: int) -> dict[str, Any]:
        return {
            "accountIndex": 4,
            "mint": MINT,
            "owner": WALLET,
            "uiTokenAmount": {"amount": str(amount), "decimals": 6},
        }

    out: dict[str, Any] = {
        "slot": 1,
        "transaction": {"message": {"accountKeys": [payer, OTHER], "instructions": []}},
        "meta": {
            "err": err,
            "fee": 5_000,
            "preBalances": [400_000_000, 0],
            "postBalances": [400_000_000 + sol_delta, 0],
            "preTokenBalances": [entry(token_pre)],
            "postTokenBalances": [entry(token_post)],
        },
    }
    if block_time is not None:
        out["blockTime"] = block_time
    return out


class _Result:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> list[dict[str, Any]]:
        return self._rows

    def scalars(self) -> _Result:
        return self

    def scalar(self) -> Any:
        return next(iter(self._rows[0].values())) if self._rows else None

    def all(self) -> list[Any]:
        return [next(iter(r.values())) for r in self._rows]


def _position(**over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": "pos-1",
        "status": "open",
        "signal_id": "sig-1",
        "market_symbol": "WIFUSDT",
        "mint": MINT,
        "tokens": TOKENS,
        "sol_spent_lamports": SPENT,
        "initial_risk_sol": Decimal("0.00075"),
        "entry_at": ENTRY_AT,
        "exit_intent": None,
        "exit_order_id": None,
        "entry_wallet": WALLET,
    }
    row.update(over)
    return row


class Conn:
    def __init__(
        self, positions: list[dict[str, Any]], known_signatures: tuple[str, ...] = ()
    ) -> None:
        self.positions = {p["id"]: dict(p) for p in positions}
        self.known = set(known_signatures)
        self.orders: list[dict[str, Any]] = []
        self.statements: list[tuple[str, Any]] = []

    async def execute(self, statement: Any, parameters: Any = None, /) -> _Result:
        sql = str(statement)
        self.statements.append((sql, parameters))
        params: dict[str, Any] = dict(parameters or {})
        if sql.startswith("SELECT") and "FROM spot_positions p" in sql:
            assert "FOR UPDATE OF p" in sql, "the row is locked against the executor"
            row = self.positions.get(params["id"])
            return _Result([row] if row else [])
        if sql.startswith("SELECT id FROM spot_orders WHERE tx_signature"):
            return _Result([{"id": "o-x"}] if params["signature"] in self.known else [])
        if sql.startswith("SELECT coalesce(max(attempt)"):
            return _Result([{"n": 3}])
        if sql.startswith("INSERT INTO spot_orders"):
            self.orders.append(dict(params))
            return _Result([{"id": "order-manual"}])
        if sql.startswith("UPDATE spot_positions SET status = 'closed'"):
            assert "exit_order_id IS NULL" in sql, "a sell in flight blocks the close atomically"
            row = self.positions.get(params["id"])
            if row is None or row["status"] != "open" or row.get("exit_order_id") is not None:
                return _Result([])
            row.update({k: v for k, v in params.items() if k != "id"}, status="closed")
            return _Result([{"id": params["id"]}])
        return _Result([])

    def writes(self) -> list[str]:
        return [s for s, _ in self.statements if not s.lstrip().startswith("SELECT")]


class Rpc:
    def __init__(self, reply: dict[str, Any] | None) -> None:
        self.reply = reply
        self.calls: list[str] = []

    def get_transaction(self, signature: str, *, commitment: str = "confirmed") -> Any:
        self.calls.append(signature)
        return self.reply


async def _run(conn: Conn, rpc: Rpc, **kw: Any) -> tuple[int, str]:
    script = _load("spot_desk_markets")
    base: dict[str, Any] = {
        "close_manual": "pos-1",
        "tx": SIG,
        "wallet": WALLET,
        "reason": REASON,
        "rpc": rpc,
    }
    base.update(kw)
    return await script.run(conn, **base)


# ---------------------------------------------------------------- the numbers
def test_the_numbers_come_from_the_transaction_meta_at_the_lamport() -> None:
    close = _load("spot_desk_markets_close")
    plan = close.check_manual_close(_position(), tx(), wallet=WALLET, signature=SIG)
    assert plan.sol_received_lamports == 48_900_000
    assert plan.pnl_sol == Decimal("-0.0011")
    assert plan.r_multiple == Decimal("-0.0011") / Decimal("0.00075")
    assert plan.exit_at == ENTRY_AT + timedelta(hours=2)
    assert "48900000" in plan.describe() and "-0.0011" in plan.describe()


@pytest.mark.parametrize(
    "transaction,refusal",
    [
        (None, "tx_not_found"),
        (tx(err={"InstructionError": [3, "Custom"]}), "tx_unreadable"),
        (tx(payer=OTHER), "tx_unreadable"),
        (tx(token_post=1), "token_delta_mismatch"),
        (tx(token_pre=TOKENS + 5), "token_delta_mismatch"),
        (tx(sol_delta=-5_000), "sol_delta_not_positive"),
        (tx(block_time=None), "tx_without_block_time"),
        (tx(block_time=int(ENTRY_AT.timestamp())), "tx_before_entry"),
    ],
)
def test_a_transaction_that_is_not_this_whole_lot_sold_for_sol_refuses(
    transaction: dict[str, Any] | None, refusal: str
) -> None:
    close = _load("spot_desk_markets_close")
    with pytest.raises(close.Refused, match=refusal):
        close.check_manual_close(_position(), transaction, wallet=WALLET, signature=SIG)


# ------------------------------------------------------------------ the act
async def test_dry_run_reads_the_transaction_and_writes_nothing() -> None:
    conn, rpc = Conn([_position()]), Rpc(tx())
    code, report = await _run(conn, rpc)
    assert code == 0 and "dry-run" in report and conn.writes() == []
    assert rpc.calls == [SIG] and "pnl_sol=-0.0011" in report


async def test_apply_inserts_the_sell_row_closes_the_position_and_audits() -> None:
    conn, rpc = Conn([_position()]), Rpc(tx())
    code, report = await _run(conn, rpc, apply=True, actor="Everton")
    assert code == 0 and "applied" in report
    [order] = conn.orders
    assert order["tx_signature"] == SIG and order["status"] == "confirmed"
    assert UUID(order["id"]).version == 7, "spot_orders.id has no default: the script mints it"
    assert order["client_order_id"] == "spot:sell:pos-1:manual" and order["attempt"] == 3
    assert order["position_id"] == "pos-1" and order["side"] == "sell"
    assert '"filled_atoms": 48900000' in order["fill"]
    row = conn.positions["pos-1"]
    assert row["status"] == "closed" and row["order_id"] == "order-manual"
    assert row["received"] == 48_900_000 and row["pnl"] == Decimal("-0.0011")
    assert '"reason": "manual_close"' in row["exit"] and SIG in row["exit"]
    _, audit = next(s for s in conn.statements if "system_events" in s[0])
    assert audit["event"] == "closed_manually" and "pos-1" in audit["message"]
    assert audit["component"] == "spot_desk"


async def test_a_signature_the_lane_already_recorded_refuses_before_the_rpc() -> None:
    conn, rpc = Conn([_position()], known_signatures=(SIG,)), Rpc(tx())
    script = _load("spot_desk_markets")
    with pytest.raises(script.Refused, match="signature_already_recorded"):
        await _run(conn, rpc, apply=True)
    assert rpc.calls == [] and conn.writes() == []


@pytest.mark.parametrize(
    "position,refusal",
    [
        (None, "position_missing"),
        (_position(status="closed"), "position_not_open"),
        (_position(exit_intent={"status": "submitted_unconfirmed"}), "exit_pending"),
        (_position(exit_order_id="o-9"), "exit_pending"),
        (_position(entry_wallet=OTHER), "wallet_mismatch"),
        (_position(entry_wallet=None), "entry_wallet_unknown"),
    ],
)
async def test_a_position_the_lane_still_owns_refuses(
    position: dict[str, Any] | None, refusal: str
) -> None:
    conn, rpc = Conn([] if position is None else [position]), Rpc(tx())
    script = _load("spot_desk_markets")
    with pytest.raises(script.Refused, match=refusal):
        await _run(conn, rpc, apply=True)
    assert conn.writes() == [] and rpc.calls == []


async def test_a_mismatching_transaction_refuses_with_nothing_written() -> None:
    conn, rpc = Conn([_position()]), Rpc(tx(token_post=10))
    script = _load("spot_desk_markets")
    with pytest.raises(script.Refused, match="token_delta_mismatch"):
        await _run(conn, rpc, apply=True)
    assert conn.writes() == []


async def test_close_manual_needs_a_reason_like_every_write() -> None:
    conn, rpc = Conn([_position()]), Rpc(tx())
    script = _load("spot_desk_markets")
    with pytest.raises(script.Refused, match="reason_required"):
        await _run(conn, rpc, apply=True, reason="curto")
    assert conn.writes() == [] and rpc.calls == []


def test_parse_args_requires_tx_and_wallet_with_close_manual() -> None:
    script = _load("spot_desk_markets")
    with pytest.raises(SystemExit):
        script.parse_args(["--close-manual", "pos-1", "--reason", REASON])
    with pytest.raises(SystemExit):
        script.parse_args(["--close-manual", "pos-1", "--tx", SIG, "--reason", REASON])
    args = script.parse_args(
        ["--close-manual", "pos-1", "--tx", SIG, "--wallet", WALLET, "--reason", REASON]
    )
    assert args.close_manual == "pos-1" and args.tx == SIG and not args.apply
    with pytest.raises(SystemExit):
        script.parse_args(["--close-manual", "pos-1", "--sell-now", "pos-1", "--reason", REASON])


# ------------------------------------------------ Astra (T4.74-7 review) #4
class _Begin:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    async def __aenter__(self) -> None:
        self.log.append("begin")

    async def __aexit__(self, exc_type: Any, *_rest: Any) -> None:
        self.log.append("rollback" if exc_type is not None else "commit")


class _Engine:
    def __init__(self, conn: Conn, log: list[str]) -> None:
        self.conn, self.log = conn, log

    def connect(self) -> _Engine:
        return self

    async def __aenter__(self) -> Conn:
        return self.conn

    async def __aexit__(self, *_exc: Any) -> None:
        return None

    async def dispose(self) -> None:
        self.log.append("dispose")


def _conn_with_begin(conn: Conn, log: list[str]) -> Conn:
    conn.begin = lambda: _Begin(log)  # type: ignore[attr-defined]
    return conn


async def test_a_refusal_after_the_first_write_rolls_the_transaction_back(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The order row is inserted, then the close finds the row gone: the
    refusal must leave the transaction (rollback), never commit the orphan."""
    script = _load("spot_desk_markets")
    log: list[str] = []
    conn = _conn_with_begin(Conn([_position()]), log)
    rpc = Rpc(tx())

    async def execute(statement: Any, parameters: Any = None, /) -> _Result:
        result = await Conn.execute(conn, statement, parameters)
        if str(statement).startswith("INSERT INTO spot_orders"):
            conn.positions["pos-1"]["status"] = "closed"  # moved under us
        return result

    conn.execute = execute  # type: ignore[method-assign]

    def engine(*_a: Any, **_k: Any) -> _Engine:
        return _Engine(conn, log)

    def open_rpc(_url: str) -> Rpc:
        return rpc

    monkeypatch.setattr(script, "create_async_engine", engine)
    monkeypatch.setattr(script, "migration_url", lambda: "postgresql://x")
    monkeypatch.setattr(script, "open_rpc", open_rpc)
    code = await script._main(
        ["--close-manual", "pos-1", "--tx", SIG, "--wallet", WALLET, "--apply", "--reason", REASON]
    )
    assert code == script.EX_REFUSED and "position_not_open" in capsys.readouterr().err
    assert log == ["begin", "rollback", "dispose"], "the inserted sell row is not committed"
