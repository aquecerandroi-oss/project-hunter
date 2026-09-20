SET statement_timeout='60s';
COPY (
SELECT b.id, b.mint, t.symbol, rs.name||'/'||rs.version AS rule_set, b.mode, b.leg, b.parent_bet_id, b.entry_at, b.exit_at, b.exit_intent->>'reason' AS exit_reason, b.pnl_sol, b.r_multiple, b.initial_risk_sol, b.params->>'size_sol' AS size_sol, b.params->>'trailing_pct' AS trailing_pct, b.params->>'target_x' AS target_x, b.params->>'max_hold_s' AS max_hold_s, b.high_water_x, b.outcome_quality
FROM meme_paper_bets b LEFT JOIN meme_tokens t USING (mint) LEFT JOIN meme_rule_sets rs ON rs.id=b.rule_set_id
WHERE b.entry_at >= '2026-09-19 03:00:00+00' AND b.status='closed' AND b.exit_at IS NOT NULL
ORDER BY b.entry_at
) TO STDOUT WITH CSV HEADER;
