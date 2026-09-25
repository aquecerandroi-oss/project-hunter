# R78 — H-015: população (uma por mint, a primeira entrada; empate → real) e assinaturas a resolver.
import csv
import json
import os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))


def population(desk_only: bool = False) -> list[dict]:
    with open(os.path.join(HERE, "cache", "h015_pop.csv"), encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if desk_only:
        rows = [r for r in rows if (r["gate"] or "").startswith("fluxo_e_holders/")]
    rows.sort(key=lambda r: (r["entry_at"], r["lane"] != "real", r["bet_id"]))
    first: dict[str, dict] = {}
    for r in rows:
        first.setdefault(r["mint"], r)
    for r in first.values():
        r["cbj"] = json.loads(r["cb"]) if r["cb"] else {}
    return list(first.values())


if __name__ == "__main__":
    for desk in (False, True):
        pop = population(desk)
        sig = [r for r in pop if r["cbj"].get("create_signature")]
        print(f"{'porta da mesa' if desk else 'pista inteira'}: {len(pop)} mints; com create_signature {len(sig)};"
              f" por lane {Counter(r['lane'] for r in sig)}; por rs {Counter(r['rs'] for r in sig).most_common()}")
        print("   reason:", Counter(r["cbj"].get("reason") for r in sig).most_common(),
              "| early_slots vazios:", sum(1 for r in sig if not r["cbj"].get("early_slots")))
    with open(os.path.join(HERE, "cache", "sigs.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(sorted({r["cbj"]["create_signature"] for r in population() if r["cbj"].get("create_signature")})))
