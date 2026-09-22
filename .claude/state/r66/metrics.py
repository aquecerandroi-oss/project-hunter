"""R66 Q1/Q2 - cobertura, faixa de taxa do PumpSwap e a forma do movimento pos-graduacao."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from load import HERE, entry_point, load_board, load_tokens, value_at, window

WINDOWS = ((60, "+1 min"), (300, "+5 min"), (900, "+15 min"), (3600, "+1 h"), (14400, "+4 h"))

# As 25 faixas REAIS do FeeConfig do PumpSwap, lidas na mainnet em 2026-09-16
# (packages/exchange-adapters/tests/unit/test_pumpfun_fee_config.py, fixture
# t429c_rpc_fee_config_amm_raw.json; identicas a POOL_FEE_TIERS_SOL de
# packages/indicators/hunter_indicators/meme/pool.py). (limiar SOL de market cap; taxa % por perna).
POOL_TIERS = (
    (Decimal(0), Decimal("1.25")),
    (Decimal(420), Decimal("1.20")),
    (Decimal(1470), Decimal("1.15")),
    (Decimal(2460), Decimal("1.10")),
    (Decimal(3440), Decimal("1.05")),
    (Decimal(4420), Decimal("1.00")),
    (Decimal(9820), Decimal("0.95")),
    (Decimal(14740), Decimal("0.90")),
    (Decimal(19650), Decimal("0.85")),
    (Decimal(24560), Decimal("0.80")),
    (Decimal(29470), Decimal("0.75")),
    (Decimal(34380), Decimal("0.70")),
    (Decimal(39300), Decimal("0.65")),
    (Decimal(44210), Decimal("0.60")),
    (Decimal(49120), Decimal("0.55")),
    (Decimal(54030), Decimal("0.525")),
    (Decimal(58940), Decimal("0.50")),
    (Decimal(63860), Decimal("0.475")),
    (Decimal(68770), Decimal("0.45")),
    (Decimal(73681), Decimal("0.425")),
    (Decimal(78590), Decimal("0.40")),
    (Decimal(83500), Decimal("0.375")),
    (Decimal(88400), Decimal("0.35")),
    (Decimal(93330), Decimal("0.325")),
    (Decimal(98240), Decimal("0.30")),
)


def pool_fee_pct(mcap_sol: Decimal) -> Decimal:
    fee = POOL_TIERS[0][1]
    for threshold, f in POOL_TIERS:
        if mcap_sol >= threshold:
            fee = f
    return fee


def pct(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    i = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[i]


def describe(values: list[float]) -> dict:
    return dict(
        n=len(values),
        p10=pct(values, 0.10),
        p25=pct(values, 0.25),
        med=pct(values, 0.50),
        p75=pct(values, 0.75),
        p90=pct(values, 0.90),
        ge15=sum(1 for v in values if v >= 15) / len(values) if values else float("nan"),
        le30=sum(1 for v in values if v <= -30) / len(values) if values else float("nan"),
    )


def main() -> None:
    tokens = load_tokens()
    series = load_board(tokens)
    out: list[str] = []
    w = out.append

    w("== R66 Q1 - cobertura ==")
    w(f"tokens com migrated_at nos 7 dias: {len(tokens)}")
    w(f"com serie do board 'graduated' pos-migracao: {len(series)} "
      f"({100 * len(series) / len(tokens):.1f} %)")

    entries, delays, mcaps, fees = {}, [], [], {}
    for mint, obs in series.items():
        e = entry_point(obs)
        if e is None:
            continue
        entries[mint] = e
        delays.append(e["dt_s"])
        mcaps.append(float(e["mcap_sol"]))
        f = pool_fee_pct(e["mcap_sol"])
        fees[str(f)] = fees.get(str(f), 0) + 1
    w(f"com ponto de entrada (1a leitura >= migrated_at): {len(entries)}")
    w(f"atraso da 1a leitura (s) p10/p50/p90: {pct(delays,0.1):.0f} / {pct(delays,0.5):.0f} / "
      f"{pct(delays,0.9):.0f}")
    w(f"market cap na entrada (SOL) p10/p50/p90: {pct(mcaps,0.1):.0f} / {pct(mcaps,0.5):.0f} / "
      f"{pct(mcaps,0.9):.0f}")
    w(f"faixa de taxa do PumpSwap na entrada (% por perna): {json.dumps(fees, sort_keys=True)}")

    w("")
    w("== R66 Q1 - cobertura por janela (leitura a +-90 s do alvo) ==")
    have: dict[int, dict[str, dict]] = {}
    for secs, label in WINDOWS:
        got = {}
        for mint, e in entries.items():
            v = value_at(series[mint], e["observed_at"], secs)
            if v is not None and v["mcap_sol"] and v["mcap_sol"] > 0:
                got[mint] = v
        have[secs] = got
        w(f"{label:>7}: {len(got):5d} mints ({100 * len(got) / len(entries):.1f} % dos "
          f"{len(entries)})")

    w("")
    w("== R66 Q2 - retorno bruto (%) desde a 1a leitura pos-graduacao ==")
    w(f"{'janela':>7} {'n':>5} {'p10':>8} {'p25':>8} {'mediana':>8} {'p75':>8} {'p90':>8} "
      f"{'>=+15%':>7} {'<=-30%':>7}")
    ret_by_window: dict[int, dict[str, float]] = {}
    for secs, label in WINDOWS:
        rets = {}
        for mint, v in have[secs].items():
            e = entries[mint]
            rets[mint] = float((v["mcap_sol"] / e["mcap_sol"] - 1) * 100)
        ret_by_window[secs] = rets
        d = describe(list(rets.values()))
        if not d["n"]:
            w(f"{label:>7} {0:>5}  (sem amostra)")
            continue
        w(f"{label:>7} {d['n']:>5} {d['p10']:>8.1f} {d['p25']:>8.1f} {d['med']:>8.1f} "
          f"{d['p75']:>8.1f} {d['p90']:>8.1f} {100*d['ge15']:>6.1f}% {100*d['le30']:>6.1f}%")

    w("")
    w("== R66 Q2 - MFE / MAE dentro da janela (%, so fecho de barra de 60 s) ==")
    w(f"{'janela':>7} {'n':>5} {'MFE p25':>8} {'MFE med':>8} {'MFE p75':>8} {'MFE p90':>8} "
      f"{'MAE p10':>8} {'MAE med':>8} {'toca+15':>8} {'toca-10':>8}")
    mfe_by_window: dict[int, dict[str, tuple[float, float]]] = {}
    for secs, label in WINDOWS:
        mfes, maes, hit15, hit10 = [], [], 0, 0
        pairs = {}
        for mint, e in entries.items():
            path = window(series[mint], e["observed_at"], secs)
            if len(path) < 2:
                continue
            rs = [float((o["mcap_sol"] / e["mcap_sol"] - 1) * 100) for o in path]
            mfe, mae = max(rs), min(rs)
            pairs[mint] = (mfe, mae)
            mfes.append(mfe)
            maes.append(mae)
            hit15 += mfe >= 15
            hit10 += mae <= -10
        mfe_by_window[secs] = pairs
        if not mfes:
            w(f"{label:>7} {0:>5}  (sem amostra)")
            continue
        n = len(mfes)
        w(f"{label:>7} {n:>5} {pct(mfes,0.25):>8.1f} {pct(mfes,0.5):>8.1f} {pct(mfes,0.75):>8.1f} "
          f"{pct(mfes,0.9):>8.1f} {pct(maes,0.1):>8.1f} {pct(maes,0.5):>8.1f} "
          f"{100*hit15/n:>7.1f}% {100*hit10/n:>7.1f}%")

    w("")
    w("== R66 - censura: o token sai do board (30 posicoes) ==")
    last_pos = [o[-1]["position"] for o in series.values() if o[-1]["position"] is not None]
    spans = [o[-1]["dt_s"] for o in series.values()]
    w(f"ultima posicao vista p10/p50/p90: {pct([float(p) for p in last_pos],0.1):.0f} / "
      f"{pct([float(p) for p in last_pos],0.5):.0f} / {pct([float(p) for p in last_pos],0.9):.0f}")
    w(f"span da serie (s) p10/p50/p90: {pct(spans,0.1):.0f} / {pct(spans,0.5):.0f} / "
      f"{pct(spans,0.9):.0f}")
    # o span depende do desempenho? (vies de sobrevivencia)
    r15 = ret_by_window[900]
    both = [(spans_m, r15[m]) for m, spans_m in
            ((m, series[m][-1]["dt_s"]) for m in series) if m in r15]
    if both:
        lo = [r for s, r in both if s <= pct([s for s, _ in both], 0.5)]
        hi = [r for s, r in both if s > pct([s for s, _ in both], 0.5)]
        w(f"retorno +15 min mediano | span curto (<=p50): {pct(lo,0.5):.1f} % (n={len(lo)}) | "
          f"span longo: {pct(hi,0.5):.1f} % (n={len(hi)})")

    text = "\n".join(out)
    print(text)
    Path(HERE / "metrics.txt").write_text(text + "\n", encoding="utf-8")
    json.dump(
        {str(s): ret_by_window[s] for s, _ in WINDOWS},
        open(HERE / "returns.json", "w"),
    )


if __name__ == "__main__":
    main()
