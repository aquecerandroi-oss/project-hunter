"""R67 - carrega as apostas de papel (fora de amostra) e as 87 operacoes reais do R65.

`buys_1m` vem de `meme_proposals.reasons` -> bloco `flow`, gravado NO INSTANTE DA DECISAO
(o mesmo campo que o R65 usou). Nada aqui usa informacao posterior a decisao como preditor:
`pnl_sol`, `high_water_x` e `exit_reason` sao DESFECHOS.
Dinheiro em Decimal; a estatistica roda em float (valores ~1e-2 SOL).
"""
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
BRT = timezone(timedelta(hours=-3))


def _ts(s):
    s = (s or "").strip()
    if not s:
        return None
    if s.endswith("+00"):
        s += ":00"
    return datetime.fromisoformat(s.replace(" ", "T"))


def _d(s):
    s = (s or "").strip()
    return Decimal(s) if s else None


def _f(s):
    s = (s or "").strip()
    if s in ("", "None"):
        return None
    if s in ("t", "true", "True"):
        return 1.0
    if s in ("f", "false", "False"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return None


def load_paper(path="paper.csv"):
    """Apostas de papel fechadas, medidas, com `buys_1m` na decisao e sem proposta partilhada com o real."""
    out = []
    for r in csv.DictReader(open(HERE / path, newline="", encoding="utf-8")):
        if r["status"] != "closed" or r["outcome_quality"] != "measured":
            continue
        if r["shared_live"] == "t":          # pureza: esta proposta virou posicao real (entrou no R65)
            continue
        if not (r["buys_1m"] or "").strip() or not (r["pnl_sol"] or "").strip():
            continue
        entry, exit_ = _ts(r["entry_at"]), _ts(r["exit_at"])
        size = _d(r["size_sol"]) or Decimal("0.05")
        pnl = _d(r["pnl_sol"])
        hw = _d(r["high_water_x"])
        out.append(dict(
            kind="paper", mint=r["mint"], arm=r["arm"], entry_at=entry,
            day=entry.astimezone(BRT).date().isoformat(),
            hour=entry.astimezone(BRT).hour,
            hold_s=(exit_ - entry).total_seconds() if exit_ else None,
            size_sol=size, pnl_sol=pnl, ret=float(pnl / size),
            hw=float(hw) if hw is not None else None,
            hit15=(1.0 if (hw is not None and hw >= Decimal("1.15")) else 0.0) if hw is not None else None,
            reason=r["exit_reason"] or "",
            target_x=_f(r["target_x"]), max_hold_s=_f(r["max_hold_s"]),
            buys_1m=_f(r["buys_1m"]), sells_1m=_f(r["sells_1m"]),
            unique_buyers_1m=_f(r["unique_buyers_1m"]), snipers=_f(r["snipers"]),
            dev_share=_f(r["dev_share"]), net_sol_flow_1m=_f(r["net_sol_flow_1m"]),
            mcap_delta_60s=_f(r["mcap_delta_60s"]),
            age_s=_f(r["age_s"]), progress_pct=_f(r["progress_pct"]),
            real_sol=_f(r["real_sol"]), mcap_sol=_f(r["mcap_sol"]),
        ))
    return out


def load_real(path="../r65/anat.csv"):
    """As 87 operacoes reais do R65 (PnL liquido realizado, ja com taxas; rent de ATA separado)."""
    out = []
    for r in csv.DictReader(open(HERE / path, newline="", encoding="utf-8")):
        if not (r["buys_1m"] or "").strip():
            continue
        size = Decimal("0.07") if r["set"].startswith("operator") and r["day_brt"] >= "2026-09-19" else Decimal("0.05")
        pnl = Decimal(r["pnl_sol"])
        rent = Decimal(r["ata_rent_sol"] or "0")
        adj = pnl + rent                       # rent devolvido (P0 do R65), para comparar com o papel
        mfe = _f(r["mfe"])
        out.append(dict(
            kind="real", mint=r["mint"], arm=r["set"], day=r["day_brt"], hour=int(r["hour_brt"]),
            hold_s=_f(r["hold_s"]), size_sol=size, pnl_sol=pnl, pnl_adj=adj,
            ret=float(adj / size), reason=r["reason"],
            hit15=1.0 if r["reason"] == "target" else 0.0,
            hw=(1.0 + mfe / 100.0) if mfe is not None else None,
            buys_1m=_f(r["buys_1m"]), sells_1m=_f(r["sells_1m"]),
            unique_buyers_1m=_f(r["unique_buyers_1m"]), snipers=_f(r["snipers"]),
            dev_share=_f(r["dev_share"]), net_sol_flow_1m=_f(r["net_sol_flow_1m"]),
            mcap_delta_60s=_f(r["mcap_delta_60s"]),
            age_s=_f(r["age_s"]), progress_pct=_f(r["progress_pct"]),
            real_sol=_f(r["real_sol"]), mcap_sol=_f(r["mcap_sol"]),
        ))
    return out


if __name__ == "__main__":
    P, R = load_paper(), load_real()
    print("papel elegivel: %d  (mints %d, dias %d)" % (len(P), len({x["mint"] for x in P}), len({x["day"] for x in P})))
    by = {}
    for x in P:
        by.setdefault((x["day"], x["arm"].split("/")[0]), 0)
        by[(x["day"], x["arm"].split("/")[0])] += 1
    for k in sorted(by):
        print("  %s %-14s %d" % (k[0], k[1], by[k]))
    print("real: %d" % len(R))
    for d in sorted({x["day"] for x in R}):
        print("  %s n=%d" % (d, sum(1 for x in R if x["day"] == d)))
