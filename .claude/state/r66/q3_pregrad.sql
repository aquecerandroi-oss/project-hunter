SET statement_timeout='600s';
COPY (
WITH m AS (SELECT mint, migrated_at FROM meme_tokens WHERE migrated_at > now() - interval '7 days'),
last_obs AS (
  SELECT DISTINCT ON (o.mint) o.mint, o.observed_at, o.board, o.market_cap_usd, o.progress_pct,
         o.volume_sol, o.volume_usd, o.volume_5m_sol, o.volume_1h_sol, o.txs, o.buys, o.sells,
         o.holders, o.top10_share, o.dev_share, o.participants, o.snipers, o.kol_count, o.age_s,
         o.has_social, o.has_twitter
  FROM meme_board_observations o JOIN m ON m.mint=o.mint
  WHERE o.board <> 'graduated' AND o.observed_at < m.migrated_at AND o.observed_at >= m.migrated_at - interval '10 minutes'
  ORDER BY o.mint, o.observed_at DESC
)
SELECT * FROM last_obs ORDER BY mint
) TO STDOUT WITH CSV HEADER;
