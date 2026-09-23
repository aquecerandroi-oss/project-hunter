"""R72 passo 5 — o que um giro REALIZADO devolve, em multiplicador de tokens.

Teoria: por ciclo, tokens' / tokens = (1-c/2)^2 / (1-X) — lucro se X > c - c^2/4.
Pratica: o X que a mesa consegue nao e o X do gatilho; entre ver e pousar passam 1,6 s.
Este script mede o multiplicador realizado por ciclo, com atraso 0 s e com 1,6 s.
"""
from decimal import Decimal
from load import load_all, resolvable, sell_net
from sim import COST, LATENCY_S, simulate_scalp
from swings import quantiles

real, paper = load_all()
for name, pop in (("REAIS", real), ("PAPEL", paper)):
    elig = [P for P in pop if resolvable(P)]
    for x in (Decimal(3), Decimal(5), Decimal(8), Decimal(12)):
        for lat in (0.0, LATENCY_S):
            mults = []
            for P in elig:
                a = simulate_scalp(P, x, 60.0, latency_s=lat)
                for rb in a.get("rebuy_log", []):
                    # Astra (2.a ronda): o multiplicador do ciclo e tokens recomprados /
                    # tokens VENDIDOS naquela volta — nao o lote da entrada.
                    if rb["sold"] > 0:
                        mults.append(float(rb["tokens"]) / float(rb["sold"]))
            if not mults:
                continue
            p25, med, p75 = quantiles(mults)
            win = sum(1 for m in mults if m > 1) / len(mults) * 100
            print("%-6s X=%-3s atraso %.1fs | ciclos=%4d | mult. de tokens por ciclo:"
                  " p25=%.4f mediana=%.4f p75=%.4f | > 1 em %.0f %%"
                  % (name, x, lat, len(mults), p25, med, p75, win))
