SET statement_timeout='60s';
\echo == rent: sells with refund ==
SELECT count(*) FILTER (WHERE COALESCE((fill->>'ata_rent_refund_lamports')::bigint,0) > 0) AS with_refund, count(*) AS sells FROM meme_live_orders WHERE side='sell' AND status='confirmed';
\echo == rent: buys creating ATA ==
SELECT count(*) AS buys_with_rent, sum((fill->>'ata_rent_lamports')::bigint) AS rent_lamports FROM meme_live_orders WHERE side='buy' AND status='confirmed' AND COALESCE((fill->>'ata_rent_lamports')::bigint,0) > 0;
\echo == distinct mints ever bought ==
SELECT count(DISTINCT p.mint) FROM meme_live_orders o JOIN meme_proposals p ON p.id=o.proposal_id WHERE o.side='buy' AND o.status='confirmed';
\echo == positions by day ==
SELECT (entry_at AT TIME ZONE 'America/Sao_Paulo')::date AS d, count(*), sum(pnl_sol) FROM meme_live_positions WHERE status='closed' GROUP BY 1 ORDER BY 1;
\echo == rule sets ==
SELECT rs.name, count(*), sum(p.pnl_sol) FROM meme_live_positions p JOIN meme_proposals pr ON pr.id=p.proposal_id JOIN meme_rule_sets rs ON rs.id=pr.rule_set_id WHERE p.status='closed' GROUP BY 1 ORDER BY 1;
\echo == exit reasons ==
SELECT exit_intent->>'reason' AS r, count(*), sum(pnl_sol) FROM meme_live_positions WHERE status='closed' GROUP BY 1 ORDER BY 2 DESC;
