-- R1 16/09 — cadencia da mesa operator/5 e desfecho das moedas que passaram pela janela

-- (a) propostas de operator/5 por hora BRT, 48 h
--     (rule_set_id fixo: meme_rule_sets.version e TEXTO, comparar com inteiro da erro de operador)
SELECT to_char(date_trunc('hour', proposed_at AT TIME ZONE 'America/Sao_Paulo'),'DD/MM HH24h') AS hora_brt,
  count(*) AS propostas, count(DISTINCT mint) AS moedas,
  count(*) FILTER (WHERE status='rejected') AS recusadas
FROM meme_proposals
WHERE proposed_at >= now() - interval '48 hours'
  AND rule_set_id = '01994d00-6c1a-7000-8000-000000000011'
GROUP BY 1 ORDER BY 1;

-- (b) desfecho da hora: das moedas que estiveram na janela, quantas encheram a curva
WITH j AS (
  SELECT DISTINCT f.mint FROM meme_features_15s f
  JOIN meme_tokens t ON t.mint=f.mint AND t.mayhem_mode IS NULL
  WHERE f.as_of >= now() - make_interval(mins => 60)
    AND f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.02 AND 0.50
    AND f.tape_reason IS NULL AND f.net_sol_flow_60s > 0
)
SELECT count(*) AS na_janela,
  count(*) FILTER (WHERE t.completed_at IS NOT NULL) AS encheu_curva,
  count(*) FILTER (WHERE t.migrated_at IS NOT NULL) AS migrou,
  string_agg(t.symbol, ', ') FILTER (WHERE t.completed_at IS NOT NULL) AS quais
FROM j JOIN meme_tokens t ON t.mint=j.mint;

-- (c) top-10 / dev / desfecho das candidatas nomeadas (ultima foto de 1 min)
WITH alvo AS (
  SELECT mint FROM meme_tokens
  WHERE left(mint,6) IN ('GiYSEX','CqY2NG','B1ixSs','ZbMYDR','A4Cs8J','CKSCzK','GAA3B3','H2mhdW','7CaaU7','5pjWRa','4kFCJ4')
    AND created_at >= now() - interval '6 hours'
), u AS (
  SELECT DISTINCT ON (f.mint) f.* FROM meme_features_1m f JOIN alvo a ON a.mint=f.mint
  WHERE f.end_time >= now() - interval '2 hours' ORDER BY f.mint, f.end_time DESC
)
SELECT left(u.mint,6) AS mint6, t.symbol, round(u.age_minutes,1) AS idade_min,
  round(u.curve_progress_pct*100,1) AS prog_pct, u.holders,
  round(u.top10_share*100,1) AS top10_pct, round(u.dev_share*100,2) AS dev_pct, u.snipers,
  u.creator_sold, u.creator_net_seller, round(u.mcap_sol,2) AS mcap_sol,
  t.completed_at IS NOT NULL AS encheu, t.migrated_at IS NOT NULL AS migrou,
  to_char(u.end_time AT TIME ZONE 'America/Sao_Paulo','HH24:MI') AS foto_brt
FROM u JOIN meme_tokens t ON t.mint=u.mint ORDER BY u.mcap_sol DESC NULLS LAST;

-- (d) trilha de 1 min de uma moeda especifica (usada para CFLOW 7CaaU7)
SELECT to_char(end_time AT TIME ZONE 'America/Sao_Paulo','HH24:MI') AS brt,
  round(age_minutes,1) AS idade, round(curve_progress_pct*100,1) AS prog, holders,
  round(top10_share*100,1) AS top10, snipers, round(mcap_sol,1) AS mcap,
  unique_buyers, round(net_sol_flow_1m,2) AS fluxo
FROM meme_features_1m
WHERE left(mint,6)='7CaaU7' AND end_time >= now() - interval '2 hours'
ORDER BY end_time LIMIT 12;
