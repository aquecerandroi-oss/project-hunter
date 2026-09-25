# R78 — H-015: só a variável (sem desfechos). Resolução, concordância do slot inferido, distribuição.
import json
import os
from collections import Counter

import numpy as np

from h015 import sol_in_create_slot
from h015_pop import population

HERE = os.path.dirname(os.path.abspath(__file__))


def slots() -> dict[str, dict]:
    with open(os.path.join(HERE, "cache", "slots.jsonl"), encoding="utf-8") as f:
        return {o["sig"]: o for o in map(json.loads, f)}


def resolved(desk_only: bool = False, strict: bool = False) -> tuple[list[dict], Counter]:
    """Linhas da população com `x` (a variável) resolvida; `strict` = só `reason` null."""
    sl = slots()
    out, why = [], Counter()
    for r in population(desk_only):
        cb = r["cbj"]
        sig = cb.get("create_signature")
        if not sig:
            why["no_create_signature"] += 1
            continue
        if cb.get("reason") == "coverage_gap" or (strict and cb.get("reason") is not None):
            why["reason:" + str(cb.get("reason"))] += 1
            continue
        o = sl.get(sig) or {}
        x, how = sol_in_create_slot(cb, o.get("slot") if o.get("status") == "ok" else None)
        why[how] += 1
        if x is None:
            continue
        r["x"], r["how"], r["real_slot"] = x, how, o["slot"]
        out.append(r)
    return out, why


if __name__ == "__main__":
    for desk, strict in ((False, False), (False, True), (True, False)):
        rows, why = resolved(desk, strict)
        tag = f"{'porta da mesa' if desk else 'pista inteira'}{' · só reason null' if strict else ''}"
        x = np.array([r["x"] for r in rows])
        inf = [r for r in rows if r["cbj"].get("creation_slot") is not None]
        agree = sum(int(r["cbj"]["creation_slot"]) == int(r["real_slot"]) for r in inf)
        print(f"{tag}: resolvidas {len(rows)} | {dict(why)}")
        print(f"   slot inferido = real em {agree} de {len(inf)}; zeros {int((x == 0).sum())} ({(x == 0).mean():.1%});"
              f" quantis 1/3, 1/2, 2/3, 0,9: {np.quantile(x, [1/3, .5, 2/3, .9]).round(3).tolist()}; máx {x.max():.2f}")
        print(f"   por lane {Counter(r['lane'] for r in rows)}")
