-- KB-0099 Q06 — candidatos por hora BRT de uma porta parametrizada (mesmos
-- parametros da Q05), para dimensionar a meta de 5-10 propostas/hora 13-22 BRT.
-- Um candidato = uma moeda distinta, na sua primeira foto que passa a porta.
SET statement_timeout = 60000;

WITH linhas AS (
  SELECT f.mint, f.as_of, f.mcap_sol, f.curve_progress_pct, f.progress_rising, f.mcap_delta_60s,
         f.holders, f.holders_prev, f.holders_rising, f.buys_60s, f.sells_60s,
         f.unique_buyers_60s, f.net_sol_flow_60s, f.curve_volume_60s_sol,
         f.creator_net_seller, f.dev_share, f.snipers,
         t.mayhem_enabled, t.completed_at, t.migrated_at, t.creator, t.symbol, t.created_at
  FROM meme_features_15s f
  JOIN meme_tokens t ON t.mint = f.mint
  WHERE f.as_of >= (:'dia')::date::timestamp AT TIME ZONE 'America/Sao_Paulo'
    AND f.as_of <  ((:'dia')::date + 1)::timestamp AT TIME ZONE 'America/Sao_Paulo'
    AND f.age_s BETWEEN 30 AND 300
), passa AS (
  SELECT mint, min(as_of) AS t0 FROM linhas
  WHERE (completed_at IS NULL OR completed_at > as_of)
    AND (migrated_at IS NULL OR migrated_at > as_of)
    AND mayhem_enabled IS NOT NULL AND NOT mayhem_enabled
    AND curve_progress_pct BETWEEN (:'prog_min')::numeric AND (:'prog_max')::numeric
    AND (creator_net_seller IS FALSE OR (creator_net_seller IS NULL AND dev_share IS NOT NULL AND dev_share <= 0.10))
    AND curve_volume_60s_sol >= (:'vol_min')::numeric
    AND dev_share <= 0.10
    AND snipers <= (:'snipers_max')::int
    AND (CASE WHEN net_sol_flow_60s IS NOT NULL THEN net_sol_flow_60s > 0
              WHEN mcap_delta_60s IS NOT NULL THEN mcap_delta_60s > 0 ELSE false END)
    AND unique_buyers_60s >= (:'buyers_min')::int
    AND buys_60s > 0 AND sells_60s::numeric / buys_60s <= (:'ratio_max')::numeric
    AND holders >= (:'holders_min')::int
    AND ((:'subindo')::int = 0 OR (
          holders_rising IS NOT NULL
          AND (holders_rising OR (holders_prev IS NOT NULL AND holders >= holders_prev))
          AND COALESCE(progress_rising IS TRUE OR mcap_delta_60s > 0, false)))
    AND mcap_sol > 0
  GROUP BY mint
), com_pedigree AS (
  SELECT p.mint, p.t0 FROM passa p JOIN meme_tokens t ON t.mint = p.mint
  WHERE (:'pedigree')::int = 0 OR (
    t.creator IS NOT NULL AND t.created_at IS NOT NULL
    AND (SELECT count(*) FROM meme_tokens o WHERE o.creator = t.creator AND o.mint <> t.mint
           AND o.created_at IS NOT NULL AND o.created_at <= t.created_at
           AND o.created_at > t.created_at - interval '1 hour') <= 1
    AND (SELECT count(*) FROM meme_tokens o WHERE o.symbol = t.symbol AND o.mint <> t.mint
           AND o.created_at IS NOT NULL AND o.created_at <= t.created_at
           AND o.created_at > t.created_at - interval '24 hours') <= 2)
)
SELECT :'dia' AS dia, :'rotulo' AS porta,
       extract(hour FROM t0 AT TIME ZONE 'America/Sao_Paulo')::int AS hora_brt,
       count(*) AS candidatos
FROM com_pedigree GROUP BY 1,2,3 ORDER BY 3;
