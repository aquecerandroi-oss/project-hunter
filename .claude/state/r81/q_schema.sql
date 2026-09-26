SELECT table_name, column_name, data_type FROM information_schema.columns
WHERE table_name IN ('meme_trades','meme_curve_snapshots','meme_features_1m','meme_features_15s') ORDER BY table_name, ordinal_position;
