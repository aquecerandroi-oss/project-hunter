SELECT column_name, data_type FROM information_schema.columns WHERE table_name='meme_paper_bets' ORDER BY ordinal_position;
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='meme_gate_refusals_by_mint' ORDER BY ordinal_position;
SELECT jsonb_pretty(entry) FROM meme_paper_bets b JOIN meme_proposals p ON p.id=b.proposal_id
 WHERE p.rule_set_id='01994d00-6c1a-7000-8000-00000000001e' AND b.status='closed' ORDER BY b.entry_at DESC LIMIT 1;
SELECT jsonb_pretty(exit) FROM meme_paper_bets b JOIN meme_proposals p ON p.id=b.proposal_id
 WHERE p.rule_set_id='01994d00-6c1a-7000-8000-00000000001e' AND b.status='closed' ORDER BY b.entry_at DESC LIMIT 1;
