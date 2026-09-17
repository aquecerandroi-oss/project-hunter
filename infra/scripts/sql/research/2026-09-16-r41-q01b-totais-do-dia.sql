-- R41 -- totais do dia ATUALIZADOS: ordens, moedas, status, motivos; e as propostas desde 19:28:44.
SET statement_timeout = 200000;
SELECT $$dia$$ AS escopo, count(*) AS ordens, count(DISTINCT p.mint) AS moedas,
  count(*) FILTER (WHERE o.status=$$refused$$) AS refused,
  count(*) FILTER (WHERE o.tx_signature IS NOT NULL) AS com_assinatura,
  to_char(min(o.received_at) AT TIME ZONE $$America/Sao_Paulo$$,$$HH24:MI:SS$$) AS primeira,
  to_char(max(o.received_at) AT TIME ZONE $$America/Sao_Paulo$$,$$HH24:MI:SS$$) AS ultima
FROM meme_live_orders o JOIN meme_proposals p ON p.id=o.proposal_id
WHERE o.received_at >= timestamptz $$2026-09-16 00:00-03$$
UNION ALL
SELECT $$desde_1928$$, count(*), count(DISTINCT p.mint),
  count(*) FILTER (WHERE o.status=$$refused$$),
  count(*) FILTER (WHERE o.tx_signature IS NOT NULL),
  to_char(min(o.received_at) AT TIME ZONE $$America/Sao_Paulo$$,$$HH24:MI:SS$$),
  to_char(max(o.received_at) AT TIME ZONE $$America/Sao_Paulo$$,$$HH24:MI:SS$$)
FROM meme_live_orders o JOIN meme_proposals p ON p.id=o.proposal_id
WHERE o.received_at > timestamptz $$2026-09-16 19:28:44-03$$;

SELECT coalesce(o.reason,$$-$$) AS motivo, count(*) AS ordens, count(DISTINCT p.mint) AS moedas
FROM meme_live_orders o JOIN meme_proposals p ON p.id=o.proposal_id
WHERE o.received_at >= timestamptz $$2026-09-16 00:00-03$$ GROUP BY 1 ORDER BY 2 DESC;

SELECT p.status, coalesce(p.refusal::text,$$-$$) AS refusal, p.mode, count(*) AS propostas,
  count(DISTINCT p.mint) AS moedas
FROM meme_proposals p WHERE p.proposed_at > timestamptz $$2026-09-16 19:28:44-03$$
GROUP BY 1,2,3 ORDER BY 4 DESC;
