SET statement_timeout='900s';
COPY (
WITH dec AS (
  SELECT p.mint, max(pr.decided_at) AS last_dec
  FROM meme_live_positions p JOIN meme_proposals pr ON pr.id = p.proposal_id
  GROUP BY p.mint
  UNION ALL
  SELECT b.mint, max(pr.decided_at)
  FROM meme_paper_bets b JOIN meme_proposals pr ON pr.id = b.proposal_id
  WHERE b.exit_at IS NOT NULL AND b.pnl_sol IS NOT NULL AND b.leg = 'single'
  GROUP BY b.mint
),
m AS (SELECT mint, max(last_dec) AS last_dec FROM dec GROUP BY mint)
SELECT t.mint, t.block_time, t.received_at, t.slot, t.event_index,
       t.trader, t.side, t.sol_lamports,
       round(t.token_amount * power(10, COALESCE(t.token_decimals, 6)))::bigint AS token_raw
FROM m JOIN meme_trades t ON t.mint = m.mint
WHERE t.block_time <= m.last_dec + interval '120 seconds'
ORDER BY t.mint, t.slot, t.event_index
) TO STDOUT WITH (FORMAT csv, HEADER);
