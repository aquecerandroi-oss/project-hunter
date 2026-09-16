-- R23 16/09 16h50 BRT — termos de vigilancia do plantao das 17h BRT
-- (obsidian/02-MARKET/Eventos/2026-09-16-17h-brt.md):
--   1) X* + "XMoney" / "X native pay" na descricao
--   2) segunda perna de PAIDLON / PAIDDOGE / casinu
--   3) ZCAT / ZEC / MONERO / privacy
--   viveiro (exclusao): WOFI / WWR
-- Contra as criacoes da ultima hora: quantas casam, quantas entraram na janela do
-- executor, quantas encheram a curva e se a graduacao e forjada (KB-0103: <= 60 s do
-- mint, ou maior comprador >= 35 % da fita).

-- (a) contagem por termo nas criacoes dos ultimos 70 min
WITH c AS (SELECT * FROM meme_tokens WHERE created_at >= now() - make_interval(mins => 70)),
txt AS (SELECT mint, (coalesce(symbol,' ')||' '||coalesce(name,' ')||' '
                      ||coalesce(description,' ')) AS s FROM c)
SELECT (SELECT count(*) FROM c) AS criadas_70min,
  count(*) FILTER (WHERE s ~* 'xmoney|x money|native pay|xpay') AS xmoney,
  count(*) FILTER (WHERE s ~* 'paidlon')  AS paidlon,
  count(*) FILTER (WHERE s ~* 'paiddoge') AS paiddoge,
  count(*) FILTER (WHERE s ~* 'casinu')   AS casinu,
  count(*) FILTER (WHERE s ~* 'zcat')     AS zcat,
  count(*) FILTER (WHERE s ~* 'zec|zcash') AS zec,
  count(*) FILTER (WHERE s ~* 'monero|xmr') AS monero,
  count(*) FILTER (WHERE s ~* 'privacy')  AS privacy,
  count(*) FILTER (WHERE s ~* 'wofi|wwr') AS viveiro,
  count(*) FILTER (WHERE s ~* 'trailcam') AS trailcam
FROM txt;

-- (b) nominais: cada moeda que casa, com desfecho e entrada na janela do executor
WITH c AS (
  SELECT t.*, (coalesce(t.symbol,' ')||' '||coalesce(t.name,' ')||' '
               ||coalesce(t.description,' ')) AS s
  FROM meme_tokens t WHERE t.created_at >= now() - make_interval(mins => 70)
)
SELECT CASE WHEN s ~* 'xmoney|x money|native pay|xpay' THEN 'xmoney'
            WHEN s ~* 'paidlon|paiddoge|casinu' THEN 'segunda_perna'
            WHEN s ~* 'zcat|zec|zcash|monero|xmr|privacy' THEN 'privacidade'
            WHEN s ~* 'wofi|wwr' THEN 'viveiro'
            ELSE 'trailcam' END AS termo,
  c.symbol, left(c.mint,6),
  to_char(c.created_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI') AS nasceu_brt,
  c.completed_at IS NOT NULL AS encheu,
  CASE WHEN c.completed_at IS NOT NULL
       THEN extract(epoch FROM (c.completed_at-c.created_at))::int END AS seg_ate_encher,
  (SELECT count(*) FROM meme_features_15s x WHERE x.mint=c.mint) AS linhas_15s,
  (SELECT count(*) FROM meme_features_15s x WHERE x.mint=c.mint
     AND x.age_s BETWEEN 30 AND 300 AND x.curve_progress_pct BETWEEN 0.02 AND 0.50
     AND x.tape_reason IS NULL AND x.net_sol_flow_60s > 0) AS fotos_na_janela,
  (SELECT round(max(x.curve_progress_pct)*100,1) FROM meme_features_15s x WHERE x.mint=c.mint) AS prog_max,
  (SELECT max(x.holders) FROM meme_features_15s x WHERE x.mint=c.mint) AS holders_max,
  left(coalesce(c.name,' '),24)
FROM c
WHERE s ~* 'xmoney|x money|native pay|xpay|paidlon|paiddoge|casinu|zcat|zec|zcash|monero|xmr|privacy|wofi|wwr|trailcam'
ORDER BY c.created_at LIMIT 40;

-- (c) as moedas-mae dos termos (ja existentes): o que fizeram na ultima hora
WITH alvo(m6) AS (VALUES ('AowPHd'),('52qkNp'),('2eMoMq'),('GFFVbG'),('7ecXbJ'),('4XcoQq'),('98kfF7'))
SELECT t.symbol, left(t.mint,6),
  to_char(t.created_at AT TIME ZONE 'America/Sao_Paulo','DD HH24:MI') AS nasceu,
  t.completed_at IS NOT NULL AS encheu, t.migrated_at IS NOT NULL AS migrou,
  (SELECT count(*) FROM meme_features_1m f WHERE f.mint=t.mint
     AND f.end_time >= now() - make_interval(mins => 60)) AS fotos_1m_ultima_hora
FROM meme_tokens t JOIN alvo a ON left(t.mint,6)=a.m6;

-- (d) base-rate da hora: quantas encheram e quantas em <= 60 s do mint
SELECT count(*) FILTER (WHERE completed_at IS NOT NULL) AS encheram,
  count(*) FILTER (WHERE extract(epoch FROM (completed_at-created_at)) <= 60) AS encheu_ate_60s,
  count(*) AS criadas
FROM meme_tokens WHERE created_at >= now() - make_interval(mins => 70);
