SET statement_timeout='120s';
COPY (
WITH pos AS (SELECT mint, min(entry_at) AS t0, max(exit_at) AS t1 FROM meme_live_positions WHERE entry_at >= '2026-09-19 03:00:00+00' GROUP BY mint)
SELECT tr.mint, tr.block_time, tr.received_at, tr.slot, tr.signature, tr.event_index, tr.trader, tr.side, tr.sol_lamports, tr.token_amount, tr.price, tr.source
FROM meme_trades tr JOIN pos ON pos.mint=tr.mint
WHERE tr.block_time >= pos.t0 - interval '15 minutes' AND tr.block_time < pos.t1 + interval '10 minutes'
ORDER BY tr.mint, tr.slot, tr.signature, tr.event_index
) TO STDOUT WITH CSV HEADER;
