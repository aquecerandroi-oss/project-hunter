-- KB-0110 Q02 — Serie de 15 s pos-entrada das entradas da PORTA ATUAL da mesa (KB-0102/KB-0106/KB-0107), um dia por execucao.
-- Porta: foto de 15 s com age_s 30-300 s, nao-Mayhem (mayhem_enabled = false E mayhem_mode IS NULL),
--   curva viva, curve_progress_pct 0,05-0,50 (FRACAO 0-1), fita presente (tape_reason IS NULL),
--   net_sol_flow_60s > 0, dev_share <= 0,10, pedigree do KB-0099, snipers >= 21 (piso da KB-0102).
-- Entrada = PRIMEIRA barra de 1 min depois dessa foto (ate :ew min) com holders >= 20,
--   unique_buyers >= 10 e sells_1m/buys_1m <= 0,6. Fill no mcap OBSERVADO da barra (base).
-- Convencao r4-q05 (KB-0099): t0 = PRIMEIRA foto que PASSA a porta (a mesa avalia
--   toda foto de 15 s, nao so a primeira do dia).
-- Saida: uma linha por foto de 15 s em (t_in, t_in + :hz min]: dt_s, mcap_sol,
--   sells_60s, buys_60s. A simulacao das saidas (S0..S4) roda fora do banco.
-- Uso: psql -v dia=2026-09-12 -v ew=5 -v hz=30 -At -F "|" -f este-arquivo.sql
SET statement_timeout = 120000;

WITH foto AS (
  SELECT f.mint, f.as_of AS t0, f.snipers, f.curve_progress_pct, f.tape_reason,
         f.net_sol_flow_60s, f.dev_share,
         t.mayhem_enabled, t.mayhem_mode, t.completed_at, t.migrated_at,
         t.creator, t.symbol, t.created_at
  FROM meme_features_15s f
  JOIN meme_tokens t ON t.mint = f.mint
  WHERE f.as_of >= (:'dia')::date::timestamp AT TIME ZONE 'America/Sao_Paulo'
    AND f.as_of <  ((:'dia')::date + 1)::timestamp AT TIME ZONE 'America/Sao_Paulo'
    AND f.age_s BETWEEN 30 AND 300
), universo AS (
  SELECT DISTINCT ON (mint) mint, t0, snipers
  FROM foto
  WHERE (completed_at IS NULL OR completed_at > t0)
    AND (migrated_at IS NULL OR migrated_at > t0)
    AND mayhem_enabled IS NOT NULL AND NOT mayhem_enabled AND mayhem_mode IS NULL
    AND curve_progress_pct BETWEEN 0.05 AND 0.50
    AND tape_reason IS NULL
    AND net_sol_flow_60s > 0
    AND dev_share IS NOT NULL AND dev_share <= 0.10
    AND snipers IS NOT NULL AND snipers >= 21
    AND creator IS NOT NULL AND created_at IS NOT NULL
    AND (SELECT count(*) FROM meme_tokens o WHERE o.creator = foto.creator AND o.mint <> foto.mint
           AND o.created_at IS NOT NULL AND o.created_at <= foto.created_at
           AND o.created_at > foto.created_at - interval '1 hour') <= 1
    AND (SELECT count(*) FROM meme_tokens o WHERE o.symbol = foto.symbol AND o.mint <> foto.mint
           AND o.created_at IS NOT NULL AND o.created_at <= foto.created_at
           AND o.created_at > foto.created_at - interval '24 hours') <= 2
  ORDER BY mint, t0
), entrada AS (
  SELECT DISTINCT ON (u.mint) u.mint, u.snipers, u.t0, b.end_time AS t_in, b.mcap_sol AS base
  FROM universo u
  JOIN meme_features_1m b ON b.mint = u.mint
   AND b.end_time > u.t0
   AND b.end_time <= u.t0 + make_interval(mins => (:'ew')::int)
  WHERE b.mcap_sol IS NOT NULL AND b.mcap_sol > 0
    AND b.holders >= 20
    AND b.unique_buyers >= 10
    AND b.buys_1m > 0 AND b.sells_1m::numeric / b.buys_1m <= 0.6
  ORDER BY u.mint, b.end_time
), serie AS (
  SELECT e.mint, e.base, e.t_in, f.as_of, f.mcap_sol, f.sells_60s, f.buys_60s
  FROM entrada e
  JOIN meme_features_15s f ON f.mint = e.mint
   AND f.as_of > e.t_in
   AND f.as_of <= e.t_in + make_interval(mins => (:'hz')::int)
  WHERE f.mcap_sol IS NOT NULL AND f.mcap_sol > 0
)
SELECT (:'dia') AS dia, mint,
       round(base, 6) AS base,
       round(EXTRACT(epoch FROM (as_of - t_in))::numeric, 0) AS dt_s,
       round(mcap_sol, 6) AS mcap_sol,
       COALESCE(sells_60s::text, $N$$N$) AS sells_60s,
       COALESCE(buys_60s::text, $N$$N$) AS buys_60s
FROM serie
ORDER BY mint, as_of;
