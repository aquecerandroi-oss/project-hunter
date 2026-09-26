\d meme_market_activity_1m
\d meme_board_observations
SELECT features_version, count(*), count(DISTINCT mint), min(end_time), max(end_time) FROM meme_features_1m WHERE end_time > now() - interval '24 hours' GROUP BY 1;
SELECT board, count(*), count(DISTINCT mint) FROM meme_board_observations WHERE observed_at > now() - interval '24 hours' GROUP BY 1;
SELECT source, count(*), count(DISTINCT mint) FROM meme_curve_snapshots WHERE observed_at > now() - interval '24 hours' GROUP BY 1;
