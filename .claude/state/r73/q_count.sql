SET statement_timeout='120s';
SELECT 'live_positions_total', count(*)::text FROM meme_live_positions;
SELECT 'live_closed', count(*)::text FROM meme_live_positions WHERE exit_at IS NOT NULL;
SELECT 'live_by_status', status||'='||count(*)::text FROM meme_live_positions GROUP BY status;
SELECT 'paper_total', count(*)::text FROM meme_paper_bets;
SELECT 'paper_closed', count(*)::text FROM meme_paper_bets WHERE exit_at IS NOT NULL AND pnl_sol IS NOT NULL;
SELECT 'entry_json_sample', jsonb_pretty(entry) FROM meme_live_positions WHERE exit_at IS NOT NULL ORDER BY entry_at DESC LIMIT 1;
SELECT 'params_sample', jsonb_pretty(params) FROM meme_live_positions ORDER BY entry_at DESC LIMIT 1;
