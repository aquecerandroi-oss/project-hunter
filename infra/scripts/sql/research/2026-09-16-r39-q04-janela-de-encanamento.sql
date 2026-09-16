-- R39 16/09 19h33 BRT -- quais das 58 recusas a janela de encanamento teria ADMITIDO:
-- progresso 5-85 %, bundle <= 35 %, top-10 <= 30 %, criador desconhecido ok se dev <= 10 %.
-- Os valores sao os que o PROPRIO admissor viu (o.admission->checks), com o retrato de risco
-- (meme_risk_snapshots com observed_at <= received_at, sem look-ahead) como segunda fonte.
-- Duas leituras: (A) estrita -- exige retrato na hora (bundle/top-10 ausentes reprovam);
--                (B) frouxa  -- bundle/top-10 ausentes passam (so o que tem dado e julgado).
-- O desfecho e o R de cada admitida saem do q02/q03 pela mesma chave (hora + mint).
SET statement_timeout = 240000;

WITH o AS (
  SELECT o.id, o.received_at, o.reason, o.admission, p.mint
  FROM meme_live_orders o JOIN meme_proposals p ON p.id = o.proposal_id
  WHERE o.received_at >= timestamptz $$2026-09-16 11:46-03$$
), chk AS (
  SELECT o.id,
    max(CASE WHEN c->>$$name$$=$$curve_progress$$ THEN (c->>$$value$$)::numeric END) AS prog_adm,
    max(CASE WHEN c->>$$name$$=$$bundled_share$$ THEN (c->>$$value$$)::numeric END) AS bundle_adm,
    max(CASE WHEN c->>$$name$$=$$top10_share$$   THEN (c->>$$value$$)::numeric END) AS top10_adm
  FROM o, LATERAL jsonb_array_elements(o.admission->$$checks$$) c GROUP BY 1
), rs AS (
  SELECT DISTINCT ON (o.id) o.id, s.bundled_share, s.top10_share, s.dev_share,
         extract(epoch FROM (o.received_at - s.observed_at))::int AS retrato_idade_s
  FROM o JOIN meme_risk_snapshots s ON s.mint = o.mint AND s.observed_at <= o.received_at
  ORDER BY o.id, s.observed_at DESC
), ft AS (
  SELECT DISTINCT ON (o.id) o.id, x.dev_share AS dev15, x.curve_progress_pct
  FROM o JOIN meme_features_15s x ON x.mint = o.mint AND x.as_of <= o.received_at
  ORDER BY o.id, x.as_of DESC
), v AS (
  SELECT o.id, o.received_at, o.mint, o.reason, chk.prog_adm,
         coalesce(chk.bundle_adm, rs.bundled_share) AS bundle,
         coalesce(chk.top10_adm,  rs.top10_share)   AS top10,
         coalesce(rs.dev_share,   ft.dev15)         AS dev,
         rs.retrato_idade_s, ft.curve_progress_pct
  FROM o LEFT JOIN chk ON chk.id = o.id LEFT JOIN rs ON rs.id = o.id LEFT JOIN ft ON ft.id = o.id
)
SELECT to_char(v.received_at AT TIME ZONE $$America/Sao_Paulo$$,$$HH24:MI:SS$$) AS hora_brt,
  coalesce(t.symbol,$$?$$) AS symbol, left(v.mint,6) AS mint6, v.reason AS motivo_real,
  round(v.prog_adm,6) AS prog_admissor, round(v.curve_progress_pct*100,2) AS prog_feature_15s,
  round(v.bundle*100,2) AS bundle_pct, round(v.top10*100,2) AS top10_pct, round(v.dev*100,2) AS dev_pct,
  v.retrato_idade_s,
  (v.prog_adm IS NOT NULL AND v.prog_adm BETWEEN 0.05 AND 0.85) AS ok_prog,
  (v.bundle IS NOT NULL AND v.bundle <= 0.35) AS ok_bundle_estrito,
  (v.top10  IS NOT NULL AND v.top10  <= 0.30) AS ok_top10_estrito,
  (v.dev    IS NOT NULL AND v.dev    <= 0.10) AS ok_dev,
  (v.bundle IS NULL OR v.bundle <= 0.35) AS ok_bundle_frouxo,
  (v.top10  IS NULL OR v.top10  <= 0.30) AS ok_top10_frouxo
FROM v LEFT JOIN meme_tokens t ON t.mint = v.mint
ORDER BY v.received_at;
