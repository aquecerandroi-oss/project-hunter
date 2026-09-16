-- R34 q06 — o numero que a porta de fato le (tape_source = activity_1m, o lote da pump.fun)
-- contra a cadeia, minuto a minuto. Fatia de 6 h para caber no statement_timeout.
\set d0 '2026-09-15 18:00+00'
\set d1 '2026-09-16 00:00+00'
SET statement_timeout = 60000;
WITH m AS (
  SELECT mint, date_trunc('minute', observed_at) AS mi,
         (array_agg(real_sol_reserves ORDER BY observed_at DESC))[1] AS last_sol
  FROM meme_curve_snapshots
  WHERE observed_at >= timestamptz :'d0' AND observed_at < timestamptz :'d1'
  GROUP BY 1, 2
), mm AS (
  SELECT mint, mi, last_sol - lag(last_sol) OVER w AS chain_net, lag(mi) OVER w AS prev_mi
  FROM m WINDOW w AS (PARTITION BY mint ORDER BY mi)
), chain AS (
  SELECT mint, mi, chain_net FROM mm WHERE prev_mi = mi - interval '1 minute' AND abs(chain_net) >= 0.1
), f AS (
  SELECT mint, date_trunc('minute', end_time - interval '1 second') AS mi, tape_source,
         net_sol_flow_1m, curve_volume_1m_sol, unique_buyers, buys_1m, sells_1m
  FROM meme_features_1m
  WHERE end_time >= timestamptz :'d0' AND end_time < timestamptz :'d1' AND tape_source IS NOT NULL
)
SELECT f.tape_source,
       count(*) AS pares, count(DISTINCT f.mint) AS moedas,
       round(100.0 * count(*) FILTER (WHERE sign(f.net_sol_flow_1m) = sign(c.chain_net)) / count(*), 1) AS sinal_igual_pct,
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY f.net_sol_flow_1m / c.chain_net))::numeric, 2) AS razao_fluxo_mediana,
       round(corr(f.net_sol_flow_1m::float8, c.chain_net::float8)::numeric, 3) AS corr_fluxo,
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY f.curve_volume_1m_sol / abs(c.chain_net)))::numeric, 2) AS razao_volume_mediana,
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY f.unique_buyers))::numeric, 1) AS compradores_unicos_mediana
FROM f JOIN chain c ON c.mint = f.mint AND c.mi = f.mi
GROUP BY 1 ORDER BY 2 DESC;
