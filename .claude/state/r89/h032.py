# R89 — H-032: Mayhem × não-Mayhem dentro da sonda de recusadas (estrato B). Lógica pura, sem IO de rede.
# Pré-registro: .claude/state/r89/prereg_frozen.md + emenda1.md (Fila de Hipóteses, H-032).
from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, localcontext

import numpy as np

MRE = 0.05
SEED = 20261007
REPS = 10_000
SPLIT = datetime.fromisoformat("2026-09-30T00:00:00+00:00")

# Famílias que não contam em n_outras_limpa (emenda 1, item 2): prefixos congelados.
FAMILIES_PRIMARY = ("mayhem_", "progress_")
FAMILIES_SENSITIVITY = FAMILIES_PRIMARY + (
    "participation_above_cap", "curve_volume_1m_", "no_buys", "sells_ratio_", "flow_", "buyers_",
)


@dataclass(frozen=True)
class Row:
    mint: str
    t: datetime
    mayhem: bool | None
    refusals: tuple[str, ...]
    stratum: str
    p: Decimal
    ret: float | None
    resolved: bool
    hw_x: float | None
    pnl: float | None
    exit_reason: str | None
    cap_applied: bool | None
    causal: bool
    tok_flag: bool | None
    snap_flag: bool | None
    snap: dict | None = None
    entry_tokens: Decimal | None = None
    size: Decimal | None = None
    fee_pct: Decimal | None = None
    prio: Decimal | None = None


def _ts(s: str) -> datetime:
    d = datetime.fromisoformat(s.replace(" ", "T"))
    if d.tzinfo is None:
        raise ValueError(f"instante sem fuso: {s}")
    return d


def _b(s: str) -> bool | None:
    return {"t": True, "true": True, "f": False, "false": False}.get((s or "").strip().lower())


def _d(s: str | None) -> Decimal | None:
    return None if s in (None, "") else Decimal(s)


def load(path: str) -> list[Row]:
    """Lê o CSV da extração única (q_pop.sql). Ausente nunca vira zero."""
    out = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            refusals = tuple(json.loads(r["refusals"])) if r["refusals"] else ()
            if "mayhem_unknown" in refusals:
                mayhem = None
            else:
                mayhem = "mayhem_curve" in refusals
            spent = _d(r["sol_spent"])
            pnl = _d(r["pnl_sol"])
            resolved = r["status"] == "closed" and r["oq"] != "indeterminate" and pnl is not None and bool(spent)
            ret = float(pnl / spent) if resolved and spent else None
            snap = json.loads(r["entry_snapshot"]) if r["entry_snapshot"] else None
            out.append(Row(
                mint=r["mint"], t=_ts(r["decided_at"]), mayhem=mayhem, refusals=refusals,
                stratum=r["stratum"], p=Decimal(r["p"]), ret=ret, resolved=resolved,
                hw_x=float(r["hw_x"]) if r["hw_x"] else None, pnl=float(pnl) if pnl is not None else None,
                exit_reason=r["exit_reason"] or None, cap_applied=_b(r["cap_applied"]),
                causal=bool(_b(r["causal"])), tok_flag=_b(r["tok_mayhem"]),
                snap_flag=snap.get("mayhem_enabled") if snap else None,
                snap=snap, entry_tokens=_d(r["entry_tokens"]), size=_d(r["size_sol"]),
                fee_pct=_d(r["fee_pct"]), prio=_d(r["prio"]),
            ))
    return out


def n_outras(refusals: tuple[str, ...], families: tuple[str, ...]) -> int:
    return sum(1 for x in refusals if not x.startswith(families))


def terciles(x: np.ndarray) -> tuple[np.ndarray, float, float]:
    """Cortes por posto (quantis lineares 1/3, 2/3); empates juntos: ≤ c1 → 0, > c2 → 2, resto → 1."""
    c1, c2 = (float(v) for v in np.quantile(x, [1 / 3, 2 / 3]))
    lab = np.where(x <= c1, 0, np.where(x > c2, 2, 1))
    return lab, c1, c2


def population_cuts(rows: list[Row], families: tuple[str, ...]) -> tuple[float, float]:
    """Cortes na população inteira (com ausentes), sem ler desfecho."""
    _, c1, c2 = terciles(np.array([n_outras(r.refusals, families) for r in rows], dtype=float))
    return c1, c2


def replace_ret(r: Row, v: float) -> Row:
    return replace(r, ret=v)


def _tercile(n: int, cuts: tuple[float, float]) -> int:
    return 0 if n <= cuts[0] else (2 if n > cuts[1] else 1)


def stratum_key(r: Row, families: tuple[str, ...], cuts: tuple[float, float]) -> tuple:
    return (r.t.date().isoformat(), r.t.hour // 6, _tercile(n_outras(r.refusals, families), cuts))


@dataclass(frozen=True)
class Adj:
    d: float
    drop_m: float
    drop_n: float
    strata: int


def _usable(rows: list[Row]) -> list[Row]:
    return [r for r in rows if r.ret is not None and r.mayhem is not None]


def d_adj(rows: list[Row], families: tuple[str, ...], *, cuts: tuple[float, float]) -> Adj:
    """D_adj = Σ w_s (média N − média M) / Σ w_s, w_s = n_M·n_N/n, só estratos com os dois grupos."""
    cells: dict[tuple, list[list[float]]] = {}
    for r in _usable(rows):
        cells.setdefault(stratum_key(r, families, cuts), [[], []])[int(r.mayhem)].append(r.ret)
    num = den = 0.0
    kept_m = kept_n = tot_m = tot_n = 0
    used = 0
    for n_vals, m_vals in cells.values():
        tot_n += len(n_vals)
        tot_m += len(m_vals)
        if n_vals and m_vals:
            w = len(n_vals) * len(m_vals) / (len(n_vals) + len(m_vals))
            num += w * (float(np.mean(n_vals)) - float(np.mean(m_vals)))
            den += w
            kept_n += len(n_vals)
            kept_m += len(m_vals)
            used += 1
    d = num / den if den > 0 else math.nan
    return Adj(d, 1 - kept_m / tot_m if tot_m else math.nan, 1 - kept_n / tot_n if tot_n else math.nan, used)


def raw_d(rows: list[Row]) -> float:
    u = _usable(rows)
    return float(np.mean([r.ret for r in u if not r.mayhem]) - np.mean([r.ret for r in u if r.mayhem]))


def _block(r: Row, block: str) -> str:
    return r.t.strftime("%Y-%m-%dT%H") if block == "hour" else r.t.date().isoformat()


def _matrices(rows: list[Row], families: tuple[str, ...], cuts: tuple[float, float], block: str):
    u = _usable(rows)
    blocks = sorted({_block(r, block) for r in u})
    strata = sorted({stratum_key(r, families, cuts) for r in u})
    bi = {b: i for i, b in enumerate(blocks)}
    si = {s: i for i, s in enumerate(strata)}
    nm, sm, nn, sn = (np.zeros((len(blocks), len(strata))) for _ in range(4))
    for r in u:
        i, j = bi[_block(r, block)], si[stratum_key(r, families, cuts)]
        if r.mayhem:
            nm[i, j] += 1
            sm[i, j] += r.ret
        else:
            nn[i, j] += 1
            sn[i, j] += r.ret
    return nm, sm, nn, sn


def _d_from_counts(k: np.ndarray, nm, sm, nn, sn) -> np.ndarray:
    NM, SM, NN, SN = k @ nm, k @ sm, k @ nn, k @ sn
    both = (NM > 0) & (NN > 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        w = np.where(both, NM * NN / (NM + NN), 0.0)
        diff = np.where(both, SN / np.where(NN > 0, NN, 1) - SM / np.where(NM > 0, NM, 1), 0.0)
        den = w.sum(axis=1)
        return np.where(den > 0, (w * diff).sum(axis=1) / np.where(den > 0, den, 1), np.nan)


def bootstrap(rows, families, cuts, *, block: str, reps: int = REPS, seed: int = SEED) -> np.ndarray:
    """Bootstrap de blocos (hora UTC ou dia UTC): reamostra blocos com reposição e recalcula o D_adj inteiro."""
    nm, sm, nn, sn = _matrices(rows, families, cuts, block)
    rng = np.random.default_rng(seed)
    nb = nm.shape[0]
    out = np.empty(reps)
    for a in range(0, reps, 1000):
        b = min(reps, a + 1000)
        idx = rng.integers(0, nb, size=(b - a, nb))
        k = np.zeros((b - a, nb))
        np.add.at(k, (np.repeat(np.arange(b - a), nb), idx.ravel()), 1)
        out[a:b] = _d_from_counts(k, nm, sm, nn, sn)
    return out


def bootstrap_identity(rows, families, cuts, *, block: str) -> float:
    nm, sm, nn, sn = _matrices(rows, families, cuts, block)
    return float(_d_from_counts(np.ones((1, nm.shape[0])), nm, sm, nn, sn)[0])


def ci(boot: np.ndarray) -> tuple[float, float, float]:
    fin = boot[np.isfinite(boot)]
    lo, hi = np.quantile(fin, [0.025, 0.975])
    return float(lo), float(hi), 1 - fin.size / boot.size


def centered_p(boot: np.ndarray, est: float) -> float:
    fin = boot[np.isfinite(boot)]
    return float((1 + np.sum(np.abs(fin - est) >= abs(est))) / (fin.size + 1))


def impute(rows: list[Row], scenario: str) -> list[Row]:
    """favor (da exclusão): N ausente = maior ret de N, M ausente = menor de M; contra: o inverso."""
    rn = [r.ret for r in rows if r.resolved and r.mayhem is False]
    rm = [r.ret for r in rows if r.resolved and r.mayhem]
    fill_n = max(rn) if scenario == "favor" else min(rn)
    fill_m = min(rm) if scenario == "favor" else max(rm)
    out = []
    for r in rows:
        if r.resolved or r.mayhem is None:
            out.append(r)
        else:
            out.append(replace(r, ret=fill_m if r.mayhem else fill_n))
    return out


def bought_top(r: Row) -> bool | None:
    """comprou_no_topo (R79): perda e pico ≤ custo (papel: high_water_x ≤ 1)."""
    if r.pnl is None or r.hw_x is None:
        return None
    return r.pnl < 0 and r.hw_x <= 1.0


def label(*, instrument_ok, data_ok, support_ok, nonfinite_ok, d, lo, hi, p, lo_day, robust,
          raw_same_sign, lo_fav, lo_con, hi_fav, hi_con) -> tuple[str, str]:
    """Precedência da emenda 1: instrumento → dado → suporte → rótulo."""
    if not instrument_ok:
        return "NÃO CONFIRMA — instrumento", "portão de instrumento"
    if not data_ok:
        return "NÃO CONFIRMA — limite de dado", "pisos de dado"
    if not support_ok:
        return "NÃO CONFIRMA — suporte", "estratos sem os dois grupos > 20 %"
    if not nonfinite_ok:
        return "NÃO CONFIRMA", "réplicas não finitas > 1 %"
    if max(hi, hi_fav, hi_con) < MRE:
        return "REFUTA", "IC superior < MRE no primário e nos dois cenários"
    conf = (d >= MRE and lo > 0 and p < 0.05 and lo_day > 0 and robust and raw_same_sign
            and lo_fav > 0 and lo_con > 0)
    if conf:
        return "CONFIRMA", "todas as cláusulas"
    return "NÃO CONFIRMA", "alguma cláusula falhou (imprecisão não refuta)"


def round_trip(snap: dict, size: Decimal, fee_pct: Decimal, prio: Decimal, *, mayhem: bool):
    """Compra de `size` pelo produto constante das reservas virtuais da foto e venda imediata
    contra as reservas pós-compra: (tokens, ret sem teto, ret com teto no SOL real OBSERVADO)."""
    with localcontext() as ctx:
        ctx.prec = 50
        vs, vt = Decimal(snap["virtual_sol_reserves"]), Decimal(snap["virtual_token_reserves"])
        c = size / (1 + fee_pct / 100)
        tokens = vt * c / (vs + c)
        spent = c + c * fee_pct / 100 + prio
        vs2, vt2 = vs + c, vt - tokens
        gross = vs2 * tokens / (vt2 + tokens)
        free = gross * (1 - fee_pct / 100) - prio
        real = _d(str(snap.get("real_sol_reserves"))) if snap.get("real_sol_reserves") is not None else None
        capped_gross = min(gross, real) if (mayhem and real is not None) else gross
        cap = capped_gross * (1 - fee_pct / 100) - prio
        return tokens, float(free / spent - 1), float(cap / spent - 1)
