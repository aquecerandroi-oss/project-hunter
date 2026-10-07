-- R91 passo 1d — disponibilidade CEGA: suporte por braço (unidades/mints/dias), Mayhem pelo token, e concordância
-- do bloco flow com a linha de meme_features_15s do features_end_time (só covariáveis da decisão; nenhum desfecho)
BEGIN READ ONLY;
SET LOCAL statement_timeout='600s';
\echo == suporte por variável e braço (unidade = proposta mais antiga do par conjunto×mint que gerou aposta single)
WITH f AS (
  SELECT p.id, p.mint, p.proposed_at, rs.name||'/'||rs.version rs, x.e fl
  FROM meme_proposals p JOIN meme_rule_sets rs ON rs.id=p.rule_set_id
  JOIN LATERAL (SELECT e FROM jsonb_array_elements(p.reasons) e WHERE e->>'feature'='flow' LIMIT 1) x ON true
  WHERE jsonb_typeof(p.reasons)='array' AND rs.name IN ('operator','flow_v2','recuo_v1','recuo_ctrl_v1')),
u AS (
  SELECT DISTINCT ON (f.rs, f.mint) f.*, (b.entry->'snapshot'->>'mayhem_enabled') may, t.mayhem_enabled tok_may
  FROM f JOIN meme_paper_bets b ON b.proposal_id=f.id AND b.leg='single'
  LEFT JOIN meme_tokens t ON t.mint=f.mint
  ORDER BY f.rs, f.mint, f.proposed_at, b.entry_at, b.id),
v AS (
  SELECT 'holders_rising' var, rs, mint, proposed_at, fl->>'holders_rising' val, may, tok_may FROM u
  UNION ALL
  SELECT 'progress_rising', rs, mint, proposed_at, fl->>'progress_rising', may, tok_may FROM u)
SELECT var, coalesce(val,'nulo') braco, count(*) un, count(DISTINCT mint) mints,
       count(DISTINCT (proposed_at AT TIME ZONE 'UTC')::date) dias, count(DISTINCT rs) conjuntos,
       count(*) FILTER (WHERE may='true' OR tok_may) mayhem_alguma_fonte, count(*) FILTER (WHERE tok_may IS NULL) tok_nulo
FROM v GROUP BY 1,2 ORDER BY 1,2;
\echo == concordância: propostas da pista de 15 s com bloco flow e linha de meme_features_15s no features_end_time (retenção 7 d)
WITH f AS (
  SELECT p.id, p.mint, p.features_end_time, rs.name||'/'||rs.version rs, x.e fl
  FROM meme_proposals p JOIN meme_rule_sets rs ON rs.id=p.rule_set_id
  JOIN LATERAL (SELECT e FROM jsonb_array_elements(p.reasons) e WHERE e->>'feature'='flow' LIMIT 1) x ON true
  WHERE jsonb_typeof(p.reasons)='array' AND p.reasons->0->>'series'='meme_features_15s_v1'
    AND p.proposed_at > now() - interval '7 days')
SELECT f.rs, count(*) props, count(m.mint) com_linha,
       count(*) FILTER (WHERE m.mint IS NOT NULL AND (f.fl->>'holders_rising') IS NOT DISTINCT FROM m.holders_rising::text) h_igual,
       count(*) FILTER (WHERE m.mint IS NOT NULL AND (f.fl->>'progress_rising') IS NOT DISTINCT FROM m.progress_rising::text) p_igual
FROM f LEFT JOIN meme_features_15s m ON m.mint=f.mint AND m.as_of=f.features_end_time
GROUP BY 1 ORDER BY 1;
COMMIT;
