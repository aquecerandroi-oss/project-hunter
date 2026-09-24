SET statement_timeout='120s';
SELECT column_name, data_type FROM information_schema.columns WHERE table_name IN ('meme_curve_snapshots','meme_trades') ORDER BY table_name, ordinal_position;
SELECT source, count(*), sum((slot IS NULL)::int) noslot FROM meme_curve_snapshots WHERE observed_at > now() - interval '1 day' GROUP BY 1;
SELECT source, count(*) FROM meme_trades WHERE block_time > now() - interval '1 day' GROUP BY 1;
