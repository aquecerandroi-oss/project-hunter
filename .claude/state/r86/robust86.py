"""R86 — verificações de robustez PÓS-DESFECHO (pedidas pelo orquestrador depois da leitura de 03:06:15Z).

Não mudam o rótulo do protocolo (pré-registro 02:56Z + emenda 03:02Z). Vêm do red-team da Astra
(`.claude/state/astra-review-astra-redteam-c1.md`) e da auditoria de dados do Lab
(`.claude/state/astra-review-astra-auditoria-lab.md`). Uma guarda que falha ou não pode ser checada deixa a
afirmação GENERALIZADA como "não verificável / não confirma" — nunca resgata nada.

cd .claude/state/r86 && PYTHONPATH=C:/dev/project-hunter uv run --no-sync --project C:/dev/project-hunter python robust86.py > robust.txt
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

import numpy as np
from analysis86 import design, scales
from data86 import CACHE, attach_outcomes, feature_rows, guard_window, load_daily, ts, units, window_days
from stats86 import fit

SEED, REPS = 20261001, 10_000


def calendar_block_ci(y, x, days, length, col=1, reps=REPS, fe=()):
    """Blocos móveis de `length` dias de calendário consecutivos (todos os mercados do dia juntos).

    `fe`: listas de chaves de efeito fixo; as dummies são refeitas em cada réplica com os níveis presentes.
    """
    d0 = date.fromisoformat(min(days))
    cal = [(d0 + timedelta(days=i)).isoformat() for i in range((date.fromisoformat(max(days)) - d0).days + 1)]
    members = {d: np.flatnonzero(np.array(days) == d) for d in cal}
    k, rng, draws, bad = len(cal), np.random.default_rng(SEED), [], 0
    for _ in range(reps):
        picked: list[str] = []
        while len(picked) < k:
            s = int(rng.integers(0, k - length + 1))
            picked += cal[s:s + length]
        idx = np.concatenate([members[d] for d in picked[:k]])
        if idx.size == 0:
            bad += 1
            continue
        xi = x[idx]
        for keys in fe:
            sub = [keys[j] for j in idx]
            if len(set(sub)) > 1:
                xi = np.column_stack([xi, dummies(sub)])
        a = np.column_stack([np.ones(idx.size), xi])
        if np.linalg.matrix_rank(a) < a.shape[1]:
            bad += 1
            continue
        draws.append(fit(y[idx], xi)[col])
    if not draws:
        return float("nan"), float("nan"), bad
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return float(lo), float(hi), bad


def dummies(keys: list[str]) -> np.ndarray:
    lv = sorted(set(keys))[1:]
    return np.column_stack([[1.0 if k == v else 0.0 for k in keys] for v in lv])


def main() -> None:
    daily = load_daily()
    rows, cnt = feature_rows(daily)
    kept, refused = guard_window(rows)
    attach_outcomes(kept)
    with (CACHE / "eligible.csv").open(encoding="utf-8") as fh:
        elig = {r["signal_id"] for r in csv.DictReader(fh)}
    with (CACHE / "out.csv").open(encoding="utf-8") as fh:
        exit_ts = {r["signal_id"]: ts(r["exit_ts"]) for r in csv.DictReader(fh)}
    mom_rows = [r for r in kept if r["signal_id"] in elig and r["strategy"] == "momentum"]
    us = units(mom_rows)
    ex = defaultdict(list)
    for r in mom_rows:
        if exit_ts.get(r["signal_id"]):
            ex[(r["market"], r["obs"])].append(exit_ts[r["signal_id"]])
    for u in us:
        u["exit"] = max(ex[(u["market"], u["obs"])]) if ex[(u["market"], u["obs"])] else None
    sym = {r["market"]: r["symbol"] for r in kept}
    y = np.array([u["r"] for u in us])
    x = design(us, scales(us))
    days, mk = [u["day"] for u in us], [u["market"] for u in us]
    print("# R86 — robustez PÓS-DESFECHO (não muda o rótulo; afirmação generalizada só se todas passarem)")
    print(f"momentum: {len(us)} unidades, β_razao pooled {fit(y, x)[1]:+.4f}")

    print("\n## RT1 — dentro da moeda / do dia (efeitos fixos)")
    for name, fe in (("FE mercado", (mk,)), ("FE dia", (days,)), ("FE mercado + dia", (mk, days))):
        xf = np.column_stack([x, *[dummies(k) for k in fe]])
        b = fit(y, xf)[1]
        lo, hi, bad = calendar_block_ci(y, x, days, 3, reps=2000, fe=fe)
        print(f"- {name}: β_razao {b:+.4f} | IC blocos de 3 dias [{lo:+.4f}, {hi:+.4f}] (2 000 réplicas, inválidas {bad})")

    print("\n## RT3 — bootstrap de blocos de calendário (todos os mercados do dia juntos), modelo primário")
    for L in (3, 5, 7):
        lo, hi, bad = calendar_block_ci(y, x, days, L)
        print(f"- blocos de {L} dias: IC [{lo:+.4f}, {hi:+.4f}] | réplicas inválidas {bad}")
    ud = sorted(set(days))
    k = (len(ud) + 1) // 2
    cut = datetime.fromisoformat(ud[k] + "T00:00:00+00:00")
    first = [i for i, u in enumerate(us) if u["day"] < ud[k]]
    purged = [i for i in first if u_exit_before(us[i], cut)]
    second = [i for i, u in enumerate(us) if u["day"] >= ud[k]]
    for name, idx in (("metade 1 (sem purga)", first), ("metade 1 purgada (saída antes de " + ud[k] + ")", purged),
                      ("metade 2", second)):
        ii = np.array(idx)
        print(f"- {name}: n {len(idx)} dias {len({days[i] for i in idx})} β {fit(y[ii], x[ii])[1]:+.4f}"
              f" | datas {min(days[i] for i in idx)} → {max(days[i] for i in idx)}")

    print("\n## RT4 — datas distintas por braço (piso proposto: 15)")
    for c in (-0.05, -0.025, 0.0, 0.025, 0.05):
        hi_d = {u["day"] for u in us if u["razao"] > c}
        lo_d = {u["day"] for u in us if u["razao"] <= c}
        print(f"- c={c:+.3f}: razão>c {len(hi_d)} datas · razão≤c {len(lo_d)} datas")
    for name, idx in (("metade 1", first), ("metade 2", second)):
        print(f"- {name}: razão>0 {len({days[i] for i in idx if us[i]['razao'] > 0})} datas"
              f" ({sum(us[i]['razao'] > 0 for i in idx)} un.) · razão≤0 {len({days[i] for i in idx if us[i]['razao'] <= 0})}"
              f" datas ({sum(us[i]['razao'] <= 0 for i in idx)} un.)")
    print("unidades razão≤0 por data:", dict(sorted(Counter(u["day"] for u in us if u["razao"] <= 0).items())))

    print("\n## RT5 — sem cada mercado (β e nível do grupo razão>0)")
    for m in sorted(set(mk), key=lambda m: sym[m]):
        ii = np.array([j for j, v in enumerate(mk) if v != m])
        lvl = np.mean([us[j]["r"] for j in ii if us[j]["razao"] > 0])
        print(f"- sem {sym[m]:<14} (n {mk.count(m):>3}): β {fit(y[ii], x[ii])[1]:+.4f} | nível razão>0 {lvl:+.4f}")

    print("\n## RT6 — custo: o nível do grupo razão>0 sob o custo ASSUMIDO do Lab já é negativo (ver h027.txt, IC dia")
    print("   inteiro < 0); um cenário mais caro só o reduz. Reconstrução por perna não feita (não verificável aqui).")

    print("\n## Auditoria — contagens")
    print("fora por tipo de mercado (market_id → markets.market_type, nunca por símbolo):",
          {k[0]: v for k, v in cnt.items() if k[1] == "fora_spot"})
    print("fora por não entrada (no_entry, result=open — não são posições):",
          {k[0]: v for k, v in cnt.items() if k[1] == "fora_no_entry"})
    print("guarda da janela de 24 h recusou:", refused)
    full = [r for r in kept if r["strategy"] in ("momentum", "volume_anomaly") and r["razao"] is not None
            and r["d_low"] is not None and r["ret4h"] is not None and r["atr_pct"] is not None]
    nul = Counter((r["strategy"], "razão>0" if r["razao"] > 0 else "razão≤0") for r in full if not r["has_r"])
    print("terminais completos SEM R_net (fora, nunca zero), por grupo:", dict(nul), "| motivos:",
          dict(Counter(r["r_net_reason"].split(":")[0] for r in full if not r["has_r"])))
    print("símbolos na população momentum:", dict(Counter(sym[m] for m in mk)))
    for s in ("ARKUSDT", "MOVRUSDT", "QNTUSDT", "SOONUSDT"):
        g = [r for r in kept if r["symbol"] == s and r["strategy"] == "momentum"]
        print(f"- {s}: terminais momentum {len(g)} | razão: {dict(Counter(r['razao_why'] or 'disponivel' for r in g))}")
    late = 0
    for u in us:
        dd = daily[u["market"]]
        if any(dd[d].max_recv > datetime.combine(d + timedelta(days=1), datetime.min.time(), u["obs"].tzinfo)
               + timedelta(minutes=5) for d in window_days(u["obs"])):
            late += 1
    print(f"unidades cuja janela de 20 dias usa ≥ 1 dia completado > 5 min depois do fim do dia (backfill antes da"
          f" emissão): {late} de {len(us)} — o estado diário é RECONSTRUÇÃO, não o que o scanner tinha na memória")


def u_exit_before(u: dict, cut: datetime) -> bool:
    return u["exit"] is not None and u["exit"] < cut


if __name__ == "__main__":
    main()
