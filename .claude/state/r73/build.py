"""R73 — constrói a população do H-010 a partir da fita e escreve `rows.csv`.

Uma linha por decisão (posição real ou aposta de papel), com `maior_comprador_pct` medido
pela guarda da T4.80 e com as duas aferições de cobertura separadas (observável na
decisão × retrospetiva), como a Astra exigiu na revisão prévia.
"""

from __future__ import annotations

import csv
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from load import (  # noqa: E402
    HERE,
    concentration,
    load_population,
    load_tape,
    tape_matches_curve,
    tape_starts_at_birth,
)

FIELDS = [
    "lane", "bet_id", "mint", "symbol", "rule_set", "rs_kind", "decided_at", "dia", "hora",
    "exit_reason", "size_sol", "pnl_sol", "ret", "r_multiple",
    "pct", "pct_bruto", "pct_estoque", "top_wallet", "top_is_creator",
    "curve_sol", "top_net_sol", "n_trades", "n_wallets",
    "blocked_by_guard", "blocked_sol", "last_block_time", "last_received_at",
    "cov_obs", "cov_obs_err", "cov_retro", "cov_retro_err", "nasce", "atraso_nascimento",
    "quote_lag_s", "quote_real_sol", "stale_s", "pct_quote", "elegivel",
]


def build() -> list[dict[str, object]]:
    tape = load_tape()
    pop = load_population()
    out: list[dict[str, object]] = []
    for p in pop:
        mint = str(p["mint"])
        t = tape.get(mint, [])
        dec = p["decided_at"]
        c = concentration(t, dec)  # type: ignore[arg-type]
        q_at, q_sol = p["quote_observed_at"], p["quote_real_sol"]
        quote_lag = (dec - q_at).total_seconds() if q_at else None  # type: ignore[operator]
        # a foto só serve de âncora se foi tirada em ou antes da decisão
        usable = q_at is not None and q_sol is not None and quote_lag is not None and quote_lag >= 0
        cov_obs, err_obs = (
            tape_matches_curve(t, q_at, q_sol, known_by=dec) if usable else (False, float("inf"))  # type: ignore[arg-type]
        )
        cov_retro, err_retro = (
            tape_matches_curve(t, q_at, q_sol) if usable else (False, float("inf"))  # type: ignore[arg-type]
        )
        nasce, atraso = tape_starts_at_birth(t, p["token_created_at"])  # type: ignore[arg-type]
        out.append(
            {
                "lane": p["lane"], "bet_id": p["bet_id"], "mint": mint, "symbol": p["symbol"],
                "rule_set": p["rule_set"], "rs_kind": p["rs_kind"],
                "decided_at": dec.isoformat(),  # type: ignore[union-attr]
                "dia": p["dia"], "hora": p["hora"], "exit_reason": p["exit_reason"],
                "size_sol": p["size_sol"], "pnl_sol": p["pnl_sol"], "ret": p["ret"],
                "r_multiple": p["r_multiple"],
                "pct": c.pct, "pct_bruto": c.pct_bruto, "pct_estoque": c.pct_estoque,
                "top_wallet": c.top_wallet,
                "top_is_creator": (c.top_wallet is not None and c.top_wallet == p["creator"]),
                "curve_sol": c.curve_sol, "top_net_sol": c.top_net_sol,
                "n_trades": c.n_trades, "n_wallets": c.n_wallets,
                "blocked_by_guard": c.blocked_by_guard,
                "blocked_sol": Decimal(c.blocked_lamports) / Decimal(10**9),
                "last_block_time": c.last_block_time.isoformat() if c.last_block_time else "",
                "last_received_at": c.last_received_at.isoformat() if c.last_received_at else "",
                "cov_obs": cov_obs, "cov_obs_err": err_obs,
                "cov_retro": cov_retro, "cov_retro_err": err_retro,
                "nasce": nasce, "atraso_nascimento": atraso,
                "quote_lag_s": quote_lag, "quote_real_sol": q_sol,
                # quão velha era a nossa visão da fita no instante da decisão
                "stale_s": (
                    (dec - c.last_block_time).total_seconds() if c.last_block_time else None  # type: ignore[operator]
                ),
                # sensibilidade: mesmo numerador, denominador = foto fresca da curva
                "pct_quote": (
                    float(c.top_net_sol / q_sol) if (q_sol and q_sol > 0 and c.top_wallet) else None
                ),
                # ELEGIBILIDADE (revista depois de medir o atraso da fita, ver notas §2):
                # cobertura = fita reconcilia com a foto da curva (auditoria retrospetiva da
                # integridade do dado) E começa no nascimento. A aferição *observável* é
                # impossível por construção — a fita chega com ~44 s de atraso mediano, por
                # isso nunca reconstrói a foto do instante da decisão.
                "elegivel": bool(cov_retro and nasce and c.pct is not None and p["ret"] is not None),
            }
        )
    return out


def one_per_mint(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Uma decisão por mint: a real ganha da de papel; entre iguais, a mais antiga.

    Regra fixada antes de olhar desfechos (não depende de `ret`)."""
    best: dict[str, dict[str, object]] = {}
    for r in rows:
        k = str(r["mint"])
        cur = best.get(k)
        if cur is None:
            best[k] = r
            continue
        key_new = (r["lane"] != "live", str(r["decided_at"]))
        key_cur = (cur["lane"] != "live", str(cur["decided_at"]))
        if key_new < key_cur:
            best[k] = r
    return sorted(best.values(), key=lambda r: str(r["decided_at"]))


if __name__ == "__main__":
    rows = build()
    with (HERE / "rows.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    live = [r for r in rows if r["lane"] == "live"]
    print(f"linhas={len(rows)}  live={len(live)}  paper={len(rows) - len(live)}")
    print(f"mints={len({r['mint'] for r in rows})}  uma-por-mint={len(one_per_mint(rows))}")
    for lane, sub in (("live", live), ("paper", [r for r in rows if r['lane'] == 'paper'])):
        el = sum(1 for r in sub if r["elegivel"])
        co = sum(1 for r in sub if r["cov_obs"])
        na = sum(1 for r in sub if r["nasce"])
        rt = sum(1 for r in sub if r["cov_retro"])
        print(
            f"{lane:6s} n={len(sub):5d}  cobertura_observavel={co:5d} ({co / len(sub):6.1%})"
            f"  retro={rt:5d} ({rt / len(sub):6.1%})"
            f"  nasce={na:5d} ({na / len(sub):6.1%})  elegivel={el:5d} ({el / len(sub):6.1%})"
        )
