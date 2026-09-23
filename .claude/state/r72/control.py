"""R72 — decomposicao do unico sinal aparente: giro ou ausencia de trailing?

Nas celulas de X alto a politica quase nao dispara (27 ciclos em 76 posicoes a X=12 %/N=30 s).
Quando nao dispara, o braco de giros e simplesmente "segurar ate aos 300 s sem trailing" — e
isso ja foi medido em R64/R65. Este modulo separa as duas coisas:

  A) braco de giros completo
  B) controlo SEGURAR: sem alvo, sem trailing, sai aos 300 s (zero giros)
  C) regra atual (alvo 1,15x / trailing 10 % / 300 s)

e reparte o braco A entre as posicoes onde houve >= 1 giro e as que nunca giraram.
"""

from __future__ import annotations

from decimal import Decimal

from load import load_all, resolvable
from run import boot_ci, pct, perm_p
from sim import per_sol, simulate_current, simulate_scalp


def hold_only(P):
    """Segurar ate aos 300 s: alvo inatingivel e trailing de 100 % nunca disparam."""
    return simulate_current(P, target_x=Decimal("999"), trailing=Decimal("0.999"))


def main():
    real, paper = load_all()
    for name, pop in (("REAIS", real), ("PAPEL", paper)):
        elig = [P for P in pop if resolvable(P)]
        cur = {P["pid"]: per_sol(simulate_current(P), P) for P in elig}
        hold = {P["pid"]: per_sol(hold_only(P), P) for P in elig}
        ok = [P for P in elig if cur[P["pid"]] is not None and hold[P["pid"]] is not None]
        dh = [hold[P["pid"]] - cur[P["pid"]] for P in ok]
        lo, hi = boot_ci(dh, [P["mint"] for P in ok])
        print("\n%s (n=%d)" % (name, len(ok)))
        print("  regra atual .............. %s por SOL" % pct(sum(cur[P["pid"]] for P in ok) / len(ok)))
        print("  SEGURAR 300 s (sem trailing) %s por SOL" % pct(sum(hold[P["pid"]] for P in ok) / len(ok)))
        print("  D (segurar - regra) ...... %s  IC95 [%s, %s]  p=%.4f"
              % (pct(sum(dh) / len(dh)), pct(lo), pct(hi), perm_p(dh)))
        for x, n in ((Decimal(12), 30.0), (Decimal(8), 30.0), (Decimal(3), 30.0)):
            girou, parado = [], []
            for P in ok:
                a = simulate_scalp(P, x, n)
                pa = per_sol(a, P)
                if pa is None:
                    continue
                (girou if a["cycles"] >= 1 else parado).append(
                    (P, pa, pa - cur[P["pid"]], pa - hold[P["pid"]]))
            print("  X=%s%% N=%.0fs: girou em %d de %d posicoes" % (x, n, len(girou), len(ok)))
            for lbl, grp in (("  girou ", girou), ("  parado", parado)):
                if not grp:
                    continue
                print("    %s n=%3d | braco %s | vs regra %s | vs SEGURAR %s"
                      % (lbl, len(grp), pct(sum(g[1] for g in grp) / len(grp)),
                         pct(sum(g[2] for g in grp) / len(grp)),
                         pct(sum(g[3] for g in grp) / len(grp))))


if __name__ == "__main__":
    main()
