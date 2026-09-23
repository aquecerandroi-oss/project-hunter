"""R68 parte A — o muro do custo. Descritivo: não elimina horizonte nenhum (emenda E1.2)."""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

import numpy as np

from load68 import HORIZONS, bars_for, forward, load_csv_gz

# Custos de ida-e-volta. Decimal na fronteira onde o dinheiro é reportado.
COSTS: dict[str, Decimal] = {
    "0.14%": Decimal("0.0014"),   # Jupiter medido, R63
    "0.30%": Decimal("0.0030"),
    "0.50%": Decimal("0.0050"),
    "0.54% (0,14% + rede)": Decimal("0.0014") + Decimal("0.0002") / Decimal("0.05"),
}


def quantiles(x: np.ndarray, qs=(25, 50, 75, 90)) -> dict[str, float]:
    return {f"p{q}": float(np.percentile(x, q)) for q in qs}


def analyse(raw: dict, label: str) -> list[dict]:
    rows: list[dict] = []
    for h in HORIZONS:
        bars = bars_for(raw, h)
        rets, mfes, per_mkt = [], [], {}
        for sym, b in bars.items():
            i, r, m = forward(b)
            if i.size == 0:
                continue
            rets.append(r)
            mfes.append(m)
            per_mkt[sym] = float(np.median(np.abs(r)))
        r = np.concatenate(rets)
        m = np.concatenate(mfes)
        absr = np.abs(r)
        pos, neg = r[r > 0], r[r < 0]
        a = float(pos.mean()) if pos.size else 0.0          # ganho médio condicional
        bb = float(-neg.mean()) if neg.size else 0.0        # perda média condicional
        row = {
            "universo": label, "h": h, "n": int(r.size), "mercados": len(per_mkt),
            "absret": quantiles(absr), "mfe": quantiles(m),
            "mean_ret": float(r.mean()), "share_pos": float((r > 0).mean()),
            "a_ganho_medio": a, "b_perda_media": bb,
            "mediana_abs_por_mercado": quantiles(np.array(list(per_mkt.values()))),
            "custo": {},
        }
        med = float(np.median(absr))
        for name, c in COSTS.items():
            cf = float(c)
            row["custo"][name] = {
                # (i) modelo didáctico ±m  — marcado como modelo
                "p_modelo_pm": (0.5 + cf / (2 * med)) if med > 0 else float("inf"),
                # (ii) equilíbrio correcto com a/b incondicionais (Astra #1)
                "p_equilibrio_ab": ((bb + cf) / (a + bb)) if (a + bb) > 0 else float("inf"),
                # (iii) o número directo: fracção de barras que bate o custo
                "P_ret_maior_custo": float((r > cf).mean()),
                "P_mfe_maior_custo": float((m > cf).mean()),
                "sempre_long_liquido": float(r.mean() - cf),
            }
        rows.append(row)
    return rows


def main() -> None:
    out: list[dict] = []
    for path, label in [(Path(sys.argv[1]), "U2 profundo (16, 11/06-23/09)"),
                        (Path(sys.argv[2]), "U1 mesa sem sobreposicao (26, 29/08-23/09)")]:
        out.extend(analyse(load_csv_gz(path), label))
    Path("parta.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    for row in out:
        print(
            f"{row['universo'][:12]} h={row['h']:>3} n={row['n']:>8} "
            f"|r| p25={row['absret']['p25']*100:.3f}% med={row['absret']['p50']*100:.3f}% "
            f"p75={row['absret']['p75']*100:.3f}% p90={row['absret']['p90']*100:.3f}% | "
            f"MFE med={row['mfe']['p50']*100:.3f}% p90={row['mfe']['p90']*100:.3f}% | "
            f"mean={row['mean_ret']*1e4:+.2f}bp pos={row['share_pos']*100:.1f}% "
            f"a={row['a_ganho_medio']*100:.3f}% b={row['b_perda_media']*100:.3f}%"
        )
    print()
    for row in out:
        for name, c in row["custo"].items():
            print(
                f"{row['universo'][:12]} h={row['h']:>3} c={name:<22} "
                f"p*_modelo={c['p_modelo_pm']:.3f} p*_a/b={c['p_equilibrio_ab']:.3f} "
                f"P(r>c)={c['P_ret_maior_custo']*100:5.2f}% P(MFE>c)={c['P_mfe_maior_custo']*100:5.2f}% "
                f"long_liq={c['sempre_long_liquido']*1e4:+.1f}bp"
            )


if __name__ == "__main__":
    main()
