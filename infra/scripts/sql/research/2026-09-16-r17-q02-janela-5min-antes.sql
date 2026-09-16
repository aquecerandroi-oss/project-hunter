-- R17 (KB-0108) — trajetoria da janela [-5 min, 0] e sinais simples com lead >= 60 s
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
  SELECT g.mint, g.t_gate, f.as_of AS ts, f.mcap_sol
  FROM g JOIN meme_features_15s f ON f.mint = g.mint
  WHERE f.as_of >= g.t_gate AND f.as_of < g.t_gate + interval '30 min' AND f.mcap_sol IS NOT NULL
  UNION
  SELECT g.mint, g.t_gate, f.end_time, f.mcap_sol
  FROM g JOIN meme_features_1m f ON f.mint = g.mint
  WHERE f.end_time >= g.t_gate AND f.end_time < g.t_gate + interval '30 min' AND f.mcap_sol IS NOT NULL
), pk AS (
  SELECT DISTINCT ON (mint) mint, t_gate, ts AS t_pico, mcap_sol AS pico
  FROM s ORDER BY mint, mcap_sol DESC, ts
), cls AS (
  SELECT pk.*,
         (SELECT min(x.ts) FROM s x WHERE x.mint = pk.mint AND x.ts > pk.t_pico AND x.mcap_sol <= 0.5 * pk.pico) AS t_morte,
         (SELECT max(x.ts) FROM s x WHERE x.mint = pk.mint) AS t_fim
  FROM pk
), u AS (
  SELECT mint, t_gate, pico, t_pico, t_morte, t_fim,
         CASE WHEN t_morte IS NOT NULL THEN 'morte'
              WHEN t_fim >= t_pico + interval '180 seconds' THEN 'sobrevivente'
              ELSE 'censurada' END AS grupo,
         coalesce(t_morte, t_pico) AS t0
  FROM cls
), w AS (   -- janela [t0-300s, t0] na serie de 15 s
  SELECT u.mint, u.grupo, u.t0, f.as_of, f.holders, f.buys_60s, f.sells_60s,
         f.net_sol_flow_60s, f.creator_net_seller, f.snipers, f.mcap_sol,
         extract(epoch from u.t0 - f.as_of) AS lead_s
  FROM u JOIN meme_features_15s f ON f.mint = u.mint
  WHERE f.as_of >= u.t0 - interval '300 seconds' AND f.as_of <= u.t0
), agg AS (
  SELECT mint, grupo,
    max(holders) FILTER (WHERE lead_s >= 60) AS h_max60,
    (array_agg(holders ORDER BY as_of DESC) FILTER (WHERE lead_s >= 60))[1] AS h_at60,
    (array_agg(holders ORDER BY as_of DESC))[1] AS h_at0,
    (array_agg(holders ORDER BY as_of))[1] AS h_ini,
    (array_agg(snipers ORDER BY as_of DESC))[1] AS snip,
    count(*) AS n_linhas,
    -- sinais avaliados so em linhas com lead >= 60 s
    min(lead_s) FILTER (WHERE lead_s >= 60 AND sells_60s > buys_60s) AS lead_razao,
    min(lead_s) FILTER (WHERE lead_s >= 60 AND net_sol_flow_60s < 0) AS lead_fluxo,
    min(lead_s) FILTER (WHERE lead_s >= 60 AND creator_net_seller) AS lead_criador,
    min(lead_s) FILTER (WHERE lead_s >= 60 AND holders < h_run.hmax) AS lead_holders,
    min(lead_s) FILTER (WHERE lead_s >= 60 AND sells_60s::numeric > 0.6 * buys_60s) AS lead_porta,
    round(avg(buys_60s) FILTER (WHERE lead_s BETWEEN 60 AND 120)::numeric,1) AS buys_60_120,
    round(avg(sells_60s) FILTER (WHERE lead_s BETWEEN 60 AND 120)::numeric,1) AS sells_60_120,
    round(avg(net_sol_flow_60s) FILTER (WHERE lead_s BETWEEN 60 AND 120)::numeric,2) AS flux_60_120,
    round(avg(buys_60s) FILTER (WHERE lead_s < 60)::numeric,1) AS buys_0_60,
    round(avg(sells_60s) FILTER (WHERE lead_s < 60)::numeric,1) AS sells_0_60,
    round(avg(net_sol_flow_60s) FILTER (WHERE lead_s < 60)::numeric,2) AS flux_0_60
  FROM w
  LEFT JOIN LATERAL (SELECT max(w2.holders) AS hmax FROM w w2 WHERE w2.mint = w.mint AND w2.as_of < w.as_of) h_run ON true
  GROUP BY mint, grupo
)
SELECT grupo, count(*) AS n,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY h_ini)::numeric,0) AS holders_m5,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY h_at60)::numeric,0) AS holders_m1,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY h_at0)::numeric,0) AS holders_t0,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY snip)::numeric,0) AS snipers,
  round(avg(buys_60_120)::numeric,1) AS buys_m1, round(avg(sells_60_120)::numeric,1) AS sells_m1,
  round(avg(flux_60_120)::numeric,2) AS fluxo_m1,
  round(avg(buys_0_60)::numeric,1) AS buys_m0, round(avg(sells_0_60)::numeric,1) AS sells_m0,
  round(avg(flux_0_60)::numeric,2) AS fluxo_m0,
  count(*) FILTER (WHERE lead_razao IS NOT NULL) AS sin_razao,
  count(*) FILTER (WHERE lead_fluxo IS NOT NULL) AS sin_fluxo,
  count(*) FILTER (WHERE lead_criador IS NOT NULL) AS sin_criador,
  count(*) FILTER (WHERE lead_holders IS NOT NULL) AS sin_holders,
  count(*) FILTER (WHERE lead_porta IS NOT NULL) AS sin_porta,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY lead_razao)::numeric,0) AS lt_razao,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY lead_fluxo)::numeric,0) AS lt_fluxo,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY lead_criador)::numeric,0) AS lt_criador,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY lead_holders)::numeric,0) AS lt_holders,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY lead_porta)::numeric,0) AS lt_porta
FROM agg GROUP BY grupo ORDER BY grupo;
