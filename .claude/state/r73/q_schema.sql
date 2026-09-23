SET statement_timeout='60s';
SELECT table_name||'.'||column_name||' :: '||data_type
FROM information_schema.columns
WHERE table_name IN ('meme_trades','meme_live_positions','meme_paper_bets','meme_tokens','meme_proposals','meme_rule_sets')
ORDER BY table_name, ordinal_position;
