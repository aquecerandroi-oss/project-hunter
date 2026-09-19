SET statement_timeout='120s';
COPY (
WITH mm AS (SELECT DISTINCT x.mint FROM meme_event_matches x WHERE x.matched_at > now() - interval '72 hours')
SELECT o.mint, o.board, o.observed_at, o.mint_updated_at, o.market_cap_usd, o.kol_count, o.holders, o.txs, o.ath_market_cap_usd, o.progress_pct, o.volume_5m_usd
FROM mm JOIN meme_board_observations_2026_09 o ON o.mint=mm.mint AND o.observed_at > now() - interval '72 hours'
) TO STDOUT WITH (FORMAT csv, HEADER, DELIMITER E'\t');
