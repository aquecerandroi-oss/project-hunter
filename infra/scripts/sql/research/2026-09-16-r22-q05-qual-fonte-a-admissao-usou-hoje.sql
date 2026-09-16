-- R22 q05 — as ordens de compra de hoje (16/09 BRT): o valor que o check top10_share
-- registrou (vem de meme_features_1m, repo.py::_FEATURES) x o retrato de risco mais
-- recente <= received_at. Resposta: 24 ordens, 23 com o check; so 3 linhas tinham
-- retrato no instante da decisao (12:53 identico; 14:13/14:14 0.1323 x 0.1832 da mesa).
SELECT o.received_at AT TIME ZONE 'America/Sao_Paulo' AS brt,
       left(p.mint, 6) AS mint, o.status, o.reason,
       c->>'state' AS estado,
       c->>'value' AS valor_features_1m,
       c->>'limit' AS teto,
       (SELECT round(s.top10_share, 4)::text FROM meme_risk_snapshots s
         WHERE s.mint = p.mint AND s.observed_at <= o.received_at
         ORDER BY s.observed_at DESC LIMIT 1) AS valor_retrato,
       (SELECT to_char(s.observed_at AT TIME ZONE 'America/Sao_Paulo', 'HH24:MI:SS')
          FROM meme_risk_snapshots s
         WHERE s.mint = p.mint AND s.observed_at <= o.received_at
         ORDER BY s.observed_at DESC LIMIT 1) AS retrato_em
FROM meme_live_orders o
JOIN meme_proposals p ON p.id = o.proposal_id,
     LATERAL jsonb_array_elements(o.admission->'checks') c
WHERE o.side = 'buy' AND c->>'name' = 'top10_share'
  AND o.received_at >= date_trunc('day', now() AT TIME ZONE 'America/Sao_Paulo') AT TIME ZONE 'America/Sao_Paulo'
ORDER BY o.received_at;

-- qual fonte alimentou a barra que o executor leu (holders_source da ultima barra do mint)
SELECT left(p.mint, 6), f.end_time AT TIME ZONE 'America/Sao_Paulo', f.holders_source,
       round(f.top10_share, 6), f.holders
FROM meme_live_orders o
JOIN meme_proposals p ON p.id = o.proposal_id
JOIN LATERAL (SELECT * FROM meme_features_1m x WHERE x.mint = p.mint
              ORDER BY x.end_time DESC LIMIT 1) f ON true
WHERE o.side = 'buy'
  AND o.received_at >= date_trunc('day', now() AT TIME ZONE 'America/Sao_Paulo') AT TIME ZONE 'America/Sao_Paulo'
GROUP BY 1, 2, 3, 4, 5 ORDER BY 2;
