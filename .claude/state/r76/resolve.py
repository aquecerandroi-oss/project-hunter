"""R76 — cliente local do resolvedor: pula o que já está no cache, manda o resto em lotes.

uso: uv run --no-project python resolve.py MODE RPS lista.txt [lote]
Cache: `cache_<MODE>.jsonl` (sem segredos: só endereços públicos e metadados on-chain).
Contabilidade de chamadas: `calls_<MODE>.jsonl` (uma linha `_stats` por lote).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


SUFFIX = os.environ.get("R76_WORKER", "")


def cached(mode: str) -> set[str]:
    done = set()
    lines = [ln for p in sorted(HERE.glob(f"cache_{mode}*.jsonl")) for ln in p.read_text(encoding="utf-8").splitlines()]
    for line in lines:
        try:
            o = json.loads(line)
        except ValueError:  # linha partida por escrita concorrente: a carteira volta à fila
            continue
        # só o que respondeu de facto; erro transitório (status None/429/5xx) volta à fila
        if "w" in o and (o.get("ok") or o.get("status") in ("truncated", "no_system_transfer_in", 404)):
            done.add(o["w"])
    return done


def run(mode: str, rps: float, wallets: list[str]) -> dict:
    src = (HERE / "resolver_tpl.py").read_text(encoding="utf-8")
    src = src.replace("__WALLETS__", json.dumps(wallets)).replace("__MODE__", mode).replace("__RPS__", str(rps))
    proc = subprocess.Popen(
        ["ssh", "hunter-vps", "docker exec -i hunter-meme-worker-1 python -"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
    )
    out, err = proc.communicate(src)
    stats: dict = {}
    with (HERE / f"cache_{mode}{SUFFIX}.jsonl").open("a", encoding="utf-8") as f:
        for line in out.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            o = json.loads(line)
            if "_stats" in o:
                stats = o["_stats"]
                continue
            f.write(json.dumps(o) + "\n")
    with (HERE / f"calls_{mode}{SUFFIX}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"n": len(wallets), "stats": stats, "rc": proc.returncode}) + "\n")
    if proc.returncode != 0:
        # stderr pode conter um traceback; nunca contém a chave (não é impressa), mas cortamos por via das dúvidas
        print("rc", proc.returncode, err[-400:].replace("api-key", "api-key<redigido>"), file=sys.stderr)
    return stats


def main() -> None:
    mode, rps, lst = sys.argv[1], float(sys.argv[2]), Path(sys.argv[3])
    batch = int(sys.argv[4]) if len(sys.argv) > 4 else 400
    want = [w.strip() for w in lst.read_text(encoding="utf-8").splitlines() if w.strip()]
    done = cached(mode)
    todo = [w for w in dict.fromkeys(want) if w not in done] if mode != "identity" else want
    if len(sys.argv) > 6:  # fatia k de n, para trabalhadores em paralelo com caches separados
        k, n = int(sys.argv[5]), int(sys.argv[6])
        todo = todo[k::n]
    print(f"{mode}: pedidas {len(want)}, a resolver {len(todo)}", flush=True)
    tot = {"calls": 0, "http429": 0, "errors": 0, "non200": 0}
    for i in range(0, len(todo), batch):
        s = run(mode, rps, todo[i:i + batch])
        for k in tot:
            tot[k] += int(s.get(k, 0))
        print(f"  lote {i // batch + 1}: {s}  acumulado {tot}", flush=True)
        if s.get("http429", 0) > 30 or not s:
            print("parado: 429 demais ou lote sem estatística", flush=True)
            break


if __name__ == "__main__":
    main()
