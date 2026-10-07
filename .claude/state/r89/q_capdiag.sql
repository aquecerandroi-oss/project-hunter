SET statement_timeout='300s';
BEGIN READ ONLY;
-- R89 diagnóstico PÓS-HOC (descritivo, declarado): valor da saída Mayhem na MESMA foto de saída, sem teto e com
-- teto = SOL real observado + o SOL que a nossa compra teria posto na curva (curve_cost_sol).
WITH m AS (
  SELECT (b.entry->>'sol_spent')::numeric spent, b.pnl_sol, (b.exit->>'sol_received')::numeric got,
         (b.entry->>'tokens')::numeric tok, (b.entry->>'curve_cost_sol')::numeric cc,
         (b.entry->>'fee_pct')::numeric/100 f, (b.exit->>'priority_fee_sol')::numeric prio,
         (b.exit->'snapshot'->>'virtual_sol_reserves')::numeric vs, (b.exit->'snapshot'->>'virtual_token_reserves')::numeric vt,
         (b.exit->'snapshot'->>'real_sol_reserves')::numeric rs, (b.exit->>'real_sol_cap_applied')::boolean capped, b.exit->>'reason' why
  FROM meme_proposals p JOIN meme_paper_bets b ON b.proposal_id=p.id
  WHERE p.rule_set_id='01994d00-6c1a-7000-8000-00000000001c' AND p.reasons->0->>'stratum'='B'
    AND (p.reasons->0->'refusals') ? 'mayhem_curve'
    AND p.decided_at >= '2026-09-23 00:00Z' AND p.decided_at < '2026-10-07 00:00Z'
    AND b.status='closed' AND coalesce(b.outcome_quality,'')<>'indeterminate' AND b.pnl_sol IS NOT NULL
), v AS (SELECT *, vs*tok/(vt+tok) gross FROM m)
SELECT capped, count(*) n,
       round(avg(pnl_sol/spent),4) ret_registrado,
       round(avg((gross*(1-f)-prio)/spent - 1),4) ret_sem_teto_mesma_foto,
       round(avg((least(gross, rs+cc)*(1-f)-prio)/spent - 1),4) ret_teto_mais_nossa_compra,
       round(avg((got - (gross*(1-f)-prio))),6) dif_recebido_vs_sem_teto,
       count(*) FILTER (WHERE why='max_loss') max_loss
FROM v GROUP BY capped ORDER BY capped;
COMMIT;
