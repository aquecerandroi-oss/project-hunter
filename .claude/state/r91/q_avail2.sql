-- R91 passo 1c — disponibilidade CEGA: histórico dos parâmetros dos "subindo", apostas de papel e posições reais por conjunto/pista
-- só existência, status e covariáveis da entrada; nenhum pnl_sol, exit, r_multiple, high_water_x, mark lido
BEGIN READ ONLY;
SET LOCAL statement_timeout='600s';
\echo == histórico desses parâmetros
SELECT rs.name||'/'||rs.version rs, h.changed_at, h.key, h.old_value, h.new_value
FROM meme_rule_set_param_history h JOIN meme_rule_sets rs ON rs.id=h.rule_set_id
WHERE h.key IN ('require_holders_rising','require_progress_rising','holders_rising_or_flat','progress_or_mcap_rising')
ORDER BY h.changed_at;
\echo == unidades candidatas: (conjunto, mint) com bloco flow e aposta single; a proposta mais antiga que gerou aposta
WITH f AS (
  SELECT p.id, p.mint, p.proposed_at, p.features_end_time, rs.name||'/'||rs.version rs, COALESCE(p.reasons->0->>'series','1m') series, x.e fl
  FROM meme_proposals p JOIN meme_rule_sets rs ON rs.id=p.rule_set_id
  JOIN LATERAL (SELECT e FROM jsonb_array_elements(p.reasons) e WHERE e->>'feature'='flow' LIMIT 1) x ON true
  WHERE jsonb_typeof(p.reasons)='array'),
u AS (
  SELECT DISTINCT ON (f.rs, f.mint) f.*, b.id bet_id, b.status bst, b.entry_at,
         (b.entry->'snapshot'->>'mayhem_enabled') may, (b.params ? 'sell_cap_model') scm_p, (b.entry ? 'sell_cap_model') scm_e
  FROM f JOIN meme_paper_bets b ON b.proposal_id=f.id AND b.leg='single'
  ORDER BY f.rs, f.mint, f.proposed_at, b.entry_at, b.id)
SELECT rs, string_agg(DISTINCT series, ',') series, count(*) unidades, count(DISTINCT (proposed_at AT TIME ZONE 'UTC')::date) dias,
       min(proposed_at)::date primeiro, max(proposed_at)::date ultimo,
       count(*) FILTER (WHERE bst='closed') fechadas, count(*) FILTER (WHERE bst<>'closed') nao_fechadas,
       count(*) FILTER (WHERE fl->>'holders_rising'='true') h_t, count(*) FILTER (WHERE fl->>'holders_rising'='false') h_f,
       count(*) FILTER (WHERE fl->>'holders_rising' IS NULL) h_nulo,
       count(*) FILTER (WHERE fl->>'progress_rising'='true') p_t, count(*) FILTER (WHERE fl->>'progress_rising'='false') p_f,
       count(*) FILTER (WHERE fl->>'progress_rising' IS NULL) p_nulo,
       count(*) FILTER (WHERE may='true') mayhem, count(*) FILTER (WHERE may IS NULL) may_nulo,
       count(*) FILTER (WHERE scm_p OR scm_e) com_sell_cap_model,
       count(*) FILTER (WHERE features_end_time > proposed_at) fet_depois
FROM u GROUP BY 1 ORDER BY 1;
\echo == posições reais (só existência/status) por bloco flow
WITH f AS (
  SELECT p.id, p.mint, rs.name||'/'||rs.version rs, x.e fl
  FROM meme_proposals p JOIN meme_rule_sets rs ON rs.id=p.rule_set_id
  JOIN LATERAL (SELECT e FROM jsonb_array_elements(p.reasons) e WHERE e->>'feature'='flow' LIMIT 1) x ON true
  WHERE jsonb_typeof(p.reasons)='array')
SELECT f.rs, count(DISTINCT lp.id) pos, count(DISTINCT lp.id) FILTER (WHERE lp.status='closed') fechadas,
       count(DISTINCT lp.id) FILTER (WHERE fl->>'holders_rising'='true') h_t, count(DISTINCT lp.id) FILTER (WHERE fl->>'holders_rising'='false') h_f,
       count(DISTINCT lp.id) FILTER (WHERE fl->>'progress_rising'='true') p_t, count(DISTINCT lp.id) FILTER (WHERE fl->>'progress_rising'='false') p_f,
       count(DISTINCT lp.id) FILTER (WHERE fl->>'progress_rising' IS NULL) p_nulo
FROM f JOIN meme_live_positions lp ON lp.proposal_id=f.id GROUP BY 1 ORDER BY 1;
COMMIT;
