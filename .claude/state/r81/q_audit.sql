SET statement_timeout='900s';
COPY (
  WITH d AS (
    SELECT DISTINCT ON (p.mint) p.mint, p.features_end_time as_of, p.decided_at
    FROM meme_proposals p
    WHERE p.reasons->0->>'rule' LIKE 'fluxo\_e\_holders/%' AND p.reasons->0->>'series'='meme_event_gate_v1'
    ORDER BY p.mint, p.decided_at
  )
  SELECT d.mint, d.as_of, d.decided_at, t.trades_in_window, t.derived->'windows'->'60s'->>'buys' w_buys, t.derived->'windows'->'60s'->>'sells' w_sells,
         t.derived->'creation_bundle'->>'creation_slot' tape_cslot, t.derived->'coverage'->>'gaps' gaps,
         t.derived->'coverage'->>'covered_since' covered_since, t.derived->'ledger'->>'reason' ledger_reason,
         (SELECT count(*) FROM meme_trades m WHERE m.mint=d.mint AND m.block_time > d.as_of - interval '60 seconds' AND m.block_time <= d.as_of) arch_60,
         (SELECT count(*) FROM meme_trades m WHERE m.mint=d.mint AND m.block_time > d.as_of - interval '60 seconds' AND m.block_time <= d.as_of AND m.received_at <= d.as_of) arch_60_known,
         (SELECT count(*) FROM meme_curve_snapshots c WHERE c.mint=d.mint AND c.observed_at >= d.decided_at - interval '300 seconds' AND c.observed_at < d.decided_at AND c.received_at < d.decided_at) snaps_5m_known,
         (SELECT count(*) FROM meme_curve_snapshots c WHERE c.mint=d.mint AND c.observed_at >= d.decided_at - interval '60 seconds' AND c.observed_at < d.decided_at AND c.received_at < d.decided_at) snaps_1m_known
  FROM d JOIN meme_decision_tapes t ON t.mint=d.mint AND t.as_of=d.as_of
) TO STDOUT WITH (FORMAT csv, HEADER);
