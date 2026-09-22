SET statement_timeout='60s';
\echo == meme_proposals ==
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='meme_proposals' ORDER BY ordinal_position;
\echo == meme_live_orders ==
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='meme_live_orders' ORDER BY ordinal_position;
\echo == meme_live_positions ==
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='meme_live_positions' ORDER BY ordinal_position;
