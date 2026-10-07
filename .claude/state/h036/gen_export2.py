"""h036 — export CEGO SEMANAL do instrumento de custo (emenda de 2026-10-07; substitui gen_export.py).

Só SPREAD, nenhum preço (Astra must-fix 8: bid/ask ao longo da trajetória deixariam calcular o retorno): para cada
sinal da mean_reversion v14 (long, Binance perpétuo, coorte prospectiva) emitido em [DE, ATE), o ``spread_pct`` de
``market_snapshots`` em cada minuto de date_trunc('minute', emitted_at) até emitted_at + 250 min (entrada ≤ 2 min,
saída ≤ 4 h depois dela, e o minuto seguinte à saída para o estresse), a mediana do spread do mercado nos 7 dias
anteriores ao sinal com a contagem de snapshots que a sustentou (``n_snap_7d``; janela completa = 10 080) e o
``tick_size`` oficial do mercado (lido hoje; pode ter mudado). Nada de ``signal_outcomes``.

Cadência: toda segunda-feira depois das 06:00Z, a semana ISO anterior [seg − 7 d, seg). A retenção do
market_snapshots (partição mensal, poda 30 d depois da borda superior) garante a semana e os 7 dias anteriores.
Recusa DE < T0 (a faixa [06:07Z; T0) nunca é lida), exceto ``--teste-exposto`` com ATE ≤ 2026-10-07T06:07Z.

uso: python3 gen_export2.py 2026-10-07T12:00:00Z 2026-10-12T00:00:00Z > q_export_w41.sql
     bash q.sh q_export_w41.sql | gzip > sealed/export_w41.csv.gz ; sha256sum sealed/export_w41.csv.gz >> exports.sha256
"""

import sys
from datetime import datetime

T0 = datetime.fromisoformat("2026-10-07T12:00:00+00:00")
EXPOSTO = datetime.fromisoformat("2026-10-07T06:07:00+00:00")


def _ts(text: str) -> datetime:
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise SystemExit(f"instante sem fuso: {text}")
    return dt


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    teste = "--teste-exposto" in sys.argv
    de, ate = _ts(args[0]), _ts(args[1])
    if teste and ate > EXPOSTO:
        raise SystemExit("--teste-exposto só vale para janelas que terminam até 2026-10-07T06:07Z")
    if not teste and de < T0:
        raise SystemExit("DE antes de T0 (2026-10-07T12:00Z): a faixa entre o corte de exposição e T0 nunca é lida")
    print(f"""-- h036 export cego (só spread) [{de.isoformat()}, {ate.isoformat()}) — gen_export2.py; só leitura
BEGIN READ ONLY;
SET LOCAL statement_timeout='600s';
COPY (
WITH v AS (SELECT sv.id FROM strategy_versions sv JOIN strategies st ON st.id = sv.strategy_id
           WHERE st.key = 'mean_reversion' AND sv.version = 'v14'),
sg AS (SELECT a.id, a.market_id, a.emitted_at, m.tick_size FROM agent_signals a JOIN v ON v.id = a.strategy_version_id
       JOIN markets m ON m.id = a.market_id JOIN exchanges e ON e.id = m.exchange_id
       WHERE a.emitted_at >= '{de.isoformat()}' AND a.emitted_at < '{ate.isoformat()}' AND a.direction::text = 'long'
         AND m.market_type::text = 'perpetual' AND e.code::text = 'binance'
         AND a.supporting_features->>'cohort' = 'prospective')
SELECT 'serie' AS tipo, sg.id AS signal_id, ms.ts, ms.spread_pct, NULL::numeric AS mediana_7d,
       NULL::bigint AS n_snap_7d, sg.tick_size
FROM sg JOIN market_snapshots ms ON ms.market_id = sg.market_id
 AND ms.ts >= date_trunc('minute', sg.emitted_at) AND ms.ts <= sg.emitted_at + interval '250 minutes'
UNION ALL
SELECT 'mediana_7d', sg.id, NULL, NULL, w.med, w.n, sg.tick_size
FROM sg CROSS JOIN LATERAL (
  SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY ms.spread_pct) AS med, count(ms.spread_pct) AS n
  FROM market_snapshots ms WHERE ms.market_id = sg.market_id
   AND ms.ts >= sg.emitted_at - interval '7 days' AND ms.ts < sg.emitted_at) w
ORDER BY 2, 1, 3
) TO STDOUT WITH (FORMAT csv, HEADER);
COMMIT;""")


if __name__ == "__main__":
    main()
