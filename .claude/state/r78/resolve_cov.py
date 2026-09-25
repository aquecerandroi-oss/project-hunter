# R78 — cliente local da prova de cobertura: itens "mint|slot_real|create_sig" das resolvidas; cache em cache/cov.jsonl.
# uso: uv run --project C:/dev/project-hunter python resolve_cov.py [n_max] [rps]
import json
import os
import subprocess
import sys

from h015_var import resolved

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache", "cov.jsonl")
N = int(sys.argv[1]) if len(sys.argv) > 1 else 10_000
RPS = sys.argv[2] if len(sys.argv) > 2 else "8"

done = set()
if os.path.exists(CACHE):
    with open(CACHE, encoding="utf-8") as f:
        last = {o["mint"]: o for o in map(json.loads, f) if o.get("ok")}
    done = {m for m, o in last.items() if all(t.get("ok") for t in o["txs"]) and o["others_in_slot"] <= len(o["txs"])}
rows, _ = resolved()
items = [f"{r['mint']}|{r['real_slot']}|{r['cbj']['create_signature']}" for r in rows if r["mint"] not in done][:N]
print("a resolver:", len(items), file=sys.stderr)
if items:
    with open(os.path.join(HERE, "gtfa_tpl.py"), encoding="utf-8") as f:
        src = f.read().replace("__ITEMS__", json.dumps(items)).replace("__RPS__", RPS)
    p = subprocess.run(["ssh", "hunter-vps", "docker exec -i hunter-meme-worker-1 python -"], input=src,
                       capture_output=True, text=True, encoding="utf-8")
    with open(CACHE, "a", encoding="utf-8") as f:
        for ln in p.stdout.splitlines():
            if ln.startswith("{") and "_stats" not in ln:
                f.write(ln + "\n")
            elif "_stats" in ln:
                print(ln, file=sys.stderr)
    if p.returncode:
        print("rc", p.returncode, p.stderr[-300:].replace("api-key", "api-key<redigido>"), file=sys.stderr)
