"""lab-cost-sweep — recompõe o R de cada desfecho do Lab sob outro custo (diagnóstico, não hipótese).

A partir do que o Lab gravou na decisão/encerramento (``progress.entry`` = abertura COM custo adverso,
``progress.exit_base`` = base da saída SEM custo, ``virtual_stop``, ``assumed_costs`` e ``funding.per_unit``):

    O = entry_c / (1 + c),  c = spread/2 + slippage (bp)     (inverso de pricing.entry_price)
    U  = entry_c − S                                          unidade de risco QUE O LAB GRAVOU (sempre > 0)
    G  = (B − O) / U                                          R bruto: sem custo e sem funding
    Φ  = F / U                                                funding em R (positivo = o comprado pagou)
    R(φ, σ) = (X' − E' − φ(E' + X') − F) / U,  E' = O(1+σ), X' = B(1−σ)
    h  = (O + B) / U                                          nocional das duas pernas por unidade de risco
    k* = 2 · Σ(G − Φ) / Σh · 1e4                              custo de ida-e-volta (bp, cobrado como taxa
                                                              k*/2 em cada perna, sem slippage) que zera a média

Todos os cenários usam o MESMO denominador U (o do Lab): o cenário muda só o numerador (custo + funding), então
R_lab − R_cenário é diferença pura de custo. Usar O − S (risco sem custo) explode quando a abertura cai em cima do
stop (O − S → 0; visto na volume_anomaly, −4e9 R) — por isso não. Com σ = c e φ = taxa do Lab, R(φ, σ) = r_multiple.
É uma REPRECIFICAÇÃO CONDICIONADA às entradas e saídas que o Lab observou, não um contrafactual de execução:
a saída (alvo/stop/expiração) é testada em preço de mercado, mas a ADMISSÃO depende do custo — o walker recusa
a geometria se não valer ``stop < entry_price(open, costs) < target1`` (walker.py, ``_enter``); com O = S o Lab
admite por causa dos 6 bp adversos e outro custo recusaria. Maker/rebate supõem preenchimento; tirar o funding de
um perpétuo é sensibilidade sobre preços de perpétuo, não backtest spot (Astra, must-fix 1). Com os custos do Lab
a reprecificação reproduz o R gravado (check.py: r_ex_funding máx |dif| 7e-11).
Estatística em float; nenhum dinheiro é publicado aqui.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

import numpy as np

BP = 1e-4
SEED = 20261007
REPS = 2_000


def _ts(text: str) -> datetime:
    s = text.strip()
    if s.endswith("+00"):
        s += ":00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        raise ValueError(f"timestamp sem fuso: {text!r}")
    return dt


def _f(text: str) -> float | None:
    return None if text is None or text.strip() == "" else float(text)


@dataclass(frozen=True, slots=True)
class Trade:
    signal_id: str
    strategy: str
    version: str
    mt: str
    symbol: str
    cohort: str
    emitted_at: datetime
    entry_ts: datetime
    exit_ts: datetime
    result: str
    open: float
    base: float
    stop: float
    entry_c: float
    c_bp: float
    f_bp: float
    funding: float | None  # por unidade; None = não estabelecido (nunca vira zero)
    r_lab: float | None  # r_multiple gravado (com funding)
    r_lab_ex: float | None  # meta.r_ex_funding gravado

    @classmethod
    def from_row(cls, r: dict[str, str]) -> Trade:
        c_bp = float(r["spread_bps"]) / 2 + float(r["slippage_bps"])
        entry_c = float(r["entry_c"])
        mt = r["mt"]
        funding = 0.0 if mt == "spot" else _f(r["funding_per_unit"])
        return cls(
            signal_id=r["signal_id"], strategy=r["strategy"], version=r["version"], mt=mt, symbol=r["symbol"],
            cohort=r["cohort"], emitted_at=_ts(r["emitted_at"]), entry_ts=_ts(r["entry_ts"]),
            exit_ts=_ts(r["exit_ts"]), result=r["result"], open=entry_c / (1 + c_bp * BP),
            base=float(r["exit_base"]), stop=float(r["stop"]), entry_c=entry_c, c_bp=c_bp,
            f_bp=float(r["fee_bps"]), funding=funding, r_lab=_f(r["r_multiple"]), r_lab_ex=_f(r["r_ex_funding"]),
        )

    @property
    def risk(self) -> float:
        return self.entry_c - self.stop

    @property
    def gross_r(self) -> float:
        return (self.base - self.open) / self.risk

    @property
    def funding_r(self) -> float | None:
        return None if self.funding is None else self.funding / self.risk

    @property
    def notional_per_r(self) -> float:
        return (self.open + self.base) / self.risk

    @property
    def duration_min(self) -> float:
        return (self.exit_ts - self.entry_ts).total_seconds() / 60.0

    @property
    def day(self) -> str:
        return self.emitted_at.strftime("%Y-%m-%d")  # emitted_at vem do banco em +00 (UTC)

    @property
    def month(self) -> str:
        return self.emitted_at.strftime("%Y-%m")

    def scenario_r(self, *, fee_bp: float, slip_bp: float, with_funding: bool) -> float | None:
        if with_funding and self.funding is None:
            return None
        fund = self.funding if with_funding and self.funding is not None else 0.0
        e = self.open * (1 + slip_bp * BP)
        x = self.base * (1 - slip_bp * BP)
        fee = fee_bp * BP
        return ((x - e) - fee * e - fee * x - fund) / self.risk

    def lab_r_recomputed(self) -> float | None:
        return self.scenario_r(fee_bp=self.f_bp, slip_bp=self.c_bp, with_funding=True)


def break_even_bp(g: np.ndarray, h: np.ndarray) -> float:
    """Custo de ida-e-volta (bp) que zera a média: Σ(g − k/2·1e-4·h) = 0."""
    return float(2.0 * np.sum(g) / np.sum(h) / BP)


def effective_cost_bp(h: np.ndarray, k: np.ndarray) -> float:
    """Custo de ida-e-volta por trade (bp) agregado do jeito que entra no R médio: Σ h·k / Σ h.

    É o número comparável com k* quando o custo varia por trade (Astra, must-fix 4): a mediana não é —
    51 % a 10 bp e 49 % a 30 bp dão mediana 10 e custo efetivo 19,8 bp.
    """
    return float(np.sum(h * k) / np.sum(h))


def _members(groups: Sequence[str]) -> list[np.ndarray]:
    labels = np.asarray(groups)
    return [np.flatnonzero(labels == u) for u in sorted(set(groups))]


def cluster_draws(stat: Callable[[np.ndarray], float], groups: Sequence[str],
                  reps: int = REPS, seed: int = SEED) -> np.ndarray:
    """Bootstrap de clusters (reamostra clusters inteiros com reposição); devolve as réplicas."""
    members = _members(groups)
    rng = np.random.default_rng(seed)
    k = len(members)
    return np.array([stat(np.concatenate([members[i] for i in rng.integers(0, k, size=k)]))
                     for _ in range(reps)])


def cluster_ci(stat: Callable[[np.ndarray], float], groups: Sequence[str],
               reps: int = REPS, seed: int = SEED) -> tuple[float, float, float]:
    d = cluster_draws(stat, groups, reps, seed)
    lo, hi = np.percentile(d, [2.5, 97.5])
    return stat(np.arange(len(groups))), float(lo), float(hi)


def ratio_ci(num: np.ndarray, den: np.ndarray, groups: Sequence[str], scale: float = 1.0,
             reps: int = REPS, seed: int = SEED) -> tuple[float, float, float]:
    """IC percentil 95 % de scale·Σnum/Σden por bootstrap de clusters — via somas por cluster (rápido).

    Mesmo gerador e mesma sequência de sorteios de ``cluster_draws`` (testado em test_sweep).
    Média = razão com den = 1.
    """
    members = _members(groups)
    ns = np.array([num[m].sum() for m in members])
    ds = np.array([den[m].sum() for m in members])
    rng = np.random.default_rng(seed)
    k = len(members)
    picks = np.array([rng.integers(0, k, size=k) for _ in range(reps)])
    d = scale * ns[picks].sum(axis=1) / ds[picks].sum(axis=1)
    lo, hi = np.percentile(d, [2.5, 97.5])
    return scale * float(num.sum() / den.sum()), float(lo), float(hi)


def activity(trades: Sequence[Trade]) -> dict[str, float]:
    days = {t.day for t in trades}
    dur = np.array([t.duration_min for t in trades])
    span = (max(t.emitted_at for t in trades) - min(t.emitted_at for t in trades)).total_seconds() / 86400 + 1
    return {
        "n": len(trades), "days": len(days), "markets": len({t.symbol for t in trades}),
        "per_active_day": len(trades) / len(days), "per_calendar_day": len(trades) / span,
        "dur_p10": float(np.percentile(dur, 10)), "dur_p50": float(np.median(dur)),
        "dur_p90": float(np.percentile(dur, 90)),
    }
