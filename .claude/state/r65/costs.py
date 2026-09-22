"""R65 - decomposicao de custo por operacao a partir de `meme_live_orders.fill` (lamports inteiros).

payer_delta(compra) = -(sol_amount + fee + creator_fee + ata_rent + network_fee)
payer_delta(venda)  =  sol_amount - fee - creator_fee - network_fee
Derrapagem realizada: compra = tokens do fill vs tokens da cotacao; venda = sell_net do fill vs
`intent.net_proceeds_lamports` (o que o executor esperava quando decidiu).
"""
import csv
import json
from decimal import Decimal
from pathlib import Path

csv.field_size_limit(10_000_000)
HERE = Path(__file__).resolve().parent


def _i(d, k):
    v = d.get(k)
    return int(v) if v is not None else 0


def load_costs(path="orders.csv"):
    """-> {proposal_id: dict} com os lamports de cada componente."""
    by = {}
    with open(HERE / path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            pid = r["proposal_id"]
            c = by.setdefault(pid, dict(
                buy_curve=0, sell_curve=0, pf_fee=0, creator_fee=0, net_fee=0, ata_rent=0,
                ata_refund=0, failed_sells=0, failed_net_fee=0,
                buy_tokens=0, sell_tokens=0, exit_expected=0, exit_actual=0,
                buy_expected_tokens=0, buy_slip_lamports=0))
            fill = (json.loads(r["fill"]) if r["fill"] else None) or {}
            intent = (json.loads(r["intent"]) if r["intent"] else None) or {}
            if r["status"] != "confirmed":
                c["failed_sells"] += 1 if r["side"] == "sell" else 0
                # taxa de rede de tx que falhou so existe se a tx foi para a cadeia
                c["failed_net_fee"] += _i(fill, "network_fee_lamports")
                continue
            c["pf_fee"] += _i(fill, "fee")
            c["creator_fee"] += _i(fill, "creator_fee")
            c["net_fee"] += _i(fill, "network_fee_lamports")
            c["ata_rent"] += _i(fill, "ata_rent_lamports")
            c["ata_refund"] += _i(fill, "ata_rent_refund_lamports")
            if r["side"] == "buy":
                c["buy_curve"] += _i(fill, "sol_amount")
                c["buy_tokens"] += _i(fill, "token_amount")
                c["buy_total"] = _i(fill, "buy_total_lamports")
                c["payer_buy"] = _i(fill, "payer_delta_lamports")
            else:
                c["sell_curve"] += _i(fill, "sol_amount")
                c["sell_tokens"] += _i(fill, "token_amount")
                c["exit_actual"] = _i(fill, "sell_net_lamports")
                c["exit_expected"] = _i(intent, "net_proceeds_lamports")
                c["payer_sell"] = _i(fill, "payer_delta_lamports")
                c["exit_reason"] = intent.get("exit_reason")
                c["closes_ata"] = bool(intent.get("closes_ata"))
    for c in by.values():
        c["exit_slip"] = c["exit_actual"] - c["exit_expected"] if c["exit_expected"] else 0
        c["gross_curve"] = c["sell_curve"] - c["buy_curve"]
        c["total_fees"] = c["pf_fee"] + c["creator_fee"] + c["net_fee"] + c["ata_rent"] \
            - c["ata_refund"] + c["failed_net_fee"]
    return by


def sol(lamports):
    return Decimal(lamports) / Decimal(10**9)


if __name__ == "__main__":
    by = load_costs()
    tot = dict(buy_curve=0, sell_curve=0, pf_fee=0, creator_fee=0, net_fee=0, ata_rent=0,
               failed_net_fee=0, exit_slip=0)
    for c in by.values():
        for k in tot:
            tot[k] += c.get(k, 0)
    print("operacoes:", len(by))
    for k, v in tot.items():
        print("  %-14s %s SOL" % (k, sol(v)))
    print("  bruto curva   ", sol(tot["sell_curve"] - tot["buy_curve"]), "SOL")
    print("  custos totais ", sol(tot["pf_fee"] + tot["creator_fee"] + tot["net_fee"]
                                  + tot["ata_rent"] + tot["failed_net_fee"]), "SOL")
