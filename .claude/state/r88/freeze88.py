"""R88 passo 3b — congela a lista elegível e os limiares ANTES de ler desfechos.

Lê só cache/units.csv (sem pnl/exit/qualidade). Escreve cache/eligible.csv e freeze.txt
(sha256 da lista, limiar de A, grades, suporte por limiar e conjunto, checagem de instantes).
"""

from __future__ import annotations

import csv
import hashlib
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from stats88 import Units, supported_sets  # noqa: E402

GRID_B = (0.20, 0.25, 0.30, 0.35, 0.40, 0.45)
QS_A = (0.50, 0.60, 2 / 3, 0.75, 0.80)
MIN_SET_B = 30
MIN_PER_ARM_SET = 5


def ts(x: str) -> datetime | None:
    if not x:
        return None
    x = x.replace("Z", "+00:00")
    if len(x) >= 3 and x[-3] in "+-" and x[-6] != ":" and ":" not in x[-6:]:
        x = x + ":00"
    return datetime.fromisoformat(x)


def load() -> list[dict[str, str]]:
    with open(HERE / "cache" / "units.csv", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def eligible(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], Counter[str]]:
    out: list[dict[str, str]] = []
    cens: Counter[str] = Counter()
    for r in rows:
        m = r["medida"]
        if not r["share"]:
            cens[f"{m}: sem fatia"] += 1
            continue
        if not r["guard_n"] or int(r["guard_n"]) < 10:
            cens[f"{m}: guarda < 10"] += 1
            continue
        if m == "B":
            if r["tape_reason"]:
                cens["B: captura recusada"] += 1
                continue
            if r["ledger_reason"]:
                cens["B: livro não provado desde o nascimento"] += 1
                continue
        out.append(r)
    if True:  # conjuntos pequenos de B saem (contados)
        n_b = Counter(r["rs"] for r in out if r["medida"] == "B")
        small = {s for s, n in n_b.items() if n < MIN_SET_B}
        for r in [r for r in out if r["medida"] == "B" and r["rs"] in small]:
            cens[f"B: conjunto com < {MIN_SET_B} unidades ({r['rs']})"] += 1
        out = [r for r in out if not (r["medida"] == "B" and r["rs"] in small)]
    return out, cens


def units_of(rows: list[dict[str, str]], thr: float) -> Units:
    share = np.array([float(r["share"]) for r in rows])
    return Units(
        y=np.zeros(len(rows)),
        low=share <= thr,
        s=np.array([r["rs"] for r in rows], object),
        mint=np.array([r["mint"] for r in rows], object),
        day=np.array([r["proposed_at"][:10] for r in rows], object),
    )


def support_line(rows: list[dict[str, str]], thr: float) -> str:
    u = units_of(rows, thr)
    w = supported_sets(u, min_per_arm=MIN_PER_ARM_SET)
    hi = ~u.low
    return (
        f"  limiar {thr:.4f}: baixo {int(u.low.sum())} un/{len(set(u.mint[u.low]))} mints/"
        f"{len(set(u.day[u.low]))} dias · alto {int(hi.sum())} un/{len(set(u.mint[hi]))} mints/"
        f"{len(set(u.day[hi]))} dias · conjuntos suportados {w}"
    )


def main() -> None:
    rows = load()
    elig, cens = eligible(rows)
    lines = [f"R88 congelamento — {datetime.now().astimezone().isoformat(timespec='seconds')}"]
    lines.append(f"units.csv: {len(rows)} linhas, sha256 {hashlib.sha256((HERE / 'cache' / 'units.csv').read_bytes()).hexdigest()}")
    lines.append("censura pela variável/guarda: " + repr(dict(sorted(cens.items()))))
    # instantes: nada capturado depois da proposta
    late = Counter()
    for r in elig:
        p = ts(r["proposed_at"])
        for col in ("features_end_time", "tape_as_of", "tape_known_at"):
            t = ts(r[col])
            if t is not None and p is not None and t > p:
                late[f"{r['medida']}:{col} > proposed_at"] += 1
    lines.append("instantes depois da proposta (deve ser vazio): " + repr(dict(late)))
    thr: dict[str, float] = {}
    grids: dict[str, tuple[float, ...]] = {}
    for m in ("A", "B"):
        rs = sorted((r for r in elig if r["medida"] == m), key=lambda r: (r["rs"], r["mint"]))
        share = np.array([float(r["share"]) for r in rs])
        if m == "A":
            grids[m] = tuple(float(np.quantile(share, q)) for q in QS_A)
            thr[m] = float(np.quantile(share, 2 / 3))
        else:
            grids[m] = GRID_B
            thr[m] = 0.35
        lines.append(
            f"[{m}] unidades {len(rs)} · mints {len({r['mint'] for r in rs})} · dias "
            f"{len({r['proposed_at'][:10] for r in rs})} · por conjunto {dict(sorted(Counter(r['rs'] for r in rs).items()))}"
        )
        lines.append(f"[{m}] limiar congelado {thr[m]:.6f} · grade {[round(g, 6) for g in grids[m]]}")
        lines.append(f"[{m}] criador como maior comprador: {sum(r['is_creator'] == 'true' for r in rs)}")
        lines.append(f"[{m}] suporte (só a variável):")
        lines += [support_line(rs, g) for g in grids[m]]
    with open(HERE / "cache" / "eligible.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(elig[0].keys()))
        w.writeheader()
        for r in sorted(elig, key=lambda r: (r["medida"], r["rs"], r["mint"])):
            w.writerow(r)
    digest = hashlib.sha256((HERE / "cache" / "eligible.csv").read_bytes()).hexdigest()
    lines.append(f"eligible.csv: {len(elig)} unidades, sha256 {digest}")
    lines.append("THR " + repr(thr))
    lines.append("GRIDS " + repr(grids))
    (HERE / "freeze.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
