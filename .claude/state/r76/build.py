"""R76 — monta uma linha por decisão (população principal + as 95 decisões reais) em `rows.json`.

uso: uv run --no-project python build.py candidates   # escreve as listas para identity/xfers
     uv run --no-project python build.py               # constrói rows.json com a regra de câmbio
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import load as L  # noqa: E402

HERE = L.HERE
DRIP = (Decimal("0.01"), Decimal("0.35"))


def proxies(tape, dec, creator: str | None) -> dict[str, object]:
    """Grandezas que o executor calcula da própria fita WS, sem RPC, no instante da decisão."""
    pre = [t for t in tape if t.block_time < dec and t.trader != L.OUR]
    buys = [t for t in pre if t.side == "buy"]
    sold = {t.trader for t in pre if t.side == "sell"}
    buyers = {t.trader for t in buys}
    nbuys = Counter(t.trader for t in buys)
    sizes = [t.sol for t in buys if t.trader != creator]
    lo, hi = (int(x * 10**9) for x in DRIP)
    cslot = min((t.slot for t in tape), default=None)
    bundle = {t.trader for t in tape if t.slot == cslot and t.side == "buy"}
    mean = statistics.fmean(sizes) if sizes else 0.0
    return {
        "p_buyers": len(buyers),
        "p_holders": len(buyers - sold),
        "p_holders_frac": (len(buyers - sold) / len(buyers)) if buyers else None,
        "p_cv": (statistics.pstdev(sizes) / mean) if len(sizes) >= 2 and mean > 0 else None,
        "p_drip_frac": (sum(1 for s in sizes if lo <= s <= hi) / len(sizes)) if sizes else None,
        "p_bundle": len(bundle),
        "p_bundle_sol": float(sum(t.sol for t in tape if t.slot == cslot and t.side == "buy")) / 1e9,
        "p_single_nosell_frac": (sum(1 for b in buyers if nbuys[b] == 1 and b not in sold) / len(buyers))
        if buyers else None,
    }


def decisions():
    rows = L.load_rows()
    chosen = L.one_per_mint(rows)
    live = [r for r in rows if r["lane"] == "live"]
    return chosen, live


def load_exchange():
    ident: dict[str, dict] = {}
    p = HERE / "cache_identity.jsonl"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            o = json.loads(line)
            ident[o["w"]] = o
    xf: dict[str, dict] = {}
    for p in sorted(HERE.glob("cache_xfers*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            o = json.loads(line)
            if o.get("ok"):
                xf[o["funder"]] = o
    return ident, xf


def labelled(o: dict | None) -> bool:
    if not o or not o.get("ok"):
        return False
    text = " ".join(str(o.get(k) or "") for k in ("category", "type", "name"))
    return re.search(r"exchange", text, re.I) is not None


def main(mode: str) -> None:
    tape = L.r73.load_tape(HERE / "tape.csv")
    funding, fstatus = L.load_funding()
    chosen, live = decisions()
    if mode == "candidates":
        cand: dict[str, int] = {}
        for r in chosen + live:
            dec = L.ts(r["decided_at"])
            b = L.pre_decision_buyers(tape.get(r["mint"], []), dec)
            for f, n in Counter(L.resolved(b, funding, dec).values()).items():
                if n >= 2:
                    cand[f] = max(cand.get(f, 0), int(dec.timestamp()) + 1)
        (HERE / "cand_identity.txt").write_text("\n".join(sorted(cand)) + "\n", encoding="utf-8")
        (HERE / "cand_xfers.txt").write_text("\n".join(f"{f}|{c}" for f, c in sorted(cand.items())) + "\n",
                                             encoding="utf-8")
        print(f"candidatos (financiador com ≥ 2 compradoras numa decisão): {len(cand)}; status gtfa {dict(fstatus)}")
        return
    ident, xf = load_exchange()
    t72 = L.r72.load_tape(str(HERE / "tape.csv"))
    s72 = L.r72.load_snaps(str(HERE / "snap.csv"))
    out = []
    for group, rs in (("pop", chosen), ("live_all", live)):
        for r in rs:
            m, dec = r["mint"], L.ts(r["decided_at"])
            tp = tape.get(m, [])
            cut = int(dec.timestamp())
            status = {}

            def rule(f, kind, cut=cut, status=status):
                if f not in status:
                    status[f] = L.exchange_status(xf.get(f), cut, labelled(ident.get(f)))
                s = status[f]
                return {"main": s == "exchange", "s1": s != "not", "s2": labelled(ident.get(f))}[kind]

            buyers = L.pre_decision_buyers(tp, dec)
            net = {k: L.network(buyers, funding, dec, is_exchange=lambda f, k=k: rule(f, k))
                   for k in ("main", "s1", "s2")}
            nasce, rec = L.birth_coverage(tp, r)
            P = L.make_P(r)
            oc: dict[str, object] = {"sim_ret": None, "censor": "no_entry_snapshot"}
            if P is not None:
                L.r72.build_path(P, t72, s72)
                oc = L.outcome(P)
            entry = P["entry_bt"] if P else L.ts(r["entry_at"])
            dump, worst = L.coordinated_dump(tp, entry)
            size = Decimal(r["size_sol"]) if r["size_sol"] else None
            pnl = Decimal(r["pnl_sol"]) if r["pnl_sol"] else None
            out.append({
                "group": group, "lane": r["lane"], "bet_id": r["bet_id"], "mint": m,
                "symbol": r["symbol"] or m[:6], "rule_set": r["rule_set"], "gate": r["gate"],
                "decided_at": dec.isoformat(), "dia": dec.date().isoformat(), "hora": dec.strftime("%Y-%m-%dT%H"),
                "exit_reason": r["exit_reason"], "size_sol": str(size), "pnl_sol": str(pnl),
                "real_ret": float(pnl / size) if (pnl is not None and size) else None,
                "nasce": nasce, "reconcilia": rec, "eligible": bool(nasce and rec),
                "ambiguous": L.ambiguous_buyers(tp, dec),
                **{("" if k == "main" else k + "_") + kk: v for k, n in net.items() for kk, v in n.items()},
                "creator_pct": L.creator_share(buyers, funding, dec, r["creator"] or None),
                "creator_is_buyer": (r["creator"] in buyers) if r["creator"] else None,
                "dump": dump, "dump_sellers": worst, **oc, **proxies(tp, dec, r["creator"] or None),
            })
    (HERE / "rows.json").write_text(json.dumps(out, default=str), encoding="utf-8")
    ex = Counter()
    for f in {f for o in out for f in [o.get("top_funder")] if f}:
        ex[labelled(ident.get(f))] += 1
    print(f"linhas {len(out)}; status gtfa {dict(fstatus)}; financiadores-topo rotulados câmbio {dict(ex)}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "build")
