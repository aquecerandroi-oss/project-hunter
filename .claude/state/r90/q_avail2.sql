-- R90 / H-033 — disponibilidade CEGA: o outbox guarda o instante real da leitura de OI?
BEGIN READ ONLY;
SET LOCAL statement_timeout='120s';
SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='public' AND table_name='outbox_events' ORDER BY ordinal_position;
SELECT indexdef FROM pg_indexes WHERE tablename='outbox_events';
SELECT * FROM outbox_events ORDER BY created_at DESC LIMIT 0;
COMMIT;
