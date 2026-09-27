SELECT now() AS agora, name||'/'||version AS rs, id, kind, status, exp_ref, md5(params::text) AS md5, created_at
FROM meme_rule_sets WHERE (name,version) IN (('recuo_v1','1'),('recuo_ctrl_v1','1'),('operator','5')) ORDER BY 2;
SELECT column_name FROM information_schema.columns WHERE table_name='meme_rule_sets' ORDER BY ordinal_position;
-- histórico de edição de parâmetros (audit_logs)
SELECT created_at, action, resource_type, resource_id, left(coalesce(after::text,''),160) FROM audit_logs
WHERE resource_id IN (SELECT id::text FROM meme_rule_sets WHERE (name,version) IN (('recuo_v1','1'),('recuo_ctrl_v1','1')))
ORDER BY created_at;
