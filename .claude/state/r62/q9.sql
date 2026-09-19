SET statement_timeout='60s';
COPY (
SELECT tr.mint, tr.block_time, tr.slot, tr.signature, tr.event_index, tr.trader, tr.side, tr.sol_lamports, tr.token_amount, tr.price
FROM meme_trades tr
WHERE tr.mint IN (SELECT DISTINCT mint FROM meme_paper_bets WHERE entry_at >= now() - interval '24 hours' AND status='closed')
  AND tr.block_time >= now() - interval '25 hours'
ORDER BY tr.mint, tr.slot, tr.signature, tr.event_index
) TO STDOUT WITH CSV HEADER;
