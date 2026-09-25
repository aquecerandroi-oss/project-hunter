SELECT table_name, string_agg(column_name||':'||data_type, ', ' ORDER BY ordinal_position) FROM information_schema.columns
WHERE table_name IN ('meme_paper_bets','meme_live_positions','meme_gate_refusals_by_mint','meme_proposals','meme_decision_tapes') AND table_schema='public'
GROUP BY 1;
