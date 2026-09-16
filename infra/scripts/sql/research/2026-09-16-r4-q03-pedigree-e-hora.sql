-- KB-0099 Q03 — o que sobra depois do pedigree, por hora BRT, e as propostas
-- que a mesa de fato gravou no mesmo dia. Uso: psql -v dia=2026-09-15 -f ...
SET statement_timeout = 60000;

WITH linhas AS (
  SELECT f.mint, f.as_of, f.curve_progress_pct, f.progress_rising, f.mcap_delta_60s,
         f.holders, f.holders_prev, f.holders_rising, f.buys_60s, f.sells_60s,
         f.unique_buyers_60s, f.net_sol_flow_60s, f.curve_volume_60s_sol,
         f.creator_net_seller, f.dev_share, f.snipers,
         t.mayhem_enabled, t.completed_at, t.migrated_at
  FROM meme_features_15s f
  JOIN meme_tokens t ON t.mint = f.mint
  WHERE f.as_of >= (:'dia')::date::timestamp AT TIME ZONE 'America/Sao_Paulo'
    AND f.as_of <  ((:'dia')::date + 1)::timestamp AT TIME ZONE 'America/Sao_Paulo'
    AND f.age_s BETWEEN 30 AND 300
), passa AS (
  SELECT mint, min(as_of) AS primeira_passagem
  FROM linhas
  WHERE (completed_at IS NULL OR completed_at > as_of)
    AND (migrated_at IS NULL OR migrated_at > as_of)
    AND mayhem_enabled IS NOT NULL AND NOT mayhem_enabled
    AND curve_progress_pct BETWEEN 0.05 AND 0.50
    AND (creator_net_seller IS FALSE OR (creator_net_seller IS NULL AND dev_share IS NOT NULL AND dev_share <= 0.10))
    AND curve_volume_60s_sol >= 5
    AND dev_share <= 0.10
    AND snipers <= 10
    AND (CASE WHEN net_sol_flow_60s IS NOT NULL THEN net_sol_flow_60s > 0
              WHEN mcap_delta_60s IS NOT NULL THEN mcap_delta_60s > 0 ELSE false END)
    AND unique_buyers_60s >= 10
    AND buys_60s > 0 AND sells_60s::numeric / buys_60s <= 0.6
    AND holders >= 20
    AND holders_rising IS NOT NULL
    AND (holders_rising OR (holders_prev IS NOT NULL AND holders >= holders_prev))
    AND COALESCE(progress_rising IS TRUE OR mcap_delta_60s > 0, false)
  GROUP BY mint
), ped AS (
  SELECT p.mint, p.primeira_passagem,
    (SELECT count(*) FROM meme_tokens o WHERE o.creator = t.creator AND o.mint <> t.mint
       AND o.created_at IS NOT NULL AND o.created_at <= t.created_at
       AND o.created_at > t.created_at - interval '1 hour') AS creator_prior_mints_1h,
    (SELECT count(*) FROM meme_tokens o WHERE o.symbol = t.symbol AND o.mint <> t.mint
       AND o.created_at IS NOT NULL AND o.created_at <= t.created_at
       AND o.created_at > t.created_at - interval '24 hours') AS symbol_dup_24h,
    t.creator IS NULL OR t.created_at IS NULL AS identidade_desconhecida
  FROM passa p JOIN meme_tokens t ON t.mint = p.mint
)
SELECT :'dia' AS dia,
       extract(hour FROM primeira_passagem AT TIME ZONE 'America/Sao_Paulo')::int AS hora_brt,
       count(*) AS passam_a_porta,
       count(*) FILTER (WHERE NOT identidade_desconhecida
                          AND creator_prior_mints_1h <= 1 AND symbol_dup_24h <= 2) AS passam_com_pedigree,
       count(*) FILTER (WHERE identidade_desconhecida) AS ident_desconhecida,
       count(*) FILTER (WHERE creator_prior_mints_1h > 1) AS creator_serial,
       count(*) FILTER (WHERE symbol_dup_24h > 2) AS symbol_clone
FROM ped GROUP BY 1, 2 ORDER BY 2;
