-- R26 / Q01 — as ordens reais de hoje (16/09 BRT): hora, moeda, progresso na
-- proposta, motivo real gravado e o mcap da cotacao (base do R simulado).
\pset pager off
SELECT to_char(o.received_at AT TIME ZONE 'America/Sao_Paulo', 'HH24:MI:SS') AS brt,
       left(o.admission->>'mint', 6)                       AS mint,
       t.symbol,
       round((p.quote->>'curve_progress_pct')::numeric, 4) AS progresso_proposta,
       o.reason                                            AS motivo_real,
       o.status,
       round((p.quote->>'mcap_sol')::numeric, 3)           AS mcap_sol_cotacao,
       to_char(p.proposed_at AT TIME ZONE 'America/Sao_Paulo', 'HH24:MI:SS') AS proposta_brt,
       round(extract(epoch FROM o.received_at - p.proposed_at)) AS mesa_executor_s,
       to_char(t.created_at AT TIME ZONE 'America/Sao_Paulo', 'HH24:MI:SS')  AS criada_brt
FROM meme_live_orders o
JOIN meme_proposals p ON p.id = o.proposal_id
LEFT JOIN meme_tokens t ON t.mint = o.admission->>'mint'
ORDER BY o.received_at;

-- resumo: quantas ordens, quantos mints
SELECT count(*) AS ordens, count(DISTINCT o.admission->>'mint') AS mints,
       min(o.received_at AT TIME ZONE 'America/Sao_Paulo') AS primeira,
       max(o.received_at AT TIME ZONE 'America/Sao_Paulo') AS ultima
FROM meme_live_orders o;
