"""R86 — passo cego: população, disponibilidade da razão e das covariáveis, guarda, dias. Nenhum desfecho é lido.

cd .claude/state/r86 && uv run --no-sync --project C:/dev/project-hunter python blind86.py > blind.txt
"""

from __future__ import annotations

from collections import Counter

from data86 import CACHE, feature_rows, guard_window, load_daily

POST_R83 = "2026-09-28T01:58:45+00:00"  # instante em que o R83 leu os desfechos


def main() -> None:
    daily = load_daily()
    rows, cnt = feature_rows(daily)
    print("# R86 passo cego — sem desfechos")
    print("mercados no painel diário:", len(daily), "| arquivos:", sorted(p.name for p in CACHE.glob("daily_*.csv")))
    print("fora (não perp / não terminal):", dict(sorted(cnt.items())))
    kept, refused = guard_window(rows)
    print(f"terminais perp: {len(rows)} | guarda da janela de 24 h recusou {refused} | mantidas {len(kept)}")
    for strat in ("momentum", "volume_anomaly", "mean_reversion_v14"):
        g = [r for r in kept if r["strategy"] == strat]
        why = Counter(r["razao_why"] or "disponivel" for r in g)
        full = [r for r in g if r["has_r"] and r["razao"] is not None and r["d_low"] is not None
                and r["ret4h"] is not None and r["atr_pct"] is not None]
        bars = {(r["market"], r["obs"]) for r in full}
        days = {r["day"] for r in full}
        post = [r for r in full if r["t"].isoformat() > POST_R83]
        print(f"\n## {strat}: terminais {len(g)} | razao: {dict(why)}")
        print(f"   com R (nulidade) {sum(r['has_r'] for r in g)} | d_low {sum(r['d_low'] is not None for r in g)}"
              f" | ret4h {sum(r['ret4h'] is not None for r in g)} | atr {sum(r['atr_pct'] is not None for r in g)}")
        print(f"   completas (R + 4 variáveis): sinais {len(full)} | unidades (mercado, barra) {len(bars)}"
              f" | dias {len(days)} | mercados {len({r['market'] for r in full})}")
        if full:
            print(f"   1.º/último dia {min(days)} → {max(days)} | versões {dict(Counter(r['version'] for r in full))}")
            print(f"   unidades por sinal da razão: >0 {len({(r['market'], r['obs']) for r in full if r['razao'] > 0})}"
                  f" | ≤0 {len({(r['market'], r['obs']) for r in full if r['razao'] <= 0})}")
            print(f"   pós-R83 (emitted > {POST_R83}): unidades {len({(r['market'], r['obs']) for r in post})}"
                  f" dias {len({r['day'] for r in post})}")
        ng = sum(r["razao_noguard"] is not None for r in g)
        print(f"   razão sem a guarda de chegada: {ng} disponíveis")


if __name__ == "__main__":
    main()
