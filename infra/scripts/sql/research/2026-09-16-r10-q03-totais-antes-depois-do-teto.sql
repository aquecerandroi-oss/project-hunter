-- R10 / Q03 — totais do dia: n, R medio, R total, acertos (R > 0),
-- quebrados por janela (antes / depois de 15:08, decisao A: teto de 50 %)
-- e por faixa de progresso na proposta (ate 50 % vs acima de 50 %).
-- Mesma simulacao da Q02 (alvo 3x, trailing 35 % apos 1,5x, piso -50 %,
-- dump do criador, tempo 1800 s, taxa 1,75 % por perna).
SET statement_timeout = 120000;

WITH prop AS (
  SELECT p.id, p.mint, p.proposed_at,
         (p.quote->>'curve_progress_pct')::numeric AS progresso_pct,
         (p.quote->>'mcap_sol')::numeric           AS base_mcap
  FROM meme_proposals p
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
  SELECT id, ts,
    CASE WHEN m <= 0.5 THEN 0.5 WHEN m >= 3.0 THEN 3.0 ELSE m END AS m_saida
  FROM mult
  WHERE m <= 0.5 OR m >= 3.0 OR (topo >= 1.5 AND m <= 0.65 * topo) OR dump
), primeiro AS (
  SELECT DISTINCT ON (id) id, ts, m_saida FROM gatilho ORDER BY id, ts
), fim AS (
  SELECT DISTINCT ON (id) id, ts, m FROM mult ORDER BY id, ts DESC
), resumo AS (
  SELECT pr.id, pr.proposed_at, pr.progresso_pct,
         coalesce(g.m_saida, f.m) AS m_saida,
         (coalesce(g.m_saida, f.m) * (0.9825 / 1.0175) - 1) / (1 - 0.5 * 0.9825 / 1.0175) AS r
  FROM prop pr
  LEFT JOIN primeiro g ON g.id = pr.id
  LEFT JOIN fim f      ON f.id = pr.id
  WHERE coalesce(g.m_saida, f.m) IS NOT NULL
)
SELECT coalesce(CASE WHEN proposed_at < '2026-09-16 15:08'::timestamp AT TIME ZONE 'America/Sao_Paulo'
                     THEN 'antes_1508' ELSE 'depois_1508' END, 'TODAS')          AS janela,
       coalesce(CASE WHEN progresso_pct <= 50 THEN 'ate_50' ELSE 'acima_50' END, 'TODAS') AS faixa,
       count(*)                                     AS n,
       round(avg(r), 2)                             AS r_medio,
       round(sum(r), 2)                             AS r_total,
       count(*) FILTER (WHERE r > 0)                AS acertos,
       round(100.0 * count(*) FILTER (WHERE r > 0) / count(*), 0) AS acerto_pct,
       round(max(r), 2)                             AS melhor,
       round(min(r), 2)                             AS pior
FROM resumo
GROUP BY GROUPING SETS (
  (CASE WHEN proposed_at < '2026-09-16 15:08'::timestamp AT TIME ZONE 'America/Sao_Paulo'
        THEN 'antes_1508' ELSE 'depois_1508' END),
  (CASE WHEN progresso_pct <= 50 THEN 'ate_50' ELSE 'acima_50' END),
  ()
)
ORDER BY janela, faixa;
