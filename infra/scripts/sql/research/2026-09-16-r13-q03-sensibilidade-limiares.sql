-- R13/Q03 (KB-0105) — sensibilidade dos dois limiares da E2-b, UM DIA POR VEZ:
--   "maior comprador >= 25/35/45 % do SOL da subida" x "encheu <= 30/60/120 s do mint",
-- cada perna sozinha e as nove combinacoes (OR). Mesmo rotulo de fita da Q01/Q02.
SET statement_timeout = 240000;
WITH g AS (
  SELECT t.mint, upper(t.symbol) AS sym, t.creator, t.created_at, t.completed_at,
         (t.twitter IS NULL AND t.website IS NULL) AS sem_social,
         extract(epoch FROM t.completed_at - t.created_at) AS s_ate_encher
  FROM meme_tokens t
  WHERE t.created_at >= timestamptz '2026-09-12 00:00:00-03'
    AND t.created_at <  timestamptz '2026-09-13 00:00:00-03'
    AND t.completed_at IS NOT NULL
),
ped AS (
  SELECT g.mint,
         (SELECT count(*) FROM meme_tokens o WHERE o.creator = g.creator AND o.mint <> g.mint
            AND o.created_at >= g.created_at - interval '1 hour' AND o.created_at < g.created_at) AS cr1h,
         (SELECT count(*) FROM meme_tokens o WHERE upper(o.symbol) = g.sym AND o.mint <> g.mint
            AND o.created_at >= g.created_at - interval '24 hours' AND o.created_at < g.created_at) AS sd24
  FROM g
),
tr AS (
  SELECT g.mint, tr.trader, sum(tr.sol_lamports) / 1e9 AS sol
  FROM g JOIN meme_trades tr ON tr.mint = g.mint AND tr.side = 'buy'
   AND tr.block_time >= g.created_at - interval '1 minute'
   AND tr.block_time <= g.completed_at + interval '1 minute'
  GROUP BY 1, 2
),
fita AS (
  SELECT mint, count(*) AS compradores, sum(sol) AS sol_comprado,
         max(sol) / nullif(sum(sol), 0) AS fatia_do_maior
  FROM tr GROUP BY 1 HAVING sum(sol) >= 20
),
base AS (
  SELECT g.*, p.cr1h, p.sd24, f.compradores, f.fatia_do_maior,
         CASE WHEN f.compradores <= 30 THEN 'forjada'
              WHEN f.compradores >= 100 THEN 'organica' ELSE 'cinza' END AS rotulo,
         EXISTS (SELECT 1 FROM meme_features_15s s WHERE s.mint = g.mint) AS tem_15s
  FROM g JOIN ped p ON p.mint = g.mint JOIN fita f ON f.mint = g.mint
),
grade AS (
  SELECT b.rotulo, s.seg, c.frac,
         (b.s_ate_encher <= s.seg) AS hit_s,
         (b.fatia_do_maior >= c.frac) AS hit_c
  FROM base b
  CROSS JOIN (VALUES (30), (60), (120)) AS s(seg)
  CROSS JOIN (VALUES (0.25), (0.35), (0.45)) AS c(frac)
)
SELECT 'so encheu <= ' || seg || ' s' AS regra, seg AS param_s, NULL::numeric AS param_conc,
       count(*) FILTER (WHERE rotulo = 'forjada' AND hit_s) AS tp,
       count(*) FILTER (WHERE rotulo = 'organica' AND hit_s) AS fp_custo,
       round(100.0 * count(*) FILTER (WHERE rotulo = 'forjada' AND hit_s)
             / nullif(count(*) FILTER (WHERE rotulo = 'forjada'), 0), 1) AS recall_pct,
       round(100.0 * count(*) FILTER (WHERE rotulo = 'forjada' AND hit_s)
             / nullif(count(*) FILTER (WHERE rotulo <> 'cinza' AND hit_s), 0), 1) AS precisao_pct,
       round(100.0 * count(*) FILTER (WHERE rotulo = 'organica' AND hit_s)
             / nullif(count(*) FILTER (WHERE rotulo = 'organica'), 0), 1) AS custo_pct_organicas
FROM grade WHERE frac = 0.25 GROUP BY seg
UNION ALL
SELECT 'so maior comprador >= ' || (100 * frac)::int || ' %', NULL, frac,
       count(*) FILTER (WHERE rotulo = 'forjada' AND hit_c),
       count(*) FILTER (WHERE rotulo = 'organica' AND hit_c),
       round(100.0 * count(*) FILTER (WHERE rotulo = 'forjada' AND hit_c)
             / nullif(count(*) FILTER (WHERE rotulo = 'forjada'), 0), 1),
       round(100.0 * count(*) FILTER (WHERE rotulo = 'forjada' AND hit_c)
             / nullif(count(*) FILTER (WHERE rotulo <> 'cinza' AND hit_c), 0), 1),
       round(100.0 * count(*) FILTER (WHERE rotulo = 'organica' AND hit_c)
             / nullif(count(*) FILTER (WHERE rotulo = 'organica'), 0), 1)
FROM grade WHERE seg = 60 GROUP BY frac
UNION ALL
SELECT 'E2-b: <= ' || seg || ' s OR >= ' || (100 * frac)::int || ' %', seg, frac,
       count(*) FILTER (WHERE rotulo = 'forjada' AND (hit_s OR hit_c)),
       count(*) FILTER (WHERE rotulo = 'organica' AND (hit_s OR hit_c)),
       round(100.0 * count(*) FILTER (WHERE rotulo = 'forjada' AND (hit_s OR hit_c))
             / nullif(count(*) FILTER (WHERE rotulo = 'forjada'), 0), 1),
       round(100.0 * count(*) FILTER (WHERE rotulo = 'forjada' AND (hit_s OR hit_c))
             / nullif(count(*) FILTER (WHERE rotulo <> 'cinza' AND (hit_s OR hit_c)), 0), 1),
       round(100.0 * count(*) FILTER (WHERE rotulo = 'organica' AND (hit_s OR hit_c))
             / nullif(count(*) FILTER (WHERE rotulo = 'organica'), 0), 1)
FROM grade GROUP BY seg, frac
ORDER BY 1;
