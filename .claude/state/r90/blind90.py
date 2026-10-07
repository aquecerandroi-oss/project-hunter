"""R90 / H-033 — passo CEGO: disponibilidade do OI em nível por sinal. Nenhum desfecho é lido
(só a nulidade de r_multiple, coluna has_r). Uso: uv run --no-sync python blind90.py"""

from __future__ import annotations

import csv
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).parent
SLOTS_7D = 7 * 24 * 12  # 2 016 buckets de 5 min
MIN_COVER = 0.90
LAG = timedelta(minutes=15)
MAX_STALE = timedelta(minutes=10)  # leitura corrente no máximo 10 min mais velha que obs - 15 min


def ts(v: str) -> datetime | None:
    if not v:
        return None
    v = v.replace(" ", "T")
    if v.endswith("+00"):
        v += ":00"
    return datetime.fromisoformat(v)


def reasons(r: dict[str, str]) -> list[str]:
    out: list[str] = []
    obs, em = ts(r["obs"]), ts(r["emitted_at"])
    assert obs is not None and em is not None
    if int(r["n"]) != 1440 or not r["close_last"] or not r["close_m240"]:
        out.append("velas_incompletas")
    elif ts(r["max_recv"]) > em:  # type: ignore[operator]
        out.append("velas_chegaram_depois")
    if not r["env_atr_pct"]:
        out.append("sem_atr")
    oi_ts = ts(r["oi_ts"])
    if oi_ts is None or not r["oi_cur"] or float(r["oi_cur"]) <= 0:
        out.append("oi_ausente")
    else:
        if oi_ts < obs - LAG - MAX_STALE:
            out.append("oi_velho")
        if not r["n_win"] or int(r["n_win"]) < MIN_COVER * SLOTS_7D:
            out.append("oi_janela_curta")
        c = ts(r["oi_created_at"])
        if c is not None and c > obs:
            out.append("oi_chegou_depois")
    if int(r["n_qv"] or 0) != 1440:
        out.append("qv_incompleto")
    return out


def main() -> None:
    rows = list(csv.DictReader((HERE / "cache" / "feat.csv").open(encoding="utf-8")))
    by: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        by[r["strategy"]].append(r)
    for strat, rs in sorted(by.items()):
        why = Counter()
        complete = []
        for r in rs:
            rr = reasons(r)
            for x in rr:
                why[x] += 1
            if not rr and r["has_r"] == "t":
                complete.append(r)
        units: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
        for r in complete:
            units[(r["market_id"], r["obs"])].append(r)
        days = sorted({k[1][:10] for k in units})
        mkts = {k[0] for k in units}
        rel = [math.log(float(v[0]["oi_cur"])) - float(v[0]["med_ln_oi"]) for v in units.values()]
        verified = sum(1 for v in units.values() if v[0]["oi_created_at"])
        print(f"## {strat}: terminais {len(rs)} | com R (nulidade) {sum(r['has_r'] == 't' for r in rs)}")
        print(f"   motivos de fora (não exclusivos): {dict(why)}")
        print(f"   completas: sinais {len(complete)} | unidades {len(units)} | dias {len(days)} | mercados {len(mkts)}")
        if days:
            print(f"   1.º/último dia {days[0]} → {days[-1]} | versões {dict(Counter(r['version'] for r in complete))}")
            rel.sort()
            q = lambda p: rel[min(len(rel) - 1, int(p * len(rel)))]  # noqa: E731
            print(f"   oi_rel7d: p10 {q(0.1):+.3f} p50 {q(0.5):+.3f} p90 {q(0.9):+.3f} | >0 {sum(x > 0 for x in rel)} ≤0 {sum(x <= 0 for x in rel)}")
            print(f"   leitura corrente com chegada verificada no outbox: {verified} unidades")
            per_mkt = Counter(k[0] for k in units)
            print(f"   maior mercado {max(per_mkt.values())} unidades | maior dia {max(Counter(k[1][:10] for k in units).values())}")


if __name__ == "__main__":
    main()
