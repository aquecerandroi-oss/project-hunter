-- R88 descritivo pré-registado: posições reais da mesa com fita da decisão (contagem e médias por braço de B a 0,35)
BEGIN READ ONLY;
SET LOCAL statement_timeout='300s';
WITH d AS (
  SELECT p.id pid, p.mint, COALESCE(e->'derived', e) dv FROM meme_proposals p, LATERAL jsonb_array_elements(p.reasons) e
  WHERE e->>'feature'='decision_tape' AND p.proposed_at < '2026-10-07'),
x AS (SELECT lp.mint, (dv->'largest_net_buyer'->>'share_of_real_sol')::numeric s,
             (dv->'ledger'->>'reason') IS NULL AND (dv->'ledger'->>'wallets')::int >= 10 AS prov,
             lp.pnl_sol / (lp.sol_spent_lamports/1e9) r, COALESCE(lp.exit->>'reason', lp.exit_intent->>'reason') ex
      FROM meme_live_positions lp JOIN d ON d.pid=lp.proposal_id WHERE lp.status='closed' AND lp.pnl_sol IS NOT NULL)
SELECT prov AS livro_provado_e_guarda, (s > 0.35) AS alto, count(*) n, count(DISTINCT mint) mints, round(avg(r),4) r_medio,
       sum(CASE WHEN ex='creator_dump' THEN 1 ELSE 0 END) golpe
FROM x GROUP BY 1,2 ORDER BY 1,2;
COMMIT;
