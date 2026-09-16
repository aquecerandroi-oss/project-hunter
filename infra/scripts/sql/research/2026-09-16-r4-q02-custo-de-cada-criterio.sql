-- KB-0099 Q02 — custo de cada criterio SEM depender da ordem do funil:
-- para cada criterio i, quantas moedas distintas teriam UMA foto de 15 s
-- passando todos os outros 12 (i solto). "todos" = as que passam os 13.
-- Uso: psql -v dia=2026-09-15 -f este-arquivo.sql
SET statement_timeout = 60000;

WITH linhas AS (
  SELECT f.mint, f.as_of, f.curve_progress_pct, f.progress_rising, f.mcap_delta_60s,
         f.holders, f.holders_prev, f.holders_rising,
         f.buys_60s, f.sells_60s, f.unique_buyers_60s, f.net_sol_flow_60s,
         f.curve_volume_60s_sol, f.creator_net_seller, f.dev_share, f.snipers,
         t.mayhem_enabled, t.completed_at, t.migrated_at
  FROM meme_features_15s f
  JOIN meme_tokens t ON t.mint = f.mint
  WHERE f.as_of >= (:'dia')::date::timestamp AT TIME ZONE 'America/Sao_Paulo'
    AND f.as_of <  ((:'dia')::date + 1)::timestamp AT TIME ZONE 'America/Sao_Paulo'
    AND f.age_s BETWEEN 30 AND 300
), c AS (
  SELECT mint,
    ARRAY[
      (completed_at IS NULL OR completed_at > as_of) AND (migrated_at IS NULL OR migrated_at > as_of),
      (mayhem_enabled IS NOT NULL AND NOT mayhem_enabled),
      (curve_progress_pct IS NOT NULL AND curve_progress_pct >= 0.05 AND curve_progress_pct <= 0.50),
      (creator_net_seller IS FALSE OR (creator_net_seller IS NULL AND dev_share IS NOT NULL AND dev_share <= 0.10)),
      (curve_volume_60s_sol IS NOT NULL AND curve_volume_60s_sol >= 5),
      (dev_share IS NOT NULL AND dev_share <= 0.10),
      (snipers IS NOT NULL AND snipers <= 10),
      (CASE WHEN net_sol_flow_60s IS NOT NULL THEN net_sol_flow_60s > 0
            WHEN mcap_delta_60s IS NOT NULL THEN mcap_delta_60s > 0 ELSE false END),
      (unique_buyers_60s IS NOT NULL AND unique_buyers_60s >= 10),
      (buys_60s IS NOT NULL AND sells_60s IS NOT NULL AND buys_60s > 0 AND sells_60s::numeric / buys_60s <= 0.6),
      (holders IS NOT NULL AND holders >= 20),
      (holders_rising IS NOT NULL AND (holders_rising OR (holders IS NOT NULL AND holders_prev IS NOT NULL AND holders >= holders_prev))),
      COALESCE(progress_rising IS TRUE OR mcap_delta_60s > 0, false)
    ] AS ok
  FROM linhas
), f AS (
  SELECT mint, ok,
         (SELECT count(*) FROM unnest(ok) AS x WHERE NOT x) AS falhas
  FROM c
), g AS (
  SELECT i.i, count(DISTINCT mint) FILTER (
           WHERE falhas = 0 OR (falhas = 1 AND NOT ok[i.i])) AS solto
  FROM f CROSS JOIN generate_series(1, 13) AS i(i)
  GROUP BY i.i
)
SELECT :'dia' AS dia, g.i AS criterio,
       (ARRAY['01 curva viva','02 nao Mayhem','03 progresso 5-50 %','04 criador nao vendedor',
              '05 participacao (vol60s >= 5 SOL)','06 dev <= 10 %','07 snipers <= 10',
              '08 fluxo > 0','09 compradores >= 10','10 vendas/compras <= 0,6','11 holders >= 20',
              '12 holders nao caindo','13 progresso/mcap subindo'])[g.i] AS nome,
       (SELECT count(DISTINCT mint) FROM f WHERE falhas = 0) AS passam_tudo,
       g.solto AS passariam_sem_ele,
       g.solto - (SELECT count(DISTINCT mint) FROM f WHERE falhas = 0) AS custo_moedas
FROM g ORDER BY custo_moedas DESC;
