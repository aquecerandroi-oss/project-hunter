# R78 — H-018: relatório. uv run --project C:/dev/project-hunter python .claude/state/r78/h018_run.py
import csv
import os
from datetime import timedelta
from decimal import Decimal

import numpy as np

from h018 import Pos, _ts, boot_diff, concurrent_pairs, cooldown_counterfactual, first_entries, load, perm_p, reentries

HERE = os.path.dirname(os.path.abspath(__file__))
B = 10_000


def rate50(ps: list[Pos]) -> float:
    return float(np.mean([p.r <= -0.5 for p in ps])) if ps else float("nan")


def verdict(n: int, d: float, lo: float, hi: float, ratio: float) -> str:
    """Errata do R76 (mesma redação da cláusula (a)): a letra 'IC sup > −0,01' sozinha dá NÃO CONFIRMA;
    REFUTA só quando o intervalo exclui o efeito (IC inf > −0,01)."""
    if n < 20:
        return f"LIMITE DE DADO (n = {n} < 20: registrar e não julgar)"
    if lo > -0.01:
        return "REFUTA (IC inf > −0,01: o intervalo exclui o efeito)"
    if hi > -0.01:
        return "NÃO CONFIRMA ((a) literal dispara: IC sup > −0,01; o intervalo não exclui o efeito)"
    if d <= -0.05 and hi < 0 and ratio >= 2:
        return "CONFIRMA"
    return "NÃO CONFIRMA"


def contrast(label: str, rq: list[Pos], ctl: list[Pos]) -> None:
    a = [(p.mint, p.r) for p in rq]
    b = [(p.mint, p.r) for p in ctl]
    if not rq or not ctl:
        print(f"  {label}: recompras {len(rq)} · controle {len(ctl)} — sem contraste")
        return
    d, lo, hi = boot_diff(a, b, n=B)
    pp = perm_p([x for _, x in a], [x for _, x in b], n=B)
    ra, rb = rate50(rq), rate50(ctl)
    ratio = ra / rb if rb > 0 else float("inf")
    print(f"  {label}: recompras n={len(rq)} (mints {len({p.mint for p in rq})}) média r {np.mean([p.r for p in rq]):+.4f}"
          f" perda≥50% {ra:.3f} | controle n={len(ctl)} média {np.mean([p.r for p in ctl]):+.4f} perda≥50% {rb:.3f}"
          f" | D {d:+.4f} IC95 [{lo:+.4f}, {hi:+.4f}] p_perm {pp:.4f} | razão perda≥50% {ratio:.2f}"
          f" → {verdict(len(rq), d, lo, hi, ratio)}")


def section(lane: str, rows: list[Pos]) -> None:
    print(f"\n## {lane}: {len(rows)} posições, {len({p.mint for p in rows})} mints")
    for prior in ("target", "gain"):
        tag = "PRIMÁRIA saída anterior alvo∧lucro" if prior == "target" else "SENSIBILIDADE saída anterior lucro (qualquer razão)"
        print(f"\n### {tag}")
        for scope in ("any", "same", "cross"):
            pairs = reentries(rows, scope, prior=prior)
            rq = [q for q, _ in pairs]
            ctl = first_entries(rows, "same" if scope == "same" else "any")
            ids = {q.bet_id for q in rq}
            ctl = [p for p in ctl if p.bet_id not in ids]
            contrast(f"escopo {scope}", rq, ctl)
            if scope == "any" and rq:
                t0 = min(q.entry_at for q in rq)
                contrast("  s1 controle desde a 1.ª recompra", rq, [p for p in ctl if p.entry_at >= t0])
                ms = {q.mint for q in rq}
                contrast("  s2 controle sem os mints recomprados", rq, [p for p in ctl if p.mint not in ms])
                if lane == "real" or len(pairs) <= 60:
                    for q, p in pairs:
                        cross = "cruzada" if p.rs != q.rs else "mesma"
                        print(f"    {q.symbol[:12]:12} {p.rs}→{q.rs} ({cross}) saída {p.exit_at:%m-%d %H:%M:%S} {p.exit_reason}"
                              f" {p.pnl:+.4f} → entrada +{(q.entry_at - p.exit_at).total_seconds():.0f}s {q.exit_reason}"
                              f" {q.pnl:+.4f} (r {q.r:+.3f})")
                print(f"    Σ pnl recompras {sum((q.pnl for q in rq), Decimal(0)):+.4f} SOL")


def counterfactual(rows: list[Pos]) -> None:
    print("\n## Contrafactual real — pausa de 300 s por mint depois de QUALQUER saída, os dois operadores")
    b_any, d_any = cooldown_counterfactual(rows, 300, "any")
    b_loss, d_loss = cooldown_counterfactual(rows, 300, "loss")
    tot = sum((p.pnl for p in rows), Decimal(0))
    print(f"PnL realizado {tot:+.4f} SOL em {len(rows)} posições")
    for name, bl, d in (("qualquer saída (proposta)", b_any, d_any), ("só perda (check 28, retroativo)", b_loss, d_loss)):
        print(f"\n### replay {name}: {len(bl)} bloqueadas, Δ {d:+.4f} SOL")
        for q, p in bl:
            print(f"    {q.symbol[:12]:12} {q.rs} {q.entry_at:%m-%d %H:%M:%S} pnl {q.pnl:+.4f} ← saída {p.rs}"
                  f" {p.exit_reason} {p.pnl:+.4f} há {(q.entry_at - p.exit_at).total_seconds():.0f}s")
    only_any = {q.bet_id for q, _ in b_any} - {q.bet_id for q, _ in b_loss}
    only_loss = {q.bet_id for q, _ in b_loss} - {q.bet_id for q, _ in b_any}
    print(f"\nIncremento sobre o check 28 (replay proposta − replay atual): Δ {d_any - d_loss:+.4f} SOL; "
          f"só na proposta {len(only_any)}, só na atual {len(only_loss)}")


def concurrency(rows: list[Pos], lane: str) -> None:
    pairs = [(a, b) for a, b in concurrent_pairs(rows) if {a.rs, b.rs} == {"operator/5", "operator/6"}]
    print(f"\n## Concorrência {lane}: entradas op5×op6 no mesmo mint com a outra posição ainda aberta: {len(pairs)}")
    s_first = sum((a.pnl for a, _ in pairs), Decimal(0))
    s_second = sum((b.pnl for _, b in pairs), Decimal(0))
    for a, b in pairs:
        print(f"    {a.symbol[:12]:12} {a.rs} {a.entry_at:%m-%d %H:%M:%S} {a.pnl:+.4f} | {b.rs} +{(b.entry_at - a.entry_at).total_seconds():.0f}s"
              f" {b.pnl:+.4f} {'mesma decisão' if a.origin == b.origin else ''}")
    print(f"    Σ primeira {s_first:+.4f} · Σ segunda {s_second:+.4f} · total {s_first + s_second:+.4f} SOL")


def stale_queue(path: str) -> None:
    """Real: entradas cuja proposta nasceu ANTES da saída anterior no mesmo mint e foi admitida DEPOIS dela
    (a fila `mint_busy` do auto_approve, até 60 s)."""
    with open(path, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["lane"] == "real"]
    print("\n## Fila mint_busy (real): proposta anterior à saída do mesmo mint, admitida depois dela")
    n = 0
    for q in rows:
        for p in rows:
            if p["mint"] == q["mint"] and p["bet_id"] != q["bet_id"] and \
                    _ts(q["features_end_time"]) < _ts(p["exit_at"]) <= _ts(q["decided_at"]):
                n += 1
                print(f"    {q['symbol'][:12]:12} {p['rule_set']} saída {p['exit_reason']} {float(p['pnl_sol']):+.4f} → {q['rule_set']}"
                      f" proposta {(_ts(q['decided_at']) - _ts(q['features_end_time'])).total_seconds():.1f}s velha, admitida"
                      f" +{(_ts(q['decided_at']) - _ts(p['exit_at'])).total_seconds():.1f}s depois da saída, pnl {float(q['pnl_sol']):+.4f}")
    print(f"    total {n}")


def main() -> None:
    path = os.path.join(HERE, "cache", "pop.csv")
    lanes = load(path, {"real": "decided_at"})  # §2c: no real a origem é a admissão
    for lane in ("real", "paper"):
        section(lane, lanes[lane])
    counterfactual(lanes["real"])
    concurrency(lanes["real"], "real")
    concurrency([p for p in lanes["paper"] if p.rs in ("operator/5", "operator/6")], "papel (sombras)")
    stale_queue(path)
    rq = [q for q, _ in reentries(lanes["real"], "any")]
    span = (max(p.entry_at for p in lanes["real"]) - min(p.entry_at for p in lanes["real"])).total_seconds() / 86400
    last2 = [q for q in rq if q.entry_at >= max(p.entry_at for p in lanes["real"]) - timedelta(days=2)]
    print(f"\n## Ritmo real: {len(rq)} recompras (primária) em {span:.1f} dias = {len(rq) / span:.2f}/dia; últimos 2 dias {len(last2)}")


if __name__ == "__main__":
    main()
