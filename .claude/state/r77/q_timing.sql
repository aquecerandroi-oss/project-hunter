SET statement_timeout='120s';
SELECT pr.reasons->0->>'series' series, pr.reasons->0->>'rule' gate, count(*) n,
  percentile_cont(0.5) within group (order by extract(epoch from pr.proposed_at - pr.features_end_time)) prop_minus_fet,
  percentile_cont(0.5) within group (order by extract(epoch from pr.decided_at - pr.proposed_at)) dec_minus_prop,
  percentile_cont(0.5) within group (order by extract(epoch from (p.entry->>'block_time')::timestamptz - pr.proposed_at)) fill_minus_prop,
  percentile_cont(0.5) within group (order by extract(epoch from (pr.quote->>'observed_at')::timestamptz - pr.proposed_at)) quote_minus_prop
FROM meme_live_positions p JOIN meme_proposals pr ON pr.id=p.proposal_id WHERE p.status='closed' GROUP BY 1,2 ORDER BY 3 DESC;
SELECT pr.reasons->0->>'series' series, split_part(pr.reasons->0->>'rule','/',1) gate, count(*) n, count(distinct b.mint) mints,
  percentile_cont(0.5) within group (order by extract(epoch from pr.proposed_at - pr.features_end_time)) prop_minus_fet,
  percentile_cont(0.5) within group (order by extract(epoch from b.entry_at - pr.proposed_at)) entry_minus_prop,
  percentile_cont(0.5) within group (order by extract(epoch from (b.entry->'snapshot'->>'observed_at')::timestamptz - pr.proposed_at)) snap_minus_prop,
  min(b.entry_at), max(b.entry_at)
FROM meme_paper_bets b JOIN meme_proposals pr ON pr.id=b.proposal_id WHERE b.exit_at IS NOT NULL AND b.pnl_sol IS NOT NULL AND b.leg='single' GROUP BY 1,2 ORDER BY 3 DESC;
SELECT b.entry::text FROM meme_paper_bets b JOIN meme_proposals pr ON pr.id=b.proposal_id WHERE pr.reasons->0->>'series'='meme_event_gate_v1' AND b.leg='single' LIMIT 1;
SELECT p.entry::text, pr.quote::text FROM meme_live_positions p JOIN meme_proposals pr ON pr.id=p.proposal_id ORDER BY p.entry_at DESC LIMIT 1;
