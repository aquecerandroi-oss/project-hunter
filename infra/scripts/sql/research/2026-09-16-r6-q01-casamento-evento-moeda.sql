-- R6/Q01 (KB-0100) — evento -> moeda: quantas criacoes de hoje casam com cada um dos 8 eventos de 2026-09-16.
-- Regra de casamento (escrita, deterministica, sem look-ahead: so usa symbol/name/twitter gravados na criacao):
--   uma moeda casa com um evento se foi criada no dia 16/09 (00:00 BRT ate agora) E
--     upper(symbol) IN (lista de tickers do evento)  OU  name ~* (regex de narrativa, com fronteira de palavra)
--     OU twitter ~* (regex de handle, quando o evento tem handle).
-- Nao ha janela temporal na regra: queremos justamente medir quantas vieram ANTES e quantas DEPOIS do observed_at.
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
tok AS (
  SELECT mint, symbol, name, twitter, created_at
  FROM meme_tokens
  WHERE created_at >= date_trunc('day', now() at time zone 'America/Sao_Paulo') at time zone 'America/Sao_Paulo'
    AND created_at <= now()
),
m AS (
  SELECT e.ekey, e.observed_at, t.mint, t.symbol, t.name, t.created_at,
         (t.created_at >= e.observed_at) AS after_event,
         extract(epoch FROM (t.created_at - e.observed_at))/60.0 AS lat_min
  FROM ev e JOIN tok t
    ON upper(t.symbol) = ANY(e.syms)
    OR t.name ~* e.rx
    OR (e.handle_rx IS NOT NULL AND t.twitter ~* e.handle_rx)
)
SELECT 'A-resumo' AS bloco, ekey, count(*)::text AS n,
       count(*) FILTER (WHERE NOT after_event)::text AS antes,
       count(*) FILTER (WHERE after_event)::text AS depois,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY lat_min) FILTER (WHERE after_event)::numeric, 1)::text AS mediana_latencia_min,
       round(min(lat_min) FILTER (WHERE after_event)::numeric,1)::text AS primeira_min
FROM m GROUP BY ekey
UNION ALL
SELECT 'B-por-hora', ekey || ' h' || to_char(created_at at time zone 'America/Sao_Paulo','HH24'),
       count(*)::text, '', '', '', ''
FROM m GROUP BY 1,2
UNION ALL
SELECT 'C-total-dia', 'todas as criacoes 16/09', count(*)::text, '', '', '', '' FROM tok
UNION ALL
SELECT 'D-criacoes-por-hora', 'h' || to_char(created_at at time zone 'America/Sao_Paulo','HH24'), count(*)::text,'','','',''
FROM tok GROUP BY 2
ORDER BY 1,2;
