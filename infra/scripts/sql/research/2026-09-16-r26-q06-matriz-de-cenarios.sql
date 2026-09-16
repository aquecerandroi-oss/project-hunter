-- R26 / Q06 — a matriz de cenarios: para cada ordem real de hoje, os quatro
-- insumos que (A) T4.28g, (B) T4.28h e (C) teto de top-10 30 % mexem, mais os
-- checks que continuam de pe. Um "true" em cada coluna = aquele check passaria.
--   A: existe retrato com bundled_share nao-nulo ate 60 s (e ate 120 s) depois
--      da proposta, ou ja fresco (<= 600 s) na decisao; e o valor <= 0,20.
--   B: creator_flow_unknown passa se dev_share medido (<= 600 s) <= 0,10.
--   C: top10_share <= 0,30 em vez de 0,25 (unknown continua recusando).
-- Progresso, participacao e sizing sao lidos do proprio admission->'checks'.
\pset pager off
WITH o AS (
  SELECT o.id, o.received_at, o.admission->>'mint' AS mint, o.reason, p.proposed_at,
         (SELECT c->>'value' FROM jsonb_array_elements(o.admission->'checks') c
           WHERE c->>'name' = 'curve_progress')  AS prog_valor,
         (SELECT c->>'state' FROM jsonb_array_elements(o.admission->'checks') c
           WHERE c->>'name' = 'curve_progress')  AS prog_estado,
         (SELECT c->>'state' FROM jsonb_array_elements(o.admission->'checks') c
           WHERE c->>'name' = 'participation')   AS part_estado,
         (SELECT c->>'state' FROM jsonb_array_elements(o.admission->'checks') c
           WHERE c->>'name' = 'top10_share')     AS top10_estado,
         (SELECT c->>'value' FROM jsonb_array_elements(o.admission->'checks') c
           WHERE c->>'name' = 'top10_share')     AS top10_valor
  FROM meme_live_orders o JOIN meme_proposals p ON p.id = o.proposal_id
), ins AS (
  SELECT o.*,
    (SELECT round(extract(epoch FROM r.observed_at - o.proposed_at)) FROM meme_risk_snapshots r
      WHERE r.mint = o.mint AND r.bundled_share IS NOT NULL AND r.observed_at > o.proposed_at
      ORDER BY r.observed_at LIMIT 1) AS atraso_s,
    COALESCE(
      (SELECT r.bundled_share FROM meme_risk_snapshots r
        WHERE r.mint = o.mint AND r.bundled_share IS NOT NULL
          AND r.observed_at <= o.received_at AND r.observed_at >= o.received_at - interval '600 seconds'
        ORDER BY r.observed_at DESC LIMIT 1),
      (SELECT r.bundled_share FROM meme_risk_snapshots r
        WHERE r.mint = o.mint AND r.bundled_share IS NOT NULL AND r.observed_at > o.proposed_at
        ORDER BY r.observed_at LIMIT 1)) AS bundled,
    (SELECT f.dev_share FROM meme_features_1m f
      WHERE f.mint = o.mint AND f.dev_share IS NOT NULL
        AND f.end_time <= o.received_at AND f.end_time >= o.received_at - interval '600 seconds'
      ORDER BY f.end_time DESC LIMIT 1) AS dev_share
  FROM o
)
SELECT to_char(received_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS brt,
       left(mint,6) AS mint,
       round(bundled,4) AS bundled, atraso_s,
       (bundled IS NOT NULL AND bundled <= 0.20
        AND (atraso_s IS NULL OR atraso_s <= 60))                      AS a_bundled_60s,
       (bundled IS NOT NULL AND bundled <= 0.20
        AND (atraso_s IS NULL OR atraso_s <= 120))                     AS a_bundled_120s,
       (dev_share IS NOT NULL AND dev_share <= 0.10)                   AS b_creator_ok,
       (top10_estado = 'passed'
        OR (top10_valor IS NOT NULL AND top10_valor::numeric <= 0.30)) AS c_top10_30,
       (prog_estado = 'passed')                                        AS progresso_ok,
       round(NULLIF(prog_valor,'')::numeric, 4)                        AS progresso,
       (COALESCE(part_estado,'passed') = 'passed')                     AS participacao_ok
FROM ins ORDER BY received_at;
