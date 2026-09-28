"""R83 — PÓS-HOC declarado (depois dos desfechos): a secundária d_low é só ATR%/retorno de 4 h?
Contraste alto − baixo de d_low com tercis dentro de (estratégia × tercil de ATR%) e (estratégia × tercil de ret 4 h).
Descritivo; não muda rótulo nenhum; serve para escrever (ou não) a próxima hipótese."""
from fractions import Fraction

from h023 import assign_extremes, guarded, load_features
from run import arms, fmt, quick, with_outcomes

pop, _ = load_features()
kept, _ = guarded(pop)
rows = [r for r in with_outcomes(kept) if r["family"] == "continuacao" and r["y"] is not None]
third = Fraction(1, 3)
for ctrl in ("atr_pct", "ret240"):
    usable = [r for r in rows if r[ctrl] is not None]
    lab = assign_extremes(usable, ctrl, third)
    strat = [dict(r, cell=f"{r['strategy']}|{ctrl}:{lb}") for r, lb in zip(usable, lab, strict=True)]
    a = arms(strat, "d_low", third, "cell", "y")
    print(fmt(f"d_low dentro de estratégia × tercil de {ctrl}", quick(a)))
    a2 = arms(strat, "d_high", third, "cell", "y")
    print(fmt(f"d_high dentro de estratégia × tercil de {ctrl}", quick(a2)))
for s in ("momentum", "volume_anomaly"):
    a = arms([r for r in rows if r["strategy"] == s], "d_low", third, "strategy", "y")
    print(fmt(f"d_low só {s}", quick(a)))
