-- R5 / Q03 — quem preenche os insumos `unavailable` e com quanto atraso.
--
--   creator_net_sol  <- meme_features_1m.creator_sold   (fold do meme-worker, features_tape.py)
--   top10_share      <- meme_features_1m.top10_share    (mesmo fold)
--   volume 1m        <- meme_features_1m.curve_volume_1m_sol (mesmo fold, fresco <= 120 s)
--   bundled_share    <- meme_risk_snapshots.bundled_share (RiskReader, GET /in-memory-coin,
--                       <= 1 leitura/mint/5 min, so para mint com aposta paper aberta ou
--                       no board `graduating`; executor exige <= 600 s, repo.py)
--
-- Negativo em *_apos_ordem_s = o insumo JA existia quando a admissao rodou.
WITH m AS (
    SELECT admission->>'mint' AS mint, min(received_at) AS first_order
    FROM meme_live_orders
    GROUP BY 1
)
SELECT left(m.mint, 6)                                                                 AS mint,
       to_char(t.created_at AT TIME ZONE 'America/Sao_Paulo', 'HH24:MI:SS')            AS criada_brt,
       round(extract(epoch FROM m.first_order - t.created_at))                         AS ordem_apos_criacao_s,
       round(extract(epoch FROM (SELECT min(f.end_time) FROM meme_features_1m f
                                 WHERE f.mint = m.mint) - t.created_at))               AS primeiro_f1m_s,
       round(extract(epoch FROM (SELECT min(f.end_time) FROM meme_features_1m f
                                 WHERE f.mint = m.mint AND f.creator_sold IS NOT NULL)
                                 - t.created_at))                                      AS creator_sold_s,
       round(extract(epoch FROM (SELECT min(r.observed_at) FROM meme_risk_snapshots r
                                 WHERE r.mint = m.mint AND r.bundled_share IS NOT NULL)
                                 - t.created_at))                                      AS bundled_s,
       round(extract(epoch FROM (SELECT min(f.end_time) FROM meme_features_1m f
                                 WHERE f.mint = m.mint AND f.creator_sold IS NOT NULL)
                                 - m.first_order))                                     AS creator_apos_ordem_s,
       round(extract(epoch FROM (SELECT min(r.observed_at) FROM meme_risk_snapshots r
                                 WHERE r.mint = m.mint AND r.bundled_share IS NOT NULL)
                                 - m.first_order))                                     AS bundled_apos_ordem_s
FROM m
JOIN meme_tokens t ON t.mint = m.mint
ORDER BY 3;

-- atraso mesa -> executor (proposta aberta pelo robo -> admissao)
SELECT round(avg(extract(epoch FROM o.received_at - p.proposed_at))) AS media_s,
       round(min(extract(epoch FROM o.received_at - p.proposed_at))) AS min_s,
       round(max(extract(epoch FROM o.received_at - p.proposed_at))) AS max_s
FROM meme_live_orders o
JOIN meme_proposals p ON p.id = o.proposal_id;
