-- R23 16/09 16h50 BRT — (a) qual checagem reprovou cada ordem real desde 16:17 BRT;
-- (b) janela do executor agora (5 min) e (c) na ultima hora, top 8 por demanda;
-- (d) desfecho de 1 min + top10 + creator_sold + criador serial das 8.
-- Janela do radar: idade 30-300 s, progresso 0,02-0,50 (FRACAO), fita presente
-- (tape_reason IS NULL), net_sol_flow_60s > 0, nao-Mayhem (mayhem_mode IS NULL).

-- (a) checagens reprovadas nas ordens reais desde 16:17 BRT
SELECT to_char(o.received_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS hora_brt,
       t.symbol, o.status,
       c->>'name' AS checagem, c->>'state' AS estado, c->>'refusal' AS refusal,
       c->>'value' AS valor, c->>'limit' AS limite, left(c->>'message',80) AS msg
FROM meme_live_orders o
JOIN meme_proposals p ON p.id=o.proposal_id
LEFT JOIN meme_tokens t ON t.mint=p.mint,
LATERAL jsonb_array_elements(o.admission->'checks') c
WHERE o.received_at >= timestamptz '2026-09-16 16:17-03'
  AND c->>'state' <> 'passed'
ORDER BY o.received_at, c->>'name';

-- (b) AGORA: ultimos 5 min, uma linha por mint, ordenado por compradores
WITH j AS (
  SELECT DISTINCT ON (f.mint) f.* FROM meme_features_15s f
  JOIN meme_tokens t ON t.mint = f.mint AND t.mayhem_mode IS NULL
  WHERE f.as_of >= now() - make_interval(mins => 5)
    AND f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.02 AND 0.50
    AND f.tape_reason IS NULL AND f.net_sol_flow_60s > 0
  ORDER BY f.mint, f.as_of DESC
)
SELECT t.symbol, left(j.mint,6), j.age_s, round(j.curve_progress_pct*100,1), j.holders,
  j.unique_buyers_60s, j.buys_60s, j.sells_60s, round(j.net_sol_flow_60s,2), j.snipers,
  round(j.dev_share*100,2), j.creator_net_seller, left(t.creator,6),
  (SELECT count(*) FROM meme_tokens t2 WHERE t2.creator=t.creator
     AND t2.created_at >= now() - make_interval(days => 7)),
  to_char(j.as_of AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS')
FROM j JOIN meme_tokens t ON t.mint=j.mint
ORDER BY j.unique_buyers_60s DESC NULLS LAST, j.net_sol_flow_60s DESC LIMIT 12;

-- (b2) funil instantaneo (ultima foto por mint nos ultimos 2 min)
WITH ult AS (
  SELECT DISTINCT ON (f.mint) f.* FROM meme_features_15s f
  WHERE f.as_of >= now() - make_interval(mins => 2) ORDER BY f.mint, f.as_of DESC
)
SELECT count(*) AS mints_2min,
  count(*) FILTER (WHERE age_s BETWEEN 30 AND 300) AS na_idade,
  count(*) FILTER (WHERE age_s BETWEEN 30 AND 300 AND curve_progress_pct BETWEEN 0.02 AND 0.50) AS mais_prog,
  count(*) FILTER (WHERE age_s BETWEEN 30 AND 300 AND curve_progress_pct BETWEEN 0.02 AND 0.50
                     AND tape_reason IS NULL) AS mais_fita,
  count(*) FILTER (WHERE age_s BETWEEN 30 AND 300 AND curve_progress_pct BETWEEN 0.02 AND 0.50
                     AND tape_reason IS NULL AND net_sol_flow_60s > 0) AS mais_fluxo
FROM ult;

-- (c) ULTIMA HORA: melhor foto (por compradores) de cada moeda que esteve na janela
WITH janela AS (
  SELECT f.* FROM meme_features_15s f
  WHERE f.as_of >= now() - make_interval(mins => 60)
    AND f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.02 AND 0.50
    AND f.tape_reason IS NULL AND f.net_sol_flow_60s > 0
), melhor AS (
  SELECT DISTINCT ON (j.mint) j.* FROM janela j
  ORDER BY j.mint, j.unique_buyers_60s DESC NULLS LAST, j.net_sol_flow_60s DESC
)
SELECT t.symbol, left(m.mint,6), m.age_s, round(m.curve_progress_pct*100,1), m.holders,
  m.unique_buyers_60s, m.buys_60s, m.sells_60s, round(m.net_sol_flow_60s,2),
  round(m.curve_volume_60s_sol,1), m.snipers, round(m.dev_share*100,2), m.creator_net_seller,
  left(t.creator,6),
  (SELECT count(*) FROM meme_tokens t2 WHERE t2.creator=t.creator
     AND t2.created_at >= now() - make_interval(days => 7)),
  t.completed_at IS NOT NULL, t.migrated_at IS NOT NULL,
  to_char(m.as_of AT TIME ZONE 'America/Sao_Paulo','HH24:MI')
FROM melhor m JOIN meme_tokens t ON t.mint=m.mint WHERE t.mayhem_mode IS NULL
ORDER BY m.unique_buyers_60s DESC NULLS LAST, m.net_sol_flow_60s DESC LIMIT 10;

-- (d) desfecho das que estiveram na janela na ultima hora (top 10 por compradores):
--     ultima foto de 1 min (progresso, holders, top10_share, creator_sold) e a fatia do
--     maior comprador na fita de 90 min (eixo de forjada da KB-0103, >= 35 % = forjada)
WITH janela AS (
  SELECT f.mint, max(f.unique_buyers_60s) AS ub FROM meme_features_15s f
  JOIN meme_tokens t ON t.mint=f.mint AND t.mayhem_mode IS NULL
  WHERE f.as_of >= now() - make_interval(mins => 60)
    AND f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.02 AND 0.50
    AND f.tape_reason IS NULL AND f.net_sol_flow_60s > 0
  GROUP BY 1 ORDER BY 2 DESC NULLS LAST LIMIT 10
), dep AS (
  SELECT DISTINCT ON (f.mint) f.mint, f.curve_progress_pct, f.holders, f.top10_share,
         f.creator_sold, f.mcap_sol, f.end_time
  FROM meme_features_1m f JOIN janela ON janela.mint=f.mint
  WHERE f.end_time >= now() - make_interval(mins => 90)
  ORDER BY f.mint, f.end_time DESC
), tr AS (
  SELECT r.mint, r.trader, sum(r.sol_lamports)/1e9 AS sol FROM meme_trades r
  JOIN janela ON janela.mint=r.mint
  WHERE r.side='buy' AND r.block_time >= now() - make_interval(mins => 90) GROUP BY 1,2
), tot AS (SELECT mint, sum(sol) AS total, count(*) AS n FROM tr GROUP BY 1),
mx AS (SELECT DISTINCT ON (mint) mint, sol FROM tr ORDER BY mint, sol DESC)
SELECT t.symbol, left(j.mint,6), j.ub AS compradores_pico,
  round(dep.curve_progress_pct*100,1) AS prog_agora, dep.holders AS holders_agora,
  round(dep.top10_share*100,1) AS top10, dep.creator_sold, round(dep.mcap_sol,1) AS mcap,
  tot.n AS compradores_fita, round(mx.sol/nullif(tot.total,0)*100,1) AS maior_comprador_pct,
  t.completed_at IS NOT NULL AS encheu,
  to_char(dep.end_time AT TIME ZONE 'America/Sao_Paulo','HH24:MI') AS ultima_foto
FROM janela j JOIN meme_tokens t ON t.mint=j.mint
LEFT JOIN dep ON dep.mint=j.mint LEFT JOIN tot ON tot.mint=j.mint LEFT JOIN mx ON mx.mint=j.mint
ORDER BY j.ub DESC;
