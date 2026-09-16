-- R21 - contrafactual do piso min_snipers sobre a mesma porta do operator,
-- 13:00-agora BRT de 16/09/2026. Passa todos os criterios da porta MENOS o
-- piso de snipers e mostra quantas moedas/linhas sobram por faixa de snipers
-- (KB-0102: 11-20 / 21-30 / 31-60). "sobreviventes" = linhas que a porta
-- aprovaria (a proposta real ainda passa por TTL, max_open e dedupe).
WITH janela AS (
  SELECT f.*, t.created_at, t.completed_at, t.migrated_at, t.creator, t.symbol,
         t.mayhem_enabled, t.mayhem_state
  FROM meme_features_15s f
  JOIN meme_tokens t ON t.mint = f.mint
  WHERE f.as_of >= timestamptz '2026-09-16 13:00-03'
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
), sem_snipers AS (
  SELECT j.mint, j.as_of, j.snipers
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
    AND coalesce(j.net_sol_flow_60s > 0, j.mcap_delta_60s > 0, false)
    AND j.unique_buyers_60s >= 10
    AND j.buys_60s > 0 AND j.sells_60s::numeric / j.buys_60s <= 0.6
    AND j.holders >= 20
    AND (j.snipers IS NOT NULL OR true)
)
SELECT faixa, linhas, moedas, round(moedas / horas, 2) AS moedas_por_hora FROM (
  SELECT 1 AS ord, 'snipers desconhecido' AS faixa, count(*) AS linhas,
         count(DISTINCT mint)::numeric AS moedas,
         extract(epoch FROM (now() - timestamptz '2026-09-16 13:00-03')) / 3600 AS horas
    FROM sem_snipers WHERE snipers IS NULL
  UNION ALL SELECT 2, '00-10', count(*), count(DISTINCT mint),
         extract(epoch FROM (now() - timestamptz '2026-09-16 13:00-03')) / 3600
    FROM sem_snipers WHERE snipers BETWEEN 0 AND 10
  UNION ALL SELECT 3, '11-20', count(*), count(DISTINCT mint),
         extract(epoch FROM (now() - timestamptz '2026-09-16 13:00-03')) / 3600
    FROM sem_snipers WHERE snipers BETWEEN 11 AND 20
  UNION ALL SELECT 4, '21-30', count(*), count(DISTINCT mint),
         extract(epoch FROM (now() - timestamptz '2026-09-16 13:00-03')) / 3600
    FROM sem_snipers WHERE snipers BETWEEN 21 AND 30
  UNION ALL SELECT 5, '31-60', count(*), count(DISTINCT mint),
         extract(epoch FROM (now() - timestamptz '2026-09-16 13:00-03')) / 3600
    FROM sem_snipers WHERE snipers BETWEEN 31 AND 60
  UNION ALL SELECT 6, '61+', count(*), count(DISTINCT mint),
         extract(epoch FROM (now() - timestamptz '2026-09-16 13:00-03')) / 3600
    FROM sem_snipers WHERE snipers > 60
  UNION ALL SELECT 7, 'piso 21 (atual, 21-1000)', count(*), count(DISTINCT mint),
         extract(epoch FROM (now() - timestamptz '2026-09-16 13:00-03')) / 3600
    FROM sem_snipers WHERE snipers BETWEEN 21 AND 1000
  UNION ALL SELECT 8, 'piso 11 (11-1000)', count(*), count(DISTINCT mint),
         extract(epoch FROM (now() - timestamptz '2026-09-16 13:00-03')) / 3600
    FROM sem_snipers WHERE snipers BETWEEN 11 AND 1000
  UNION ALL SELECT 9, 'piso 16 (16-1000)', count(*), count(DISTINCT mint),
         extract(epoch FROM (now() - timestamptz '2026-09-16 13:00-03')) / 3600
    FROM sem_snipers WHERE snipers BETWEEN 16 AND 1000
  UNION ALL SELECT 10, 'sem piso (snipers medido)', count(*), count(DISTINCT mint),
         extract(epoch FROM (now() - timestamptz '2026-09-16 13:00-03')) / 3600
    FROM sem_snipers WHERE snipers IS NOT NULL
) g ORDER BY ord;
