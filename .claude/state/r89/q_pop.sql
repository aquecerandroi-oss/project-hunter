SET statement_timeout='600s';
BEGIN READ ONLY;
-- R89 — extração ÚNICA da H-032 (depois da emenda 1). Sonda refused_probe_v0/1, decisões em [23/09, 07/10).
COPY (
  SELECT p.id::text proposal_id, p.mint, p.decided_at, p.reasons->0->>'stratum' stratum,
         p.reasons->0->>'inclusion_probability' p, (p.reasons->0->'refusals')::text refusals,
         p.reasons->0->>'refused_by' refused_by, t.mayhem_enabled::text tok_mayhem,
         b.id::text bet_id, b.status, b.outcome_quality oq, b.entry->>'sol_spent' sol_spent, b.pnl_sol::text pnl_sol,
         b.high_water_x::text hw_x, b.r_multiple::text r_mult, b.exit->>'reason' exit_reason, b.exit->>'trigger' exit_trigger,
         b.exit->>'real_sol_cap_applied' cap_applied, (b.params ? 'line_support_causal')::text causal,
         b.params->>'size_sol' size_sol, b.entry->>'fee_pct' fee_pct, b.entry->>'priority_fee_sol' prio,
         b.entry->>'tokens' entry_tokens, (b.entry->'snapshot')::text entry_snapshot,
         b.exit->'snapshot'->>'real_sol_reserves' exit_real_sol, b.entry_at, b.exit_at
  FROM meme_proposals p
  LEFT JOIN meme_paper_bets b ON b.proposal_id=p.id
  LEFT JOIN meme_tokens t ON t.mint=p.mint
  WHERE p.rule_set_id='01994d00-6c1a-7000-8000-00000000001c'
    AND p.decided_at >= '2026-09-23 00:00Z' AND p.decided_at < '2026-10-07 00:00Z'
  ORDER BY p.decided_at
) TO STDOUT WITH (FORMAT csv, HEADER);
COMMIT;
