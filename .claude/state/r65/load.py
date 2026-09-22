"""R65 - carrega as 87 posicoes reais fechadas, a fita e as fotos; reconstroi o caminho "segurar".

Metodo herdado de R62/R64 (`.claude/state/r64/load.py`): a partir das reservas exatas do fill de compra,
cada trade da fita soma/subtrai; cada foto `solana_rpc` com slot >= ultimo trade aplicado ressincroniza.
Dinheiro em Decimal/int de lamports; nada de float em PnL.
"""
import csv
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

csv.field_size_limit(10_000_000)

HERE = Path(__file__).resolve().parent
OUR = "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"
FEE = Decimal("0.0125")  # pump.fun 0,95 % + criador 0,30 %
BRT = timezone(timedelta(hours=-3))
HOLD = 300


def ts(s):
    s = (s or "").strip()
    if not s:
        return None
    if s.endswith("+00"):
        s += ":00"
    return datetime.fromisoformat(s.replace(" ", "T"))


def brt(d, fmt="%H:%M:%S"):
    return d.astimezone(BRT).strftime(fmt)


def net(vsol, vtok, amount):
    """Lamports liquidos de vender `amount` tokens nas reservas (vsol, vtok), menos a taxa de 1,25 %."""
    p = vsol - (vsol * vtok) // (vtok + amount)
    return int(Decimal(p) * (1 - FEE))


def _jload(s):
    try:
        return json.loads(s) if s else None
    except Exception:
        return None


def _flow(reasons):
    """Extrai as features de gate do `meme_proposals.reasons` (lista de dicts)."""
    out = {}
    for item in reasons or []:
        if not isinstance(item, dict):
            continue
        feat = item.get("feature")
        if item.get("rule") and "rule" not in out:
            out["rule"] = item["rule"]
        if feat == "age_s":
            out["age_s"] = Decimal(str(item.get("value")))
        elif feat == "curve_progress_pct":
            out["progress_pct"] = Decimal(str(item.get("value")))
        elif feat == "creator_net_seller":
            out["creator_net_seller"] = bool(item.get("value"))
        elif feat == "participation_pct":
            out["participation_pct"] = Decimal(str(item.get("value")))
        elif feat == "flow":
            for k in ("buys_1m", "sells_1m", "snipers", "unique_buyers_1m", "min_unique_buyers"):
                if item.get(k) is not None:
                    out[k] = int(item[k])
            for k in ("dev_share", "net_sol_flow_1m", "mcap_delta_60s", "max_sells_to_buys"):
                if item.get(k) is not None:
                    out[k] = Decimal(str(item[k]))
            for k in ("holders_rising", "progress_rising"):
                if item.get(k) is not None:
                    out[k] = bool(item[k])
        elif feat == "pedigree":
            for k in ("symbol_dup_24h", "creator_prior_mints_1h",
                      "creator_prior_dead_count", "creator_prior_dump_count"):
                if item.get(k) is not None:
                    out[k] = int(item[k])
    return out


def load_positions(path="positions.csv"):
    rows = list(csv.DictReader(open(HERE / path, newline="", encoding="utf-8")))
    out = []
    for r in rows:
        entry = _jload(r["entry_json"]) or {}
        exitj = _jload(r["exit_json"]) or {}
        quote = _jload(r["quote"]) or {}
        reasons = _jload(r["reasons"])
        params = _jload(r["params"]) or {}
        P = dict(
            pid=r["position_id"], proposal_id=r["proposal_id"], mint=r["mint"], sym=(r["symbol"] or "?").strip(),
            creator=r["creator"], token_created_at=ts(r["token_created_at"]),
            set="%s/%s" % (r["rule_set"], r["rule_set_version"]),
            entry_at=ts(r["entry_at"]), exit_at=ts(r["exit_at"]),
            spent=int(r["sol_spent_lamports"]), received=int(r["sol_received_lamports"]),
            pnl_sol=Decimal(r["pnl_sol"]), hw=Decimal(r["high_water_sol"] or 0),
            reason=r["exit_reason"], decided_at=ts(r["exit_decided_at"]),
            proposed_at=ts(r["proposed_at"]), qdecided_at=ts(r["decided_at"]),
            tokens=int(Decimal(str(entry.get("token_amount", 0)))),
            entry_slot=int(entry.get("slot") or 0),
            entry_bt=ts(entry.get("block_time")) or ts(r["entry_at"]),
            vsol_after=int(Decimal(str(entry.get("virtual_sol_reserves_after", 0)))),
            vtok_after=int(Decimal(str(entry.get("virtual_token_reserves_after", 0)))),
            exit_slot=int(exitj.get("slot") or 0),
            exit_bt=ts(exitj.get("block_time")) or ts(r["exit_at"]),
            exit_net=int(Decimal(str(exitj.get("sell_net_lamports", 0)))),
            quote_real_sol=Decimal(str(quote.get("real_sol_reserves", "0"))),
            quote_mcap_sol=Decimal(str(quote.get("mcap_sol", "0"))),
            quote_tokens=Decimal(str(quote.get("tokens", "0"))),
            quote_price=Decimal(str(quote.get("price_sol_per_token", "0"))),
            quote_observed_at=ts(quote.get("observed_at")),
            size_sol=Decimal(str(params.get("size_sol", "0.07"))),
            creator_sold_seen_at=ts(r["creator_sold_seen_at"]),
            creator_sold_fraction=Decimal(r["creator_sold_fraction"]) if r["creator_sold_fraction"] else None,
            g=_flow(reasons),
        )
        P["hold_s"] = (P["exit_at"] - P["entry_at"]).total_seconds()
        P["hour_brt"] = P["entry_at"].astimezone(BRT).hour
        P["day_brt"] = P["entry_at"].astimezone(BRT).date()
        out.append(P)
    counts = {}
    for P in out:
        counts[P["mint"]] = counts.get(P["mint"], 0) + 1
    idx = {}
    for P in out:
        if counts[P["mint"]] > 1:
            idx[P["mint"]] = idx.get(P["mint"], 0) + 1
            P["tag"] = "%s#%d" % (P["sym"], idx[P["mint"]])
        else:
            P["tag"] = P["sym"]
    return out


def load_tape(path="trades.csv"):
    trades = {}
    with open(HERE / path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            r["bt"] = ts(r["block_time"])
            r["slot"] = int(r["slot"])
            r["ei"] = int(r["event_index"])
            r["sol"] = int(r["sol_lamports"])
            r["tok"] = int(Decimal(r["token_amount"]) * 10**6)
            trades.setdefault(r["mint"], []).append(r)
    for m in trades:
        trades[m].sort(key=lambda r: (r["slot"], r["signature"], r["ei"]))
    return trades


def load_snaps(path="snaps.csv"):
    snaps = {}
    with open(HERE / path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            snaps.setdefault(r["mint"], []).append(dict(
                t=ts(r["observed_at"]),
                vsol=int(Decimal(r["virtual_sol_reserves"]) * 10**9),
                vtok=int(Decimal(r["virtual_token_reserves"]) * 10**6),
                real=Decimal(r["real_sol_reserves"] or 0),
                slot=int(r["slot"] or 0)))
    for m in snaps:
        snaps[m].sort(key=lambda r: r["t"])
    return snaps


def build_path(P, trades, snaps):
    tokens = P["tokens"]
    T = [r for r in trades.get(P["mint"], []) if r["trader"] != OUR and r["slot"] > P["entry_slot"]]
    S = [s for s in snaps.get(P["mint"], []) if s["t"] > P["entry_bt"]]
    vsol, vtok = P["vsol_after"], P["vtok_after"]
    P["resync_max_sol"] = 0.0
    P["n_trades"] = len(T)
    if not vsol or not vtok or not tokens:
        P["source"] = "none"
        P["path"] = []
        return []
    path = [(P["entry_bt"], vsol, vtok, net(vsol, vtok, tokens), None)]
    if T:
        P["source"] = "tape+photos"
        events = [(r["slot"], 0, r["bt"], r) for r in T] + \
                 [(s["slot"], 1, s["t"], s) for s in S if s["slot"] and s["slot"] >= P["entry_slot"]]
        events.sort(key=lambda e: (e[0], e[1], e[2]))
        last_slot = P["entry_slot"]
        for slot, kind, t, e in events:
            if kind == 0:
                if e["side"] == "buy":
                    vsol += e["sol"]
                    vtok -= e["tok"]
                else:
                    vsol -= e["sol"]
                    vtok += e["tok"]
                last_slot = slot
                path.append((t, vsol, vtok, net(vsol, vtok, tokens), e))
            else:
                if slot < last_slot:
                    continue
                P["resync_max_sol"] = max(P["resync_max_sol"], abs(e["vsol"] - vsol) / 1e9)
                vsol, vtok = e["vsol"], e["vtok"]
                path.append((t, vsol, vtok, net(vsol, vtok, tokens), None))
    else:
        P["source"] = "photos" if S else "none"
        for s in S:
            path.append((s["t"], s["vsol"], s["vtok"], net(s["vsol"], s["vtok"], tokens), None))
    path.sort(key=lambda p: p[0])
    P["path"] = path
    return path


def fill_after(path, t, tokens):
    last = path[0]
    for p in path:
        if p[0] <= t:
            last = p
        else:
            break
    return net(last[1], last[2], tokens)


def mfe_mae(P, horizon=HOLD):
    """MFE/MAE em % sobre o gasto, dentro de `horizon` s a partir do fill de compra."""
    spent = P["spent"]
    P["mfe"] = P["mae"] = P["mark300"] = P["mfe_to_exit"] = None
    P["mfe_t"] = P["mae_t"] = 0
    if not P["path"] or not spent:
        return P
    end = P["entry_bt"] + timedelta(seconds=horizon)
    best = worst = last = None
    for t, _vs, _vt, mark, _ in P["path"]:
        if t > end:
            break
        pct = (Decimal(mark) - spent) / spent * 100
        if best is None or pct > best:
            best, P["mfe_t"] = pct, (t - P["entry_bt"]).total_seconds()
        if worst is None or pct < worst:
            worst, P["mae_t"] = pct, (t - P["entry_bt"]).total_seconds()
        last = pct
    P["mfe"], P["mae"], P["mark300"] = best, worst, last
    bs = None
    for t, _vs, _vt, mark, _ in P["path"]:
        if t > P["exit_bt"]:
            break
        pct = (Decimal(mark) - spent) / spent * 100
        if bs is None or pct > bs:
            bs = pct
    P["mfe_to_exit"] = bs
    return P


def load_all():
    positions = load_positions()
    trades = load_tape()
    snaps = load_snaps()
    for P in positions:
        build_path(P, trades, snaps)
        mfe_mae(P)
    return positions, trades, snaps


if __name__ == "__main__":
    positions, trades, snaps = load_all()
    by_src = {}
    for P in positions:
        by_src[P["source"]] = by_src.get(P["source"], 0) + 1
    print("posicoes:", len(positions), "| PnL total:", sum(P["pnl_sol"] for P in positions))
    print("fonte:", by_src)
    for P in positions:
        print("%-14s %s %-12s %-12s src=%-12s tr=%4d mfe=%s mae=%s pnl=%s" % (
            P["tag"][:14], P["entry_at"].astimezone(BRT).strftime("%d/%m %H:%M:%S"), P["set"], P["reason"],
            P["source"], P["n_trades"],
            ("%+7.1f" % P["mfe"]) if P["mfe"] is not None else "    n/a",
            ("%+7.1f" % P["mae"]) if P["mae"] is not None else "    n/a", P["pnl_sol"]))
