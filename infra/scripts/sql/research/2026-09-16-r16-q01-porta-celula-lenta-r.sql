-- KB-0107 Q01 — a porta "celula lenta" (L) como porta da mesa do estagio 1:
-- uma linha por (variante, moeda) com a entrada, a idade na entrada e o R simulado.
--
-- Celula lenta (KB-0098 §6 / KB-0104 §2): a moeda cruza 30 SOL REAIS na curva
-- (meme_curve_snapshots.real_sol_reserves >= 30) com idade >= 180 s.
-- Porta L (todas as variantes): entrada na PRIMEIRA barra de 1 min
-- (meme_features_1m) em que, cumulativamente:
--   * a moeda ja cruzou 30 SOL reais (end_time >= at_30);
--   * idade >= 180 s;
--   * curve_progress_pct <= :prog_max  (FRACAO 0-1 nesta serie, KB-0099 §4);
--   * fita presente (tape_reason IS NULL);
--   * fluxo do minuto > 0 (net_sol_flow_1m > 0);
--   * curva viva (nao completa / nao migrada na barra);
--   * nao-Mayhem (mayhem_enabled = false E mayhem_mode IS NULL);
--   * nao nascida cheia (KB-0104: perna D, completed_at - created_at <= 60 s).
-- Variantes: L1 so isso; L2 + holders >= 20; L3 + snipers 21-60; L4 + top10 <= 30 %;
--            L1b = L1 SEM o teto de progresso (diagnostico do custo desse criterio).
-- Janela de entrada: ate :janela minutos depois do cruzamento dos 30 SOL (sem isso a
-- "primeira barra que passa" poderia cair horas depois; o atraso vai na saida).
-- Saida = metodologia do KB-0099 §3 / r4-q05, sem mudar nada: barras de 1 min,
--   alvo 3x, trailing 35 % armado depois de 1,5x, piso -50 %, tempo :hz minutos,
--   taxa 1,75 % por perna, stop preenchido no mcap OBSERVADO da barra.
--   R = (multiplo liquido - 1) / 0,5.
-- Uso: psql -v dia=2026-09-14 -v janela=30 -v hz=30 -v prog_max=0.50 -A -F '|' -f -
SET statement_timeout = 60000;

WITH bounds AS (
  SELECT (:'dia')::date::timestamp AT TIME ZONE 'America/Sao_Paulo' AS d0,
         ((:'dia')::date + 1)::timestamp AT TIME ZONE 'America/Sao_Paulo' AS d1
), tok AS (
  SELECT t.mint, t.created_at, t.completed_at, t.migrated_at
  FROM meme_tokens t, bounds b
  WHERE t.created_at >= b.d0 - interval '6 hours'
    AND t.created_at <  b.d1
    AND t.mayhem_enabled IS NOT NULL AND NOT t.mayhem_enabled
    AND t.mayhem_mode IS NULL
    AND NOT (t.completed_at IS NOT NULL
             AND t.completed_at - t.created_at <= interval '60 seconds')
), lentas AS (
  SELECT k.mint, k.created_at, k.completed_at, k.migrated_at, x.at_30
  FROM tok k
  CROSS JOIN LATERAL (
    SELECT min(cs.observed_at) AS at_30
    FROM meme_curve_snapshots cs
    WHERE cs.mint = k.mint AND cs.real_sol_reserves >= 30
  ) x
  WHERE x.at_30 IS NOT NULL
    AND x.at_30 >= k.created_at + interval '180 seconds'
), v(rotulo, holders_min, snip_min, snip_max, top10_max, prog_max) AS (
  VALUES ('L1', 0, -1, 1000000, 9.9, (:'prog_max')::numeric),
         ('L2', 20, -1, 1000000, 9.9, (:'prog_max')::numeric),
         ('L3', 0, 21, 60, 9.9, (:'prog_max')::numeric),
         ('L4', 0, -1, 1000000, 0.30, (:'prog_max')::numeric),
         ('L1b', 0, -1, 1000000, 9.9, 9.9::numeric)
), entrada AS (
  SELECT DISTINCT ON (v.rotulo, l.mint)
         v.rotulo, l.mint, l.created_at, l.at_30,
         b.end_time AS t_in, b.mcap_sol AS base,
         b.curve_progress_pct, b.holders, b.snipers, b.top10_share,
         b.unique_buyers, b.buys_1m, b.sells_1m, b.net_sol_flow_1m
  FROM lentas l
  CROSS JOIN v
  JOIN meme_features_1m b
    ON b.mint = l.mint
   AND b.end_time >= l.at_30
   AND b.end_time <= l.at_30 + make_interval(mins => (:'janela')::int)
  CROSS JOIN bounds bb
  WHERE b.end_time >= bb.d0 AND b.end_time < bb.d1
    AND b.mcap_sol IS NOT NULL AND b.mcap_sol > 0
    AND b.end_time >= l.created_at + interval '180 seconds'
    AND (l.completed_at IS NULL OR l.completed_at > b.end_time)
    AND (l.migrated_at IS NULL OR l.migrated_at > b.end_time)
    AND b.curve_progress_pct IS NOT NULL AND b.curve_progress_pct <= v.prog_max
    AND b.tape_reason IS NULL
    AND b.net_sol_flow_1m IS NOT NULL AND b.net_sol_flow_1m > 0
    AND (v.holders_min = 0 OR (b.holders IS NOT NULL AND b.holders >= v.holders_min))
    AND (v.snip_min < 0 OR (b.snipers IS NOT NULL
         AND b.snipers >= v.snip_min AND b.snipers <= v.snip_max))
    AND (v.top10_max > 1 OR (b.top10_share IS NOT NULL AND b.top10_share <= v.top10_max))
  ORDER BY v.rotulo, l.mint, b.end_time
), barras AS (
  SELECT e.rotulo, e.mint, e.base, s.end_time, s.mcap_sol,
         row_number() OVER (PARTITION BY e.rotulo, e.mint ORDER BY s.end_time) AS i,
         max(s.mcap_sol) OVER (PARTITION BY e.rotulo, e.mint ORDER BY s.end_time
                               ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS pico_ate_anterior
  FROM entrada e
  JOIN meme_features_1m s ON s.mint = e.mint
   AND s.end_time > e.t_in
   AND s.end_time <= e.t_in + make_interval(mins => (:'hz')::int)
  WHERE s.mcap_sol IS NOT NULL
), gatilho AS (
  SELECT *,
    CASE WHEN COALESCE(pico_ate_anterior, base) >= 1.5 * base
         THEN greatest(0.65 * COALESCE(pico_ate_anterior, base), 0.5 * base)
         ELSE 0.5 * base END AS nivel_stop
  FROM barras
), saida AS (
  SELECT DISTINCT ON (rotulo, mint) rotulo, mint, i,
    CASE WHEN mcap_sol >= 3 * base THEN 3 * base ELSE mcap_sol END AS preco_saida,
    CASE WHEN mcap_sol >= 3 * base THEN 'alvo_3x' ELSE 'stop' END AS motivo
  FROM gatilho
  WHERE mcap_sol >= 3 * base OR mcap_sol <= nivel_stop
  ORDER BY rotulo, mint, i
), fim AS (
  SELECT DISTINCT ON (rotulo, mint) rotulo, mint, mcap_sol AS preco_saida, 'tempo' AS motivo
  FROM gatilho ORDER BY rotulo, mint, i DESC
)
SELECT :'dia' AS dia, e.rotulo, e.mint,
       e.t_in,
       extract(hour FROM e.t_in AT TIME ZONE 'America/Sao_Paulo')::int AS hora_brt,
       round(extract(epoch FROM (e.t_in - e.created_at)))::int AS idade_s,
       round(extract(epoch FROM (e.t_in - e.at_30)))::int AS atraso_30sol_s,
       round(e.base, 3) AS base_mcap_sol,
       round(e.curve_progress_pct, 4) AS prog,
       e.holders, e.snipers, round(e.top10_share, 4) AS top10,
       COALESCE(s.motivo, f.motivo) AS motivo,
       round((COALESCE(s.preco_saida, f.preco_saida) / e.base) * 0.9825 * 0.9825 - 1, 6) AS retorno,
       round((((COALESCE(s.preco_saida, f.preco_saida) / e.base) * 0.9825 * 0.9825 - 1) / 0.5)::numeric, 6) AS r
FROM entrada e
LEFT JOIN saida s ON s.rotulo = e.rotulo AND s.mint = e.mint
LEFT JOIN fim f ON f.rotulo = e.rotulo AND f.mint = e.mint;
