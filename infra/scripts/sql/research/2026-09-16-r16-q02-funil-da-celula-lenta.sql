-- KB-0107 Q02 — o funil da porta L sobre a celula lenta, por dia (BRT).
-- Universo = moedas nao-Mayhem, nao nascidas cheias (KB-0104 perna D), que
-- cruzam 30 SOL REAIS com idade >= 180 s, e cujo cruzamento cai no dia.
-- Cada linha do funil = quantas moedas tem PELO MENOS UMA barra de 1 min
-- (dentro de :janela min do cruzamento, idade >= 180 s, curva viva) que
-- satisfaz todos os criterios ate ali. A ordem e a da porta L; a ultima
-- coluna repete o funil SEM o teto de progresso (diagnostico do KB-0107 §2).
-- Uso: psql -v dia=2026-09-14 -v janela=30 -A -F '|' -f -
SET statement_timeout = 60000;

WITH bounds AS (
  SELECT (:'dia')::date::timestamp AT TIME ZONE 'America/Sao_Paulo' AS d0,
         ((:'dia')::date + 1)::timestamp AT TIME ZONE 'America/Sao_Paulo' AS d1
), tok AS (
  SELECT t.mint, t.created_at, t.completed_at, t.migrated_at
  FROM meme_tokens t, bounds b
  WHERE t.created_at >= b.d0 - interval '6 hours' AND t.created_at < b.d1
    AND t.mayhem_enabled IS NOT NULL AND NOT t.mayhem_enabled AND t.mayhem_mode IS NULL
    AND NOT (t.completed_at IS NOT NULL
             AND t.completed_at - t.created_at <= interval '60 seconds')
), lentas AS (
  SELECT k.*, x.at_30
  FROM tok k
  CROSS JOIN LATERAL (
    SELECT min(cs.observed_at) AS at_30 FROM meme_curve_snapshots cs
    WHERE cs.mint = k.mint AND cs.real_sol_reserves >= 30
  ) x, bounds bb
  WHERE x.at_30 IS NOT NULL
    AND x.at_30 >= k.created_at + interval '180 seconds'
    AND x.at_30 >= bb.d0 AND x.at_30 < bb.d1
), barras AS (
  SELECT l.mint,
         b.curve_progress_pct AS prog, b.tape_reason, b.net_sol_flow_1m AS fluxo,
         b.holders, b.snipers, b.top10_share, b.mcap_sol
  FROM lentas l
  JOIN meme_features_1m b ON b.mint = l.mint
   AND b.end_time >= l.at_30
   AND b.end_time <= l.at_30 + make_interval(mins => (:'janela')::int)
   AND b.end_time >= l.created_at + interval '180 seconds'
  WHERE (l.completed_at IS NULL OR l.completed_at > b.end_time)
    AND (l.migrated_at IS NULL OR l.migrated_at > b.end_time)
), agg AS (
  SELECT mint,
    bool_or(mcap_sol IS NOT NULL AND mcap_sol > 0) AS c1,
    bool_or(mcap_sol > 0 AND prog IS NOT NULL AND prog <= 0.50) AS c2,
    bool_or(mcap_sol > 0 AND prog <= 0.50 AND tape_reason IS NULL) AS c3,
    bool_or(mcap_sol > 0 AND prog <= 0.50 AND tape_reason IS NULL AND fluxo > 0) AS c4,
    bool_or(mcap_sol > 0 AND prog <= 0.50 AND tape_reason IS NULL AND fluxo > 0
            AND holders >= 20) AS c5,
    bool_or(mcap_sol > 0 AND prog <= 0.50 AND tape_reason IS NULL AND fluxo > 0
            AND snipers BETWEEN 21 AND 60) AS c6,
    bool_or(mcap_sol > 0 AND prog <= 0.50 AND tape_reason IS NULL AND fluxo > 0
            AND top10_share <= 0.30) AS c7,
    bool_or(mcap_sol > 0 AND tape_reason IS NULL) AS d3,
    bool_or(mcap_sol > 0 AND tape_reason IS NULL AND fluxo > 0) AS d4,
    bool_or(mcap_sol > 0 AND tape_reason IS NULL AND fluxo > 0 AND holders >= 20) AS d5
  FROM barras GROUP BY mint
)
SELECT :'dia' AS dia,
  (SELECT count(*) FROM lentas) AS lentas_no_dia,
  (SELECT count(*) FROM agg) AS com_barra_1m,
  count(*) FILTER (WHERE c1) AS c1_mcap,
  count(*) FILTER (WHERE c2) AS c2_prog_le_50,
  count(*) FILTER (WHERE c3) AS c3_fita,
  count(*) FILTER (WHERE c4) AS c4_fluxo,
  count(*) FILTER (WHERE c5) AS c5_holders20,
  count(*) FILTER (WHERE c6) AS c6_snipers21_60,
  count(*) FILTER (WHERE c7) AS c7_top10_30,
  count(*) FILTER (WHERE d3) AS sem_prog_fita,
  count(*) FILTER (WHERE d4) AS sem_prog_fluxo,
  count(*) FILTER (WHERE d5) AS sem_prog_holders20
FROM agg;
