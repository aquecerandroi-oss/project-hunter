SET statement_timeout='600s';
COPY (
SELECT mint, symbol, creator, created_at, completed_at, migrated_at, migrated_pool, pool_created_at,
       total_supply, first_seen_source, mayhem_enabled, twitter IS NOT NULL AS has_twitter
FROM meme_tokens WHERE migrated_at > now() - interval '7 days' ORDER BY mint
) TO STDOUT WITH CSV HEADER;
