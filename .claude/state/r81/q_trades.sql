SET statement_timeout='1800s';
COPY (
  WITH d AS (
    SELECT DISTINCT p.mint, p.decided_at FROM meme_proposals p
    WHERE p.reasons->0->>'rule' LIKE 'fluxo\_e\_holders/%'
      AND (EXISTS (SELECT 1 FROM meme_live_positions l WHERE l.proposal_id=p.id)
        OR EXISTS (SELECT 1 FROM meme_paper_bets b WHERE b.proposal_id=p.id AND b.leg='single'))
  )
  SELECT d.mint, d.decided_at, t.block_time, t.received_at, t.slot, t.outer_ix_index, t.inner_ix_index, t.event_index,
         t.signature, t.side, t.price::text price, t.sol_lamports, t.program
  FROM d JOIN meme_trades t ON t.mint=d.mint AND t.block_time >= d.decided_at - interval '360 seconds'
                            AND t.block_time < d.decided_at + interval '60 seconds'
  ORDER BY d.mint, d.decided_at, t.block_time, t.slot
) TO STDOUT WITH (FORMAT csv, HEADER);
