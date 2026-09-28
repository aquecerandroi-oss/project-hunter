"""R84 passo 3 — auditoria do dado SEM retorno: completude contra inventários históricos, cobertura temporal, fins de
série, lacunas longas, migrações documentadas e composição do universo. Lê só nomes, datas, existência de vela e
volume (o volume decide o universo; nenhum preço de desfecho é calculado aqui). Saída: audit.txt.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
CACHE = HERE / "cache"
sys.path.insert(0, str(HERE))
from config import AS_OF_DAY, EXCLUDED, LAST_T_DAY, day_iso, load_rows, trading_symbols  # noqa: E402


def main() -> None:
    out: list[str] = []
    csv_path = CACHE / "candles_1d.csv"
    out.append(f"candles_1d.csv sha256 {hashlib.sha256(csv_path.read_bytes()).hexdigest()}")
    rows = load_rows()
    by: dict[str, set[int]] = defaultdict(set)
    for s, d, *_ in rows:
        by[s].add(d)
    src = Counter(r["source"] for r in csv.DictReader(csv_path.open(encoding="utf-8")))
    out.append(f"velas finais (< {day_iso(AS_OF_DAY)}): {len(rows)} em {len(by)} símbolos; fontes {dict(src)}")
    ours = set(json.load((CACHE / "archive_families.json").open(encoding="utf-8"))["data/spot/daily/klines/"])
    ours |= {s for s in (CACHE / "archive_symbols.txt").read_text(encoding="utf-8").split() if s.endswith("USDT")}
    ours |= set(trading_symbols(all_status=True))
    no_data = sorted(s for s in ours if s not in by and len(s) > 4)
    out.append(f"pares no inventário sem nenhuma vela final: {len(no_data)} {no_data[:40]}")

    # --- inventários históricos (Wayback): completude e cobertura temporal
    missing: dict[str, list[str]] = defaultdict(list)
    cover_bad: list[str] = []
    n_snap = n_checked = 0
    for f in sorted((CACHE / "wayback").glob("*.txt")):
        ts = f.name[:8]
        day = (dt.date(int(ts[:4]), int(ts[4:6]), int(ts[6:8])) - dt.date(1970, 1, 1)).days
        n_snap += 1
        for line in f.read_text(encoding="utf-8").splitlines():
            sym, st = line.split(" ", 1)
            if sym not in by:
                missing[sym].append(f.name[:8] + ":" + f.name[15:40])
                continue
            if st == "TRADING" and day < AS_OF_DAY:
                n_checked += 1
                if not any(d in by[sym] for d in range(day - 3, day + 4)):
                    cover_bad.append(f"{sym}@{ts}")
    yrs = Counter(f.name[:4] for f in (CACHE / "wayback").glob("*.txt"))
    out.append(f"cópias históricas lidas: {n_snap} (por ano {sorted(yrs.items())}); pares nelas que NÃO estão no nosso dado: {len(missing)}")
    for s, where in sorted(missing.items()):
        out.append(f"  - {s}: {len(where)} cópias, 1.ª {where[0]}")
    out.append(f"cobertura: {n_checked} (par TRADING × cópia) conferidos; sem vela real em ±3 d: {len(cover_bad)} {cover_bad[:30]}")

    # --- por mês: pares com vela
    per_month: Counter[str] = Counter()
    for s, days in by.items():
        for m in {day_iso(d)[:7] for d in days}:
            per_month[m] += 1
    out.append("pares USDT com vela por mês (jan/jul): " + " ".join(f"{m}:{per_month[m]}" for m in sorted(per_month) if m[5:] in ("01", "07")))

    # --- fins de série e lacunas longas
    trading = set(trading_symbols())
    ends = sorted((max(d), s) for s, d in by.items() if s not in trading)
    ends_by_month = Counter(day_iso(e)[:7] for e, _ in ends)
    out.append(f"símbolos não TRADING hoje: {len(ends)}; fins por mês (top 8): {ends_by_month.most_common(8)}")
    end_aug31 = [s for e, s in ends if day_iso(e) == "2026-08-31"]
    out.append(f"fins exatamente em 2026-08-31 (suspeita de fim de arquivo): {end_aug31}")
    trading_stale = sorted((day_iso(max(by[s])), s) for s in trading if s in by and max(by[s]) < AS_OF_DAY - 3)
    out.append(f"TRADING hoje mas sem vela nos últimos 3 d: {trading_stale}")
    gaps = []
    for s, days in by.items():
        ds = sorted(days)
        for a, b in zip(ds, ds[1:], strict=False):
            if b - a - 1 >= 1:
                gaps.append((b - a - 1, s, day_iso(a), day_iso(b)))
    out.append(f"lacunas internas (≥ 1 d): {len(gaps)}; por tamanho: {Counter(min(g[0], 30) for g in gaps).most_common(12)}")
    for g in sorted(gaps, reverse=True):
        if g[0] >= 14:
            out.append(f"  LACUNA ≥ 14 d: {g[1]} {g[2]} → {g[3]} ({g[0]} d)")

    # --- migrações documentadas no catálogo e se o símbolo antigo estava no universo nas últimas 3 semanas de vida
    cat = json.loads((CACHE / "all_assets.json").read_text(encoding="utf-8"))["data"]
    mig = sorted({(a["oldAssetCode"], a["newAssetCode"]) for a in cat
                  if a.get("oldAssetCode") and a.get("newAssetCode") and a["oldAssetCode"] != a["newAssetCode"]})
    from analyze import mondays
    from engine import week
    from gaps import KEEP_TOGETHER
    from panel import build_panel

    from config import apply_links

    lrows, ltrading = apply_links(rows, trading)
    p = build_panel(lrows, ltrading, EXCLUDED, AS_OF_DAY, keep_together=KEEP_TOGETHER)
    ts = mondays(p, LAST_T_DAY)
    top_by_t = {t: {p.ids[i] for i in week(p, t, 14).top_ids} for t in ts}
    out.append(f"semanas: {len(ts)} de {day_iso(p.day0 + ts[0])} a {day_iso(p.day0 + ts[-1])}")
    ever = Counter(s for v in top_by_t.values() for s in v)
    out.append(f"séries que já estiveram no top-20 (universo): {len(ever)}")
    for old, new in mig:
        so, sn = old + "USDT", new + "USDT"
        if so not in by:
            continue
        end_col = max(by[so]) - p.day0
        near = [t for t in ts if end_col - 21 <= t <= end_col + 1]
        inu = [day_iso(p.day0 + t) for t in near if any(x.split("#")[0] == so for x in top_by_t[t])]
        out.append(f"  migração {so} → {sn} (novo com dado: {sn in by}); fim {day_iso(max(by[so]))}; no universo nas "
                   f"semanas finais: {inu or 'não'}")
    ended_in_u = []
    for i, sid in enumerate(p.ids):
        if p.ended[i]:
            near = [t for t in ts if p.last[i] - 21 <= t <= p.last[i] + 1 and sid in top_by_t[t]]
            if near:
                ended_in_u.append(f"{sid} fim {day_iso(p.day0 + p.last[i])}")
    out.append(f"séries com fim que estavam no universo nas 3 semanas finais: {len(ended_in_u)} {ended_in_u}")

    # --- exclusões presentes
    bases = {s[:-4] for s in by}
    out.append(f"excluídos presentes no dado: {sorted(bases & EXCLUDED)}")
    out.append(f"excluídos da lista sem dado (inofensivos): {sorted(EXCLUDED - bases)}")
    out.append(f"último T {day_iso(LAST_T_DAY)}")
    (HERE / "audit.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
