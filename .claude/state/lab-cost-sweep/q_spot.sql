-- lab-cost-sweep — posições fechadas da mesa spot/1 (dinheiro real, Jupiter), com o R gravado. Só leitura.
BEGIN READ ONLY;
SET LOCAL statement_timeout='120s';
COPY (
SELECT p.id, p.signal_id, p.market_symbol, p.status, p.entry_at, p.exit_at, p.sol_spent_lamports, p.sol_received_lamports,
       p.ata_rent_lamports, p.pnl_sol, p.r_multiple, p.initial_risk_sol, sv.version, st.key AS strategy
FROM spot_positions p
JOIN agent_signals s ON s.id = p.signal_id
JOIN strategy_versions sv ON sv.id = s.strategy_version_id
JOIN strategies st ON st.id = sv.strategy_id
WHERE p.exit_at IS NOT NULL
ORDER BY p.entry_at
) TO STDOUT WITH (FORMAT csv, HEADER);
COMMIT;
