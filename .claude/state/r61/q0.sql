SET statement_timeout='60s';
SELECT now();
SELECT 'boards' AS t, board, count(*), count(DISTINCT mint), min(observed_at), max(observed_at),
       count(*) FILTER (WHERE kol_count > 0) AS kol_rows, count(DISTINCT mint) FILTER (WHERE kol_count > 0) AS kol_mints
FROM meme_board_observations_2026_09 WHERE observed_at > now() - interval '72 hours' GROUP BY board;
SELECT 'f15s' AS t, count(*), count(DISTINCT mint), min(as_of), max(as_of) FROM meme_features_15s_2026_09 WHERE as_of > now() - interval '72 hours';
SELECT 'f1m' AS t, count(*), count(DISTINCT mint), min(end_time), max(end_time) FROM meme_features_1m_2026_09 WHERE end_time > now() - interval '72 hours';
SELECT 'snap' AS t, count(*), count(DISTINCT mint), min(observed_at), max(observed_at) FROM meme_curve_snapshots_2026_09 WHERE observed_at > now() - interval '72 hours';
SELECT 'tokens' AS t, count(*), count(twitter), count(telegram), count(website), count(completed_at) FROM meme_tokens WHERE created_at > now() - interval '72 hours';
SELECT 'events' AS t, count(*), min(observed_at), max(observed_at) FROM meme_events WHERE observed_at > now() - interval '72 hours';
SELECT 'matches' AS t, count(*), count(DISTINCT mint), min(matched_at), max(matched_at) FROM meme_event_matches WHERE matched_at > now() - interval '72 hours';
