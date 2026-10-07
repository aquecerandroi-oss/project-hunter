-- R90 / H-033 — disponibilidade CEGA: amostra dos eventos de OI no outbox (últimos ids; sem desfecho).
BEGIN READ ONLY;
SET LOCAL statement_timeout='120s';
SELECT min(id), max(id), min(created_at), max(created_at) FROM outbox_events;
SELECT stream, count(*) FROM outbox_events WHERE id > (SELECT max(id) - 200000 FROM outbox_events) GROUP BY 1 ORDER BY 2 DESC;
SELECT id, stream, left(payload::text, 600) p, created_at FROM outbox_events
 WHERE id > (SELECT max(id) - 200000 FROM outbox_events) AND payload::text LIKE '%open_interest%' ORDER BY id DESC LIMIT 3;
COMMIT;
