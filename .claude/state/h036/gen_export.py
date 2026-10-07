"""h036 — gera o export CEGO mensal do instrumento de custo (nenhum desfecho é lido): para cada sinal da
mean_reversion v14 (long, Binance perpétuo) emitido em [DE, ATE), a série de market_snapshots (bid, ask, spread) do
mercado de emitted_at até emitted_at + 250 min (cobre a entrada, ≤ 2 min, e qualquer saída, ≤ 4 h depois dela), e a
mediana diária do spread de cada mercado nos 7 dias anteriores (substituto congelado). Só agent_signals ×
market_snapshots: o instante e o motivo da saída NÃO entram — eles só são lidos na consulta do calendário.

uso: python3 gen_export.py 2026-10-07T08:00:00Z 2026-11-01T00:00:00Z > q_export_2026-10.sql
     bash q.sh q_export_2026-10.sql > cache/export_2026-10.csv ; sha256sum cache/export_2026-10.csv >> exports.sha256
"""
import sys
de, ate = sys.argv[1], sys.argv[2]
print(f"""-- h036 export cego [{de}, {ate}) — gerado por gen_export.py; só leitura
BEGIN READ ONLY;
SET LOCAL statement_timeout='600s';
COPY (
WITH v AS (SELECT sv.id FROM strategy_versions sv JOIN strategies st ON st.id = sv.strategy_id
           WHERE st.key = 'mean_reversion' AND sv.version = 'v14'),
sg AS (SELECT a.id, a.market_id, a.emitted_at FROM agent_signals a JOIN v ON v.id = a.strategy_version_id
       JOIN markets m ON m.id = a.market_id JOIN exchanges e ON e.id = m.exchange_id
       WHERE a.emitted_at >= '{de}' AND a.emitted_at < '{ate}' AND a.direction::text = 'long'
         AND m.market_type::text = 'perpetual' AND e.code::text = 'binance'
         AND a.supporting_features->>'cohort' = 'prospective')
SELECT 'serie' AS tipo, sg.id AS signal_id, ms.ts, ms.bid, ms.ask, ms.spread_pct, NULL::numeric AS mediana_7d
FROM sg JOIN market_snapshots ms ON ms.market_id = sg.market_id
 AND ms.ts >= date_trunc('minute', sg.emitted_at) AND ms.ts <= sg.emitted_at + interval '250 minutes'
UNION ALL
SELECT 'mediana_7d', sg.id, NULL, NULL, NULL, NULL,
       (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY ms.spread_pct) FROM market_snapshots ms
        WHERE ms.market_id = sg.market_id AND ms.ts >= sg.emitted_at - interval '7 days' AND ms.ts < sg.emitted_at)
FROM sg
ORDER BY 2, 1, 3
) TO STDOUT WITH (FORMAT csv, HEADER);
COMMIT;""")
