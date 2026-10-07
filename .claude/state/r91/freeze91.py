"""R91 passo 3b — congela a lista elegível, os estratos e o suporte ANTES de ler desfechos.

Lê só cache/units.csv (sem pnl/exit/qualidade/status). Escreve cache/eligible.csv e freeze.txt.
Regime dos quatro parâmetros dos "subindo": histórico completo dessas chaves (avail2.txt) — só a
operator/5 mudou; janelas de transição da emenda 1 (2) saem e são contadas.
"""

from __future__ import annotations

import csv
import hashlib
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from stats91 import Units, supported_strata  # noqa: E402

UTC = timezone.utc
MIN_PER_ARM = 5
# avail2.txt: operator/5, todas as quatro chaves true -> false em 16/09 19:14:49–19:15:00 e de volta em 18/09 13:38:32–13:38:43
OP5_OFF = datetime(2026, 9, 16, 19, 14, 49, 908897, tzinfo=UTC)
OP5_ON = datetime(2026, 9, 18, 13, 38, 32, 732370, tzinfo=UTC)
WINDOWS = (
    (datetime(2026, 9, 16, 19, 14, 49, tzinfo=UTC), datetime(2026, 9, 16, 19, 30, 0, tzinfo=UTC)),
    (datetime(2026, 9, 18, 13, 38, 32, tzinfo=UTC), datetime(2026, 9, 18, 13, 53, 43, tzinfo=UTC)),
)
# avail0.txt: parâmetros vivos (req_h, or_flat, req_p, or_mcap) dos conjuntos sem histórico
LIVE = {
    "operator/4": "req_h,or_flat,req_p,or_mcap",
    "operator/6": "req_h,req_p",
    "flow_v2/1": "req_h,req_p",
    **{f"flow_v2/{v}": "req_h,or_flat,req_p,or_mcap" for v in (2, 3, 4, 5)},
    **{f"flow_v2/{v}": "or_flat,or_mcap" for v in (6, 7, 8, 9, 10)},
    "recuo_v1/1": "req_h,or_flat,req_p,or_mcap",
    "recuo_ctrl_v1/1": "req_h,or_flat,req_p,or_mcap",
}


def ts(x: str) -> datetime:
    x = x.strip().replace(" ", "T", 1)
    if x.endswith("+00"):
        x += ":00"
    return datetime.fromisoformat(x)


def regime(rs: str, at: datetime) -> str:
    if rs == "operator/5":
        return "nada" if OP5_OFF <= at < OP5_ON else "req_h,or_flat,req_p,or_mcap"
    return LIVE[rs]


def main() -> None:
    raw = list(csv.DictReader(open(HERE / "cache" / "units.csv", encoding="utf-8")))
    lines = [f"R91 congelamento — {datetime.now(UTC).isoformat(timespec='seconds')}"]
    lines.append(f"units.csv: {len(raw)} linhas, sha256 {hashlib.sha256((HERE / 'cache' / 'units.csv').read_bytes()).hexdigest()}")
    cens: Counter[str] = Counter()
    keep: list[dict[str, str]] = []
    late = 0
    for r in raw:
        at = ts(r["proposed_at"])
        if ts(r["features_end_time"]) > at:
            late += 1
        if r["snap_mayhem"] == "true" or r["tok_mayhem"] == "true":
            cens["Mayhem"] += 1
            continue
        if r["rs"] == "operator/5" and any(a <= at <= b for a, b in WINDOWS):
            cens["operator/5 em janela de transição"] += 1
            continue
        r["stratum"] = f"{r['rs']}|{regime(r['rs'], at)}"
        r["day"] = at.astimezone(UTC).date().isoformat()
        keep.append(r)
    lines.append(f"features_end_time > proposed_at: {late} (deve ser 0)")
    lines.append(f"saídas antes da variável: {dict(cens)}")
    agree = Counter()
    for r in keep:
        if r["f15_row"] == "t":
            agree["linhas"] += 1
            agree["h_igual"] += r["holders_rising"] == r["f15_holders_rising"]
            agree["p_igual"] += r["progress_rising"] == r["f15_progress_rising"]
    lines.append(f"concordância nas unidades com linha de 15 s ainda retida: {dict(agree)}")
    frozen_days = sorted({r["day"] for r in keep})
    lines.append(f"dias UTC com unidade (fronteira das metades): {len(frozen_days)} {frozen_days[0]}…{frozen_days[-1]}; "
                 f"1.ª metade = {frozen_days[: -(-len(frozen_days) // 2)][-1]} e antes")
    out: list[dict[str, str]] = []
    for var, col in (("H", "holders_rising"), ("P", "progress_rising")):
        rows = [r for r in keep if r[col] in ("true", "false")]
        nulls = Counter(r["rs"] for r in keep if r[col] not in ("true", "false"))
        u = Units(
            y=np.zeros(len(rows)), x=np.array([r[col] == "true" for r in rows]),
            s=np.array([r["stratum"] for r in rows], object), mint=np.array([r["mint"] for r in rows], object),
            day=np.array([r["day"] for r in rows], object), conj=np.array([r["rs"] for r in rows], object),
        )
        sup = supported_strata(u, min_per_arm=MIN_PER_ARM)
        lines.append(f"[{var}] nulos fora: {dict(nulls)}")
        per = Counter((r["stratum"], r[col]) for r in rows)
        for s in sorted({r["stratum"] for r in rows}):
            tag = "SUPORTADO" if s in sup else "sem suporte"
            lines.append(f"[{var}]   {s}: true {per[(s, 'true')]} · false {per[(s, 'false')]} — {tag}")
        el = [r for r in rows if r["stratum"] in sup]
        for arm in ("true", "false"):
            a = [r for r in el if r[col] == arm]
            lines.append(f"[{var}] braço {arm} (suportados): {len(a)} un · {len({r['mint'] for r in a})} mints · "
                         f"{len({r['day'] for r in a})} dias · pistas {dict(Counter(r['series'] for r in a))}")
        for r in el:
            out.append({"var": var, "x": r[col], **{k: r[k] for k in (
                "rs", "stratum", "mint", "proposal_id", "proposed_at", "day", "series", "bet_id", "entry_at")}})
    fields = ["var", "x", "rs", "stratum", "mint", "proposal_id", "proposed_at", "day", "series", "bet_id", "entry_at"]
    with open(HERE / "cache" / "eligible.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in sorted(out, key=lambda r: (r["var"], r["stratum"], r["mint"])):
            w.writerow(r)
    with open(HERE / "cache" / "days.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(frozen_days) + "\n")
    digest = hashlib.sha256((HERE / "cache" / "eligible.csv").read_bytes()).hexdigest()
    lines.append(f"eligible.csv: {len(out)} linhas (H+P), sha256 {digest}")
    (HERE / "freeze.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
