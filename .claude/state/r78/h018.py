# R78 — H-018: recompra do mesmo mint até 300 s depois de uma saída com lucro. Lógica pura (sem IO de rede).
import csv
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import NamedTuple

import numpy as np


class Pos(NamedTuple):
    bet_id: str
    mint: str
    rs: str
    entry_at: datetime
    exit_at: datetime
    pnl: Decimal
    size: Decimal
    exit_reason: str
    symbol: str
    origin: str  # instante da decisão de origem (mint + features_end_time): sombras da mesma decisão partilham

    @property
    def r(self) -> float:
        return float(self.pnl / self.size)


def _ts(s: str) -> datetime:
    s = s.strip()
    if s.endswith("+00"):
        s += ":00"
    return datetime.fromisoformat(s)


def load(path: str, origin_col: dict[str, str] | None = None) -> dict[str, list[Pos]]:
    """origin_col por lane: coluna que identifica a decisão de origem (padrão features_end_time)."""
    origin_col = origin_col or {}
    out: dict[str, list[Pos]] = defaultdict(list)
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[row["lane"]].append(Pos(row["bet_id"], row["mint"], row["rule_set"], _ts(row["entry_at"]),
                                        _ts(row["exit_at"]), Decimal(row["pnl_sol"]), Decimal(row["size_sol"]),
                                        row["exit_reason"] or "", row["symbol"] or "",
                                        row["mint"] + "|" + (row[origin_col.get(row["lane"], "features_end_time")] or row["bet_id"])))
    for v in out.values():
        v.sort(key=lambda p: (p.entry_at, p.bet_id))
    return dict(out)


def _by_mint(rows: list[Pos]) -> dict[str, list[Pos]]:
    d: dict[str, list[Pos]] = defaultdict(list)
    for p in sorted(rows, key=lambda p: (p.entry_at, p.bet_id)):
        d[p.mint].append(p)
    return d



def _scope_rows(ps: list[Pos], q: Pos, scope: str) -> list[Pos]:
    return [p for p in ps if p.rs == q.rs] if scope == "same" else ps


def reentries(rows: list[Pos], scope: str, prior: str = "target", window_s: int = 300) -> list[tuple[Pos, Pos]]:
    """(q, p): p é a saída IMEDIATAMENTE anterior a entry_q no escopo (same: da mesma mesa; any/cross: de
    qualquer mesa) e foi lucrativa (prior='target': lucrativa E por alvo, a leitura literal do bloco);
    exit_p ≤ entry_q ≤ exit_p + window; q é a primeira entrada do escopo depois de exit_p, ignorando entradas
    da mesma decisão de origem de p (não são uma recompra); cross exige mesa diferente. Uma q por p."""
    win = timedelta(seconds=window_s)
    out: list[tuple[Pos, Pos]] = []
    for ps in _by_mint(rows).values():
        for q in ps:
            closed = [p for p in _scope_rows(ps, q, scope) if p is not q and p.exit_at <= q.entry_at]
            if not closed:
                continue
            p = max(closed, key=lambda x: (x.exit_at, x.bet_id))
            if p.pnl <= 0 or (prior == "target" and p.exit_reason != "target"):
                continue
            if q.entry_at > p.exit_at + win or p.origin == q.origin or (scope == "cross" and p.rs == q.rs):
                continue
            after = [x for x in ps if x is not p and x.origin != p.origin and p.exit_at <= x.entry_at
                     and (scope != "same" or x.rs == p.rs) and (scope != "cross" or x.rs != p.rs)]
            if after and after[0] is q:
                out.append((q, p))
    return sorted(out, key=lambda t: (t[0].entry_at, t[0].bet_id))


def first_entries(rows: list[Pos], scope: str) -> list[Pos]:
    first: dict[tuple[str, str], Pos] = {}
    for p in sorted(rows, key=lambda p: (p.entry_at, p.bet_id)):
        first.setdefault((p.mint, p.rs if scope == "same" else ""), p)
    return sorted(first.values(), key=lambda p: (p.entry_at, p.bet_id))


def cooldown_counterfactual(rows: list[Pos], window_s: int, trigger: str = "any") -> tuple[list[tuple[Pos, Pos]], Decimal]:
    """Varredura cronológica: q é bloqueada se uma posição EXECUTADA do mesmo mint (qualquer mesa; trigger='any':
    qualquer resultado; 'loss': pnl < 0, o check 28) saiu com exit_p ≤ entry_q < exit_p + window (a janela do
    check 28 libera no instante exato). Devolve (bloqueada, saída que bloqueou) e Δ SOL = −Σ pnl bloqueadas."""
    win = timedelta(seconds=window_s)
    kept: dict[str, list[Pos]] = defaultdict(list)
    blocked: list[tuple[Pos, Pos]] = []
    for q in sorted(rows, key=lambda p: (p.entry_at, p.bet_id)):
        prev = [p for p in kept[q.mint] if p.exit_at <= q.entry_at < p.exit_at + win
                and (trigger == "any" or p.pnl < 0)]
        if prev:
            blocked.append((q, max(prev, key=lambda p: p.exit_at)))
        else:
            kept[q.mint].append(q)
    return blocked, -sum((b.pnl for b, _ in blocked), Decimal(0))


def concurrent_pairs(rows: list[Pos]) -> list[tuple[Pos, Pos]]:
    """(a, b) mesmo mint, mesas diferentes, b entra enquanto a está aberta (entry_a ≤ entry_b < exit_a)."""
    out = []
    for ps in _by_mint(rows).values():
        for i, a in enumerate(ps):
            out += [(a, b) for b in ps[i + 1:] if b.rs != a.rs and a.entry_at <= b.entry_at < a.exit_at]
    return out


def _cluster(items: list[tuple[str, float]], index: dict[str, int]) -> tuple[np.ndarray, np.ndarray]:
    s = np.zeros(len(index))
    c = np.zeros(len(index))
    for m, v in items:
        s[index[m]] += v
        c[index[m]] += 1
    return s, c


def boot_diff(a: list[tuple[str, float]], b: list[tuple[str, float]], n: int = 10_000, seed: int = 78) -> tuple[float, float, float]:
    """D = média(a) − média(b); IC 95 % percentil por bootstrap de mint (todas as linhas do mint juntas)."""
    mints = sorted({m for m, _ in a} | {m for m, _ in b})
    idx = {m: i for i, m in enumerate(mints)}
    sa, ca = _cluster(a, idx)
    sb, cb = _cluster(b, idx)
    rng = np.random.default_rng(seed)
    w = rng.multinomial(len(mints), np.full(len(mints), 1 / len(mints)), size=n).astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        ds = (w @ sa) / (w @ ca) - (w @ sb) / (w @ cb)
    ds = ds[np.isfinite(ds)]
    d = sa.sum() / ca.sum() - sb.sum() / cb.sum()
    lo, hi = np.percentile(ds, [2.5, 97.5])
    return float(d), float(lo), float(hi)


def perm_p(a: list[float], b: list[float], n: int = 10_000, seed: int = 78) -> float:
    """p bilateral por permutação de rótulos linha a linha (ignora o cluster; descritivo)."""
    x = np.array(a + b)
    obs = abs(np.mean(a) - np.mean(b))
    rng = np.random.default_rng(seed)
    k = len(a)
    hits = 0
    for _ in range(n):
        rng.shuffle(x)
        hits += abs(x[:k].mean() - x[k:].mean()) >= obs - 1e-12
    return (hits + 1) / (n + 1)
