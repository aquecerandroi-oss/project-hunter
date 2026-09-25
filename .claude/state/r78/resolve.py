# R78 — cliente local: pula o que já está em cache/slots.jsonl, manda o resto ao contêiner.
# uso: uv run --project C:/dev/project-hunter python resolve.py [lista] [rps]
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache", "slots.jsonl")
LIST = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "cache", "sigs.txt")
RPS = sys.argv[2] if len(sys.argv) > 2 else "8"

done = set()
if os.path.exists(CACHE):
    with open(CACHE, encoding="utf-8") as f:
        for ln in f:
            o = json.loads(ln)
            if o.get("status") in ("ok", "not_found"):
                done.add(o["sig"])
with open(LIST, encoding="utf-8") as f:
    sigs = [s for s in f.read().split() if s not in done]
print("a resolver:", len(sigs), file=sys.stderr)
if sigs:
    with open(os.path.join(HERE, "helius_tpl.py"), encoding="utf-8") as f:
        src = f.read().replace("__SIGS__", json.dumps(sigs)).replace("__RPS__", RPS)
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
