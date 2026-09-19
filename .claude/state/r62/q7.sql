SET statement_timeout='60s';
WITH b AS (SELECT * FROM meme_paper_bets WHERE entry_at >= now() - interval '24 hours' AND status='closed' AND exit_at IS NOT NULL)
SELECT count(*) AS closed, count(DISTINCT mint) AS mints,
 count(*) FILTER (WHERE EXISTS (SELECT 1 FROM meme_trades tr WHERE tr.mint=b.mint AND tr.block_time BETWEEN b.entry_at - interval '5 s' AND b.entry_at + interval '5 s')) AS tape_at_entry,
 count(*) FILTER (WHERE EXISTS (SELECT 1 FROM meme_trades tr WHERE tr.mint=b.mint AND tr.block_time BETWEEN b.exit_at - interval '15 s' AND b.exit_at + interval '15 s')) AS tape_at_exit,
 percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM exit_at-entry_at)) AS hold_p50,
 avg(r_multiple) AS r_avg, count(*) FILTER (WHERE r_multiple>0) AS wins
FROM b;
