SET statement_timeout='300s';
BEGIN READ ONLY;
-- 8. universo de moedas (controle fora de proposta): bit Mayhem conhecido na descoberta?
SELECT coalesce(mayhem_enabled::text,'null') me, count(*) n, min(created_at) a, max(created_at) z
FROM meme_tokens GROUP BY 1 ORDER BY 1;
-- 9. colunas da aposta de papel (só nomes)
SELECT string_agg(column_name, ', ' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_name='meme_paper_bets';
-- 10. trilha do quase-passou mayhem_curve por conjunto (7 d)
SELECT rs.name||'/'||rs.version rs, count(*) n, count(DISTINCT r.mint) mints
FROM meme_gate_refusals_by_mint r JOIN meme_rule_sets rs ON rs.id=r.rule_set_id WHERE r.refusal='mayhem_curve' GROUP BY 1 ORDER BY 2 DESC;
COMMIT;
