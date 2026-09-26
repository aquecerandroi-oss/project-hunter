SET statement_timeout='900s';
COPY (SELECT mint, created_at, social_observed_at, social_source, twitter, twitter_kind, twitter_reuse_count, twitter_reuse_observed_at, creator
      FROM meme_tokens WHERE created_at >= '2026-09-11') TO STDOUT WITH (FORMAT csv, HEADER);
