-- R6/Q05 (derivado de Q02) — MESMA medida, excluindo o evento 8 (clones 'fundo/instituicao' com preco forjado, lista AVISO).
-- R6/Q02 (KB-0100) — desfecho das moedas casadas com evento vs. controle pareado por hora.
-- Coorte "casada": uniao (dedup) das moedas que casam com qualquer dos 8 eventos pela regra de Q01,
--   amostrada a 200 mints por md5(mint) (pseudo-aleatorio deterministico, reprodutivel).
-- Coorte "controle": moedas do MESMO dia SEM casamento, amostradas com a MESMA distribuicao por hora BRT
--   da amostra casada (mesmo n por hora), tambem por md5(mint). Duas consultas separadas: cada juncao
--   com meme_curve_snapshots / meme_features_15s carrega no maximo 200 mints (regra de leitura da VPS).
-- Desfecho: pico de SOL REAL na curva (real_sol_reserves; KB-0098: mcap teorico e' Mayhem), limiares 10/30/85 SOL
--   (85 ~ graduacao), migracao (meme_tokens.migrated_at) e mediana do pico de mcap_sol em meme_features_15s.
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
  SELECT mint, symbol, name, twitter, created_at, migrated_at
  FROM meme_tokens
  WHERE created_at >= date_trunc('day', now() at time zone 'America/Sao_Paulo') at time zone 'America/Sao_Paulo'
    AND created_at <= now()
),
matched AS (
  SELECT DISTINCT t.mint, t.created_at, t.migrated_at
  FROM ev e JOIN tok t
    ON upper(t.symbol) = ANY(e.syms) OR t.name ~* e.rx
    OR (e.handle_rx IS NOT NULL AND t.twitter ~* e.handle_rx)
  WHERE e.ekey <> '8-trustfund'
),
sample_m AS (SELECT mint, created_at, migrated_at, 'casada' AS grp FROM matched ORDER BY md5(mint) LIMIT 200),
hrs AS (SELECT date_trunc('hour', created_at) h, count(*) n FROM sample_m GROUP BY 1),
ctrl AS (
  SELECT x.mint, x.created_at, x.migrated_at, 'controle' AS grp
  FROM (SELECT t.*, row_number() OVER (PARTITION BY date_trunc('hour', t.created_at) ORDER BY md5(t.mint)) rn
        FROM tok t WHERE NOT EXISTS (SELECT 1 FROM matched m WHERE m.mint = t.mint)) x
  JOIN hrs ON hrs.h = date_trunc('hour', x.created_at) AND x.rn <= hrs.n
),
coh AS (SELECT * FROM sample_m UNION ALL SELECT * FROM ctrl),
g AS (SELECT * FROM coh WHERE grp = 'casada'),
peak AS (
  SELECT g.mint, max(s.real_sol_reserves) AS peak_real, max(s.mcap_sol) AS peak_mcap_snap,
         bool_or(s.mayhem_enabled) AS mayhem
  FROM g LEFT JOIN meme_curve_snapshots s ON s.mint = g.mint
   AND s.observed_at >= date_trunc('day', now() at time zone 'America/Sao_Paulo') at time zone 'America/Sao_Paulo'
  GROUP BY 1
),
pk15 AS (
  SELECT g.mint, max(f.mcap_sol) AS peak_mcap_15s
  FROM g LEFT JOIN meme_features_15s f ON f.mint = g.mint
   AND f.as_of >= date_trunc('day', now() at time zone 'America/Sao_Paulo') at time zone 'America/Sao_Paulo'
  GROUP BY 1
)
SELECT 'casada-sem-clones-fundo' AS grupo, count(*) AS n,
       count(*) FILTER (WHERE p.peak_real IS NOT NULL) AS com_fotografia,
       count(*) FILTER (WHERE p.peak_real >= 10) AS ge10,
       count(*) FILTER (WHERE p.peak_real >= 30) AS ge30,
       count(*) FILTER (WHERE p.peak_real >= 85) AS ge85,
       count(*) FILTER (WHERE g.migrated_at IS NOT NULL) AS migraram,
       count(*) FILTER (WHERE p.mayhem) AS mayhem,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY p.peak_real)::numeric, 2) AS mediana_pico_sol_real,
       round(percentile_cont(0.9) WITHIN GROUP (ORDER BY p.peak_real)::numeric, 2) AS p90_pico_sol_real,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY k.peak_mcap_15s)::numeric, 2) AS mediana_pico_mcap_15s
FROM g JOIN peak p ON p.mint = g.mint LEFT JOIN pk15 k ON k.mint = g.mint;
