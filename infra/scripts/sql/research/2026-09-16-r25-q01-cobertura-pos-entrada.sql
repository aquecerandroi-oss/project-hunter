-- KB-0113 Q01 — Cobertura POS-ENTRADA das tres series (15 s, 1 min, fita de pool) para as
-- entradas da PORTA ATUAL (REUSE literal dos blocos foto/universo/entrada do
-- 2026-09-16-r20-q01-entradas-porta-atual.sql, KB-0110 1a). Um dia por execucao.
-- Unidades: curve_progress_pct e FRACAO 0-1; mayhem_mode e texto.
-- Uso: psql -v dia=2026-09-15 -v ew=5 -At -F "|" -f este-arquivo.sql
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
    AND b.holders >= 20 AND b.unique_buyers >= 10
    AND b.buys_1m > 0 AND b.sells_1m::numeric / b.buys_1m <= 0.6
  ORDER BY u.mint, b.end_time
),
c15 AS (
  SELECT e.mint, count(*) AS n, max(f.as_of) AS last_at, max(f.age_s) AS last_age_s
  FROM entrada e JOIN meme_features_15s f ON f.mint = e.mint
   AND f.as_of > e.t_in AND f.as_of <= e.t_in + interval '60 minutes'
  GROUP BY e.mint
), c1m AS (
  SELECT e.mint, count(*) AS n,
         count(*) FILTER (WHERE b.mcap_sol IS NOT NULL AND b.mcap_sol > 0) AS n_mcap,
         max(b.end_time) AS last_at,
         max(b.end_time) FILTER (WHERE b.mcap_sol IS NOT NULL AND b.mcap_sol > 0) AS last_mcap_at
  FROM entrada e JOIN meme_features_1m b ON b.mint = e.mint
   AND b.end_time > e.t_in AND b.end_time <= e.t_in + interval '60 minutes'
  GROUP BY e.mint
), cpool AS (
  SELECT e.mint, count(*) AS n, max(tr.block_time) AS last_at
  FROM entrada e JOIN meme_trades tr ON tr.mint = e.mint
   AND tr.block_time > e.t_in AND tr.block_time <= e.t_in + interval '60 minutes'
   AND tr.program = 'pump_amm'
  GROUP BY e.mint
), base AS (
  SELECT e.mint, e.t_in, t.created_at, t.completed_at, t.migrated_at,
         EXTRACT(epoch FROM e.t_in - t.created_at)::int AS age_in_s,
         COALESCE(EXTRACT(epoch FROM c15.last_at - e.t_in), 0)::int  AS cov15_s,
         COALESCE(c15.n, 0) AS n15, COALESCE(c15.last_age_s, 0) AS last_age_s,
         COALESCE(EXTRACT(epoch FROM c1m.last_at - e.t_in), 0)::int AS cov1m_s,
         COALESCE(EXTRACT(epoch FROM c1m.last_mcap_at - e.t_in), 0)::int AS cov1m_mcap_s,
         COALESCE(c1m.n, 0) AS n1m, COALESCE(c1m.n_mcap, 0) AS n1m_mcap,
         COALESCE(EXTRACT(epoch FROM cpool.last_at - e.t_in), 0)::int AS covpool_s,
         COALESCE(cpool.n, 0) AS npool
  FROM entrada e JOIN meme_tokens t ON t.mint = e.mint
  LEFT JOIN c15 ON c15.mint = e.mint
  LEFT JOIN c1m ON c1m.mint = e.mint
  LEFT JOIN cpool ON cpool.mint = e.mint
)
SELECT 'A_resumo' AS bloco, serie AS k, n::text AS c1, med::text AS c2, p75::text AS c3,
       p90::text AS c4, mx::text AS c5, ge5::text AS c6, ge10::text AS c7, ge30::text AS c8
FROM (
  SELECT '15s' AS serie, count(*) AS n,
         percentile_disc(0.5) WITHIN GROUP (ORDER BY cov15_s) AS med,
         percentile_disc(0.75) WITHIN GROUP (ORDER BY cov15_s) AS p75,
         percentile_disc(0.90) WITHIN GROUP (ORDER BY cov15_s) AS p90,
         max(cov15_s) AS mx,
         count(*) FILTER (WHERE cov15_s >= 300) AS ge5,
         count(*) FILTER (WHERE cov15_s >= 600) AS ge10,
         count(*) FILTER (WHERE cov15_s >= 1800) AS ge30
  FROM base
  UNION ALL
  SELECT '1m', count(*),
         percentile_disc(0.5) WITHIN GROUP (ORDER BY cov1m_s),
         percentile_disc(0.75) WITHIN GROUP (ORDER BY cov1m_s),
         percentile_disc(0.90) WITHIN GROUP (ORDER BY cov1m_s),
         max(cov1m_s),
         count(*) FILTER (WHERE cov1m_s >= 300), count(*) FILTER (WHERE cov1m_s >= 600),
         count(*) FILTER (WHERE cov1m_s >= 1800)
  FROM base
  UNION ALL
  SELECT '1m_com_mcap', count(*),
         percentile_disc(0.5) WITHIN GROUP (ORDER BY cov1m_mcap_s),
         percentile_disc(0.75) WITHIN GROUP (ORDER BY cov1m_mcap_s),
         percentile_disc(0.90) WITHIN GROUP (ORDER BY cov1m_mcap_s),
         max(cov1m_mcap_s),
         count(*) FILTER (WHERE cov1m_mcap_s >= 300), count(*) FILTER (WHERE cov1m_mcap_s >= 600),
         count(*) FILTER (WHERE cov1m_mcap_s >= 1800)
  FROM base
  UNION ALL
  SELECT 'pool_tape', count(*),
         percentile_disc(0.5) WITHIN GROUP (ORDER BY covpool_s),
         percentile_disc(0.75) WITHIN GROUP (ORDER BY covpool_s),
         percentile_disc(0.90) WITHIN GROUP (ORDER BY covpool_s),
         max(covpool_s),
         count(*) FILTER (WHERE covpool_s >= 300), count(*) FILTER (WHERE covpool_s >= 600),
         count(*) FILTER (WHERE covpool_s >= 1800)
  FROM base
) s
UNION ALL
SELECT 'B_motivo_15s', motivo, count(*)::text,
       percentile_disc(0.5) WITHIN GROUP (ORDER BY cov15_s)::text,
       percentile_disc(0.5) WITHIN GROUP (ORDER BY age_in_s)::text,
       percentile_disc(0.5) WITHIN GROUP (ORDER BY last_age_s)::text,
       '', '', '', ''
FROM (
  SELECT b.*, CASE
    WHEN n15 = 0 THEN 'sem_serie_pos_entrada'
    WHEN last_age_s >= 285 THEN 'teto_via_rapida_age_300'
    WHEN completed_at IS NOT NULL AND completed_at <= t_in + make_interval(secs => cov15_s + 30)
      THEN 'curva_completa_migrou'
    ELSE 'parou_antes_do_teto'
  END AS motivo FROM base b
) b15 GROUP BY motivo
UNION ALL
SELECT 'C_motivo_1m', motivo, count(*)::text,
       percentile_disc(0.5) WITHIN GROUP (ORDER BY cov1m_s)::text,
       percentile_disc(0.5) WITHIN GROUP (ORDER BY cov1m_mcap_s)::text,
       count(*) FILTER (WHERE npool > 0)::text, '', '', '', ''
FROM (
  SELECT b.*, CASE
    WHEN n1m = 0 THEN 'sem_serie_pos_entrada'
    WHEN cov1m_s >= 3540 THEN 'ainda_viva_aos_60min'
    WHEN completed_at IS NOT NULL AND completed_at <= t_in + make_interval(secs => cov1m_s + 120)
      THEN 'curva_completa_migrou'
    ELSE 'saiu_do_rastreador'
  END AS motivo FROM base b
) b1m GROUP BY motivo
ORDER BY 1, 2;
