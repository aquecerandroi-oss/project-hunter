SET statement_timeout='60s';
COPY (
SELECT s.mint, s.observed_at, s.received_at, s.source, s.slot, s.virtual_sol_reserves, s.virtual_token_reserves, s.real_sol_reserves, s.real_token_reserves, s.complete, s.mcap_sol
FROM meme_curve_snapshots s
WHERE s.mint IN ('2TqMkSTqMpxACay3j8Cjt7uqUAWTG8HYqwWJ3xmbpump','3wFxx4idkMbWyRDW9ir16oS2ChuKp1KZHboABxnTpump','FmuDycv6ymbQZL26TR3gNKzx5jKTfKKWxBZX4Mzkpump','7ktpRquhU8dViBCPNZsaQiZLbseMD7N3ctme7DsUpump','Dfe4h6BqhJqPq667gXUTy1vuhgRibbdiMy81KNsMpump','5K63VHEhV7jucMaBsov1H5wgyy62mEiYJm23Zy1jpump')
  AND s.observed_at >= '2026-09-19 05:00:00+00' AND s.observed_at < '2026-09-19 12:30:00+00'
ORDER BY s.mint, s.observed_at
) TO STDOUT WITH CSV HEADER;
