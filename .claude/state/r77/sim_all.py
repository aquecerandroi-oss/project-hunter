"""R77 / H-016 — simula controlo + 8 células (1,6 s e 5 s) + sensibilidades para cada decisão elegível.

Saída: `cache/arms.jsonl` (uma linha por decisão, censuradas incluídas com o motivo).
Uso: cd .claude/state/r77 && uv run --project ../../.. python sim_all.py
"""

from __future__ import annotations

import csv
import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from chain import OUR, build_chain, load_photos, load_tape, max_gap, state_at, trades_in, ts
from entry import Dip, find_trigger, simulate_arm

HERE = Path(__file__).resolve().parent
XS, WS, LATS = (3, 5, 8, 12), (20, 60), (1.6, 5.0)
HORIZON_S, MAX_GAP_S, MIN_TRADES = 370, 60.0, 3


def first_per_mint(rows):
    best: dict = {}
    for r in rows:
        k = (r["pop"], r["mint"])
        key = (ts(r["proposed_at"]), r["bet_id"])
        if k not in best or key < best[k][0]:
            best[k] = (key, r)
    return sorted((v[1] for v in best.values()), key=lambda r: (r["pop"], ts(r["proposed_at"])))


def size_lamports(r) -> int:
    params = json.loads(r["params"] or "{}")
    entry = json.loads(r["entry_json"] or "{}")
    s = params.get("size_sol") or entry.get("sol_spent") or "0.07"
    return int(Decimal(str(s)) * 10**9)


def own_fills(path: Path = HERE / "own.csv") -> dict[str, list[dict]]:
    """As nossas trocas a partir dos fills persistidos (`meme_live_positions.entry/exit`).

    Onde a fita tem o nosso fill, ele bate ao lamport com o registo (144 de 144); 50 pernas faltam no
    arquivo por polling e, sem elas, a foto seguinte carregava a nossa compra sem desconto (Astra, emenda 1).
    """
    out: dict[str, list[dict]] = {}
    with path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            for leg in ("entry_json", "exit_json"):
                e = json.loads(r[leg] or "{}")
                if not e.get("signature") or not e.get("slot"):
                    continue
                out.setdefault(r["mint"], []).append(dict(
                    bt=ts(e["block_time"]), slot=int(e["slot"]), sig=e["signature"], ei=0, trader=OUR,
                    side="buy" if e.get("is_buy") else "sell", sol=int(e["sol_amount"]),
                    tok=int(e["token_amount"])))
    return out


def with_own(tape: list[dict], own: list[dict]) -> tuple[list[dict], int]:
    have = {t["sig"] for t in tape if t["trader"] == OUR}
    add = [o for o in own if o["sig"] not in have]
    return tape + add, len(add)


def arm(pts, t0, t_trig, size, lat, min_index, k=None):
    a = simulate_arm(pts, t_trig, size, lat, min_index=min_index)
    out = dict(ok=a["ok"])
    if a["ok"]:
        land = a["exit_trigger"] + timedelta(seconds=lat)
        out.update(ret=a["ret"], reason=a["reason"], peak_le_cost=a["peak_le_cost"],
                   pnl_lamports=int(a["final"]) - size,
                   hold_s=(a["exit_trigger"] - a["landing"]).total_seconds(),
                   gap=max_gap(pts, t0, (land - t0).total_seconds()))
    if k is not None:
        p = pts[k]
        out.update(entered=True, trig_kind=p.kind, trig_last_in_slot=p.last_in_slot)
    return out


def simulate(r, tape, photos) -> dict:
    t0 = ts(r["proposed_at"])
    size = size_lamports(r)
    rec = dict(pop=r["pop"], mint=r["mint"], sym=(r["symbol"] or r["mint"][:6]).strip(), series=r["series"],
               rule_set=r["rule_set"], bet_id=r["bet_id"], t0=t0.isoformat(), size=size, censor=None)
    if r["pop"] == "real":
        spent = int(r["spent_lamports"])
        hw = Decimal(r["high_water_sol"] or "0")
        rec.update(hist_pnl=r["pnl_sol"], hist_ret=float(Decimal(r["pnl_sol"]) / (Decimal(spent) / 10**9)),
                   hist_never_above=hw <= Decimal(spent) / 10**9)
    pts, info = build_chain(t0, tape, photos)
    rec["chain"] = {k: v for k, v in info.items() if k != "censor"}
    if pts is None or info["censor"]:
        rec["censor"] = info["censor"]
        return rec
    if trades_in(tape, t0, 300) < MIN_TRADES:
        rec["censor"] = "menos_de_3_trocas"
        return rec
    rec["gap370_s"] = max_gap(pts, t0, HORIZON_S)  # sensibilidade (emenda 5 original)
    i0 = state_at(pts, t0)
    arms: dict = {}
    for lat in LATS:
        arms[f"ctrl@{lat}"] = arm(pts, t0, t0, size, lat, i0)
    for x in XS:
        for w in WS:
            variants = [("main", Dip(x), LATS), ("photos", Dip(x, use_photos=True), (1.6,)),
                        ("slotfinal", Dip(x, slot_final=True), (1.6,))]
            for tag, pol, lats in variants:
                k = find_trigger(pts, t0, pol, w)
                for lat in lats:
                    key = f"{tag}:{x}:{w}@{lat}"
                    if k is None:
                        arms[key] = dict(ok=True, entered=False, ret=0.0, pnl_lamports=0, gap=max_gap(pts, t0, w))
                    else:
                        arms[key] = arm(pts, t0, pts[k].t, size, lat, k, k)
                        arms[key]["delay_s"] = (pts[k].t - t0).total_seconds()
    # só a linha principal censura a decisão; uma falha numa sensibilidade fica marcada nesse braço (Astra, r2)
    bad = [k for k, v in arms.items() if not v["ok"] and k.startswith(("ctrl@", "main:"))]
    if bad:
        rec["censor"] = "sim_nao_ok:" + ",".join(bad[:3])
        return rec
    rec["arms"] = arms
    return rec


def main() -> None:
    with (HERE / "pop.csv").open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    firsts = first_per_mint(rows)
    tapes, photos, own = load_tape(), load_photos(), own_fills()
    out = HERE / "cache" / "arms.jsonl"
    n = 0
    with out.open("w", encoding="utf-8") as f:
        for r in firsts:
            key = (r["pop"], r["mint"])
            tape, n_add = with_own(tapes.get(key, []), own.get(r["mint"], []))
            rec = simulate(r, tape, photos.get(key, []))
            rec["own_injected"] = n_add
            rec["our_buy_in_archive"] = any(t["trader"] == OUR and t["side"] == "buy"
                                            for t in tapes.get(key, []))
            f.write(json.dumps(rec, default=str) + "\n")
            n += 1
    print(f"{n} decisões escritas em {out}")


if __name__ == "__main__":
    main()
