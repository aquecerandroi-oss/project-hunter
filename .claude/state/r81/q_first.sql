SET statement_timeout='900s';
COPY (
  WITH m AS (SELECT DISTINCT p.mint FROM meme_proposals p WHERE p.reasons->0->>'rule' LIKE 'fluxo\_e\_holders/%')
  SELECT m.mint, f.block_time first_bt, f.slot first_slot, f.received_at first_recv
  FROM m LEFT JOIN LATERAL (SELECT block_time, slot, received_at FROM meme_trades t WHERE t.mint=m.mint
       ORDER BY block_time, slot LIMIT 1) f ON true
) TO STDOUT WITH (FORMAT csv, HEADER);
