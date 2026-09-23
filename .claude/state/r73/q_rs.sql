SET statement_timeout='60s';
SELECT name||'/'||version||' | kind='||kind||' | status='||status
       ||' | max_top10_share='||COALESCE(params->'entry'->>'max_top10_share', params->>'max_top10_share', '<NULO>')
FROM meme_rule_sets ORDER BY created_at;
