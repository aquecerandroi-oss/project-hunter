"""R66 - o melhor corte de 2 variaveis chega ao lucro? (exploratorio, escolhido nestes dados)"""
import json, statistics
rows = json.load(open("rows.json"))
def q(key, p):
    v = sorted(r[key] for r in rows if r[key] is not None)
    return v[int(p*(len(v)-1))]
cuts = {
 "idade>=p67": lambda r: r["age_to_grad_s"] is not None and r["age_to_grad_s"] >= q("age_to_grad_s",2/3),
 "mcap<=p33": lambda r: r["mcap_sol"] <= q("mcap_sol",1/3),
 "buys>=p67": lambda r: r["buys"] is not None and r["buys"] >= q("buys",2/3),
 "top10>=p67": lambda r: r["top10"] is not None and r["top10"] >= q("top10",2/3),
 "snipers<=p33": lambda r: r["snipers"] is not None and r["snipers"] <= q("snipers",1/3),
}
print(f"{'corte':<34} {'n':>5} {'PnL/op':>10} {'total':>9} {'alvo %':>7} {'dias verdes':>12}")
def show(name, sel):
    s = [r for r in rows if sel(r)]
    if len(s) < 30: print(f"{name:<34} {len(s):>5}  (n insuficiente)"); return
    tot = sum(r["pnl"] for r in s)
    days = {}
    for r in s: days[r["day"]] = days.get(r["day"],0)+r["pnl"]
    green = sum(1 for v in days.values() if v>0)
    print(f"{name:<34} {len(s):>5} {tot/len(s):>10.6f} {tot:>9.3f} "
          f"{100*sum(r['target'] for r in s)/len(s):>6.1f}% {green:>6}/{len(days):<5}")
show("(todos)", lambda r: True)
for a in cuts:
    show(a, cuts[a])
ks = list(cuts)
for i in range(len(ks)):
    for j in range(i+1, len(ks)):
        show(f"{ks[i]} & {ks[j]}", lambda r, a=ks[i], b=ks[j]: cuts[a](r) and cuts[b](r))
show("idade>=p67 & mcap<=p33 & buys>=p67",
     lambda r: cuts["idade>=p67"](r) and cuts["mcap<=p33"](r) and cuts["buys>=p67"](r))
