SET statement_timeout='60s';
COPY (
SELECT f.*
FROM meme_features_15s f
WHERE f.mint IN ('2TqMkSTqMpxACay3j8Cjt7uqUAWTG8HYqwWJ3xmbpump','3wFxx4idkMbWyRDW9ir16oS2ChuKp1KZHboABxnTpump','FmuDycv6ymbQZL26TR3gNKzx5jKTfKKWxBZX4Mzkpump','7ktpRquhU8dViBCPNZsaQiZLbseMD7N3ctme7DsUpump','Dfe4h6BqhJqPq667gXUTy1vuhgRibbdiMy81KNsMpump','5K63VHEhV7jucMaBsov1H5wgyy62mEiYJm23Zy1jpump')
  AND f.as_of >= '2026-09-19 05:00:00+00' AND f.as_of < '2026-09-19 12:30:00+00'
ORDER BY f.mint, f.as_of
) TO STDOUT WITH CSV HEADER;
