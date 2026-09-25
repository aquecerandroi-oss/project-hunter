SELECT as_of, jsonb_pretty(derived->'windows') w, derived->'coverage' cov, derived->>'reason' r, derived->>'version' v, trades_in_window FROM meme_decision_tapes WHERE series='meme_event_gate_v1' AND cardinality(proposal_ids)>0 ORDER BY as_of DESC LIMIT 2;
SELECT min(as_of), max(as_of), count(*), count(*) FILTER (WHERE cardinality(proposal_ids)>0) FROM meme_decision_tapes;
