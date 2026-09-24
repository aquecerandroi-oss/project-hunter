SET statement_timeout='60s';
SELECT table_name, column_name, data_type FROM information_schema.columns WHERE table_name IN ('meme_proposals','meme_paper_bets','meme_live_positions') ORDER BY table_name, ordinal_position;
SELECT count(*) n, sum((status='closed')::int) closed, sum(CASE WHEN status='closed' THEN pnl_sol END) pnl FROM meme_live_positions;
SELECT now();
