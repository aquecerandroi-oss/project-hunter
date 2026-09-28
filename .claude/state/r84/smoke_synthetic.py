"""R84 — fumaça com PAINÉIS SINTÉTICOS (nenhum preço real): efeito conhecido → CONFIRMA; nulo → NÃO CONFIRMA.

Painel: 45 moedas 2018-01-01…2026-09-27, 25 listadas no início e 20 escalonadas, 8 deslistadas; volume log-normal
persistente; retorno diário = mercado N(0, 3,5 %) + idiossincrático N(0, 4 %) + deriva μ(i, semana).
Efeito: μ AR(1) semanal (φ 0,85, dp estacionário 0,4 %/dia por moeda; 0,8 %/dia no fator comum quando `market_trend`) — o retorno de 14 d carrega a deriva que persiste.
Nulo: μ = 0. Nos dois, o log-retorno é corrigido por −σ²/2 para a média ARITMÉTICA ser zero (nulo verdadeiro).
Terceiro cenário, ilustrativo: nulo SEM a correção (deriva aritmética > 0 por convexidade) — mostra que a primária
D_ts, pelo braço de caixa, fica negativa sem nenhuma previsibilidade: E[D_ts] ≈ −(1 − exposição)·E[r_EW].
Saída: smoke_synth.txt.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
from analyze import mondays, report, run
from panel import build_panel

D0 = (dt.date(2018, 1, 1) - dt.date(1970, 1, 1)).days
TODAY = (dt.date(2026, 9, 28) - dt.date(1970, 1, 1)).days
LAST_T = (dt.date(2026, 9, 14) - dt.date(1970, 1, 1)).days


def synth(effect: bool, seed: int, zero_drift: bool = True, market_trend: bool = False) -> list[tuple[str, int, float, float, float]]:
    rng = np.random.default_rng(seed)
    n_days = TODAY - D0
    n_coins = 45
    weeks = n_days // 7 + 1
    mkt = rng.normal(0, 0.035, n_days)
    if market_trend:  # deriva persistente do fator comum (o que um sinal de série temporal consegue explorar)
        mw = np.zeros(weeks)
        for w in range(1, weeks):
            mw[w] = 0.85 * mw[w - 1] + rng.normal(0, 0.008 * np.sqrt(1 - 0.85**2))  # dp estacionário 0,8 %/dia
        mkt = mkt + np.repeat(mw, 7)[:n_days]
    rows = []
    for j in range(n_coins):
        start = 0 if j < 25 else int(rng.integers(0, n_days - 400))
        end = n_days if j % 6 else int(rng.integers(start + 200, n_days))  # 8 deslistadas
        mu_w = np.zeros(weeks)
        if effect:
            sd_innov = 0.004 * np.sqrt(1 - 0.85**2)
            for w in range(1, weeks):
                mu_w[w] = 0.85 * mu_w[w - 1] + rng.normal(0, sd_innov)
        mu = np.repeat(mu_w, 7)[:n_days]
        lr = mkt + rng.normal(0, 0.04, n_days) + mu - (0.5 * (0.035**2 + 0.04**2) if zero_drift else 0.0)
        px = 10.0 * np.exp(np.cumsum(lr))
        lvl = rng.normal(16, 1.5)
        vol = np.exp(lvl + rng.normal(0, 0.5, n_days))
        for k in range(start, end):
            o = px[k - 1] if k > 0 else 10.0
            rows.append((f"S{j:02d}USDT", D0 + k, float(o), float(px[k]), float(vol[k])))
    return rows


def main() -> None:
    out = []
    cases = (("EFEITO DE SÉRIE TEMPORAL (fator comum + moeda persistentes)", True, 11, True, True),
             ("EFEITO SÓ TRANSVERSAL (deriva só por moeda; D_ts não deve achar)", True, 15, True, False),
             ("NULO", False, 12, True, False), ("NULO", False, 13, True, False),
             ("NULO COM DERIVA > 0 (ilustrativo)", False, 14, False, False))
    for label, eff, seed, zd, mt in cases:
        rows = synth(eff, seed, zd, mt)
        trading = {f"S{j:02d}USDT" for j in range(45) if j % 6}
        p = build_panel(rows, trading, set(), TODAY, day0=D0)
        res = run(p, mondays(p, LAST_T))
        out.append(f"## {label} (semente {seed})\n{report(res)}\n")
    text = "\n".join(out)
    (Path(__file__).parent / "smoke_synth.txt").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
