SET statement_timeout='600s';
COPY (
WITH m AS (SELECT mint, migrated_at FROM meme_tokens WHERE migrated_at > now() - interval '7 days')
SELECT o.mint, o.observed_at, m.migrated_at, o.position, o.market_cap_usd, o.ath_market_cap_usd,
       o.volume_sol, o.volume_usd, o.volume_5m_sol, o.volume_1h_sol, o.txs, o.buys, o.sells,
       o.holders, o.top10_share, o.dev_share, o.participants, o.snipers, o.kol_count, o.exposure_censored
FROM meme_board_observations o JOIN m ON m.mint=o.mint
WHERE o.board='graduated' AND o.observed_at >= m.migrated_at AND o.observed_at < m.migrated_at + interval '5 hours'
ORDER BY o.mint, o.observed_at
) TO STDOUT WITH CSV HEADER;
