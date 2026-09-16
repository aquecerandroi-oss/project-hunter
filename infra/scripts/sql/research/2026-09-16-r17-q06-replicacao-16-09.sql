-- R17 (KB-0108) — replicacao no dia seguinte (16/09) — mesma classificacao, mesmos sinais
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
, w AS (
  SELECT v.mint, v.grupo, v.t0, f.as_of, f.holders, f.holders_rising, f.buys_60s, f.sells_60s,
    f.net_sol_flow_60s, f.creator_net_seller, f.snipers, f.mcap_sol, extract(epoch from v.t0 - f.as_of) AS lead_s,
    max(f.mcap_sol) OVER (PARTITION BY v.mint ORDER BY f.as_of) AS pico_run,
    max(f.buys_60s) OVER (PARTITION BY v.mint ORDER BY f.as_of) AS buys_max,
    max(f.holders) OVER (PARTITION BY v.mint ORDER BY f.as_of) AS h_max
  FROM v JOIN meme_features_15s f ON f.mint = v.mint
  WHERE f.as_of >= v.t0 - interval '300 seconds' AND f.as_of <= v.t0
), agg AS (
  SELECT mint, grupo,
    (array_agg(holders ORDER BY as_of))[1] AS h_ini,
    (array_agg(holders ORDER BY as_of DESC) FILTER (WHERE lead_s>=60))[1] AS h_60,
    (array_agg(holders ORDER BY as_of DESC))[1] AS h_0,
    round(avg(net_sol_flow_60s) FILTER (WHERE lead_s BETWEEN 60 AND 120)::numeric,2) AS flux_m1,
    round(avg(net_sol_flow_60s) FILTER (WHERE lead_s < 60)::numeric,2) AS flux_m0,
    min(lead_s) FILTER (WHERE lead_s>=60 AND mcap_sol <= 0.80*pico_run) AS l_dd20,
    min(lead_s) FILTER (WHERE lead_s>=60 AND mcap_sol <= 0.70*pico_run) AS l_dd30,
    min(lead_s) FILTER (WHERE lead_s>=60 AND sells_60s::numeric > 0.6*buys_60s) AS l_porta,
    min(lead_s) FILTER (WHERE lead_s>=60 AND net_sol_flow_60s < 0) AS l_fluxo,
    min(lead_s) FILTER (WHERE lead_s>=60 AND creator_net_seller) AS l_criador,
    min(lead_s) FILTER (WHERE lead_s>=60 AND holders_rising IS FALSE) AS l_hstop,
    min(lead_s) FILTER (WHERE lead_s>=60 AND buys_60s <= 0.5*buys_max) AS l_dem,
    min(lead_s) FILTER (WHERE lead_s>=60 AND sells_60s::numeric > 0.6*buys_60s AND mcap_sol <= 0.80*pico_run) AS l_comb
  FROM w GROUP BY 1,2
)
SELECT grupo, count(*) AS n,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY h_ini)::numeric,0) AS h_m5,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY h_60)::numeric,0) AS h_m1,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY h_0)::numeric,0) AS h_t0,
  round(avg(flux_m1)::numeric,2) AS fluxo_m1, round(avg(flux_m0)::numeric,2) AS fluxo_m0,
  count(*) FILTER (WHERE l_dd20 IS NOT NULL) AS dd20, round(percentile_cont(0.5) WITHIN GROUP (ORDER BY l_dd20)::numeric,0) AS lt_dd20,
  count(*) FILTER (WHERE l_dd30 IS NOT NULL) AS dd30,
  count(*) FILTER (WHERE l_porta IS NOT NULL) AS porta,
  count(*) FILTER (WHERE l_fluxo IS NOT NULL) AS fluxo,
  count(*) FILTER (WHERE l_criador IS NOT NULL) AS criador,
  count(*) FILTER (WHERE l_hstop IS NOT NULL) AS hstop,
  count(*) FILTER (WHERE l_dem IS NOT NULL) AS dem,
  count(*) FILTER (WHERE l_comb IS NOT NULL) AS comb, round(percentile_cont(0.5) WITHIN GROUP (ORDER BY l_comb)::numeric,0) AS lt_comb
FROM agg GROUP BY grupo ORDER BY grupo;
