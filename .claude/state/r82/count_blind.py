# R82 — contagem cega (nenhum PnL impresso): população, classes do braço e do controle, pares.
# cd .claude/state/r82 && uv run --project C:/dev/project-hunter python count_blind.py
from collections import Counter

from h017 import classify_arm, classify_ctl, load, population, ts

rows = load()
pop, cnt = population(rows)
print(f"extraído {rows[0]['extracted_at']}; armações 1.ª por mint {len(rows)}; população {dict(cnt)}")
print(f"t0 de {pop[0]['t0']} a {pop[-1]['t0']}")
print("rearmação (n_armed > 1):", sum(int(r["n_armed"]) > 1 for r in rows),
      "| 1.ª armação do mint antes do início:", sum(ts(r["first_t0_any"]) < ts(r["t0"]) for r in rows))
ca = Counter(classify_arm(r)[0] for r in pop)
cc = Counter(classify_ctl(r)[0] for r in pop)
print("braço:", dict(ca))
print("controle:", dict(cc))
both = Counter((classify_arm(r)[1] is not None, classify_ctl(r)[1] is not None) for r in pop)
print("resolvido (braço, controle):", dict(both))
print("pares resolvidos:", both[(True, True)])
print("série da proposta do controle:", dict(Counter(r["ctl_series"] or "-" for r in pop)))
print("decided_by controle:", dict(Counter(r["ctl_decided_by"] or "-" for r in pop)), "| posições reais do controle:",
      sum(int(r["ctl_live_n"] or 0) for r in pop))
print("recusas do controle em (mint,t0) quando ausente:",
      dict(Counter(r["ctl_refusals_t0"] or "-" for r in pop if not r["ctl_prop"])))
print("1.ª proposta do controle quando ausente em t0:",
      [(r["symbol"], r["ctl_first_fet"], r["ctl_first_series"], r["ctl_first_status"]) for r in pop if not r["ctl_prop"]])
print("pares por dia UTC:", dict(Counter(r["t0"][:10] for r in pop
                                        if classify_arm(r)[1] is not None and classify_ctl(r)[1] is not None)))
print("op5 status na mesma decisão:", dict(Counter(r["op_prop_status"] or "sem proposta" for r in pop)))
