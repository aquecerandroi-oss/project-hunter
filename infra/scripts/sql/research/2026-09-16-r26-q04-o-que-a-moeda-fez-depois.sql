-- R26 / Q04 — o que cada moeda das ordens de hoje fez nos 30 min seguintes a
-- decisao, e o R simulado com a regra da mesa (alvo 3x, trailing 35 % armado
-- depois de 1,5x, piso -50 %, tempo 30 min, taxa 1,75 % por perna, fill
-- pessimista no mcap OBSERVADO da barra). Base = quote->>'mcap_sol' da propria
-- proposta que gerou a ordem. R = (multiplo liquido - 1) / 0,5.
\pset pager off
SET statement_timeout = 120000;
WITH ordem AS (
  SELECT DISTINCT ON (o.admission->>'mint')
         o.admission->>'mint' AS mint, o.received_at AS t0,
         (p.quote->>'mcap_sol')::numeric AS base
  FROM meme_live_orders o JOIN meme_proposals p ON p.id = o.proposal_id
  WHERE (p.quote->>'mcap_sol')::numeric > 0
  ORDER BY o.admission->>'mint', o.received_at
), barras AS (
  SELECT e.mint, e.t0, e.base, s.end_time, s.mcap_sol,
         row_number() OVER (PARTITION BY e.mint ORDER BY s.end_time) AS i,
         max(s.mcap_sol) OVER (PARTITION BY e.mint ORDER BY s.end_time
                               ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS pico_ate_anterior
  FROM ordem e
  JOIN meme_features_1m s ON s.mint = e.mint
   AND s.end_time > e.t0 AND s.end_time <= e.t0 + interval '30 minutes'
  WHERE s.mcap_sol IS NOT NULL
), gatilho AS (
  SELECT *, CASE WHEN COALESCE(pico_ate_anterior, base) >= 1.5 * base
                 THEN greatest(0.65 * COALESCE(pico_ate_anterior, base), 0.5 * base)
                 ELSE 0.5 * base END AS nivel_stop
  FROM barras
), saida AS (
  SELECT DISTINCT ON (mint) mint, i,
         CASE WHEN mcap_sol >= 3 * base THEN 3 * base ELSE mcap_sol END AS preco_saida,
         CASE WHEN mcap_sol >= 3 * base THEN 'alvo_3x' ELSE 'stop_trailing' END AS motivo
  FROM gatilho WHERE mcap_sol >= 3 * base OR mcap_sol <= nivel_stop ORDER BY mint, i
), fim AS (
  SELECT DISTINCT ON (mint) mint, mcap_sol AS preco_saida, 'tempo_30m' AS motivo
  FROM gatilho ORDER BY mint, i DESC
), extremos AS (
  SELECT mint, max(mcap_sol) AS pico, min(mcap_sol) AS mini, count(*) AS barras
  FROM barras GROUP BY mint
)
SELECT left(e.mint,6) AS mint,
       to_char(e.t0 AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS decisao_brt,
       round(e.base,2) AS base_mcap_sol,
       x.barras AS barras_30m,
       round(x.pico / e.base, 3) AS pico_rel,
       round(x.mini / e.base, 3) AS minimo_rel,
       COALESCE(s.motivo, f.motivo) AS saida,
       round(COALESCE(s.preco_saida, f.preco_saida) / e.base, 3) AS multiplo_bruto,
       round(((COALESCE(s.preco_saida, f.preco_saida) / e.base) * 0.9825 * 0.9825 - 1) / 0.5, 3) AS r
FROM ordem e
LEFT JOIN extremos x ON x.mint = e.mint
LEFT JOIN saida s ON s.mint = e.mint
LEFT JOIN fim f ON f.mint = e.mint
ORDER BY e.t0;
