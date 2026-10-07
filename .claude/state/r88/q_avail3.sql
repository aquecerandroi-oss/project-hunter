-- R88 passo 1d — disponibilidade CEGA por conjunto com decision_tape: existência/nulidade de aposta e posição; distribuição só da VARIÁVEL
BEGIN READ ONLY;
SET LOCAL statement_timeout='600s';
\echo == por conjunto: status da proposta, aposta fechada single (nulidade), posição real (existência), mints e dias elegíveis
WITH d AS (
  SELECT p.id, p.mint, p.proposed_at, p.status, rs.name||'/'||rs.version rs, COALESCE(e->'derived', e) dv
  FROM meme_proposals p JOIN meme_rule_sets rs ON rs.id=p.rule_set_id
  CROSS JOIN LATERAL jsonb_array_elements(p.reasons) e
  WHERE jsonb_typeof(p.reasons)='array' AND e->>'feature'='decision_tape')
SELECT d.rs, count(DISTINCT d.id) props,
       string_agg(DISTINCT d.status, ',') status_vistos,
       count(DISTINCT b.proposal_id) FILTER (WHERE b.exit_at IS NOT NULL AND b.pnl_sol IS NOT NULL AND b.leg='single') aposta_fechada,
       count(DISTINCT b.mint) FILTER (WHERE b.exit_at IS NOT NULL AND b.pnl_sol IS NOT NULL AND b.leg='single') mints_ap,
       count(DISTINCT b.mint) FILTER (WHERE b.exit_at IS NOT NULL AND b.pnl_sol IS NOT NULL AND b.leg='single' AND d.dv->'ledger'->>'reason' IS NULL) mints_ap_nasc,
       count(DISTINCT (b.entry_at AT TIME ZONE 'UTC')::date) FILTER (WHERE b.exit_at IS NOT NULL) dias_ap,
       count(DISTINCT lp.proposal_id) FILTER (WHERE lp.status='closed') pos_real_fechada,
       count(DISTINCT lp.mint) FILTER (WHERE lp.status='closed') mints_real
FROM d LEFT JOIN meme_paper_bets b ON b.proposal_id=d.id LEFT JOIN meme_live_positions lp ON lp.proposal_id=d.id
GROUP BY 1 ORDER BY 2 DESC;
\echo == variável (sem desfecho) na população operator/5+6 com aposta fechada e ledger desde o nascimento: quantis de share_of_real_sol (maior comprador líquido) e share_of_supply (maior saldo)
WITH d AS (
  SELECT p.id, p.mint, p.proposed_at, COALESCE(e->'derived', e) dv
  FROM meme_proposals p JOIN meme_rule_sets rs ON rs.id=p.rule_set_id
  CROSS JOIN LATERAL jsonb_array_elements(p.reasons) e
  WHERE jsonb_typeof(p.reasons)='array' AND e->>'feature'='decision_tape' AND rs.name='operator'),
f AS (SELECT DISTINCT ON (d.mint) d.mint, d.dv FROM d JOIN meme_paper_bets b ON b.proposal_id=d.id
      WHERE b.exit_at IS NOT NULL AND b.pnl_sol IS NOT NULL AND b.leg='single' AND d.dv->'ledger'->>'reason' IS NULL
      ORDER BY d.mint, d.proposed_at)
SELECT count(*) mints,
  percentile_cont(ARRAY[0.1,0.25,0.333,0.5,0.667,0.75,0.9]) WITHIN GROUP (ORDER BY (dv->'largest_net_buyer'->>'share_of_real_sol')::numeric) lnb_q,
  count(*) FILTER (WHERE (dv->'largest_net_buyer'->>'share_of_real_sol')::numeric>=0.35) lnb_ge35,
  count(*) FILTER (WHERE (dv->'largest_net_buyer'->>'is_creator')::boolean) lnb_is_creator,
  percentile_cont(ARRAY[0.1,0.25,0.333,0.5,0.667,0.75,0.9]) WITHIN GROUP (ORDER BY (dv->'largest_holder'->>'share_of_supply')::numeric) holder_q
FROM f;
COMMIT;
