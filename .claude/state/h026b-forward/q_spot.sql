BEGIN READ ONLY;
SET LOCAL statement_timeout='60s';
SELECT side, count(*) n,
  percentile_cont(0.5) WITHIN GROUP (ORDER BY (fill->>'network_fee_lamports')::bigint) med_net,
  min((fill->>'network_fee_lamports')::bigint) mn, max((fill->>'network_fee_lamports')::bigint) mx,
  avg((fill->>'network_fee_lamports')::bigint)::bigint avg_net,
  percentile_cont(0.5) WITHIN GROUP (ORDER BY (fill->>'priority_fee_lamports')::bigint) med_prio,
  sum((fill->>'ata_rent_lamports')::bigint) rent,
  percentile_cont(0.5) WITHIN GROUP (ORDER BY abs((fill->>'sol_delta_lamports')::bigint)) med_size
FROM spot_orders WHERE status='confirmed' GROUP BY 1;
SELECT count(*) n, sum(ata_rent_lamports) rent_pos FROM spot_positions;
COMMIT;
