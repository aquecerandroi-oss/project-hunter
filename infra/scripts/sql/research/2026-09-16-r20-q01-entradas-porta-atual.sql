-- KB-0110 Q01 — Entradas da PORTA ATUAL da mesa (KB-0102/KB-0106/KB-0107), um dia por execucao.
-- Porta: foto de 15 s com age_s 30-300 s, nao-Mayhem (mayhem_enabled = false E mayhem_mode IS NULL),
--   curva viva, curve_progress_pct 0,05-0,50 (FRACAO 0-1), fita presente (tape_reason IS NULL),
--   net_sol_flow_60s > 0, dev_share <= 0,10, pedigree do KB-0099, snipers >= 21 (piso da KB-0102).
-- Entrada = PRIMEIRA barra de 1 min depois dessa foto (ate :ew min) com holders >= 20,
--   unique_buyers >= 10 e sells_1m/buys_1m <= 0,6. Fill no mcap OBSERVADO da barra (base).
-- Convencao r4-q05 (KB-0099): t0 = PRIMEIRA foto que PASSA a porta (a mesa avalia
--   toda foto de 15 s, nao so a primeira do dia).
-- Uso: psql -v dia=2026-09-12 -v ew=5 -At -F "|" -f este-arquivo.sql
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
)
SELECT (:'dia') AS dia, e.mint, t.symbol, e.snipers,
       to_char(e.t_in AT TIME ZONE $Z$America/Sao_Paulo$Z$, $F$YYYY-MM-DD HH24:MI:SS$F$) AS t_in_brt,
       e.base
FROM entrada e JOIN meme_tokens t ON t.mint = e.mint
ORDER BY e.t_in;
