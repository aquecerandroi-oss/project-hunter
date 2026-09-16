-- R17 (KB-0108) — cobertura pos-porta e quantas mortes (queda >= 50%% do pico) sao observaveis
-- Universo: moedas que passaram a porta calibrada (operator/5) em meme_features_15s.
-- Rodar um dia por vez (<= 24 h): trocar DIA0/DIA1 por '2026-09-15 00:00-03'/'2026-09-16 00:00-03'
-- (ou 16/09) antes de executar. curve_progress_pct e fracao 0-1.
SET statement_timeout = 240000;
WITH g AS (
  SELECT f.mint, min(f.as_of) AS t_gate
  FROM meme_features_15s f JOIN meme_tokens t ON t.mint = f.mint AND t.mayhem_mode IS NULL
  WHERE f.as_of >= timestamptz '2026-09-15 00:00-03' AND f.as_of < timestamptz '2026-09-16 00:00-03'
    AND f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.05 AND 0.50
    AND f.holders >= 20 AND f.unique_buyers_60s >= 10
    AND f.buys_60s > 0 AND f.sells_60s::numeric <= 0.6 * f.buys_60s
    AND f.net_sol_flow_60s > 0 AND f.tape_reason IS NULL
  GROUP BY 1
), s AS (
  SELECT g.mint, g.t_gate, f.as_of AS ts, f.mcap_sol
  FROM g JOIN meme_features_15s f ON f.mint = g.mint
  WHERE f.as_of >= g.t_gate AND f.as_of < g.t_gate + interval '30 min' AND f.mcap_sol IS NOT NULL
  UNION
  SELECT g.mint, g.t_gate, f.end_time, f.mcap_sol
  FROM g JOIN meme_features_1m f ON f.mint = g.mint
  WHERE f.end_time >= g.t_gate AND f.end_time < g.t_gate + interval '30 min' AND f.mcap_sol IS NOT NULL
), c AS (
  SELECT mint, count(*) AS n, extract(epoch from max(ts) - min(ts)) AS span_s,
         max(mcap_sol) AS pico, min(mcap_sol) AS vale,
         (SELECT x.ts FROM s x WHERE x.mint = s.mint ORDER BY x.mcap_sol DESC, x.ts LIMIT 1) AS t_pico
  FROM s GROUP BY mint
)
SELECT count(*) AS n,
  count(*) FILTER (WHERE span_s >= 300) AS span_ge_5min,
  count(*) FILTER (WHERE span_s >= 600) AS span_ge_10min,
  count(*) FILTER (WHERE span_s >= 1500) AS span_ge_25min,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY span_s)::numeric,0) AS span_mediano_s,
  count(*) FILTER (WHERE (SELECT min(x.mcap_sol) FROM s x WHERE x.mint = c.mint AND x.ts > c.t_pico) <= 0.5 * c.pico) AS mortas_obs,
  count(*) FILTER (WHERE (SELECT count(*) FROM s x WHERE x.mint = c.mint AND x.ts > c.t_pico) = 0) AS pico_no_fim
FROM c;
