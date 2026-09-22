SET statement_timeout='600s';
COPY (
WITH m AS (SELECT mint, migrated_at FROM meme_tokens WHERE migrated_at > now() - interval '7 days')
SELECT tr.mint, tr.block_time, tr.slot, tr.signature, tr.event_index, tr.trader, tr.side,
       tr.sol_lamports, tr.token_amount, tr.price, tr.token_decimals, m.migrated_at
FROM meme_trades tr JOIN m ON m.mint=tr.mint
WHERE tr.program='pump_amm' AND tr.block_time >= m.migrated_at - interval '2 minutes'
  AND tr.block_time < m.migrated_at + interval '5 hours'
ORDER BY tr.mint, tr.slot, tr.signature, tr.event_index
) TO STDOUT WITH CSV HEADER;
