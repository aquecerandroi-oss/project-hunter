SET statement_timeout='600s';
-- 1) cobertura do universo (todas as moedas criadas), por dia UTC
SELECT created_at::date d, count(*) n, round(avg((social_observed_at IS NOT NULL)::int),3) soc_obs,
       round(avg((twitter IS NOT NULL)::int),3) tw, round(avg((uri IS NOT NULL)::int),3) uri,
       round(avg((twitter_reuse_count IS NOT NULL)::int),3) reuse_idx
FROM meme_tokens WHERE created_at >= '2026-09-14' GROUP BY 1 ORDER BY 1;
-- 2) decisoes da porta fluxo_e_holders com aposta, por serie e dia, com cobertura social da propria moeda
WITH bets AS (
  SELECT 'real' lane, p.mint, pr.reasons->0->>'series' series, pr.decided_at FROM meme_live_positions p JOIN meme_proposals pr ON pr.id=p.proposal_id WHERE pr.reasons->0->>'rule' LIKE 'fluxo\_e\_holders/%'
  UNION ALL
  SELECT 'paper', b.mint, pr.reasons->0->>'series', pr.decided_at FROM meme_paper_bets b JOIN meme_proposals pr ON pr.id=b.proposal_id WHERE b.leg='single' AND pr.reasons->0->>'rule' LIKE 'fluxo\_e\_holders/%'
)
SELECT series, decided_at::date d, count(*) n, count(DISTINCT b.mint) mints,
  round(avg((t.social_observed_at IS NOT NULL)::int),3) soc_obs,
  round(avg((t.social_observed_at < b.decided_at)::int),3) soc_obs_before,
  round(avg((t.twitter IS NOT NULL)::int),3) tw
FROM bets b LEFT JOIN meme_tokens t ON t.mint=b.mint GROUP BY 1,2 ORDER BY 1,2;
