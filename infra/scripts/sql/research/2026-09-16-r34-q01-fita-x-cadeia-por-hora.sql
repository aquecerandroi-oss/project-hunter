-- R34 q01 — quanto da negociacao real a fita ve, por hora BRT.
-- Cadeia: soma de |delta real_sol_reserves| entre fotos consecutivas do mesmo mint
-- (piso: o que acontece DENTRO de uma janela de 15 s se anula). Fita: meme_trades.
-- Rodar um dia BRT por vez (<= 24 h): 15/09 = [2026-09-15 03:00Z, 2026-09-16 03:00Z).
\set d0 '2026-09-15 03:00+00'
\set d1 '2026-09-16 03:00+00'
SET statement_timeout = 60000;
WITH s AS (
  SELECT mint, observed_at, real_sol_reserves,
         lag(real_sol_reserves) OVER (PARTITION BY mint ORDER BY observed_at) AS prev,
         lag(observed_at)       OVER (PARTITION BY mint ORDER BY observed_at) AS prev_at
  FROM meme_curve_snapshots
  WHERE observed_at >= timestamptz :'d0' AND observed_at < timestamptz :'d1'
), chain AS (
  SELECT date_trunc('hour', observed_at - interval '3 hours') AS h,
         sum(abs(real_sol_reserves - prev)) FILTER (WHERE observed_at - prev_at <= interval '60 seconds') AS chain_sol_60s,
         sum(abs(real_sol_reserves - prev)) AS chain_sol_all,
         count(DISTINCT mint) AS chain_mints
  FROM s WHERE prev IS NOT NULL GROUP BY 1
), tape AS (
  SELECT date_trunc('hour', block_time - interval '3 hours') AS h,
         sum(sol_lamports) FILTER (WHERE program = 'pump')     / 1e9 AS tape_sol_pump,
         sum(sol_lamports) FILTER (WHERE program = 'pump_amm') / 1e9 AS tape_sol_amm,
         count(*) FILTER (WHERE program = 'pump') AS n_pump,
         count(*) FILTER (WHERE program = 'pump_amm') AS n_amm,
         count(DISTINCT mint) AS tape_mints
  FROM meme_trades
  WHERE block_time >= timestamptz :'d0' AND block_time < timestamptz :'d1'
  GROUP BY 1
)
SELECT to_char(c.h, 'HH24') AS hora_brt,
       round(c.chain_sol_60s, 1) AS cadeia_sol,
       round(c.chain_sol_all, 1) AS cadeia_sol_sem_filtro,
       c.chain_mints AS moedas_cadeia,
       round(t.tape_sol_pump, 1) AS fita_sol_pump,
       round(t.tape_sol_amm, 1)  AS fita_sol_amm,
       t.n_pump, t.n_amm, t.tape_mints AS moedas_fita,
       round(100 * t.tape_sol_pump / nullif(c.chain_sol_60s, 0), 1) AS cobertura_pct,
       round(100.0 * t.tape_mints / nullif(c.chain_mints, 0), 1) AS cobertura_moedas_pct
FROM chain c LEFT JOIN tape t USING (h)
ORDER BY c.h;
