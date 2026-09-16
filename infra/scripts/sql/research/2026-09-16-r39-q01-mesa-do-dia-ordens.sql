-- R39 16/09 19h33 BRT -- BALANCO DO DIA DA MESA REAL: todas as ordens de meme_live_orders
-- desde 11:46 BRT (a primeira do dia em mode = live), com o motivo REAL da recusa
-- (o o.reason e a lista de checagens reprovadas do admissor, com valor e teto).
-- Reuso do r35-q01 (bloco b) com o corte movido de 17:25 para 11:46 BRT.
-- Executado via: docker exec <pg> psql -U hunter -d hunter -Atc "<esta consulta>"
-- (as aspas simples estao escritas como $$...$$ porque a consulta viaja dentro de aspas duplas).
-- Unidades: curve_progress_pct e FRACAO 0-1. Horas em America/Sao_Paulo (BRT = UTC-3).
SET statement_timeout = 240000;

\echo == (a) as 58 ordens do dia, motivo e checagens reprovadas
WITH o AS (
  SELECT o.id, o.received_at, o.status, o.reason, o.admission, o.tx_signature, o.side,
         p.mint, p.proposed_at, p.status AS pstatus, p.refusal AS prefusal, p.origin, p.mode
  FROM meme_live_orders o JOIN meme_proposals p ON p.id = o.proposal_id
  WHERE o.received_at >= timestamptz $$2026-09-16 11:46-03$$
), f AS (
  SELECT DISTINCT ON (o.id) o.id, x.curve_progress_pct, x.holders, x.unique_buyers_60s, x.snipers,
         x.net_sol_flow_60s, x.dev_share, x.age_s
  FROM o JOIN meme_features_15s x ON x.mint = o.mint AND x.as_of <= o.proposed_at
  ORDER BY o.id, x.as_of DESC
), ck AS (
  SELECT o.id, string_agg(coalesce(c->>$$name$$,$$?$$)||$$:$$||coalesce(c->>$$refusal$$,c->>$$state$$)
           ||$$[v=$$||coalesce(c->>$$value$$,$$-$$)||$$/lim=$$||coalesce(c->>$$limit$$,$$-$$)||$$]$$,
           $$ + $$ ORDER BY c->>$$name$$) AS falhas
  FROM o, LATERAL jsonb_array_elements(o.admission->$$checks$$) c
  WHERE c->>$$state$$ <> $$passed$$ GROUP BY 1
)
SELECT to_char(o.received_at AT TIME ZONE $$America/Sao_Paulo$$,$$HH24:MI:SS$$) AS hora_brt,
  coalesce(t.symbol,$$?$$) AS symbol, left(o.mint,6) AS mint6, o.side, o.status, o.mode,
  coalesce(o.reason,$$-$$) AS motivo, coalesce(o.prefusal::text,$$-$$) AS prop_refusal,
  round(f.curve_progress_pct*100,2) AS prog_pct, f.holders, f.unique_buyers_60s, f.snipers,
  round(f.net_sol_flow_60s,2) AS fluxo, f.age_s, coalesce(o.tx_signature,$$-$$) AS tx,
  coalesce(ck.falhas,$$(sem checks)$$) AS checagens
FROM o LEFT JOIN meme_tokens t ON t.mint = o.mint
       LEFT JOIN f ON f.id = o.id LEFT JOIN ck ON ck.id = o.id
ORDER BY o.received_at;

\echo == (b) propostas do dia por modo/status: quantas viraram ordem
SELECT p.mode, p.status, coalesce(p.refusal::text,$$-$$) AS refusal, count(*) AS propostas,
       count(DISTINCT p.mint) AS moedas, count(o.id) AS viraram_ordem
FROM meme_proposals p LEFT JOIN meme_live_orders o ON o.proposal_id = p.id
WHERE p.proposed_at >= timestamptz $$2026-09-16 11:46-03$$
GROUP BY 1,2,3 ORDER BY 4 DESC;

\echo == (c) a mesa gastou alguma coisa?
SELECT count(*) FILTER (WHERE status = $$refused$$) AS recusadas,
       count(*) FILTER (WHERE status <> $$refused$$) AS outras,
       count(*) FILTER (WHERE tx_signature IS NOT NULL) AS com_assinatura,
       count(*) FILTER (WHERE fill IS NOT NULL) AS com_fill
FROM meme_live_orders WHERE received_at >= timestamptz $$2026-09-16 00:00-03$$;
