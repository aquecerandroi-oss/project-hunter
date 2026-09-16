-- R17 (KB-0108) — tempo porta->morte e quando a linha de tendencia (distance_to_support_pct < 0) dispara
-- Universo: moedas que passaram a porta calibrada (operator/5) em meme_features_15s.
-- Rodar um dia por vez (<= 24 h): trocar DIA0/DIA1 por '2026-09-15 00:00-03'/'2026-09-16 00:00-03'
-- (ou 16/09) antes de executar. curve_progress_pct e fracao 0-1.
SET statement_timeout = 240000;
WITH g AS (
  SELECT f.mint, min(f.as_of) AS t_gate
  FROM meme_features_15s f JOIN meme_tokens t ON t.mint = f.mint AND t.mayhem_mode IS NULL
  WHERE f.as_of >= timestamptz 'DIA0' AND f.as_of < timestamptz 'DIA1'
    AND f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.05 AND 0.50
    AND f.holders >= 20 AND f.unique_buyers_60s >= 10
    AND f.buys_60s > 0 AND f.sells_60s::numeric <= 0.6 * f.buys_60s
    AND f.net_sol_flow_60s > 0 AND f.tape_reason IS NULL
  GROUP BY 1
), s AS (
  SELECT g.mint, g.t_gate, f.as_of AS ts, f.mcap_sol FROM g JOIN meme_features_15s f ON f.mint = g.mint
  WHERE f.as_of >= g.t_gate AND f.as_of < g.t_gate + interval '30 min' AND f.mcap_sol IS NOT NULL
  UNION
  SELECT g.mint, g.t_gate, f.end_time, f.mcap_sol FROM g JOIN meme_features_1m f ON f.mint = g.mint
  WHERE f.end_time >= g.t_gate AND f.end_time < g.t_gate + interval '30 min' AND f.mcap_sol IS NOT NULL
), pk AS (
  SELECT DISTINCT ON (mint) mint, t_gate, ts AS t_pico, mcap_sol AS pico FROM s ORDER BY mint, mcap_sol DESC, ts
), u AS (
  SELECT pk.mint, pk.t_gate, pk.pico, pk.t_pico,
    (SELECT min(x.ts) FROM s x WHERE x.mint = pk.mint AND x.ts > pk.t_pico AND x.mcap_sol <= 0.5*pk.pico) AS t_morte,
    (SELECT max(x.ts) FROM s x WHERE x.mint = pk.mint) AS t_fim FROM pk
), v AS (
  SELECT mint, t_gate, pico, t_pico, t_morte,
    CASE WHEN t_morte IS NOT NULL THEN 'morte'
         WHEN t_fim >= t_pico + interval '180 seconds' THEN 'sobrevivente' ELSE 'censurada' END AS grupo,
    coalesce(t_morte, t_pico) AS t0 FROM u
)
, lb AS (
  SELECT v.mint, v.grupo, v.t0,
    min(extract(epoch from v.t0 - f.end_time)) FILTER (WHERE f.distance_to_support_pct < 0 AND f.line_reason IS NULL) AS l_linha,
    count(*) FILTER (WHERE f.line_reason IS NULL) AS n_linha
  FROM v LEFT JOIN meme_features_1m f ON f.mint = v.mint
    AND f.end_time >= v.t0 - interval '300 seconds' AND f.end_time <= v.t0
  GROUP BY 1,2,3
)
SELECT 'tempo' AS bloco, grupo, count(*)::text AS n,
  round(percentile_cont(0.25) WITHIN GROUP (ORDER BY extract(epoch from t0 - t_gate))::numeric,0)::text AS p25,
  round(percentile_cont(0.5)  WITHIN GROUP (ORDER BY extract(epoch from t0 - t_gate))::numeric,0)::text AS p50,
  round(percentile_cont(0.75) WITHIN GROUP (ORDER BY extract(epoch from t0 - t_gate))::numeric,0)::text AS p75,
  ''::text AS x, ''::text AS y
FROM v GROUP BY grupo
UNION ALL
SELECT 'linha', grupo, count(*)::text,
  count(*) FILTER (WHERE n_linha > 0)::text,
  count(*) FILTER (WHERE l_linha IS NOT NULL)::text,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY l_linha)::numeric,0)::text,
  count(*) FILTER (WHERE l_linha >= 60)::text, ''
FROM lb GROUP BY grupo
ORDER BY 1,2;
