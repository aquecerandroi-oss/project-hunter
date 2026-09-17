-- R46 q02: propostas e ordens reais na janela [19:25, 22:25) BRT
SET statement_timeout = 200000;
\pset format unaligned
\pset fieldsep '|'
SELECT 'por_rule_set' AS q, rs.name||'/'||rs.version AS rule_set, p.mode, p.status, coalesce(p.refusal,'-') AS refusal, count(*) AS n, count(DISTINCT p.mint) AS moedas
FROM meme_proposals p JOIN meme_rule_sets rs ON rs.id=p.rule_set_id
WHERE p.proposed_at >= timestamptz '2026-09-16 19:25-03' AND p.proposed_at < timestamptz '2026-09-16 22:25-03'
GROUP BY 1,2,3,4,5 ORDER BY 2,3,4,5;
SELECT 'ordens_por_motivo' AS q, o.side, o.status, coalesce(o.reason,'-') AS reason, count(*) AS n, count(DISTINCT p.mint) AS moedas
FROM meme_live_orders o JOIN meme_proposals p ON p.id=o.proposal_id
WHERE o.received_at >= timestamptz '2026-09-16 19:25-03' AND o.received_at < timestamptz '2026-09-16 22:25-03'
GROUP BY 1,2,3,4 ORDER BY n DESC;
-- lista das ordens reais com a feature de 15 s mais recente antes da ordem e o desfecho pela cadeia
WITH o AS (
  SELECT o.id, o.received_at, o.side, o.status, o.reason, o.tx_signature, o.admission, p.mint, p.origin, p.mode, rs.name||'/'||rs.version AS rule_set,
    (p.quote->>'curve_progress_pct')::numeric AS prog_quote
  FROM meme_live_orders o JOIN meme_proposals p ON p.id=o.proposal_id JOIN meme_rule_sets rs ON rs.id=p.rule_set_id
  WHERE o.received_at >= timestamptz '2026-09-16 19:25-03' AND o.received_at < timestamptz '2026-09-16 22:25-03'
), chk AS (
  SELECT o.id,
    max(CASE WHEN c->>'name'='curve_progress' THEN (c->>'value')::numeric END) AS prog_adm,
    max(CASE WHEN c->>'name'='bundled_share' THEN (c->>'value')::numeric END) AS bundle_adm,
    max(CASE WHEN c->>'name'='top10_share' THEN (c->>'value')::numeric END) AS top10_adm,
    string_agg(CASE WHEN (c->>'ok')::boolean IS FALSE THEN c->>'name' END, ',') AS falhou
  FROM o, LATERAL jsonb_array_elements(o.admission->'checks') c GROUP BY 1
), f AS (
  SELECT DISTINCT ON (o.id) o.id, x.as_of, x.curve_progress_pct, x.holders, x.unique_buyers_60s, x.snipers, x.net_sol_flow_60s, x.buys_60s, x.sells_60s, x.dev_share, x.creator_net_seller, x.creator_net_seller_reason
  FROM o JOIN meme_features_15s x ON x.mint=o.mint AND x.as_of <= o.received_at ORDER BY o.id, x.as_of DESC
), rk AS (
  SELECT DISTINCT ON (o.id) o.id, r.observed_at, r.bundled_share, r.top10_share, extract(epoch FROM (o.received_at - r.observed_at))::int AS idade_retrato_s
  FROM o JOIN meme_risk_snapshots r ON r.mint=o.mint AND r.observed_at <= o.received_at ORDER BY o.id, r.observed_at DESC
), rk2 AS (
  SELECT DISTINCT ON (o.id) o.id, r.bundled_share, extract(epoch FROM (r.observed_at - o.received_at))::int AS atraso_s
  FROM o JOIN meme_risk_snapshots r ON r.mint=o.mint AND r.observed_at > o.received_at ORDER BY o.id, r.observed_at
), cns AS (
  SELECT DISTINCT ON (o.id) o.id, x.creator_net_seller, x.as_of
  FROM o JOIN meme_features_15s x ON x.mint=o.mint AND x.as_of > o.received_at AND x.creator_net_seller IS NOT NULL ORDER BY o.id, x.as_of
), ent AS (
  SELECT DISTINCT ON (o.id) o.id, c.real_sol_reserves AS rsol0 FROM o JOIN meme_curve_snapshots c ON c.mint=o.mint AND c.observed_at <= o.received_at AND c.observed_at > o.received_at - interval '30 minutes' ORDER BY o.id, c.observed_at DESC
), w AS (
  SELECT o.id, c.observed_at, c.real_sol_reserves AS rsol, c.complete FROM o JOIN meme_curve_snapshots c ON c.mint=o.mint AND c.observed_at > o.received_at AND c.observed_at <= o.received_at + interval '30 minutes'
), ag AS (SELECT id, count(*) AS n, min(rsol) AS rmin, max(rsol) AS rmax, bool_or(complete) AS graduou FROM w GROUP BY 1)
SELECT 'ordens' AS q, to_char(o.received_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS hora_brt, coalesce(t.symbol,'?') AS symbol, left(o.mint,8) AS mint8,
  o.rule_set, o.origin, o.side, o.status, coalesce(o.reason,'-') AS motivo, coalesce(chk.falhou,'-') AS checks_falhos, coalesce(left(o.tx_signature,12),'-') AS tx,
  round(o.prog_quote,1) AS prog_quote, round(f.curve_progress_pct*100,1) AS prog15, round(chk.prog_adm*100,1) AS prog_adm,
  f.holders, f.unique_buyers_60s AS compr, f.snipers, f.buys_60s, f.sells_60s, round(f.dev_share*100,2) AS dev_pct, round(f.net_sol_flow_60s,2) AS fluxo,
  coalesce(f.creator_net_seller::text, coalesce(f.creator_net_seller_reason,'null')) AS cns_na_ordem,
  coalesce(cns.creator_net_seller::text,'nunca') AS cns_depois, extract(epoch FROM (cns.as_of - o.received_at))::int AS cns_atraso_s,
  round(rk.bundled_share*100,1) AS bundle_antes, rk.idade_retrato_s, round(rk2.bundled_share*100,1) AS bundle_depois, rk2.atraso_s AS retrato_atraso_s,
  round(ent.rsol0,3) AS rsol0, coalesce(ag.n,0) AS fotos30, round(ag.rmin,3) AS rmin30, round(ag.rmax,3) AS rmax30, coalesce(ag.graduou,false) AS graduou
FROM o LEFT JOIN meme_tokens t ON t.mint=o.mint LEFT JOIN chk ON chk.id=o.id LEFT JOIN f ON f.id=o.id LEFT JOIN rk ON rk.id=o.id LEFT JOIN rk2 ON rk2.id=o.id
  LEFT JOIN cns ON cns.id=o.id LEFT JOIN ent ON ent.id=o.id LEFT JOIN ag ON ag.id=o.id
ORDER BY o.received_at;
-- propostas sem ordem (nao-live, ou live sem executor)
SELECT 'propostas_sem_ordem' AS q, rs.name||'/'||rs.version AS rule_set, p.mode, p.status, coalesce(p.refusal,'-') AS refusal, count(*) AS n, count(DISTINCT p.mint) AS moedas
FROM meme_proposals p JOIN meme_rule_sets rs ON rs.id=p.rule_set_id
WHERE p.proposed_at >= timestamptz '2026-09-16 19:25-03' AND p.proposed_at < timestamptz '2026-09-16 22:25-03'
  AND NOT EXISTS (SELECT 1 FROM meme_live_orders o WHERE o.proposal_id=p.id)
GROUP BY 1,2,3,4,5 ORDER BY n DESC;
