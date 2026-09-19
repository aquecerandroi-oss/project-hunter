SET statement_timeout='60s';
COPY (
SELECT tr.mint, tr.block_time, tr.received_at, tr.slot, tr.signature, tr.event_index, tr.trader, tr.side, tr.sol_lamports, tr.token_amount, tr.price, tr.source, tr.program, tr.is_mayhem_agent
FROM meme_trades tr
WHERE tr.mint IN ('2TqMkSTqMpxACay3j8Cjt7uqUAWTG8HYqwWJ3xmbpump','3wFxx4idkMbWyRDW9ir16oS2ChuKp1KZHboABxnTpump','FmuDycv6ymbQZL26TR3gNKzx5jKTfKKWxBZX4Mzkpump','7ktpRquhU8dViBCPNZsaQiZLbseMD7N3ctme7DsUpump','Dfe4h6BqhJqPq667gXUTy1vuhgRibbdiMy81KNsMpump','5K63VHEhV7jucMaBsov1H5wgyy62mEiYJm23Zy1jpump')
  AND tr.block_time >= '2026-09-19 05:00:00+00' AND tr.block_time < '2026-09-19 12:30:00+00'
ORDER BY tr.mint, tr.block_time, tr.slot, tr.event_index
) TO STDOUT WITH CSV HEADER;
