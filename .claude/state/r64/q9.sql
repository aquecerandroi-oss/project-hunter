SET statement_timeout='60s';
SELECT count(*) AS buys_with_rent, sum((fill->>'ata_rent_lamports')::bigint) AS rent_lamports, min(received_at), max(received_at)
FROM meme_live_orders WHERE side='buy' AND status='confirmed' AND (fill->>'ata_rent_lamports')::bigint > 0;
SELECT count(DISTINCT p.mint) AS mints_ever_bought FROM meme_live_orders o JOIN meme_proposals p ON p.id=o.proposal_id WHERE o.side='buy' AND o.status='confirmed';
