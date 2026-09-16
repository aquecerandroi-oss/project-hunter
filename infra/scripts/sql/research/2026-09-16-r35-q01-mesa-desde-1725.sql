-- R35 16/09 17h49 BRT -- a mesa desde 17:25 BRT: propostas, ordens reais e o motivo,
-- e o DESFECHO PELA CADEIA (meme_curve_snapshots.real_sol_reserves pico/atual), nao por mcap_sol
-- nem pela fita -- conforme KB-0115 (a fita explica 5 % do SOL que sai; Mayhem quebra vsol-rsol=30).
-- Reuso do r30-q01 com o corte movido de 17:00 para 17:25 BRT + bloco (c) reescrito para a cadeia.
-- Unidades: curve_progress_pct e FRACAO 0-1. Horas em America/Sao_Paulo (BRT = UTC-3).
SET statement_timeout = 240000;

\echo == (a) propostas desde 17:25 BRT
WITH p AS (
  SELECT * FROM meme_proposals WHERE proposed_at >= timestamptz '2026-09-16 17:25-03'
), f AS (
  SELECT DISTINCT ON (p.id) p.id, x.curve_progress_pct, x.holders, x.unique_buyers_60s,
         x.snipers, x.net_sol_flow_60s, x.age_s
  FROM p JOIN meme_features_15s x ON x.mint = p.mint AND x.as_of <= p.proposed_at
  ORDER BY p.id, x.as_of DESC
)
SELECT to_char(p.proposed_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS hora_brt,
       t.symbol, left(p.mint,6) AS mint6, r.name||'/'||r.version AS regra, p.origin, p.status,
       p.mode, coalesce(p.refusal::text,'-') AS refusal,
       round(f.curve_progress_pct*100,1) AS prog_pct, f.holders, f.unique_buyers_60s,
       f.snipers, round(f.net_sol_flow_60s,2) AS fluxo, f.age_s
FROM p LEFT JOIN meme_tokens t ON t.mint=p.mint
       LEFT JOIN meme_rule_sets r ON r.id=p.rule_set_id
       LEFT JOIN f ON f.id=p.id
ORDER BY p.proposed_at;

\echo == (b) ordens reais desde 17:25 BRT + checagens reprovadas
SELECT to_char(o.received_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS recebida_brt,
       t.symbol, left(p.mint,6) AS mint6, o.side, o.status,
       coalesce(o.reason,'-') AS motivo, coalesce(o.tx_signature,'-') AS tx
FROM meme_live_orders o
JOIN meme_proposals p ON p.id = o.proposal_id
LEFT JOIN meme_tokens t ON t.mint = p.mint
WHERE o.received_at >= timestamptz '2026-09-16 17:25-03'
ORDER BY o.received_at;

SELECT to_char(o.received_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS hora_brt,
       t.symbol, c->>'name' AS checagem, c->>'state' AS estado, c->>'refusal' AS refusal,
       c->>'value' AS valor, c->>'limit' AS limite
FROM meme_live_orders o
JOIN meme_proposals p ON p.id=o.proposal_id
LEFT JOIN meme_tokens t ON t.mint=p.mint,
LATERAL jsonb_array_elements(o.admission->'checks') c
WHERE o.received_at >= timestamptz '2026-09-16 17:25-03' AND c->>'state' <> 'passed'
ORDER BY o.received_at, c->>'name';

\echo == (c) DESFECHO PELA CADEIA das moedas propostas desde 17:25 (real_sol_reserves)
WITH p AS (
  SELECT DISTINCT ON (mint) mint, proposed_at, status, refusal
  FROM meme_proposals WHERE proposed_at >= timestamptz '2026-09-16 17:25-03'
  ORDER BY mint, proposed_at
), na AS (
  SELECT DISTINCT ON (p.mint) p.mint, c.real_sol_reserves AS rsol_na_proposta,
         c.virtual_sol_reserves - c.real_sol_reserves AS inv_na, c.mcap_sol AS mcap_na
  FROM p JOIN meme_curve_snapshots c ON c.mint=p.mint AND c.observed_at <= p.proposed_at + interval '60 s'
  ORDER BY p.mint, c.observed_at DESC
), pk AS (
  SELECT p.mint, max(c.real_sol_reserves) AS rsol_pico
  FROM p JOIN meme_curve_snapshots c ON c.mint=p.mint GROUP BY 1
), ag AS (
  SELECT DISTINCT ON (p.mint) p.mint, c.real_sol_reserves AS rsol_agora, c.mcap_sol AS mcap_agora,
         c.complete, c.mayhem_enabled, c.observed_at,
         c.virtual_sol_reserves - c.real_sol_reserves AS inv_agora
  FROM p JOIN meme_curve_snapshots c ON c.mint=p.mint ORDER BY p.mint, c.observed_at DESC
)
SELECT to_char(p.proposed_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI') AS hora_brt,
       t.symbol, left(p.mint,6) AS mint6, p.status, coalesce(p.refusal::text,'-') AS refusal,
       round(na.rsol_na_proposta,3) AS rsol_na_proposta, round(pk.rsol_pico,3) AS rsol_pico,
       round(ag.rsol_agora,3) AS rsol_agora,
       round(100*(ag.rsol_agora/nullif(pk.rsol_pico,0)-1),1) AS delta_rsol_vs_pico_pct,
       round(na.mcap_na,1) AS mcap_na, round(ag.mcap_agora,1) AS mcap_agora,
       ag.complete AS encheu, ag.mayhem_enabled, round(ag.inv_agora,3) AS invariante_agora,
       to_char(ag.observed_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS ultima_leitura
FROM p LEFT JOIN meme_tokens t ON t.mint=p.mint
       LEFT JOIN na ON na.mint=p.mint LEFT JOIN pk ON pk.mint=p.mint LEFT JOIN ag ON ag.mint=p.mint
ORDER BY p.proposed_at;

\echo == (d) contagem por status/refusal desde 17:25 e ultimas 8 ordens do dia
SELECT status, coalesce(refusal::text,'-') AS refusal, count(*) AS linhas, count(DISTINCT mint) AS moedas
FROM meme_proposals WHERE proposed_at >= timestamptz '2026-09-16 17:25-03' GROUP BY 1,2 ORDER BY 3 DESC;

SELECT to_char(o.received_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS hora_brt,
       t.symbol, o.status, coalesce(o.reason,'-'), coalesce(o.tx_signature,'-')
FROM meme_live_orders o LEFT JOIN meme_proposals p ON p.id=o.proposal_id
LEFT JOIN meme_tokens t ON t.mint=p.mint ORDER BY o.received_at DESC LIMIT 8;
