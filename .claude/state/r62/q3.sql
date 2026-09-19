SET statement_timeout='60s';
WITH m AS (SELECT unnest(ARRAY['2TqMkSTqMpxACay3j8Cjt7uqUAWTG8HYqwWJ3xmbpump','3wFxx4idkMbWyRDW9ir16oS2ChuKp1KZHboABxnTpump','FmuDycv6ymbQZL26TR3gNKzx5jKTfKKWxBZX4Mzkpump','7ktpRquhU8dViBCPNZsaQiZLbseMD7N3ctme7DsUpump','Dfe4h6BqhJqPq667gXUTy1vuhgRibbdiMy81KNsMpump','5K63VHEhV7jucMaBsov1H5wgyy62mEiYJm23Zy1jpump']) AS mint)
SELECT t.symbol, t.mint, t.created_at, t.creator, t.creator_initial_tokens, t.completed_at, t.migrated_at, t.total_supply,
 (SELECT count(*) FROM meme_trades tr WHERE tr.mint=m.mint) AS n_trades,
 (SELECT min(block_time) FROM meme_trades tr WHERE tr.mint=m.mint) AS first_tr,
 (SELECT max(block_time) FROM meme_trades tr WHERE tr.mint=m.mint) AS last_tr,
 (SELECT string_agg(DISTINCT source||'/'||coalesce(commitment,'-'),',') FROM meme_trades tr WHERE tr.mint=m.mint) AS srcs,
 (SELECT count(*) FROM meme_curve_snapshots s WHERE s.mint=m.mint) AS n_snap,
 (SELECT min(observed_at) FROM meme_curve_snapshots s WHERE s.mint=m.mint) AS first_snap,
 (SELECT max(observed_at) FROM meme_curve_snapshots s WHERE s.mint=m.mint) AS last_snap,
 (SELECT count(*) FROM meme_features_15s f WHERE f.mint=m.mint) AS n_f15
FROM m JOIN meme_tokens t USING (mint);
