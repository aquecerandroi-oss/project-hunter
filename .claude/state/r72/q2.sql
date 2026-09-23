SET statement_timeout='240s';
COPY (
WITH pos AS (SELECT mint, min(entry_at) AS t0, max(exit_at) AS t1 FROM meme_live_positions WHERE status='closed' GROUP BY mint)
SELECT tr.mint, tr.block_time, tr.slot, tr.signature, tr.event_index, tr.trader, tr.side, tr.sol_lamports, tr.token_amount, tr.source
FROM meme_trades tr JOIN pos ON pos.mint=tr.mint
WHERE tr.block_time >= pos.t0 - interval '2 minutes' AND tr.block_time < greatest(pos.t1, pos.t0 + interval '6 minutes') + interval '2 minutes'
ORDER BY tr.mint, tr.slot, tr.signature, tr.event_index
) TO STDOUT WITH CSV HEADER;
