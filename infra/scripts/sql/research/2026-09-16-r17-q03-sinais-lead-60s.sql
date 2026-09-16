-- R17 (KB-0108) — sinais de drawdown, demanda e holders — precisao/recall e lead mediano
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
), w AS (
  SELECT v.mint, v.grupo, v.t0, f.as_of, f.holders, f.holders_rising, f.buys_60s, f.sells_60s,
    f.net_sol_flow_60s, f.mcap_sol, extract(epoch from v.t0 - f.as_of) AS lead_s,
    max(f.mcap_sol) OVER (PARTITION BY v.mint ORDER BY f.as_of) AS pico_run,
    max(f.buys_60s) OVER (PARTITION BY v.mint ORDER BY f.as_of) AS buys_max,
    max(f.holders) OVER (PARTITION BY v.mint ORDER BY f.as_of) AS h_max
  FROM v JOIN meme_features_15s f ON f.mint = v.mint
  WHERE f.as_of >= v.t0 - interval '300 seconds' AND f.as_of <= v.t0
), agg AS (
  SELECT mint, grupo,
    min(lead_s) FILTER (WHERE lead_s>=60 AND mcap_sol <= 0.80*pico_run) AS l_dd20,
    min(lead_s) FILTER (WHERE lead_s>=60 AND mcap_sol <= 0.70*pico_run) AS l_dd30,
    min(lead_s) FILTER (WHERE lead_s>=60 AND buys_60s <= 0.5*buys_max) AS l_demanda,
    min(lead_s) FILTER (WHERE lead_s>=60 AND holders <= 0.9*h_max) AS l_h10,
    min(lead_s) FILTER (WHERE lead_s>=60 AND holders_rising IS FALSE) AS l_hstop,
    min(lead_s) FILTER (WHERE lead_s>=60 AND sells_60s::numeric > 0.6*buys_60s AND mcap_sol <= 0.80*pico_run) AS l_comb,
    min(lead_s) FILTER (WHERE lead_s>=60 AND buys_60s <= 0.5*buys_max AND mcap_sol <= 0.80*pico_run) AS l_comb2,
    extract(epoch from max(t0) - max(t0)) AS z
  FROM w GROUP BY 1,2
), t AS (
  SELECT grupo, extract(epoch from t_morte - t_gate) AS dur, extract(epoch from t_pico - t_gate) AS durp FROM v
)
SELECT a.grupo, count(*) AS n,
  count(*) FILTER (WHERE l_dd20 IS NOT NULL) AS dd20, round(percentile_cont(0.5) WITHIN GROUP (ORDER BY l_dd20)::numeric,0) AS lt_dd20,
  count(*) FILTER (WHERE l_dd30 IS NOT NULL) AS dd30, round(percentile_cont(0.5) WITHIN GROUP (ORDER BY l_dd30)::numeric,0) AS lt_dd30,
  count(*) FILTER (WHERE l_demanda IS NOT NULL) AS dem, round(percentile_cont(0.5) WITHIN GROUP (ORDER BY l_demanda)::numeric,0) AS lt_dem,
  count(*) FILTER (WHERE l_h10 IS NOT NULL) AS h10, round(percentile_cont(0.5) WITHIN GROUP (ORDER BY l_h10)::numeric,0) AS lt_h10,
  count(*) FILTER (WHERE l_hstop IS NOT NULL) AS hstop, round(percentile_cont(0.5) WITHIN GROUP (ORDER BY l_hstop)::numeric,0) AS lt_hstop,
  count(*) FILTER (WHERE l_comb IS NOT NULL) AS comb, round(percentile_cont(0.5) WITHIN GROUP (ORDER BY l_comb)::numeric,0) AS lt_comb,
  count(*) FILTER (WHERE l_comb2 IS NOT NULL) AS comb2, round(percentile_cont(0.5) WITHIN GROUP (ORDER BY l_comb2)::numeric,0) AS lt_comb2
FROM agg a GROUP BY a.grupo ORDER BY a.grupo;
