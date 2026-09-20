SET statement_timeout='60s';
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='meme_proposals' ORDER BY ordinal_position;
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='meme_paper_bets' ORDER BY ordinal_position;
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='meme_curve_snapshots' ORDER BY ordinal_position;
