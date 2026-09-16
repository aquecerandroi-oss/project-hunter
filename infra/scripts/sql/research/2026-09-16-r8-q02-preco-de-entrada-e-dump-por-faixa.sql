-- KB-0102 Q02 — diagnostico por moeda: preco de entrada, atraso ate a entrada,
-- Universo = janela do executor (KB-0101 §3): a primeira foto de 15 s com
--   age_s 30-300 s, curva viva, nao-Mayhem (flag false E mayhem_mode nulo),
--   curve_progress_pct 0,02-0,50 (fracao), fita presente (tape_reason NULL),
--   fluxo liquido 60 s > 0, dev_share <= 0,10 e pedigree (KB-0099).
-- Entrada = a PRIMEIRA barra de 1 min depois dessa foto (ate :ew minutos)
--   que satisfaz a porta calibrada do KB-0099: holders >= 20,
--   unique_buyers >= 10 e sells_1m/buys_1m <= 0,6. Sem filtro de snipers
--   (snipers e a variavel em teste; as regras sao aplicadas na analise).
-- Saida = metodologia do KB-0099 (r4-q05) nas barras de 1 min: alvo 3x,
--   trailing 35 % armado depois de 1,5x, piso -50 %, tempo :hz minutos,
--   taxa 1,75 % por perna, stop preenchido no mcap OBSERVADO da barra.
--   R = (multiplo liquido - 1) / 0,5.
-- pico e vale do multiplo em :hz min. Mesmo universo, entrada e janela da Q01.
-- Uso: psql -v dia=2026-09-12 -v ew=5 -v hz=30 -At -f este-arquivo.sql
SET statement_timeout = 60000;

WITH foto AS (
  SELECT DISTINCT ON (f.mint)
         f.mint, f.as_of AS t0, f.snipers, f.curve_progress_pct, f.tape_reason,
         f.net_sol_flow_60s, f.mcap_delta_60s, f.dev_share,
         t.mayhem_enabled, t.mayhem_mode, t.completed_at, t.migrated_at,
         t.creator, t.symbol, t.created_at
  FROM meme_features_15s f
  JOIN meme_tokens t ON t.mint = f.mint
  WHERE f.as_of >= (:'dia')::date::timestamp AT TIME ZONE 'America/Sao_Paulo'
    AND f.as_of <  ((:'dia')::date + 1)::timestamp AT TIME ZONE 'America/Sao_Paulo'
    AND f.age_s BETWEEN 30 AND 300
  ORDER BY f.mint, f.as_of
), universo AS (
  SELECT mint, t0, snipers
  FROM foto
  WHERE (completed_at IS NULL OR completed_at > t0)
    AND (migrated_at IS NULL OR migrated_at > t0)
    AND mayhem_enabled IS NOT NULL AND NOT mayhem_enabled AND mayhem_mode IS NULL
    AND curve_progress_pct BETWEEN 0.02 AND 0.50
    AND tape_reason IS NULL
    AND net_sol_flow_60s > 0
    AND dev_share IS NOT NULL AND dev_share <= 0.10
    AND creator IS NOT NULL AND created_at IS NOT NULL
    AND (SELECT count(*) FROM meme_tokens o WHERE o.creator = foto.creator AND o.mint <> foto.mint
           AND o.created_at IS NOT NULL AND o.created_at <= foto.created_at
           AND o.created_at > foto.created_at - interval '1 hour') <= 1
    AND (SELECT count(*) FROM meme_tokens o WHERE o.symbol = foto.symbol AND o.mint <> foto.mint
           AND o.created_at IS NOT NULL AND o.created_at <= foto.created_at
           AND o.created_at > foto.created_at - interval '24 hours') <= 2
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
), barras AS (
  SELECT e.mint, e.base, s.end_time, s.mcap_sol,
         row_number() OVER (PARTITION BY e.mint ORDER BY s.end_time) AS i,
         max(s.mcap_sol) OVER (PARTITION BY e.mint ORDER BY s.end_time
                               ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS pico_ate_anterior
  FROM entrada e
  JOIN meme_features_1m s ON s.mint = e.mint
   AND s.end_time > e.t_in AND s.end_time <= e.t_in + make_interval(mins => (:'hz')::int)
  WHERE s.mcap_sol IS NOT NULL
), gatilho AS (
  SELECT *,
    CASE WHEN COALESCE(pico_ate_anterior, base) >= 1.5 * base
         THEN greatest(0.65 * COALESCE(pico_ate_anterior, base), 0.5 * base)
         ELSE 0.5 * base END AS nivel_stop
  FROM barras
), saida AS (
  SELECT DISTINCT ON (mint) mint, i,
    CASE WHEN mcap_sol >= 3 * base THEN 3 * base ELSE mcap_sol END AS preco_saida,
    CASE WHEN mcap_sol >= 3 * base THEN 'alvo_3x' ELSE 'stop' END AS motivo
  FROM gatilho
  WHERE mcap_sol >= 3 * base OR mcap_sol <= nivel_stop
  ORDER BY mint, i
), fim AS (
  SELECT DISTINCT ON (mint) mint, mcap_sol AS preco_saida, 'tempo' AS motivo
  FROM gatilho ORDER BY mint, i DESC
)
, extremos AS (
  SELECT mint, max(mcap_sol / base) AS pico_mult, min(mcap_sol / base) AS vale_mult, count(*) AS barras
  FROM barras GROUP BY mint
)
SELECT :'dia' AS dia, e.mint, e.snipers,
       CASE WHEN e.snipers IS NULL THEN 'desconhecido'
            WHEN e.snipers <= 2 THEN '0-2'
            WHEN e.snipers <= 10 THEN '3-10'
            WHEN e.snipers <= 20 THEN '11-20'
            WHEN e.snipers <= 30 THEN '21-30'
            WHEN e.snipers <= 60 THEN '31-60'
            ELSE '>60' END AS faixa,
       round(e.base, 3) AS base_mcap_sol,
       round(extract(epoch FROM (e.t_in - e.t0))::numeric, 0) AS atraso_s,
       round(x.pico_mult, 4) AS pico_mult,
       round(x.vale_mult, 4) AS vale_mult,
       x.barras
FROM entrada e JOIN extremos x ON x.mint = e.mint;
