"""The audited spot/1 scripts of T4.74-6 — ``spot_desk_markets.py`` and
``spot_ficha.py`` — against fake connections and a tmp vault: dry-run writes
nothing, ``--apply``/``--write`` need the guards their docstrings promise,
every refusal is named, the ficha's scoreboard append is idempotent.

No database, no network: the connections record the statements they receive
and answer canned rows. Run:
``uv run pytest infra/scripts/tests/test_spot_scripts.py -q``
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]


def _load(name: str) -> ModuleType:
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(
        f"hunter_infra_{name}_ut", SCRIPTS_DIR / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Result:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> list[dict[str, Any]]:
        return self._rows

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[Any]:
        return [next(iter(r.values())) for r in self._rows]


# ------------------------------------------------------------- spot_desk_markets


def _market(**over: Any) -> dict[str, Any]:
    row = {
        "binance_symbol": "WIFUSDT",
        "mint": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
        "kind": "nativo",
        "tier": "A",
        "round_trip_cost_pct_at_seed": Decimal("0.00082"),
        "enabled": True,
    }
    row.update(over)
    return row


class DeskConn:
    """Answers ``spot_desk_markets``/``spot_positions`` selects and updates."""

    def __init__(
        self,
        markets: list[dict[str, Any]] | None = None,
        positions: list[dict[str, Any]] | None = None,
    ) -> None:
        self.markets = {m["binance_symbol"]: dict(m) for m in (markets or [])}
        self.positions = {p["id"]: dict(p) for p in (positions or [])}
        self.statements: list[tuple[str, Any]] = []

    async def execute(self, statement: Any, parameters: Any = None, /) -> _Result:
        sql = str(statement)
        self.statements.append((sql, parameters))
        params = parameters or {}
        if (
            "spot_desk_markets" in sql
            and "WHERE binance_symbol" in sql
            and sql.startswith("SELECT")
        ):
            row = self.markets.get(params["symbol"])
            return _Result([row] if row else [])
        if sql.startswith("SELECT binance_symbol"):
            return _Result(list(self.markets.values()))
        if sql.startswith("UPDATE spot_desk_markets SET enabled"):
            row = self.markets.get(params["symbol"])
            if row is None:
                return _Result([])
            row["enabled"] = params["enabled"]
            row["updated_by"] = params["actor"]
            return _Result([{"binance_symbol": params["symbol"]}])
        if sql.startswith("UPDATE spot_desk_markets SET mint"):
            row = self.markets.get(params["symbol"])
            if row is None:
                return _Result([])
            row["mint"] = params["mint"]
            return _Result([{"binance_symbol": params["symbol"]}])
        if sql.startswith("SELECT id, status FROM spot_positions"):
            row = self.positions.get(params["id"])
            return _Result([row] if row else [])
        if sql.startswith("UPDATE spot_positions"):
            row = self.positions.get(params["id"])
            if row is None or row["status"] != "open":
                return _Result([])
            row["sell_requested_at"] = "now"
            row["sell_requested_by"] = params["actor"]
            return _Result([{"id": params["id"]}])
        return _Result([])

    def writes(self) -> list[str]:
        return [s for s, _ in self.statements if not s.lstrip().startswith("SELECT")]


REASON = "revisão do R63 §5.5, liquidez subiu bastante"


def _obsidian_note(tmp_path: Path, *mentions: str) -> str:
    """T4.93: a fixture note under ``obsidian/`` mentioning every target."""
    note_dir = tmp_path / "obsidian" / "11-KNOWLEDGE"
    note_dir.mkdir(parents=True, exist_ok=True)
    note_path = note_dir / "fixture.md"
    note_path.write_text("# fixture de teste\n\n" + "\n".join(mentions), encoding="utf-8")
    return "obsidian/11-KNOWLEDGE/fixture.md"


async def test_list_prints_the_table_and_writes_nothing() -> None:
    script = _load("spot_desk_markets")
    conn = DeskConn(markets=[_market(), _market(binance_symbol="SUIUSDT", tier="C", enabled=False)])
    code, report = await script.run(conn)
    assert code == 0 and "WIFUSDT" in report and "SUIUSDT" in report and "enabled" in report
    assert conn.writes() == []


async def test_enable_dry_run_writes_nothing() -> None:
    script = _load("spot_desk_markets")
    conn = DeskConn(markets=[_market(enabled=False)])
    code, report = await script.run(conn, enable="WIFUSDT", reason=REASON)
    assert code == 0 and "dry-run" in report and conn.writes() == []
    assert conn.markets["WIFUSDT"]["enabled"] is False


async def test_enable_apply_writes_and_leaves_an_audit_row(tmp_path: Path) -> None:
    script = _load("spot_desk_markets")
    conn = DeskConn(markets=[_market(enabled=False)])
    note = _obsidian_note(tmp_path, "WIFUSDT")
    code, report = await script.run(
        conn,
        enable="WIFUSDT",
        apply=True,
        reason=REASON,
        actor="Everton",
        note=note,
        repo_root=tmp_path,
    )
    assert code == 0 and "applied" in report
    assert conn.markets["WIFUSDT"]["enabled"] is True
    update, params = next(s for s in conn.statements if s[0].startswith("UPDATE spot_desk_markets"))
    assert params == {"symbol": "WIFUSDT", "enabled": True, "actor": "Everton"}
    _, audit_params = next(s for s in conn.statements if "system_events" in s[0])
    assert audit_params["component"] == "spot_desk" and audit_params["event"] == "enabled"
    assert REASON in audit_params["message"]


async def test_enable_without_reason_refuses_before_touching_the_database() -> None:
    script = _load("spot_desk_markets")
    conn = DeskConn(markets=[_market(enabled=False)])
    with pytest.raises(script.Refused, match="reason_required"):
        await script.run(conn, enable="WIFUSDT", apply=True, reason="short")
    assert conn.statements == []


async def test_enable_already_enabled_is_a_plain_no_op() -> None:
    script = _load("spot_desk_markets")
    conn = DeskConn(markets=[_market(enabled=True)])
    code, report = await script.run(conn, enable="WIFUSDT", apply=True, reason=REASON)
    assert code == 0 and "already" in report and conn.writes() == []


async def test_disable_missing_market_refuses_by_name() -> None:
    script = _load("spot_desk_markets")
    conn = DeskConn(markets=[])
    with pytest.raises(script.Refused, match="market_missing"):
        await script.run(conn, disable="NOPEUSDT", apply=True, reason=REASON)
    assert conn.writes() == []


async def test_set_mint_validates_base58_length_before_touching_the_database() -> None:
    script = _load("spot_desk_markets")
    conn = DeskConn(markets=[_market()])
    with pytest.raises(script.Refused, match="invalid_mint"):
        await script.run(conn, set_mint=("WIFUSDT", "tooshort"), apply=True, reason=REASON)
    assert conn.statements == []


async def test_set_mint_apply_writes_the_new_mint_and_an_audit_row(tmp_path: Path) -> None:
    script = _load("spot_desk_markets")
    new_mint = "9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump"
    conn = DeskConn(markets=[_market()])
    note = _obsidian_note(tmp_path, "WIFUSDT")
    code, report = await script.run(
        conn,
        set_mint=("WIFUSDT", new_mint),
        apply=True,
        reason=REASON,
        actor="Everton",
        note=note,
        repo_root=tmp_path,
    )
    assert code == 0 and "applied" in report
    assert conn.markets["WIFUSDT"]["mint"] == new_mint
    _, audit_params = next(s for s in conn.statements if "system_events" in s[0])
    assert audit_params["event"] == "mint_changed" and "Everton" in audit_params["message"]


async def test_sell_now_dry_run_writes_nothing() -> None:
    script = _load("spot_desk_markets")
    conn = DeskConn(positions=[{"id": "pos-1", "status": "open"}])
    code, report = await script.run(conn, sell_now="pos-1", reason=REASON)
    assert code == 0 and "dry-run" in report and conn.writes() == []


async def test_sell_now_apply_sets_the_columns_and_leaves_an_audit_row() -> None:
    script = _load("spot_desk_markets")
    conn = DeskConn(positions=[{"id": "pos-1", "status": "open"}])
    code, report = await script.run(
        conn, sell_now="pos-1", apply=True, reason=REASON, actor="Everton"
    )
    assert code == 0 and "applied" in report
    assert conn.positions["pos-1"]["sell_requested_by"] == "Everton"
    _, audit_params = next(s for s in conn.statements if "system_events" in s[0])
    assert audit_params["event"] == "sell_requested" and "pos-1" in audit_params["message"]


async def test_sell_now_on_a_closed_position_refuses() -> None:
    script = _load("spot_desk_markets")
    conn = DeskConn(positions=[{"id": "pos-1", "status": "closed"}])
    with pytest.raises(script.Refused, match="position_not_open"):
        await script.run(conn, sell_now="pos-1", apply=True, reason=REASON)
    assert conn.writes() == []


async def test_sell_now_on_a_missing_position_refuses() -> None:
    script = _load("spot_desk_markets")
    conn = DeskConn(positions=[])
    with pytest.raises(script.Refused, match="position_missing"):
        await script.run(conn, sell_now="ghost", apply=True, reason=REASON)
    assert conn.writes() == []


def test_parse_args_rejects_two_acts_at_once() -> None:
    script = _load("spot_desk_markets")
    with pytest.raises(SystemExit):
        script.parse_args(["--enable", "WIFUSDT", "--disable", "SUIUSDT", "--reason", REASON])


def test_parse_args_requires_one_act() -> None:
    script = _load("spot_desk_markets")
    with pytest.raises(SystemExit):
        script.parse_args([])


# --------------------------------------------------- T4.93: Obsidian primeiro


async def test_enable_apply_without_a_note_is_refused_before_writing(tmp_path: Path) -> None:
    script = _load("spot_desk_markets")
    conn = DeskConn(markets=[_market(enabled=False)])
    with pytest.raises(script.Refused, match="note_required"):
        await script.run(conn, enable="WIFUSDT", apply=True, reason=REASON, repo_root=tmp_path)
    assert conn.writes() == []


async def test_enable_apply_with_a_missing_note_file_is_refused(tmp_path: Path) -> None:
    script = _load("spot_desk_markets")
    conn = DeskConn(markets=[_market(enabled=False)])
    with pytest.raises(script.Refused, match="note_missing"):
        await script.run(
            conn,
            enable="WIFUSDT",
            apply=True,
            reason=REASON,
            note="obsidian/11-KNOWLEDGE/ghost.md",
            repo_root=tmp_path,
        )
    assert conn.writes() == []


async def test_enable_apply_with_a_note_not_mentioning_the_symbol_is_refused(
    tmp_path: Path,
) -> None:
    script = _load("spot_desk_markets")
    conn = DeskConn(markets=[_market(enabled=False)])
    note = _obsidian_note(tmp_path, "outro mercado qualquer")
    with pytest.raises(script.Refused, match="note_does_not_mention_target"):
        await script.run(
            conn, enable="WIFUSDT", apply=True, reason=REASON, note=note, repo_root=tmp_path
        )
    assert conn.writes() == []


async def test_enable_dry_run_needs_no_note_and_prints_the_hint(tmp_path: Path) -> None:
    script = _load("spot_desk_markets")
    conn = DeskConn(markets=[_market(enabled=False)])
    code, report = await script.run(conn, enable="WIFUSDT", reason=REASON, repo_root=tmp_path)
    assert code == 0 and "dry-run" in report and "--note" in report and "WIFUSDT" in report
    assert conn.writes() == []


# ------------------------------------------------------------------- spot_ficha

POSITION_ID = "01924f6e-0000-7000-8000-00000000000a"
ENTRY_AT = datetime(2026, 9, 19, 14, 0, tzinfo=UTC)


def _position(**over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": POSITION_ID,
        "market_symbol": "WIFUSDT",
        "mint": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
        "status": "open",
        "entry_at": ENTRY_AT,
        "entry": {"out_amount": "1000000"},
        "tokens": 1_000_000,
        "sol_spent_lamports": 50_000_000,
        "initial_risk_sol": Decimal("0.001"),
        "params": {
            "ref": "1.23",
            "stop_frac": "0.02",
            "target_frac": "0.03",
            "horizon_s": 14400,
            "sol_usd_at_entry": "200",
            "bin_usd_at_entry": "1.23",
            "jup_usd_at_entry": "1.24",
        },
        "ata_rent_lamports": 2_040_000,
        "mark_sol": None,
        "mark_reason": None,
        "exit_at": None,
        "exit": None,
        "sol_received_lamports": None,
        "pnl_sol": None,
        "r_multiple": None,
        "entry_order_id": "order-buy-1",
        "exit_order_id": None,
        "base": "WIF",
        "kind": "nativo",
    }
    row.update(over)
    return row


def _order(**over: Any) -> dict[str, Any]:
    row = {
        "side": "buy",
        "status": "confirmed",
        "tx_signature": "5FakeSignature",
        "admission": {"checks": [{"name": "cost_r", "value": "0.2"}]},
    }
    row.update(over)
    return row


class FichaConn:
    def __init__(
        self, position: dict[str, Any] | None, orders: dict[str, dict[str, Any]] | None = None
    ) -> None:
        self.position = position
        self.orders = orders or {}
        self.statements: list[tuple[str, Any]] = []

    async def execute(self, statement: Any, parameters: Any = None, /) -> _Result:
        sql = str(statement)
        self.statements.append((sql, parameters))
        params = parameters or {}
        if "FROM spot_positions p JOIN" in sql:
            if self.position is None or self.position["id"] != params["id"]:
                return _Result([])
            return _Result([self.position])
        if "FROM spot_orders" in sql:
            row = self.orders.get(params["id"])
            return _Result([row] if row else [])
        return _Result([])


async def test_ficha_dry_run_prints_markdown_and_writes_nothing(tmp_path: Path) -> None:
    script = _load("spot_ficha")
    conn = FichaConn(_position(), {"order-buy-1": _order()})
    spot_dir = tmp_path / "Spot"
    code, report = await script.run(conn, position_id=POSITION_ID, write=False, spot_dir=spot_dir)
    assert code == 0 and "dry-run" in report
    assert "## Sinal e geometria" in report and "## Lição" in report
    assert not spot_dir.exists()


async def test_ficha_write_creates_the_file_and_appends_the_scoreboard(tmp_path: Path) -> None:
    script = _load("spot_ficha")
    conn = FichaConn(_position(), {"order-buy-1": _order()})
    spot_dir = tmp_path / "Spot"
    code, report = await script.run(conn, position_id=POSITION_ID, write=True, spot_dir=spot_dir)
    assert code == 0 and "applied" in report
    ficha_path = spot_dir / "Ficha-2026-09-19-WIFUSDT-01924f6e.md"
    assert ficha_path.exists()
    board = (spot_dir / "Mesa-spot-1.md").read_text(encoding="utf-8")
    assert "<!-- 01924f6e -->" in board and "WIFUSDT" in board


async def test_ficha_write_is_idempotent_on_the_scoreboard(tmp_path: Path) -> None:
    script = _load("spot_ficha")
    spot_dir = tmp_path / "Spot"
    conn1 = FichaConn(_position(), {"order-buy-1": _order()})
    await script.run(conn1, position_id=POSITION_ID, write=True, spot_dir=spot_dir)
    board_path = spot_dir / "Mesa-spot-1.md"
    first = board_path.read_text(encoding="utf-8")
    conn2 = FichaConn(_position(), {"order-buy-1": _order()})
    code, report = await script.run(conn2, position_id=POSITION_ID, write=True, spot_dir=spot_dir)
    second = board_path.read_text(encoding="utf-8")
    assert code == 0 and "idempotent" in report
    assert first == second
    assert second.count("<!-- 01924f6e -->") == 1


async def test_ficha_missing_position_refuses() -> None:
    script = _load("spot_ficha")
    conn = FichaConn(None)
    with pytest.raises(script.Refused, match="position_missing"):
        await script.run(conn, position_id="ghost", write=False)


async def test_ficha_shows_a_closed_position_s_net_r_and_indisponivel_without_cost_r() -> None:
    script = _load("spot_ficha")
    closed = _position(
        status="closed",
        exit_at=datetime(2026, 9, 19, 18, 0, tzinfo=UTC),
        exit={"out_amount": "900000"},
        sol_received_lamports=49_000_000,
        pnl_sol=Decimal("-0.001"),
        r_multiple=Decimal("-1"),
        exit_order_id="order-sell-1",
    )
    conn = FichaConn(
        closed,
        {"order-buy-1": _order(admission={"checks": []}), "order-sell-1": _order(side="sell")},
    )
    code, report = await script.run(conn, position_id=POSITION_ID, write=False)
    assert code == 0
    assert "R líquido: -1" in report
    assert "falta admission.checks.cost_r" in report
