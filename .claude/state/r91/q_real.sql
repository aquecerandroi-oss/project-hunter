-- R91 descritivo pré-registrado: posições reais da operator/5 com bloco flow (r real por braço de holders_rising)
BEGIN READ ONLY;
SET LOCAL statement_timeout='300s';
COPY (
SELECT lp.id AS position_id, lp.mint, p.proposed_at, x.e->>'holders_rising' AS holders_rising,
       x.e->>'progress_rising' AS progress_rising, lp.status, lp.pnl_sol::text AS pnl_sol,
       lp.sol_spent_lamports::text AS sol_spent_lamports,
       COALESCE(lp.exit->>'reason', lp.exit_intent->>'reason') AS exit_reason
FROM meme_live_positions lp JOIN meme_proposals p ON p.id=lp.proposal_id
JOIN meme_rule_sets rs ON rs.id=p.rule_set_id
JOIN LATERAL (SELECT e FROM jsonb_array_elements(p.reasons) e WHERE e->>'feature'='flow' LIMIT 1) x ON true
WHERE rs.name='operator' AND rs.version='5' AND p.proposed_at < '2026-10-07 00:00:00+00'
ORDER BY p.proposed_at
) TO STDOUT WITH (FORMAT csv, HEADER);
COMMIT;
