-- R91 passo 1a — disponibilidade CEGA: conjuntos, parâmetros dos dois "subindo" e o bloco flow (nenhum desfecho lido)
BEGIN READ ONLY;
SET LOCAL statement_timeout='300s';
\echo == conjuntos: kind, clock, ativo, parâmetros dos dois "subindo" (vivos hoje)
SELECT name||'/'||version rs, kind, params->>'clock' clock, retired_at IS NULL ativo,
       params->>'require_holders_rising' req_h, params->>'require_progress_rising' req_p,
       params->>'holders_rising_or_flat' h_or_flat, params->>'progress_or_mcap_rising' p_or_mcap
FROM meme_rule_sets ORDER BY kind, name, version;
\echo == histórico de mudança desses parâmetros
SELECT rs.name||'/'||rs.version rs, h.changed_at, h.param, h.old_value, h.new_value
FROM meme_rule_set_param_history h JOIN meme_rule_sets rs ON rs.id=h.rule_set_id
WHERE h.param IN ('require_holders_rising','require_progress_rising','holders_rising_or_flat','progress_or_mcap_rising')
ORDER BY h.changed_at;
COMMIT;
