"""The pure half of ``spot_fix_ata_rent.py`` (KB-0171): a closed position's
entry transaction against the row → ``Fix`` (before/after) or ``Refused`` by
name. No database, no network. Split from the script for the 350-line budget."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final

from hunter_meme_executor.spot_send_rules import entry_spend, fill_from_transaction

__all__ = ["LAMPORTS", "Fix", "Refused", "plan_fix"]

LAMPORTS = Decimal(1_000_000_000)
_R_TOLERANCE = Decimal("1e-9")
"""``r_multiple`` is NUMERIC(28,10): its rounding (≤ 5e-11) never reads as a change."""
_EXACT: Final = (
    "sol_spent_lamports", "ata_rent_lamports", "pnl_sol", "sol_spent_source",
    "entry_sol_spent_lamports", "entry_ata_rent_lamports", "params_ata_rent_lamports",
)  # fmt: skip


def _decimal(value: Any) -> Decimal | None:
    try:
        return None if value is None else Decimal(str(value))
    except ArithmeticError:
        return None


class Refused(Exception):
    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason


@dataclass(frozen=True, slots=True)
class Fix:
    """One position's accounting before and after, from its entry transaction."""

    position_id: str
    market_symbol: str
    signature: str
    before: dict[str, Any]
    after: dict[str, Any]
    entry_sol_per_atom: Decimal

    @property
    def changed(self) -> bool:
        """Everything this script writes, compared — columns **and** the copies in
        ``entry``/``params`` (Astra, diff review: right columns with stale JSON
        must not read "already correct"); R within the column's rounding."""
        b, a = self.before, self.after
        same = all(b[k] == a[k] for k in _EXACT)
        same = same and _decimal(b["entry_sol_per_atom"]) == _decimal(a["entry_sol_per_atom"])
        return not (
            same and abs(Decimal(b["r_multiple"]) - Decimal(a["r_multiple"])) < _R_TOLERANCE
        )

    def describe(self) -> str:
        b, a = self.before, self.after
        state = "CORRECT" if self.changed else "already correct"
        return (
            f"{self.position_id} {self.market_symbol} [{state}] tx {self.signature[:16]}…\n"
            f"  sol_spent {b['sol_spent_lamports']} -> {a['sol_spent_lamports']}  "
            f"ata_rent {b['ata_rent_lamports']} -> {a['ata_rent_lamports']} "
            f"({a['sol_spent_source']})\n"
            f"  pnl_sol {b['pnl_sol']} -> {a['pnl_sol']}  "
            f"r_multiple {Decimal(b['r_multiple']):.4f} -> {Decimal(a['r_multiple']):.4f}"
        )


def plan_fix(row: Mapping[str, Any], tx: Mapping[str, Any] | None) -> Fix:
    """Pure: the transaction against the closed row, or ``Refused`` by name."""
    pid, signature, wallet = str(row["id"]), row["tx_signature"], row["wallet"]
    if signature is None:
        raise Refused("entry_signature_missing", pid)
    if wallet is None:
        raise Refused("entry_wallet_unknown", f"{pid}: the entry order names no wallet")
    if tx is None:
        raise Refused("tx_not_found", f"{pid}: {signature} not served by the RPC (confirmed)")
    landed = fill_from_transaction(dict(tx), wallet=str(wallet), mint=str(row["mint"]))
    if landed is None:
        raise Refused(
            "tx_unreadable", f"{pid}: meta missing/errored, or the payer is not the wallet"
        )
    entry = dict(row["entry"] or {})
    filled, delta = int(entry.get("filled_atoms") or 0), entry.get("sol_delta_lamports")
    if filled <= 0 or landed.token_delta_atoms != filled:
        raise Refused("token_delta_mismatch", f"{pid}: tx {landed.token_delta_atoms} vs {filled}")
    if delta is None or landed.sol_delta_lamports != int(delta):
        raise Refused("sol_delta_mismatch", f"{pid}: tx {landed.sol_delta_lamports} vs {delta}")
    fill_delta = dict(row.get("entry_fill") or {}).get("sol_delta_lamports")
    if fill_delta is not None and int(fill_delta) != landed.sol_delta_lamports:
        raise Refused("fill_mismatch", f"{pid}: order fill {fill_delta} vs tx")
    if landed.ata_rent_lamports is None:
        raise Refused(
            "rent_unreadable", f"{pid}: the ATA was created but its deposit is unreadable"
        )
    spent, rent, source = entry_spend(landed.sol_delta_lamports, landed.ata_rent_lamports)
    risk = Decimal(str(row["initial_risk_sol"]))
    nulls = [c for c in ("sol_received_lamports", "pnl_sol", "r_multiple") if row[c] is None]
    if risk <= 0 or nulls:
        raise Refused("position_not_closable", f"{pid}: risk {risk}, null {nulls}")
    pnl = Decimal(int(row["sol_received_lamports"]) - spent) / LAMPORTS
    per_atom = Decimal(spent) / LAMPORTS / Decimal(filled)
    params = dict(row.get("params") or {})
    before = {
        "sol_spent_lamports": int(row["sol_spent_lamports"]),
        "ata_rent_lamports": int(row["ata_rent_lamports"]),
        "pnl_sol": Decimal(str(row["pnl_sol"])),
        "r_multiple": Decimal(str(row["r_multiple"])),
        "sol_spent_source": entry.get("sol_spent_source"),
        "entry_sol_spent_lamports": entry.get("sol_spent_lamports"),
        "entry_ata_rent_lamports": entry.get("ata_rent_lamports"),
        "params_ata_rent_lamports": params.get("ata_rent_lamports"),
        "entry_sol_per_atom": params.get("entry_sol_per_atom"),
    }
    after = {
        "sol_spent_lamports": spent,
        "ata_rent_lamports": rent,
        "pnl_sol": pnl,
        "r_multiple": pnl / risk,
        "sol_spent_source": source,
        "entry_sol_spent_lamports": spent,
        "entry_ata_rent_lamports": rent,
        "params_ata_rent_lamports": rent,
        "entry_sol_per_atom": str(per_atom),
    }
    return Fix(pid, str(row["market_symbol"]), str(signature), before, after, per_atom)
