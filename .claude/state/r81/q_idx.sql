SELECT indexdef FROM pg_indexes WHERE tablename LIKE 'meme_trades%' AND tablename IN ('meme_trades','meme_trades_2026_09','meme_trades_p2026_09') ;
SELECT inhrelid::regclass FROM pg_inherits WHERE inhparent='meme_trades'::regclass;
SELECT indexdef FROM pg_indexes WHERE tablename LIKE 'meme_features_1m%' LIMIT 5;
