-- R88 passo 3a — lista de unidades CEGA (sem pnl, sem exit, sem outcome_quality, sem sol_spent)
-- unidade = proposta mais antiga do par (conjunto, mint) que gerou aposta de papel single; nunca trocada
BEGIN READ ONLY;
SET LOCAL statement_timeout='900s';
COPY (
WITH pa AS (
  SELECT 'A'::text AS medida, p.id AS proposal_id, p.mint, p.proposed_at, p.features_end_time,
         rs.name||'/'||rs.version AS rs,
         e->>'top_buyer_share' AS share, (e->>'buyers')::text AS guard_n, NULL::text AS tape_reason,
         NULL::text AS ledger_reason, NULL::text AS tape_as_of, NULL::text AS tape_known_at, NULL::text AS is_creator
  FROM meme_proposals p JOIN meme_rule_sets rs ON rs.id=p.rule_set_id
  CROSS JOIN LATERAL jsonb_array_elements(p.reasons) e
  WHERE jsonb_typeof(p.reasons)='array' AND e->>'feature'='pedigree_e2b'
    AND p.proposed_at < '2026-10-07 00:00:00+00'
), pb AS (
  SELECT 'B', p.id, p.mint, p.proposed_at, p.features_end_time, rs.name||'/'||rs.version,
         dv->'largest_net_buyer'->>'share_of_real_sol', dv->'ledger'->>'wallets', dv->>'reason',
         dv->'ledger'->>'reason', dv->>'as_of', dv->'ledger'->>'known_at', dv->'largest_net_buyer'->>'is_creator'
  FROM meme_proposals p JOIN meme_rule_sets rs ON rs.id=p.rule_set_id
  CROSS JOIN LATERAL jsonb_array_elements(p.reasons) e
  CROSS JOIN LATERAL (SELECT COALESCE(e->'derived', e) AS dv) x
  WHERE jsonb_typeof(p.reasons)='array' AND e->>'feature'='decision_tape'
    AND p.proposed_at >= '2026-09-24 00:00:00+00' AND p.proposed_at < '2026-10-07 00:00:00+00'
), allp AS (SELECT * FROM pa UNION ALL SELECT * FROM pb)
SELECT DISTINCT ON (a.medida, a.rs, a.mint)
       a.medida, a.rs, a.mint, a.proposal_id, a.proposed_at, a.features_end_time,
       b.id AS bet_id, b.entry_at, b.leg,
       b.params->>'exit_on_creator_dump' AS exit_on_creator_dump, b.params->>'fee_pct' AS fee_pct_param,
       a.share, a.guard_n, a.tape_reason, a.ledger_reason, a.tape_as_of, a.tape_known_at, a.is_creator
FROM allp a JOIN meme_paper_bets b ON b.proposal_id=a.proposal_id AND b.leg='single'
ORDER BY a.medida, a.rs, a.mint, a.proposed_at, b.entry_at, b.id
) TO STDOUT WITH (FORMAT csv, HEADER);
COMMIT;
