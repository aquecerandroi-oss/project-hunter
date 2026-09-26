SET statement_timeout='600s';
SELECT min(block_time), count(*) FROM meme_trades;
-- o indexador muda hasTwitter ao longo do tempo para a mesma moeda?
WITH s AS (SELECT mint, (raw->>'hasTwitter')::boolean ht, observed_at FROM meme_risk_snapshots WHERE raw ? 'hasTwitter')
SELECT count(DISTINCT mint) mints, count(DISTINCT mint) FILTER (WHERE n_vals>1) flips FROM (SELECT mint, count(DISTINCT ht) n_vals FROM s GROUP BY mint) x;
WITH s AS (SELECT mint, (raw->>'hasTwitter')::boolean ht, observed_at, row_number() OVER (PARTITION BY mint ORDER BY observed_at) rn, count(*) OVER (PARTITION BY mint) c FROM meme_risk_snapshots WHERE raw ? 'hasTwitter')
SELECT (f.ht) first_ht, (l.ht) last_ht, count(*) FROM s f JOIN s l ON l.mint=f.mint AND l.rn=l.c WHERE f.rn=1 GROUP BY 1,2;
-- REST (meme_tokens.twitter) contra o indexador (última foto)
WITH l AS (SELECT DISTINCT ON (mint) mint, (raw->>'hasTwitter')::boolean ht, observed_at FROM meme_risk_snapshots WHERE raw ? 'hasTwitter' ORDER BY mint, observed_at DESC)
SELECT (t.twitter IS NOT NULL) rest_tw, l.ht idx_tw, count(*), sum(CASE WHEN l.observed_at > t.social_observed_at THEN 1 ELSE 0 END) idx_later
FROM l JOIN meme_tokens t USING (mint) WHERE t.social_observed_at IS NOT NULL GROUP BY 1,2;
