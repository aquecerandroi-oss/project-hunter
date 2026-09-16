-- R1 16/09 — pedigree dos criadores das candidatas (serial / despejo anterior)
-- Nota de esquema: meme_tokens NAO tem creator_sold nem dead. creator_sold e creator_net_seller
-- vivem em meme_features_1m; "morreu" nao tem coluna — o que existe e completed_at (encheu a curva)
-- e migrated_at (migrou para a pool).

-- (a) volume e acerto historico do criador em 7 d
WITH alvo(creator6) AS (
  VALUES ('FvEKrD'),('Aqje5D'),('JC1irm'),('FDfyqq'),('C8rLpL'),('4kQeEH'),('DzJZdP'),('BKuo26')
), c AS (
  SELECT DISTINCT t.creator FROM meme_tokens t JOIN alvo a ON left(t.creator,6)=a.creator6
  WHERE t.created_at >= now() - interval '7 days'
), h AS (
  SELECT c.creator, t.mint, t.created_at, t.completed_at, t.migrated_at
  FROM c JOIN meme_tokens t ON t.creator = c.creator AND t.created_at >= now() - interval '7 days'
)
SELECT left(creator,6) AS creator6, count(*) AS moedas_7d,
  count(*) FILTER (WHERE completed_at IS NOT NULL) AS encheu_curva,
  count(*) FILTER (WHERE migrated_at IS NOT NULL) AS migrou,
  min(created_at AT TIME ZONE 'America/Sao_Paulo') AS primeira_brt,
  max(created_at AT TIME ZONE 'America/Sao_Paulo') AS ultima_brt
FROM h GROUP BY 1 ORDER BY 2 DESC;

-- (b) despejo anterior: moedas antigas (> 2 h) do mesmo criador com creator_sold / creator_net_seller
SET statement_timeout = '120s';
WITH c AS (
  SELECT DISTINCT t.creator FROM meme_tokens t
  WHERE left(t.creator,6) IN ('FvEKrD','Aqje5D','JC1irm','FDfyqq','C8rLpL','4kQeEH','DzJZdP','BKuo26')
    AND t.created_at >= now() - interval '7 days'
), m AS (
  SELECT c.creator, t.mint FROM c JOIN meme_tokens t ON t.creator=c.creator
  WHERE t.created_at >= now() - interval '7 days' AND t.created_at < now() - interval '2 hours'
)
SELECT left(m.creator,6) AS creator6, count(DISTINCT m.mint) AS moedas_antigas,
  count(DISTINCT m.mint) FILTER (WHERE f.creator_sold IS TRUE) AS com_creator_sold,
  count(DISTINCT m.mint) FILTER (WHERE f.creator_net_seller IS TRUE) AS com_creator_net_seller
FROM m LEFT JOIN meme_features_1m f ON f.mint = m.mint
GROUP BY 1 ORDER BY 2 DESC;
