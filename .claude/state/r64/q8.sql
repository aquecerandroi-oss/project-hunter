SET statement_timeout='60s';
SELECT t.symbol, o.attempt, o.status, o.intent->>'closes_ata' AS closes_ata, o.intent->>'creates_ata' AS creates_ata, o.fill->>'ata_rent_refund_lamports' AS refund, o.fill->>'payer_delta_lamports' AS payer_delta, o.fill->>'sell_net_lamports' AS sell_net
FROM meme_live_orders o JOIN meme_proposals p ON p.id=o.proposal_id JOIN meme_tokens t ON t.mint=p.mint
WHERE o.received_at >= '2026-09-19 03:00:00+00' AND o.side='sell' AND o.status='confirmed' ORDER BY o.received_at;
SELECT count(*) FILTER (WHERE (fill->>'ata_rent_refund_lamports')::bigint > 0) AS with_refund, count(*) AS sells, min(received_at) FROM meme_live_orders WHERE side='sell' AND status='confirmed';
