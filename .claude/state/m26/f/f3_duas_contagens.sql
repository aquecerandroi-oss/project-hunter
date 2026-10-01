-- F 3b: só as duas contagens de PEDIGREE_V1 (as que C/L/H usam; repeat_dumper = false), mesmos mints.
\timing on
SELECT count(*), sum(COALESCE(a,0)+COALESCE(b,0)) FROM (
 SELECT (SELECT count(*) FROM meme_tokens o WHERE o.creator = t.creator AND o.mint <> t.mint
           AND o.created_at IS NOT NULL AND o.created_at <= t.created_at
           AND o.created_at > t.created_at - make_interval(secs => 3600)) a,
        (SELECT count(*) FROM meme_tokens o WHERE o.symbol = t.symbol AND o.mint <> t.mint
           AND o.created_at IS NOT NULL AND o.created_at <= t.created_at
           AND o.created_at > t.created_at - make_interval(secs => 86400)) b
 FROM meme_tokens t WHERE t.mint = ANY(ARRAY(SELECT mint FROM meme_features_1m
   WHERE features_version = 'meme_features_v3' AND end_time = date_trunc('minute', now()) - interval '3 minutes'))) q;
SELECT count(*), sum(COALESCE(a,0)+COALESCE(b,0)) FROM (
 SELECT (SELECT count(*) FROM meme_tokens o WHERE o.creator = t.creator AND o.mint <> t.mint
           AND o.created_at IS NOT NULL AND o.created_at <= t.created_at
           AND o.created_at > t.created_at - make_interval(secs => 3600)) a,
        (SELECT count(*) FROM meme_tokens o WHERE o.symbol = t.symbol AND o.mint <> t.mint
           AND o.created_at IS NOT NULL AND o.created_at <= t.created_at
           AND o.created_at > t.created_at - make_interval(secs => 86400)) b
 FROM meme_tokens t WHERE t.mint = ANY(ARRAY(SELECT mint FROM meme_features_1m
   WHERE features_version = 'meme_features_v3' AND end_time = date_trunc('minute', now()) - interval '9 minutes'))) q;
