-- R10 / Q04 — as 16 ordens reais recusadas de hoje: teriam ganho ou perdido?
-- Agrega o R simulado (mesmas regras da Q02) por motivo da recusa da ordem,
-- em duas leituras:
--   * por proposta (as 16 ordens, com repeticao da mesma moeda);
--   * por moeda (a primeira proposta de cada mint) -- e o que a mesa teria
--     de fato aberto, porque max_exposure_per_mint_sol = size_sol = 0,05.
SET statement_timeout = 120000;

WITH prop AS (
  SELECT p.id, p.mint, p.proposed_at,
         (p.quote->>'curve_progress_pct')::numeric AS progresso_pct,
         (p.quote->>'mcap_sol')::numeric           AS base_mcap,
         o.reason                                  AS motivo_ordem,
         row_number() OVER (PARTITION BY p.mint ORDER BY p.proposed_at) AS ordem_no_mint
  FROM meme_proposals p
  LEFT JOIN LATERAL (
    SELECT lo.reason FROM meme_live_orders lo
    WHERE lo.proposal_id = p.id ORDER BY lo.received_at LIMIT 1
  ) o ON true
  WHERE p.rule_set_id = '01994d00-6c1a-7000-8000-000000000011'
    AND p.proposed_at >= '2026-09-16'::date::timestamp AT TIME ZONE 'America/Sao_Paulo'
    AND (p.quote->>'mcap_sol')::numeric > 0
), serie AS (
  SELECT pr.id, f.as_of AS ts, f.mcap_sol, coalesce(f.creator_net_seller, false) AS dump
  FROM prop pr
  JOIN meme_features_15s f ON f.mint = pr.mint
   AND f.as_of > pr.proposed_at AND f.as_of <= pr.proposed_at + interval '1800 seconds'
  WHERE f.mcap_sol IS NOT NULL
  UNION ALL
  SELECT pr.id, f.end_time, f.mcap_sol, coalesce(f.creator_sold, f.creator_net_seller, false)
  FROM prop pr
  JOIN meme_features_1m f ON f.mint = pr.mint
   AND f.end_time > pr.proposed_at AND f.end_time <= pr.proposed_at + interval '1800 seconds'
  WHERE f.mcap_sol IS NOT NULL
), barras AS (
  SELECT id, ts, max(mcap_sol) AS mcap_sol, bool_or(dump) AS dump
  FROM serie GROUP BY id, ts
), mult AS (
  SELECT b.id, b.ts, b.dump, b.mcap_sol / pr.base_mcap AS m,
         max(b.mcap_sol / pr.base_mcap) OVER (PARTITION BY b.id ORDER BY b.ts
             ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS topo
  FROM barras b JOIN prop pr ON pr.id = b.id
), gatilho AS (
  SELECT id, ts, CASE WHEN m <= 0.5 THEN 0.5 WHEN m >= 3.0 THEN 3.0 ELSE m END AS m_saida
  FROM mult
  WHERE m <= 0.5 OR m >= 3.0 OR (topo >= 1.5 AND m <= 0.65 * topo) OR dump
), primeiro AS (
  SELECT DISTINCT ON (id) id, ts, m_saida FROM gatilho ORDER BY id, ts
), fim AS (
  SELECT DISTINCT ON (id) id, ts, m FROM mult ORDER BY id, ts DESC
), resumo AS (
  SELECT pr.*, (coalesce(g.m_saida, f.m) * (0.9825 / 1.0175) - 1) / (1 - 0.5 * 0.9825 / 1.0175) AS r
  FROM prop pr
  LEFT JOIN primeiro g ON g.id = pr.id
  LEFT JOIN fim f      ON f.id = pr.id
  WHERE coalesce(g.m_saida, f.m) IS NOT NULL
)
SELECT 'por proposta' AS leitura, coalesce(motivo_ordem, 'sem ordem (paper, expirou)') AS motivo_ordem,
       count(*) AS n, round(avg(r), 2) AS r_medio, round(sum(r), 2) AS r_total,
       count(*) FILTER (WHERE r > 0) AS acertos
FROM resumo GROUP BY 1, 2
UNION ALL
SELECT 'por moeda', coalesce(motivo_ordem, 'sem ordem (paper, expirou)'),
       count(*), round(avg(r), 2), round(sum(r), 2), count(*) FILTER (WHERE r > 0)
FROM resumo WHERE ordem_no_mint = 1 GROUP BY 1, 2
ORDER BY 1 DESC, 5 DESC;
