-- R88 passo 1b — disponibilidade CEGA: só contagens e a distribuição da VARIÁVEL; nenhum pnl/r/exit lido
BEGIN READ ONLY;
SET LOCAL statement_timeout='600s';
\echo == propostas com bloco pedigree_e2b, por conjunto
WITH e2b AS (
SELECT p.id, p.mint, p.proposed_at, p.features_end_time, p.status, p.origin, p.mode,
       rs.name||'/'||rs.version AS rs, rs.kind,
       e->>'top_buyer_share' AS share_txt, (e->>'buyers')::int AS buyers,
       (e->>'fill_seconds')::int AS fill_s, e->>'tape_reason' AS tape_reason, e->>'rule' AS e2b_rule,
       p.reasons->0->>'rule' AS gate
FROM meme_proposals p
JOIN meme_rule_sets rs ON rs.id=p.rule_set_id
CROSS JOIN LATERAL jsonb_array_elements(p.reasons) e
WHERE jsonb_typeof(p.reasons)='array' AND e->>'feature'='pedigree_e2b'
)
SELECT rs, kind, gate, count(*) n, count(DISTINCT mint) mints,
       count(DISTINCT (proposed_at AT TIME ZONE 'UTC')::date) dias,
       min(proposed_at) primeiro, max(proposed_at) ultimo,
       count(share_txt) com_share, count(*) FILTER (WHERE buyers>=10) buyers_ge10,
       count(fill_s) com_fill, count(*) FILTER (WHERE tape_reason IS NOT NULL) com_tape_reason
FROM e2b GROUP BY 1,2,3 ORDER BY 1;
\echo == total
WITH e2b AS (
SELECT p.id, p.mint, p.proposed_at, p.features_end_time, p.status, p.origin, p.mode,
       rs.name||'/'||rs.version AS rs, rs.kind,
       e->>'top_buyer_share' AS share_txt, (e->>'buyers')::int AS buyers,
       (e->>'fill_seconds')::int AS fill_s, e->>'tape_reason' AS tape_reason, e->>'rule' AS e2b_rule,
       p.reasons->0->>'rule' AS gate
FROM meme_proposals p
JOIN meme_rule_sets rs ON rs.id=p.rule_set_id
CROSS JOIN LATERAL jsonb_array_elements(p.reasons) e
WHERE jsonb_typeof(p.reasons)='array' AND e->>'feature'='pedigree_e2b'
)
SELECT count(*) n, count(DISTINCT mint) mints, count(DISTINCT (proposed_at AT TIME ZONE 'UTC')::date) dias,
       min(proposed_at), max(proposed_at), count(share_txt) com_share, count(fill_s) com_fill
FROM e2b;
\echo == distribuição da variável (sem desfecho): share em faixas, por guarda de compradores
WITH e2b AS (
SELECT p.id, p.mint, p.proposed_at, p.features_end_time, p.status, p.origin, p.mode,
       rs.name||'/'||rs.version AS rs, rs.kind,
       e->>'top_buyer_share' AS share_txt, (e->>'buyers')::int AS buyers,
       (e->>'fill_seconds')::int AS fill_s, e->>'tape_reason' AS tape_reason, e->>'rule' AS e2b_rule,
       p.reasons->0->>'rule' AS gate
FROM meme_proposals p
JOIN meme_rule_sets rs ON rs.id=p.rule_set_id
CROSS JOIN LATERAL jsonb_array_elements(p.reasons) e
WHERE jsonb_typeof(p.reasons)='array' AND e->>'feature'='pedigree_e2b'
)
SELECT CASE WHEN share_txt IS NULL THEN 'null' WHEN share_txt::numeric<0.1 THEN 'a <0.10'
            WHEN share_txt::numeric<0.2 THEN 'b 0.10-0.20' WHEN share_txt::numeric<0.35 THEN 'c 0.20-0.35'
            WHEN share_txt::numeric<0.5 THEN 'd 0.35-0.50' ELSE 'e >=0.50' END faixa,
       (buyers>=10) guarda, count(*) n, count(DISTINCT mint) mints
FROM e2b GROUP BY 1,2 ORDER BY 1,2;
\echo == quantis da variável (share, buyers, fill_seconds)
WITH e2b AS (
SELECT p.id, p.mint, p.proposed_at, p.features_end_time, p.status, p.origin, p.mode,
       rs.name||'/'||rs.version AS rs, rs.kind,
       e->>'top_buyer_share' AS share_txt, (e->>'buyers')::int AS buyers,
       (e->>'fill_seconds')::int AS fill_s, e->>'tape_reason' AS tape_reason, e->>'rule' AS e2b_rule,
       p.reasons->0->>'rule' AS gate
FROM meme_proposals p
JOIN meme_rule_sets rs ON rs.id=p.rule_set_id
CROSS JOIN LATERAL jsonb_array_elements(p.reasons) e
WHERE jsonb_typeof(p.reasons)='array' AND e->>'feature'='pedigree_e2b'
)
SELECT percentile_cont(ARRAY[0.05,0.25,0.5,0.75,0.95]) WITHIN GROUP (ORDER BY share_txt::numeric) share_q,
       percentile_cont(ARRAY[0.05,0.25,0.5,0.75,0.95]) WITHIN GROUP (ORDER BY buyers) buyers_q
FROM e2b WHERE share_txt IS NOT NULL;
WITH e2b AS (
SELECT p.id, p.mint, p.proposed_at, p.features_end_time, p.status, p.origin, p.mode,
       rs.name||'/'||rs.version AS rs, rs.kind,
       e->>'top_buyer_share' AS share_txt, (e->>'buyers')::int AS buyers,
       (e->>'fill_seconds')::int AS fill_s, e->>'tape_reason' AS tape_reason, e->>'rule' AS e2b_rule,
       p.reasons->0->>'rule' AS gate
FROM meme_proposals p
JOIN meme_rule_sets rs ON rs.id=p.rule_set_id
CROSS JOIN LATERAL jsonb_array_elements(p.reasons) e
WHERE jsonb_typeof(p.reasons)='array' AND e->>'feature'='pedigree_e2b'
)
SELECT count(fill_s) n_fill, min(fill_s), max(fill_s), count(*) FILTER (WHERE fill_s<=60) le60 FROM e2b;
\echo == quantas têm aposta de papel / posição real (EXISTÊNCIA e nulidade, sem ler valores)
WITH e2b AS (
SELECT p.id, p.mint, p.proposed_at, p.features_end_time, p.status, p.origin, p.mode,
       rs.name||'/'||rs.version AS rs, rs.kind,
       e->>'top_buyer_share' AS share_txt, (e->>'buyers')::int AS buyers,
       (e->>'fill_seconds')::int AS fill_s, e->>'tape_reason' AS tape_reason, e->>'rule' AS e2b_rule,
       p.reasons->0->>'rule' AS gate
FROM meme_proposals p
JOIN meme_rule_sets rs ON rs.id=p.rule_set_id
CROSS JOIN LATERAL jsonb_array_elements(p.reasons) e
WHERE jsonb_typeof(p.reasons)='array' AND e->>'feature'='pedigree_e2b'
)
SELECT count(DISTINCT e.id) props,
       count(DISTINCT b.proposal_id) com_aposta,
       count(DISTINCT b.proposal_id) FILTER (WHERE b.exit_at IS NOT NULL AND b.pnl_sol IS NOT NULL AND b.leg='single') com_aposta_fechada_single,
       count(DISTINCT b.mint) FILTER (WHERE b.exit_at IS NOT NULL AND b.pnl_sol IS NOT NULL AND b.leg='single') mints_fechadas,
       count(DISTINCT lp.proposal_id) com_posicao_real
FROM e2b e LEFT JOIN meme_paper_bets b ON b.proposal_id=e.id LEFT JOIN meme_live_positions lp ON lp.proposal_id=e.id;
\echo == legs/modos das apostas
WITH e2b AS (
SELECT p.id, p.mint, p.proposed_at, p.features_end_time, p.status, p.origin, p.mode,
       rs.name||'/'||rs.version AS rs, rs.kind,
       e->>'top_buyer_share' AS share_txt, (e->>'buyers')::int AS buyers,
       (e->>'fill_seconds')::int AS fill_s, e->>'tape_reason' AS tape_reason, e->>'rule' AS e2b_rule,
       p.reasons->0->>'rule' AS gate
FROM meme_proposals p
JOIN meme_rule_sets rs ON rs.id=p.rule_set_id
CROSS JOIN LATERAL jsonb_array_elements(p.reasons) e
WHERE jsonb_typeof(p.reasons)='array' AND e->>'feature'='pedigree_e2b'
)
SELECT b.leg, b.mode, count(*) FROM e2b e JOIN meme_paper_bets b ON b.proposal_id=e.id GROUP BY 1,2 ORDER BY 1,2;
COMMIT;
