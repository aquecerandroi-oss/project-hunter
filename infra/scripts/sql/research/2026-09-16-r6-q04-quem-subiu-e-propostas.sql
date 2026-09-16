-- R6/Q04 (KB-0100) — quem de fato subiu entre as casadas (top 15 por pico de SOL real na curva) e
-- se alguma proposta do Lab ficou ligada a evento (meme_proposals.event_id, preenchido por link_proposals).
WITH ev(ekey, observed_at, syms, rx, handle_rx) AS (VALUES
  ('1-fed',       timestamptz '2026-09-16T18:00:00Z', ARRAY['FED','FOMC','HIKE','WARSH','POWELL','RATEHIKE'], '(^|[^a-z])(fed|fomc|powell|warsh|rate hike)([^a-z]|$)', NULL),
  ('2-clarity',   timestamptz '2026-09-16T17:29:00Z', ARRAY['CLARITY','LUMMIS','WARREN','TAX','CFTC'],        '(^|[^a-z])(clarity act|clarity|lummis|warren|cftc|crypto tax)([^a-z]|$)', NULL),
  ('3-arc',       timestamptz '2026-09-16T10:30:00Z', ARRAY['ARC','ARCH','ARCC','CIRCLE','USDC'],             '(^|[^a-z])(arc|circle)([^a-z]|$)', NULL),
  ('4-elon',      timestamptz '2026-09-16T18:42:00Z', ARRAY['ELON','XMONEY','PAIDLON','800B','H1T','ELONIUS'],'(^|[^a-z])(elon|x money|xmoney|musk)([^a-z]|$)', '(paidlon|elon|xmoney)'),
  ('5-token2049', timestamptz '2026-09-16T18:50:00Z', ARRAY['TOKEN2049','T2049','2049'],                      '(token ?2049)', NULL),
  ('6-praxis',    timestamptz '2026-09-16T18:42:00Z', ARRAY['PRAXIS'],                                        '(praxis)', '(praxisnation)'),
  ('7-hbo',       timestamptz '2026-09-16T17:06:00Z', ARRAY['HBO','HBOMAX','HACKED'],                         '(^|[^a-z])(hbo|hbo max)([^a-z]|$)', NULL),
  ('8-trustfund', timestamptz '2026-09-16T18:42:00Z', ARRAY['WOTF','WOFI','ECTF','NTDA','USGR','DANGR','KIBA'],'(trust fund|world trust|worlds trust)', NULL)
),
tok AS (SELECT mint, symbol, name, twitter, created_at, migrated_at FROM meme_tokens
        WHERE created_at >= date_trunc('day', now() at time zone 'America/Sao_Paulo') at time zone 'America/Sao_Paulo'
          AND created_at <= now()),
matched AS (SELECT DISTINCT ON (t.mint) t.mint, t.symbol, t.created_at, t.migrated_at, e.ekey
            FROM ev e JOIN tok t ON upper(t.symbol) = ANY(e.syms) OR t.name ~* e.rx
              OR (e.handle_rx IS NOT NULL AND t.twitter ~* e.handle_rx) ORDER BY t.mint, e.ekey),
top AS (SELECT m.* FROM matched m ORDER BY md5(m.mint) LIMIT 200)
SELECT t.ekey, t.symbol, to_char(t.created_at at time zone 'America/Sao_Paulo','HH24:MI') AS criada_brt,
       round(max(s.real_sol_reserves)::numeric,1) AS pico_sol_real,
       bool_or(s.mayhem_enabled) AS mayhem, (t.migrated_at IS NOT NULL) AS migrou, t.mint
FROM top t JOIN meme_curve_snapshots s ON s.mint = t.mint
 AND s.observed_at >= date_trunc('day', now() at time zone 'America/Sao_Paulo') at time zone 'America/Sao_Paulo'
GROUP BY t.ekey, t.symbol, t.created_at, t.migrated_at, t.mint
ORDER BY 4 DESC NULLS LAST LIMIT 15;
SELECT count(*) AS propostas_total, count(*) FILTER (WHERE event_id IS NOT NULL) AS com_event_id FROM meme_proposals;
