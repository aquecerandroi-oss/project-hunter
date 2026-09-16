-- KB-0109 Q02 — as ordens reais de hoje recusadas por top10_share_above_cap:
-- qual era o valor, e o que a moeda fez depois (R simulado pela metodologia
-- KB-0099 a partir da barra de 1 min seguinte a ordem: alvo 3x, trailing 35 %
-- depois de 1,5x, piso -50 %, 30 min, taxa 1,75 % por perna).
SET statement_timeout = 60000;

WITH ordens AS (
  SELECT o.received_at, o.admission->>'mint' AS mint,
         (c->>'value')::numeric AS top10, o.reason
  FROM meme_live_orders o, jsonb_array_elements(o.admission->'checks') c
  WHERE c->>'refusal' = 'top10_share_above_cap'
    AND o.received_at >= (now() AT TIME ZONE 'America/Sao_Paulo')::date::timestamp AT TIME ZONE 'America/Sao_Paulo'
), base AS (
  SELECT DISTINCT ON (o.received_at) o.received_at, o.mint, o.top10,
         b.end_time AS t_in, b.mcap_sol AS base, b.holders, b.snipers, b.curve_progress_pct
  FROM ordens o
  JOIN meme_features_1m b ON b.mint = o.mint AND b.end_time > o.received_at
   AND b.end_time <= o.received_at + interval '5 minutes' AND b.mcap_sol > 0
  ORDER BY o.received_at, b.end_time
), barras AS (
  SELECT e.received_at, e.mint, e.base, s.end_time, s.mcap_sol,
         row_number() OVER (PARTITION BY e.received_at ORDER BY s.end_time) AS i,
         max(s.mcap_sol) OVER (PARTITION BY e.received_at ORDER BY s.end_time
                               ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS pico
  FROM base e JOIN meme_features_1m s ON s.mint = e.mint
   AND s.end_time > e.t_in AND s.end_time <= e.t_in + interval '30 minutes'
  WHERE s.mcap_sol IS NOT NULL
), gat AS (
  SELECT *, CASE WHEN COALESCE(pico, base) >= 1.5 * base
                 THEN greatest(0.65 * COALESCE(pico, base), 0.5 * base)
                 ELSE 0.5 * base END AS nivel FROM barras
), saida AS (
  SELECT DISTINCT ON (received_at) received_at, i,
    CASE WHEN mcap_sol >= 3 * base THEN 3 * base ELSE mcap_sol END AS preco,
    CASE WHEN mcap_sol >= 3 * base THEN 'alvo_3x' ELSE 'stop' END AS motivo
  FROM gat WHERE mcap_sol >= 3 * base OR mcap_sol <= nivel ORDER BY received_at, i
), fim AS (
  SELECT DISTINCT ON (received_at) received_at, mcap_sol AS preco, 'tempo' AS motivo
  FROM gat ORDER BY received_at, i DESC
)
SELECT to_char(e.received_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS brt,
       left(e.mint,6) AS mint, e.top10, e.base, e.holders, e.snipers, e.curve_progress_pct,
       (SELECT round(max(s.mcap_sol)/e.base,3) FROM meme_features_1m s
         WHERE s.mint = e.mint AND s.end_time > e.t_in
           AND s.end_time <= e.t_in + interval '30 minutes') AS multiplo_max,
       COALESCE(s.motivo, f.motivo) AS motivo,
       round(((COALESCE(s.preco, f.preco)/e.base)*0.9825*0.9825 - 1)/0.5, 3) AS r,
       (SELECT t.completed_at IS NOT NULL FROM meme_tokens t WHERE t.mint = e.mint) AS graduou
FROM base e LEFT JOIN saida s ON s.received_at = e.received_at
            LEFT JOIN fim f ON f.received_at = e.received_at
ORDER BY e.received_at;
