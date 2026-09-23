SET statement_timeout='300s';
COPY (
WITH first_bet AS (
  SELECT DISTINCT ON (mint) mint, entry_at FROM meme_paper_bets
  WHERE status='closed' AND entry_at >= '2026-09-16' AND exit_at IS NOT NULL AND leg <> 'probe'
  ORDER BY mint, entry_at
)
SELECT tr.mint, tr.block_time, tr.slot, tr.signature, tr.event_index, tr.trader, tr.side, tr.sol_lamports, tr.token_amount
FROM meme_trades tr JOIN first_bet b ON b.mint=tr.mint
WHERE tr.block_time >= b.entry_at - interval '2 minutes' AND tr.block_time < b.entry_at + interval '7 minutes'
ORDER BY tr.mint, tr.slot, tr.signature, tr.event_index
) TO STDOUT WITH CSV HEADER;
