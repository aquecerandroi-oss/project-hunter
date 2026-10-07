-- R88 passo 1c — disponibilidade CEGA do bloco decision_tape (0062, H-010 'medida nova'); nenhum desfecho lido
BEGIN READ ONLY;
SET LOCAL statement_timeout='600s';
\echo == uma amostra da FORMA do bloco (chaves apenas)
WITH d AS (SELECT e FROM meme_proposals p CROSS JOIN LATERAL jsonb_array_elements(p.reasons) e
           WHERE jsonb_typeof(p.reasons)='array' AND e->>'feature'='decision_tape' ORDER BY p.proposed_at DESC LIMIT 1)
SELECT (SELECT string_agg(k, ',') FROM jsonb_object_keys(e) k) top_keys,
       (SELECT string_agg(k, ',') FROM jsonb_object_keys(COALESCE(e->'derived', e)->'largest_net_buyer') k) lnb_keys,
       (SELECT string_agg(k, ',') FROM jsonb_object_keys(COALESCE(e->'derived', e)->'ledger') k) ledger_keys
FROM d;
\echo == propostas com decision_tape, por conjunto (contagens e nulidade)
WITH d AS (
  SELECT p.id, p.mint, p.proposed_at, rs.name||'/'||rs.version rs, rs.kind,
         COALESCE(e->'derived', e) AS dv
  FROM meme_proposals p JOIN meme_rule_sets rs ON rs.id=p.rule_set_id
  CROSS JOIN LATERAL jsonb_array_elements(p.reasons) e
  WHERE jsonb_typeof(p.reasons)='array' AND e->>'feature'='decision_tape')
SELECT rs, kind, count(*) n, count(DISTINCT mint) mints, count(DISTINCT (proposed_at AT TIME ZONE 'UTC')::date) dias,
       min(proposed_at)::date primeiro, max(proposed_at)::date ultimo,
       count(*) FILTER (WHERE dv ? 'reason' AND dv->>'reason' IS NOT NULL) recusada_captura,
       count(*) FILTER (WHERE dv->'largest_net_buyer'->>'share_of_real_sol' IS NOT NULL) com_lnb_share,
       count(*) FILTER (WHERE dv->'ledger'->>'reason' IS NULL AND dv ? 'ledger') ledger_desde_nascimento,
       count(*) FILTER (WHERE dv->'largest_holder'->>'share_of_supply' IS NOT NULL) com_holder_share
FROM d GROUP BY 1,2 ORDER BY 3 DESC;
COMMIT;
