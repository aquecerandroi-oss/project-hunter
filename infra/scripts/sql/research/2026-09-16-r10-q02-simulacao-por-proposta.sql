-- R10 / Q02 — simulacao da aposta que a mesa propos, proposta a proposta.
-- Nenhuma proposta de operator/5 virou aposta hoje (0 fills), entao TUDO e simulado.
--
-- Regras do conjunto operator/5 (params): entrada no preco do quote,
-- alvo 3x, trailing 35 % armado depois de 1,5x, piso -50 %, dump do criador,
-- tempo max_hold_s = 1800 s, taxa 1,75 % por perna.
-- Preco ~ mcap_sol (oferta fixa), entao o multiplo e mcap(t) / quote.mcap_sol.
-- Serie: meme_features_15s enquanto existe (age_s <= 300) + meme_features_1m depois.
-- R liquido: k = (1-f)/(1+f), R = (mult*k - 1) / (1 - 0.5*k), f = 0.0175
--   -> mult 3,0 = +3,667 R ; mult 0,5 = -1,000 R (o piso e 1 R por definicao).
-- Ordem de gatilho na mesma barra (conservadora): piso, alvo, trailing, dump, tempo.
SET statement_timeout = 120000;

WITH prop AS (
  SELECT p.id, p.mint, p.proposed_at, p.status, p.mode,
         coalesce(t.symbol, '?') AS simbolo,
         (p.quote->>'curve_progress_pct')::numeric AS progresso_pct,
         (p.quote->>'mcap_sol')::numeric           AS base_mcap
  FROM meme_proposals p
  LEFT JOIN meme_tokens t ON t.mint = p.mint
  WHERE p.rule_set_id = '01994d00-6c1a-7000-8000-000000000011'
    AND p.proposed_at >= '2026-09-16'::date::timestamp AT TIME ZONE 'America/Sao_Paulo'
    AND (p.quote->>'mcap_sol')::numeric > 0
), serie AS (
  SELECT pr.id, f.as_of AS ts, f.mcap_sol,
         coalesce(f.creator_net_seller, false) AS dump
  FROM prop pr
  JOIN meme_features_15s f ON f.mint = pr.mint
   AND f.as_of > pr.proposed_at AND f.as_of <= pr.proposed_at + interval '1800 seconds'
  WHERE f.mcap_sol IS NOT NULL
  UNION ALL
  SELECT pr.id, f.end_time, f.mcap_sol,
         coalesce(f.creator_sold, f.creator_net_seller, false)
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
  SELECT id, ts, m, topo, dump,
    CASE WHEN m <= 0.5                              THEN 'piso_-50%'
         WHEN m >= 3.0                              THEN 'alvo_3x'
         WHEN topo >= 1.5 AND m <= 0.65 * topo      THEN 'trailing_35%'
         WHEN dump                                  THEN 'dump_do_criador'
    END AS motivo,
    CASE WHEN m <= 0.5                              THEN 0.5
         WHEN m >= 3.0                              THEN 3.0
         WHEN topo >= 1.5 AND m <= 0.65 * topo      THEN m
         WHEN dump                                  THEN m
    END AS m_saida
  FROM mult
), primeiro AS (
  SELECT DISTINCT ON (id) id, ts, motivo, m_saida
  FROM gatilho WHERE motivo IS NOT NULL ORDER BY id, ts
), fim AS (
  SELECT DISTINCT ON (id) id, ts, m FROM mult ORDER BY id, ts DESC
), resumo AS (
  SELECT pr.id, pr.proposed_at, pr.simbolo, pr.mint, pr.progresso_pct, pr.status, pr.mode,
         (SELECT count(*) FROM mult mm WHERE mm.id = pr.id)             AS barras,
         (SELECT max(topo) FROM mult mm WHERE mm.id = pr.id)            AS topo,
         coalesce(g.motivo, CASE WHEN f.id IS NULL THEN 'sem_serie' ELSE 'tempo_30min' END) AS motivo,
         coalesce(g.m_saida, f.m)                                       AS m_saida,
         coalesce(g.ts, f.ts)                                           AS saida_ts
  FROM prop pr
  LEFT JOIN primeiro g ON g.id = pr.id
  LEFT JOIN fim f      ON f.id = pr.id
)
SELECT to_char(proposed_at AT TIME ZONE 'America/Sao_Paulo', 'HH24:MI:SS') AS brt,
       simbolo, left(mint, 6) AS mint,
       round(progresso_pct, 1)                                     AS progresso_pct,
       CASE WHEN progresso_pct <= 50 THEN 'ate_50' ELSE 'acima_50' END AS faixa,
       CASE WHEN proposed_at < '2026-09-16 15:08'::timestamp AT TIME ZONE 'America/Sao_Paulo'
            THEN 'antes_1508' ELSE 'depois_1508' END               AS janela,
       status, barras,
       round(topo, 3)                                              AS topo_x,
       -- a serie de uma moeda acaba quando ela migra/completa a curva ou o
       -- coletor para; saida por tempo com menos de 1700 s e fim de serie.
       CASE WHEN motivo = 'tempo_30min'
                 AND extract(epoch FROM saida_ts - proposed_at) < 1700
            THEN 'fim_da_serie' ELSE motivo END                    AS motivo_saida,
       round(m_saida, 3)                                           AS mult_saida,
       round((m_saida * (0.9825 / 1.0175) - 1) / (1 - 0.5 * 0.9825 / 1.0175), 2) AS r_simulado,
       round(extract(epoch FROM saida_ts - proposed_at))           AS duracao_s
FROM resumo
ORDER BY proposed_at;
