-- R26 / Q03 — cenario (A) T4.28g: o robo espera ate 60 s pelo retrato de risco
-- (meme_risk_snapshots com bundled_share nao-nulo) antes de abrir a proposta.
-- Para cada ordem real de hoje: existiu retrato ate 60 s / 120 s depois da
-- proposta? com que bundled_share (teto 0,20), dev_share e top10_share?
\pset pager off
WITH o AS (
  SELECT o.id, o.received_at, o.admission->>'mint' AS mint, o.reason,
         p.proposed_at
  FROM meme_live_orders o JOIN meme_proposals p ON p.id = o.proposal_id
)
SELECT to_char(o.received_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS brt,
       left(o.mint,6) AS mint,
       -- retrato ja existente e fresco (<= 600 s) no instante da decisao
       (SELECT round(r.bundled_share,4) FROM meme_risk_snapshots r
         WHERE r.mint = o.mint AND r.bundled_share IS NOT NULL
           AND r.observed_at <= o.received_at
           AND r.observed_at >= o.received_at - interval '600 seconds'
         ORDER BY r.observed_at DESC LIMIT 1)                          AS bundled_na_decisao,
       -- primeiro retrato com bundled DEPOIS da proposta e o atraso
       (SELECT round(extract(epoch FROM r.observed_at - o.proposed_at))
          FROM meme_risk_snapshots r
         WHERE r.mint = o.mint AND r.bundled_share IS NOT NULL
           AND r.observed_at > o.proposed_at
         ORDER BY r.observed_at LIMIT 1)                               AS atraso_retrato_s,
       (SELECT round(r.bundled_share,4) FROM meme_risk_snapshots r
         WHERE r.mint = o.mint AND r.bundled_share IS NOT NULL
           AND r.observed_at > o.proposed_at
         ORDER BY r.observed_at LIMIT 1)                               AS bundled_do_retrato,
       (SELECT round(r.dev_share,4) FROM meme_risk_snapshots r
         WHERE r.mint = o.mint AND r.bundled_share IS NOT NULL
           AND r.observed_at > o.proposed_at
         ORDER BY r.observed_at LIMIT 1)                               AS dev_share_do_retrato,
       (SELECT round(r.top10_share,4) FROM meme_risk_snapshots r
         WHERE r.mint = o.mint AND r.bundled_share IS NOT NULL
           AND r.observed_at > o.proposed_at
         ORDER BY r.observed_at LIMIT 1)                               AS top10_do_retrato
FROM o ORDER BY o.received_at;

-- (B) T4.28h: dev_share medido e fresco (<= 600 s) no instante da decisao,
-- pela serie de 1 min e pelo retrato de risco. Teto proposto: 0,10.
WITH o AS (
  SELECT o.id, o.received_at, o.admission->>'mint' AS mint
  FROM meme_live_orders o
)
SELECT to_char(o.received_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS brt,
       left(o.mint,6) AS mint,
       (SELECT round(f.dev_share,4) FROM meme_features_1m f
         WHERE f.mint = o.mint AND f.dev_share IS NOT NULL
           AND f.end_time <= o.received_at
           AND f.end_time >= o.received_at - interval '600 seconds'
         ORDER BY f.end_time DESC LIMIT 1)                             AS dev_share_f1m,
       (SELECT round(f.top10_share,4) FROM meme_features_1m f
         WHERE f.mint = o.mint AND f.top10_share IS NOT NULL
           AND f.end_time <= o.received_at
           AND f.end_time >= o.received_at - interval '600 seconds'
         ORDER BY f.end_time DESC LIMIT 1)                             AS top10_f1m,
       (SELECT round(f.curve_volume_1m_sol,3) FROM meme_features_1m f
         WHERE f.mint = o.mint AND f.curve_volume_1m_sol IS NOT NULL
           AND f.end_time <= o.received_at
           AND f.end_time >= o.received_at - interval '120 seconds'
         ORDER BY f.end_time DESC LIMIT 1)                             AS vol_1m_fresco,
       (SELECT f.creator_sold FROM meme_features_1m f
         WHERE f.mint = o.mint AND f.creator_sold IS NOT NULL
           AND f.end_time <= o.received_at
         ORDER BY f.end_time DESC LIMIT 1)                             AS creator_sold
FROM o ORDER BY o.received_at;
