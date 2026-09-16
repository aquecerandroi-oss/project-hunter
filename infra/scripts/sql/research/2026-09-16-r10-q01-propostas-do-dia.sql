-- R10 / Q01 — todas as propostas da mesa (operator/5) de hoje, 00:00 BRT ate agora,
-- com a aposta de papel em sombra (se existir) e a ordem real (se houve).
--   operator/5 = 01994d00-6c1a-7000-8000-000000000011 (kind = operator, status = active)
-- Unidades: meme_proposals.quote->>curve_progress_pct e PORCENTAGEM (0-100).
SET statement_timeout = 60000;

SELECT to_char(p.proposed_at AT TIME ZONE 'America/Sao_Paulo', 'HH24:MI:SS') AS brt,
       coalesce(t.symbol, '?')                                    AS simbolo,
       left(p.mint, 6)                                            AS mint,
       round((p.quote->>'curve_progress_pct')::numeric, 1)        AS progresso_pct,
       p.mode                                                     AS modo,
       p.status                                                   AS status,
       p.decided_by                                               AS decidido_por,
       p.refusal                                                  AS recusa_proposta,
       o.status                                                   AS ordem_real,
       o.reason                                                   AS motivo_ordem,
       b.id                                                       AS aposta_paper,
       b.r_multiple                                               AS r_paper,
       b.exit->>'reason'                                          AS saida_paper
FROM meme_proposals p
LEFT JOIN meme_tokens t      ON t.mint = p.mint
LEFT JOIN meme_paper_bets b  ON b.proposal_id = p.id
LEFT JOIN LATERAL (
  SELECT lo.status, lo.reason FROM meme_live_orders lo
  WHERE lo.proposal_id = p.id ORDER BY lo.received_at LIMIT 1
) o ON true
WHERE p.rule_set_id = '01994d00-6c1a-7000-8000-000000000011'
  AND p.proposed_at >= '2026-09-16'::date::timestamp AT TIME ZONE 'America/Sao_Paulo'
ORDER BY p.proposed_at;
