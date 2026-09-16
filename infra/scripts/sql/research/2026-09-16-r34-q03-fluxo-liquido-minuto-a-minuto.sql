-- R34 q03 — a fita serve para FLUXO? Casamento minuto a minuto, so nas moedas que a fita cobre.
-- chain_net = ultima real_sol_reserves do minuto menos a ultima do minuto anterior (minutos contiguos).
-- tape_net  = soma de compras menos vendas da fita no mesmo minuto (program = pump).
\set d0 '2026-09-15 03:00+00'
\set d1 '2026-09-16 03:00+00'
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
  SELECT mint, mi, chain_net FROM mm WHERE prev_mi = mi - interval '1 minute'
), tape AS (
  SELECT mint, date_trunc('minute', block_time) AS mi,
         sum(CASE WHEN side = 'buy' THEN sol_lamports ELSE -sol_lamports END) / 1e9 AS tape_net,
         sum(sol_lamports) / 1e9 AS tape_gross,
         count(*) AS n, count(DISTINCT trader) AS traders,
         count(DISTINCT trader) FILTER (WHERE side = 'buy') AS buyers
  FROM meme_trades
  WHERE block_time >= timestamptz :'d0' AND block_time < timestamptz :'d1' AND program = 'pump'
  GROUP BY 1, 2
), j AS (
  SELECT c.mint, c.mi, c.chain_net, t.tape_net, t.tape_gross, t.n, t.buyers
  FROM chain c JOIN tape t ON t.mint = c.mint AND t.mi = c.mi
  WHERE abs(c.chain_net) >= 0.1
)
SELECT count(*) AS pares_minuto_moeda,
       count(DISTINCT mint) AS moedas,
       round(100.0 * count(*) FILTER (WHERE sign(tape_net) = sign(chain_net)) / count(*), 1) AS sinal_igual_pct,
       round(100.0 * count(*) FILTER (WHERE abs(tape_net - chain_net) <= 0.2 * abs(chain_net)) / count(*), 1) AS dentro_20pct,
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY tape_net / chain_net))::numeric, 2) AS razao_mediana,
       round((percentile_cont(0.25) WITHIN GROUP (ORDER BY tape_net / chain_net))::numeric, 2) AS razao_p25,
       round((percentile_cont(0.75) WITHIN GROUP (ORDER BY tape_net / chain_net))::numeric, 2) AS razao_p75,
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY tape_gross / abs(chain_net)))::numeric, 2) AS bruto_sobre_liquido_mediana,
       round(corr(tape_net, chain_net)::numeric, 3) AS correlacao,
       round(100.0 * count(*) FILTER (WHERE n >= 100) / count(*), 1) AS pagina_cheia_pct
FROM j;
