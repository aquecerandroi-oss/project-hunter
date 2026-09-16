-- R21 - as linhas que a porta do operator aprovaria, minuto a minuto, desde
-- 16:17 BRT de 16/09/2026, com os valores que decidiram. Serve de checagem da
-- q01: cada linha aqui e uma linha de meme_features_15s que passou TODOS os
-- criterios, na ordem de evaluate_entry, incluindo o pedigree.
WITH janela AS (
  SELECT f.*, t.created_at, t.completed_at, t.migrated_at, t.creator, t.symbol,
         t.mayhem_enabled
  FROM meme_features_15s f
  JOIN meme_tokens t ON t.mint = f.mint
  WHERE f.as_of >= timestamptz '2026-09-16 16:17-03'
    AND f.features_version = 'meme_features_15s_v1'
), ped AS (
  SELECT t.mint,
    CASE WHEN t.creator IS NULL OR t.created_at IS NULL THEN NULL ELSE (
      SELECT count(*) FROM meme_tokens o WHERE o.creator = t.creator AND o.mint <> t.mint
        AND o.created_at IS NOT NULL AND o.created_at <= t.created_at
        AND o.created_at > t.created_at - interval '1 hour') END AS creator_prior_mints_1h,
    CASE WHEN t.symbol IS NULL OR t.created_at IS NULL THEN NULL ELSE (
      SELECT count(*) FROM meme_tokens o WHERE o.symbol = t.symbol AND o.mint <> t.mint
        AND o.created_at IS NOT NULL AND o.created_at <= t.created_at
        AND o.created_at > t.created_at - interval '24 hours') END AS symbol_dup_24h,
    CASE WHEN t.creator IS NULL OR t.created_at IS NULL THEN NULL ELSE (
      SELECT count(*) FROM meme_tokens o WHERE o.creator = t.creator AND o.mint <> t.mint
        AND o.created_at IS NOT NULL AND o.created_at <= t.created_at
        AND o.created_at > t.created_at - interval '7 days'
        AND (EXISTS (SELECT 1 FROM meme_features_1m pf WHERE pf.mint = o.mint
                       AND pf.creator_sold = true AND pf.end_time < t.created_at)
          OR EXISTS (SELECT 1 FROM meme_paper_bets pb WHERE pb.mint = o.mint
                       AND pb.creator_sold_seen_at IS NOT NULL
                       AND pb.creator_sold_seen_at < t.created_at)
          OR EXISTS (SELECT 1 FROM meme_paper_bets pb2 WHERE pb2.mint = o.mint
                       AND pb2.exit ->> 'reason' = 'creator_dump'
                       AND pb2.exit_at < t.created_at))) END AS creator_prior_dump_count
  FROM meme_tokens t WHERE t.mint IN (SELECT DISTINCT mint FROM janela)
)
SELECT to_char(j.as_of AT TIME ZONE 'America/Sao_Paulo', 'HH24:MI:SS') AS hora_brt,
       j.mint, j.age_s, round(j.curve_progress_pct * 100, 1) AS progresso_pct,
       round(j.curve_volume_60s_sol, 2) AS vol60s_sol, j.snipers, j.holders,
       j.unique_buyers_60s, j.buys_60s, j.sells_60s, round(j.dev_share, 3) AS dev_share,
       round(j.net_sol_flow_60s, 2) AS fluxo_sol
FROM janela j LEFT JOIN ped pd ON pd.mint = j.mint
WHERE j.completed_at IS NULL AND j.migrated_at IS NULL
  AND pd.creator_prior_mints_1h IS NOT NULL AND pd.creator_prior_mints_1h <= 1
  AND pd.symbol_dup_24h IS NOT NULL AND pd.symbol_dup_24h <= 2
  AND coalesce(pd.creator_prior_dump_count, 0) = 0
  AND j.mayhem_enabled = false
  AND j.age_s BETWEEN 30 AND 300
  AND j.curve_progress_pct >= 0.05 AND j.curve_progress_pct <= 0.50
  AND (j.creator_net_seller = false
       OR (j.creator_net_seller IS NULL AND j.dev_share IS NOT NULL AND j.dev_share <= 0.10))
  AND j.curve_volume_60s_sol >= 5
  AND j.dev_share IS NOT NULL AND j.dev_share <= 0.10
  AND j.snipers BETWEEN 21 AND 1000
  AND coalesce(j.net_sol_flow_60s > 0, j.mcap_delta_60s > 0, false)
  AND j.unique_buyers_60s >= 10
  AND j.buys_60s > 0 AND j.sells_60s::numeric / j.buys_60s <= 0.6
  AND j.holders >= 20
ORDER BY j.as_of;
