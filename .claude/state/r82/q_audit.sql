SELECT created_at, action, entity_type, entity_id, left(coalesce(after::text,''),200) after_ FROM audit_logs
WHERE entity_id IN ('01994d00-6c1a-7000-8000-00000000001d','01994d00-6c1a-7000-8000-00000000001e')
   OR (after::text LIKE '%recuo%' AND created_at >= '2026-09-26') ORDER BY created_at;
SELECT column_name FROM information_schema.columns WHERE table_name='meme_rule_set_param_history' ORDER BY ordinal_position;
SELECT * FROM meme_rule_set_param_history WHERE rule_set_id IN ('01994d00-6c1a-7000-8000-00000000001d','01994d00-6c1a-7000-8000-00000000001e');
