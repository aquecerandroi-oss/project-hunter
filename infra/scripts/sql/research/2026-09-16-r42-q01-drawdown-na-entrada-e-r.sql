-- KB-0118 Q01 — para cada entrada da PORTA ATUAL, o drawdown recente de
-- real_sol_reserves na barra de entrada e o R simulado da aposta.
-- Reuso literal do motor de R da KB-0099 (r4-q05), com duas mudancas
-- declaradas: (a) horizonte de tempo 30 min (o do conjunto vivo, EXP-M10),
-- (b) piso de snipers >= 21 (KB-0102), em vez do teto <= 10 do operator/5.
-- Drawdown: real_sol_reserves vem de meme_curve_snapshots (a cadeia; a serie
-- de 15 s NAO tem a coluna). Pico = max em [t0-300 s, t0]; atual = ultima foto
-- de curva <= t0. dd_pct = 100*(1 - atual/pico); t_pico_s = t0 - hora do pico.
-- Uma linha por moeda; agregacao por faixa e feita fora (r42-q02/q03).
-- Uso: psql -v dia=2026-09-15 < este-arquivo.sql
SET statement_timeout = 60000;

WITH linhas AS (
  SELECT f.mint, f.as_of, f.mcap_sol, f.curve_progress_pct, f.mcap_delta_60s,
         f.holders, f.buys_60s, f.sells_60s, f.unique_buyers_60s,
         f.net_sol_flow_60s, f.curve_volume_60s_sol, f.tape_reason,
         f.creator_net_seller, f.dev_share, f.snipers,
         t.mayhem_enabled, t.mayhem_mode, t.completed_at, t.migrated_at,
         t.creator, t.symbol, t.created_at
  FROM meme_features_15s f
  JOIN meme_tokens t ON t.mint = f.mint
  WHERE f.as_of >= (:'dia')::date::timestamp AT TIME ZONE 'America/Sao_Paulo'
    AND f.as_of <  ((:'dia')::date + 1)::timestamp AT TIME ZONE 'America/Sao_Paulo'
    AND f.age_s BETWEEN 30 AND 300
), passa AS (
  SELECT mint, min(as_of) AS t0 FROM linhas
  WHERE (completed_at IS NULL OR completed_at > as_of)
    AND (migrated_at IS NULL OR migrated_at > as_of)
    AND mayhem_enabled IS NOT NULL AND NOT mayhem_enabled AND mayhem_mode IS NULL
    AND tape_reason IS NULL
    AND curve_progress_pct BETWEEN 0.05 AND 0.50
    AND (creator_net_seller IS FALSE OR (creator_net_seller IS NULL AND dev_share IS NOT NULL AND dev_share <= 0.10))
    AND dev_share IS NOT NULL AND dev_share <= 0.10
    AND snipers IS NOT NULL AND snipers >= 21
    AND net_sol_flow_60s IS NOT NULL AND net_sol_flow_60s > 0
    AND unique_buyers_60s >= 10
    AND buys_60s > 0 AND sells_60s::numeric / buys_60s <= 0.6
    AND holders >= 20
    AND mcap_sol > 0
  GROUP BY mint
), entrada AS (
  SELECT p.mint, p.t0, l.mcap_sol AS base, l.symbol, l.curve_progress_pct,
         l.holders, l.unique_buyers_60s, l.net_sol_flow_60s, l.snipers
  FROM passa p
  JOIN linhas l ON l.mint = p.mint AND l.as_of = p.t0
  JOIN meme_tokens t ON t.mint = p.mint
  WHERE t.creator IS NOT NULL AND t.created_at IS NOT NULL
    AND (SELECT count(*) FROM meme_tokens o WHERE o.creator = t.creator AND o.mint <> t.mint
           AND o.created_at IS NOT NULL AND o.created_at <= t.created_at
           AND o.created_at > t.created_at - interval '1 hour') <= 1
    AND (SELECT count(*) FROM meme_tokens o WHERE o.symbol = t.symbol AND o.mint <> t.mint
           AND o.created_at IS NOT NULL AND o.created_at <= t.created_at
           AND o.created_at > t.created_at - interval '24 hours') <= 2
), curva AS (
  SELECT e.mint, e.t0, c.observed_at, c.real_sol_reserves
  FROM entrada e
  JOIN meme_curve_snapshots c ON c.mint = e.mint
   AND c.observed_at >= e.t0 - interval '300 seconds'
   AND c.observed_at <= e.t0
  WHERE c.real_sol_reserves IS NOT NULL
), pico AS (
  SELECT DISTINCT ON (mint) mint, real_sol_reserves AS rsol_pico, observed_at AS t_pico
  FROM curva ORDER BY mint, real_sol_reserves DESC, observed_at DESC
), atual AS (
  SELECT DISTINCT ON (mint) mint, real_sol_reserves AS rsol_atual, observed_at AS t_atual
  FROM curva ORDER BY mint, observed_at DESC
), barras AS (
  SELECT e.mint, e.t0, e.base, s.end_time, s.mcap_sol,
         row_number() OVER (PARTITION BY e.mint ORDER BY s.end_time) AS i,
         max(s.mcap_sol) OVER (PARTITION BY e.mint ORDER BY s.end_time
                               ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS pico_ate_anterior
  FROM entrada e
  JOIN meme_features_1m s ON s.mint = e.mint
   AND s.end_time > e.t0 AND s.end_time <= e.t0 + interval '30 minutes'
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
  SELECT DISTINCT ON (mint) mint, mcap_sol AS preco_saida, 'tempo_30m' AS motivo
  FROM gatilho ORDER BY mint, i DESC
)
SELECT :'dia' AS dia,
       e.mint, e.symbol,
       to_char(e.t0 AT TIME ZONE 'America/Sao_Paulo', 'HH24:MI:SS') AS t0_brt,
       round(e.base, 3) AS base_mcap,
       round(e.curve_progress_pct, 4) AS prog,
       e.holders, e.unique_buyers_60s AS compradores, e.snipers,
       round(p.rsol_pico, 3) AS rsol_pico,
       round(a.rsol_atual, 3) AS rsol_atual,
       CASE WHEN p.rsol_pico > 0 THEN round(100.0 * (1 - a.rsol_atual / p.rsol_pico), 2) END AS dd_pct,
       round(extract(epoch FROM e.t0 - p.t_pico)::numeric, 0) AS t_pico_s,
       round(extract(epoch FROM e.t0 - a.t_atual)::numeric, 0) AS defasagem_s,
       COALESCE(s.motivo, f.motivo) AS motivo,
       round((COALESCE(s.preco_saida, f.preco_saida) / e.base * 0.9825 * 0.9825 - 1) / 0.5, 4) AS r_unidades
FROM entrada e
LEFT JOIN pico p ON p.mint = e.mint
LEFT JOIN atual a ON a.mint = e.mint
LEFT JOIN saida s ON s.mint = e.mint
LEFT JOIN fim f ON f.mint = e.mint
ORDER BY e.t0;
