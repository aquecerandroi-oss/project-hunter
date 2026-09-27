-- R82 — cópia integral da trilha dos dois conjuntos (podada em 7 d), para o arquivo.
SET statement_timeout='600s';
COPY (
  SELECT r.id, r.as_of, rs.name||'/'||rs.version rule_set, r.rule_set_id, r.mint, r.refusal, r.value, r."limit"
  FROM meme_gate_refusals_by_mint r JOIN meme_rule_sets rs ON rs.id=r.rule_set_id
  WHERE r.rule_set_id IN ('01994d00-6c1a-7000-8000-00000000001d','01994d00-6c1a-7000-8000-00000000001e')
  ORDER BY r.as_of, r.rule_set_id, r.mint
) TO STDOUT WITH (FORMAT csv, HEADER);
