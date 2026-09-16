-- R17 (KB-0108) — fita (meme_trades): fatia dos 3 maiores vendedores nos 5 min antes — amostra <= 200 mints/grupo
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
, amostra AS (
  (SELECT mint, grupo, t0 FROM v WHERE grupo = 'morte' ORDER BY mint LIMIT 200)
  UNION ALL
  (SELECT mint, grupo, t0 FROM v WHERE grupo = 'sobrevivente' ORDER BY mint LIMIT 200)
), tr AS (
  SELECT a.mint, a.grupo, tr.side, tr.trader,
         sum(tr.sol_lamports)/1e9 AS sol,
         sum(CASE WHEN tr.block_time <= a.t0 - interval '60 seconds' THEN tr.sol_lamports ELSE 0 END)/1e9 AS sol_ate_m60
  FROM amostra a JOIN meme_trades tr ON tr.mint = a.mint
   AND tr.block_time >= a.t0 - interval '300 seconds' AND tr.block_time <= a.t0
  GROUP BY 1,2,3,4
), perfil AS (
  SELECT mint, grupo,
    sum(sol) FILTER (WHERE side='sell') AS vendas,
    sum(sol) FILTER (WHERE side='buy')  AS compras,
    sum(sol_ate_m60) FILTER (WHERE side='sell') AS vendas_m60,
    sum(sol_ate_m60) FILTER (WHERE side='buy')  AS compras_m60,
    count(*) FILTER (WHERE side='sell') AS n_vendedores,
    (SELECT sum(x.sol) FROM (SELECT sol FROM tr t2 WHERE t2.mint=tr.mint AND t2.side='sell' ORDER BY sol DESC LIMIT 3) x) AS top3_sell,
    (SELECT sum(x.sol_ate_m60) FROM (SELECT sol_ate_m60 FROM tr t3 WHERE t3.mint=tr.mint AND t3.side='sell' ORDER BY sol_ate_m60 DESC LIMIT 3) x) AS top3_sell_m60
  FROM tr GROUP BY mint, grupo
)
SELECT grupo, count(*) AS n,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY vendas)::numeric,2) AS vendas_sol,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY compras)::numeric,2) AS compras_sol,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY n_vendedores)::numeric,0) AS vendedores,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY top3_sell/nullif(vendas,0))::numeric,3) AS fatia_top3,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY top3_sell_m60/nullif(vendas_m60,0))::numeric,3) AS fatia_top3_m60,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY vendas_m60/nullif(compras_m60,0))::numeric,3) AS vc_m60,
  count(*) FILTER (WHERE vendas_m60 > compras_m60) AS n_vc_m60_gt1,
  count(*) FILTER (WHERE top3_sell_m60/nullif(vendas_m60,0) >= 0.6 AND vendas_m60 >= 0.5) AS n_top3_60pct_m60
FROM perfil GROUP BY grupo ORDER BY grupo;
