"""``spot_desk_markets.py --close-manual`` (T4.74-7, finding A1 of
``.claude/state/review-T4.74.md``): close a ``spot_positions`` row whose lot
was sold **outside** the lane (``meme_spot_swap.py --from <mint> --to SOL``,
another DEX) with the numbers of the sell transaction itself — never a hand
``UPDATE``. Split from ``spot_desk_markets.py`` for the 350-line budget.

The chain is the source: ``getTransaction(<signature>)`` meta, read by the
executor's own ``fill_from_transaction`` (fee payer must be ``--wallet``,
the wallet's token account of the position's mint before/after). Refused,
by name and with nothing written, unless **all** of: the row is ``open``
and no lane sell is in flight (``exit_pending``: the reconcile owns it),
``--wallet`` is the wallet the entry order was admitted for
(``spot_orders.admission.wallet_id`` of ``entry_order_id`` — Astra, T4.74-7
review: a personal wallet's sale of the same lot must not quit the desk's
row), the signature is not already a ``spot_orders`` row, the transaction is served,
readable and not errored, its token delta is exactly ``-tokens`` (the whole
lot, ``token_delta_mismatch``), it landed SOL (``sol_delta_not_positive``),
and its ``blockTime`` is after ``entry_at``. ``sol_received_lamports`` is the
fee payer's lamport delta (net of fees, the lane's own convention),
``pnl_sol = received − spent``, ``r_multiple = pnl ÷ initial_risk_sol`` —
``Decimal``, atoms ``int``.

``--apply`` writes, in one transaction: a ``spot_orders`` sell row
(``confirmed``, ``client_order_id = spot:sell:<id>:manual``, the fill, the
signature — one signature per row, so the ficha's join and the refutation
read it like any lane exit, ``exit->>'reason' = manual_close``), the
position ``closed`` by the lane's predicate plus ``exit_order_id IS NULL``,
and one ``system_events`` row (``closed_manually``). The position row is read
``FOR UPDATE``: the executor's own pending marker (``set_exit_pending``) waits
for this transaction and then finds the row closed — it sells nothing
(``spot_exits.py``, ``position_not_open``). A refusal after the first write
propagates out of the transaction (rollback), never a committed orphan.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in ("services/meme-executor", "packages/exchange-adapters", "packages/risk-core"):
    _candidate = str(REPO_ROOT / _extra)
    if _candidate not in sys.path:
        sys.path.insert(0, _candidate)

from meme_ops_db import record_event  # noqa: E402
from spot_desk_markets_plan import COMPONENT, Refused  # noqa: E402
from sqlalchemy import text  # noqa: E402

from hunter_core.domain.types import uuid7  # noqa: E402
from hunter_meme_executor.spot_send_rules import fill_from_transaction  # noqa: E402

__all__ = ["ManualClose", "Refused", "TxReader", "check_manual_close", "close_manual", "open_rpc"]

LAMPORTS = Decimal(1_000_000_000)
MANUAL_REASON = "manual_close"
PENDING_EXIT_STATUS = "submitted_unconfirmed"


class Connection(Protocol):
    async def execute(self, statement: Any, parameters: Any = None, /) -> Any: ...


class TxReader(Protocol):
    def get_transaction(
        self, signature: str, *, commitment: str = "confirmed"
    ) -> dict[str, Any] | None: ...


_POSITION = text(
    "SELECT p.id, p.status, p.signal_id, p.market_symbol, p.mint, p.tokens, "
    "  p.sol_spent_lamports, p.initial_risk_sol, p.entry_at, p.exit_intent, p.exit_order_id, "
    "  o.admission->>'wallet_id' AS entry_wallet "
    "FROM spot_positions p LEFT JOIN spot_orders o ON o.id = p.entry_order_id "
    "WHERE p.id = CAST(:id AS uuid) FOR UPDATE OF p"
)
_SIGNATURE_KNOWN = text("SELECT id FROM spot_orders WHERE tx_signature = :signature")
_NEXT_ATTEMPT = text(
    "SELECT coalesce(max(attempt), 0) + 1 AS n FROM spot_orders "
    "WHERE side = 'sell' AND position_id = CAST(:id AS uuid)"
)
_INSERT_SELL = text(
    "INSERT INTO spot_orders (id, signal_id, position_id, market_symbol, mint, side, "
    "  client_order_id, attempt, intent, admission, status, tx_signature, fill, "
    "  received_at, admitted_at, signing_at, submitted_at, settled_at, updated_at) "
    "VALUES (CAST(:id AS uuid), :signal_id, CAST(:position_id AS uuid), :market_symbol, "
    "  :mint, :side, "
    "  :client_order_id, :attempt, CAST(:intent AS jsonb), CAST(:admission AS jsonb), "
    "  :status, :tx_signature, CAST(:fill AS jsonb), "
    "  :now, :now, :exit_at, :exit_at, :now, :now) RETURNING id"
)
_CLOSE = text(
    "UPDATE spot_positions SET status = 'closed', exit_order_id = :order_id, exit_at = :exit_at, "
    "  exit = CAST(:exit AS jsonb), sol_received_lamports = :received, pnl_sol = :pnl, "
    "  r_multiple = :r, tokens = 0, updated_at = :now "
    "WHERE id = CAST(:id AS uuid) AND status = 'open' AND exit_order_id IS NULL RETURNING id"
)


@dataclass(frozen=True, slots=True)
class ManualClose:
    """What the transaction proves about this position — the plan of the act."""

    position_id: str
    signature: str
    wallet: str
    tokens: int
    sol_spent_lamports: int
    sol_received_lamports: int
    pnl_sol: Decimal
    r_multiple: Decimal
    exit_at: datetime
    token_before_atoms: int
    token_after_atoms: int
    network_fee_lamports: int

    def describe(self) -> str:
        return (
            f"close-manual {self.position_id}\n"
            f"  signature={self.signature}\n"
            f"  wallet={self.wallet}\n"
            f"  tokens {self.token_before_atoms} -> {self.token_after_atoms} "
            f"(the lot of {self.tokens})\n"
            f"  sol_spent_lamports={self.sol_spent_lamports} "
            f"sol_received_lamports={self.sol_received_lamports} "
            f"(fee {self.network_fee_lamports})\n"
            f"  pnl_sol={self.pnl_sol} r_multiple={self.r_multiple.quantize(Decimal('0.001'))}\n"
            f"  exit_at={self.exit_at.isoformat()} (blockTime)"
        )

    def fill(self) -> dict[str, Any]:
        return {
            "signature": self.signature,
            "side": "sell",
            "source": "transaction_meta",
            "sol_delta_lamports": self.sol_received_lamports,
            "token_before_atoms": self.token_before_atoms,
            "token_after_atoms": self.token_after_atoms,
            "filled_atoms": self.sol_received_lamports,
            "ata_rent_lamports": 0,
            "priority_fee_lamports": None,
            "network_fee_lamports": self.network_fee_lamports,
            "quoted_out_atoms": None,
            "confirmed_at": self.exit_at.isoformat(),
        }


def check_manual_close(
    position: Mapping[str, Any], tx: Mapping[str, Any] | None, *, wallet: str, signature: str
) -> ManualClose:
    """Pure: the transaction against the row, or ``Refused`` by name."""
    if tx is None:
        raise Refused("tx_not_found", f"{signature} is not served by the RPC (confirmed)")
    mint = str(position["mint"])
    landed = fill_from_transaction(dict(tx), wallet=wallet, mint=mint)
    if landed is None:
        raise Refused("tx_unreadable", "meta missing or errored, or the fee payer is not --wallet")
    tokens = int(position["tokens"])
    token_delta = landed.token_after_atoms - landed.token_before_atoms
    if token_delta != -tokens:
        raise Refused(
            "token_delta_mismatch",
            f"the transaction moved {token_delta} atoms of {mint[:8]}; the position holds {tokens}",
        )
    if landed.sol_delta_lamports <= 0:
        raise Refused(
            "sol_delta_not_positive",
            f"the wallet's lamport delta is {landed.sol_delta_lamports}: not a sell for SOL",
        )
    block_time = tx.get("blockTime")
    if block_time is None:
        raise Refused("tx_without_block_time", "getTransaction served no blockTime")
    exit_at = datetime.fromtimestamp(int(block_time), UTC)
    entry_at = position["entry_at"]
    if exit_at <= entry_at:
        raise Refused("tx_before_entry", f"blockTime {exit_at.isoformat()} <= entry_at")
    spent = int(position["sol_spent_lamports"])
    risk = Decimal(str(position["initial_risk_sol"]))
    if risk <= 0:
        raise Refused("initial_risk_not_positive", str(risk))
    pnl = Decimal(landed.sol_delta_lamports - spent) / LAMPORTS
    return ManualClose(
        position_id=str(position["id"]),
        signature=signature,
        wallet=wallet,
        tokens=tokens,
        sol_spent_lamports=spent,
        sol_received_lamports=landed.sol_delta_lamports,
        pnl_sol=pnl,
        r_multiple=pnl / risk,
        exit_at=exit_at,
        token_before_atoms=landed.token_before_atoms,
        token_after_atoms=landed.token_after_atoms,
        network_fee_lamports=landed.network_fee_lamports,
    )


async def close_manual(
    conn: Connection,
    rpc: TxReader,
    *,
    position_id: str,
    signature: str,
    wallet: str,
    apply: bool,
    actor: str,
    reason: str,
) -> tuple[int, str]:
    """``(exit code, report)``; every refusal happens before any write."""
    rows = (await conn.execute(_POSITION, {"id": position_id})).mappings()
    row = next(iter(rows), None)
    if row is None:
        raise Refused("position_missing", position_id)
    if str(row["status"]) != "open":
        raise Refused("position_not_open", f"{position_id} is {row['status']}")
    intent = dict(row["exit_intent"] or {})
    if intent.get("status") == PENDING_EXIT_STATUS or row["exit_order_id"] is not None:
        raise Refused(
            "exit_pending", f"{position_id} has a lane sell in flight; the reconcile settles it"
        )
    entry_wallet = row["entry_wallet"]
    if entry_wallet is None:
        raise Refused("entry_wallet_unknown", f"{position_id}: the entry order names no wallet")
    if str(entry_wallet) != wallet:
        raise Refused(
            "wallet_mismatch", f"--wallet {wallet[:8]}… is not the entry's {str(entry_wallet)[:8]}…"
        )
    known = (await conn.execute(_SIGNATURE_KNOWN, {"signature": signature})).scalars().all()
    if known:
        raise Refused("signature_already_recorded", f"{signature} is spot_orders {known[0]}")
    plan = check_manual_close(
        row, rpc.get_transaction(signature), wallet=wallet, signature=signature
    )
    report = f"{plan.describe()}\nreason: {reason}"
    if not apply:
        return 0, report + "\ndry-run: nothing written (add --apply)"
    now = datetime.now(UTC)
    attempt = int((await conn.execute(_NEXT_ATTEMPT, {"id": position_id})).scalar() or 1)
    order_id = (
        await conn.execute(
            _INSERT_SELL,
            {
                "id": str(uuid7()),
                "signal_id": row["signal_id"],
                "position_id": position_id,
                "market_symbol": row["market_symbol"],
                "mint": row["mint"],
                "side": "sell",
                "client_order_id": f"spot:sell:{position_id}:manual",
                "attempt": attempt,
                "intent": json.dumps(
                    {
                        "side": "sell",
                        "reason": MANUAL_REASON,
                        "amount_atoms": plan.tokens,
                        "attempt": attempt,
                        "market_symbol": row["market_symbol"],
                    }
                ),
                "admission": json.dumps(
                    {
                        "decided_by": "script:spot_desk_markets",
                        "actor": actor,
                        "reason": reason,
                        "exit_reason": MANUAL_REASON,
                    }
                ),
                "status": "confirmed",
                "tx_signature": signature,
                "fill": json.dumps(plan.fill()),
                "now": now,
                "exit_at": plan.exit_at,
            },
        )
    ).scalar()
    if order_id is None:
        raise Refused("order_not_written", "the sell row was not inserted")
    exit_payload = {
        "reason": MANUAL_REASON,
        "attempt": attempt,
        "order_id": str(order_id),
        "signature": signature,
        "filled_lamports": plan.sol_received_lamports,
        "sol_delta_lamports": plan.sol_received_lamports,
        "actor": actor,
        "note": reason,
        "source": "spot_desk_markets --close-manual",
    }
    closed = (
        (
            await conn.execute(
                _CLOSE,
                {
                    "id": position_id,
                    "order_id": order_id,
                    "exit_at": plan.exit_at,
                    "exit": json.dumps(exit_payload, default=str),
                    "received": plan.sol_received_lamports,
                    "pnl": plan.pnl_sol,
                    "r": plan.r_multiple,
                    "now": now,
                },
            )
        )
        .scalars()
        .all()
    )
    if not closed:
        raise Refused("position_not_open", f"{position_id} moved under us")
    await record_event(
        conn,
        component=COMPONENT,
        level="info",
        event="closed_manually",
        message=(
            f"{position_id} closed by {actor} from {signature}: "
            f"received {plan.sol_received_lamports} lamports, pnl_sol {plan.pnl_sol}; "
            f"reason: {reason}"
        ),
        data={
            "position_id": position_id,
            "order_id": str(order_id),
            "signature": signature,
            "wallet": wallet,
            "sol_received_lamports": plan.sol_received_lamports,
            "pnl_sol": str(plan.pnl_sol),
            "r_multiple": str(plan.r_multiple),
            "actor": actor,
        },
    )
    return 0, report + "\napplied: spot_orders sell row + position closed; system_events written"


def open_rpc(url: str) -> TxReader:
    """The read-only RPC client (``allow_send`` stays off: this script never sends)."""
    from hunter_exchanges.pumpfun.tx_rpc import SolanaTxRpcClient

    return SolanaTxRpcClient(url)


def default_rpc_url() -> str:
    from hunter_exchanges.pumpfun.tx_rpc import MAINNET_PUBLIC_RPC_URL

    return str(MAINNET_PUBLIC_RPC_URL)
