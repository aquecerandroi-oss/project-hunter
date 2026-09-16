-- R23 16/09 16h50 BRT — a mesa desde 16:17 BRT (boot da porta calibrada operator/5 com
-- min_snipers 21): propostas, ordens reais (meme_live_orders JOIN meme_proposals) e o que
-- cada moeda proposta fez depois (mcap/progresso agora vs na proposta).
-- Unidades: curve_progress_pct e FRACAO 0-1. Horas em America/Sao_Paulo (BRT = UTC-3).
-- Rodado na VPS: docker exec -i <pg> psql -U hunter -d hunter -F "|" -At < este-arquivo

-- (a) propostas desde 16:17 BRT, com a foto de 15 s mais proxima do instante da proposta
WITH p AS (
  SELECT * FROM meme_proposals WHERE proposed_at >= timestamptz '2026-09-16 16:17-03'
), f AS (
  SELECT DISTINCT ON (p.id) p.id, x.curve_progress_pct, x.holders, x.unique_buyers_60s,
         x.snipers, x.net_sol_flow_60s, x.age_s
  FROM p JOIN meme_features_15s x ON x.mint = p.mint AND x.as_of <= p.proposed_at
  ORDER BY p.id, x.as_of DESC
)
SELECT to_char(p.proposed_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS hora_brt,
       t.symbol, left(p.mint,6) AS mint6, r.name||'/'||r.version AS regra, p.origin, p.status,
       p.mode, coalesce(p.refusal::text,'-') AS refusal, coalesce(p.decision::text,'-') AS decision,
       coalesce(p.decided_by,'-') AS decided_by,
       round(f.curve_progress_pct*100,1) AS prog_pct, f.holders, f.unique_buyers_60s,
       f.snipers, round(f.net_sol_flow_60s,2) AS fluxo, f.age_s,
       (p.bet_id IS NOT NULL) AS tem_aposta
FROM p LEFT JOIN meme_tokens t ON t.mint=p.mint
       LEFT JOIN meme_rule_sets r ON r.id=p.rule_set_id
       LEFT JOIN f ON f.id=p.id
ORDER BY p.proposed_at;

-- (b) ordens reais da mesa desde 16:17 BRT (join com a proposta que as gerou)
SELECT to_char(o.received_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS recebida_brt,
       t.symbol, left(p.mint,6) AS mint6, o.side, o.status, o.admission::text AS admissao,
       coalesce(o.reason,'-') AS motivo, o.intent::text AS intencao, o.fill::text AS fill,
       coalesce(o.tx_signature,'-') AS tx
FROM meme_live_orders o
JOIN meme_proposals p ON p.id = o.proposal_id
LEFT JOIN meme_tokens t ON t.mint = p.mint
WHERE o.received_at >= timestamptz '2026-09-16 16:17-03'
ORDER BY o.received_at;

-- (b2) ordens da mesa nas ultimas 24 h (contexto: houve alguma ordem real hoje?)
SELECT to_char(o.received_at AT TIME ZONE 'America/Sao_Paulo','DD HH24:MI') AS recebida_brt,
       t.symbol, o.side, o.status, o.admission::text, coalesce(o.reason,'-')
FROM meme_live_orders o
LEFT JOIN meme_proposals p ON p.id = o.proposal_id
LEFT JOIN meme_tokens t ON t.mint = p.mint
WHERE o.received_at >= now() - interval '24 hours'
ORDER BY o.received_at DESC LIMIT 20;

-- (c) o que cada moeda proposta desde 16:17 fez depois: foto de 1 min na proposta vs a ultima
WITH p AS (
  SELECT DISTINCT ON (mint) mint, proposed_at, status, refusal
  FROM meme_proposals WHERE proposed_at >= timestamptz '2026-09-16 16:17-03'
  ORDER BY mint, proposed_at
), na AS (
  SELECT DISTINCT ON (p.mint) p.mint, b.mcap_sol, b.curve_progress_pct, b.holders, b.top10_share
  FROM p JOIN meme_features_1m b ON b.mint=p.mint AND b.end_time <= p.proposed_at + interval '60 s'
  ORDER BY p.mint, b.end_time DESC
), ago AS (
  SELECT DISTINCT ON (p.mint) p.mint, b.mcap_sol, b.curve_progress_pct, b.holders, b.top10_share,
         b.creator_sold, b.end_time
  FROM p JOIN meme_features_1m b ON b.mint=p.mint
  ORDER BY p.mint, b.end_time DESC
)
SELECT to_char(p.proposed_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI') AS hora_brt,
       t.symbol, left(p.mint,6) AS mint6, p.status, coalesce(p.refusal::text,'-') AS refusal,
       round(na.mcap_sol,1) AS mcap_na_proposta, round(ago.mcap_sol,1) AS mcap_agora,
       round(100*(ago.mcap_sol/nullif(na.mcap_sol,0)-1),1) AS delta_mcap_pct,
       round(na.curve_progress_pct*100,1) AS prog_na_proposta,
       round(ago.curve_progress_pct*100,1) AS prog_agora,
       na.holders AS holders_na_proposta, ago.holders AS holders_agora,
       round(ago.top10_share*100,1) AS top10_agora, ago.creator_sold,
       t.completed_at IS NOT NULL AS encheu, t.migrated_at IS NOT NULL AS migrou,
       to_char(ago.end_time AT TIME ZONE 'America/Sao_Paulo','HH24:MI') AS ultima_foto
FROM p LEFT JOIN meme_tokens t ON t.mint=p.mint
       LEFT JOIN na ON na.mint=p.mint LEFT JOIN ago ON ago.mint=p.mint
ORDER BY p.proposed_at;

-- (d) contagem: propostas por status/refusal desde 16:17
SELECT status, coalesce(refusal::text,'-') AS refusal, count(*) AS linhas,
       count(DISTINCT mint) AS moedas
FROM meme_proposals WHERE proposed_at >= timestamptz '2026-09-16 16:17-03'
GROUP BY 1,2 ORDER BY 3 DESC;
