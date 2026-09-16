-- R13/Q02 (KB-0105) — matriz de confusao das regras contra o ROTULO da fita, UM DIA POR VEZ.
-- Mesmas regras de 2026-09-16-r9-q04 (A..H), para replicar 12/09 e 13/09 fora da amostra do R9.
-- CUSTO = quantas organicas a regra recusaria. Limites do dia BRT em timestamptz explicito.
SET statement_timeout = 240000;
WITH g AS (
  SELECT t.mint, upper(t.symbol) AS sym, t.creator, t.created_at, t.completed_at,
         (t.twitter IS NULL AND t.website IS NULL) AS sem_social,
         (extract(epoch FROM t.completed_at - t.created_at) <= 60) AS encheu_em_60s
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
aval AS (
  SELECT r.nome, b.rotulo, r.hit
  FROM base b
  CROSS JOIN LATERAL (VALUES
    ('A. E2 hoje: cr1h>=2 OR sd24>=3',        (b.cr1h >= 2 OR b.sd24 >= 3)),
    ('B. so sem twitter/website',              b.sem_social),
    ('C. so sd24>=2',                          (b.sd24 >= 2)),
    ('D. so encheu <= 60 s do mint',           b.encheu_em_60s),
    ('E. so maior comprador >= 20 %',          (b.fatia_do_maior >= 0.20)),
    ('F. so nunca teve serie de 15 s',         (NOT b.tem_15s)),
    ('G. E2-b = D OR maior comprador >= 35 %', (b.encheu_em_60s OR b.fatia_do_maior >= 0.35)),
    ('H. E2-b estreita = D OR F',              (b.encheu_em_60s OR NOT b.tem_15s))
  ) AS r(nome, hit)
)
SELECT nome,
       count(*) FILTER (WHERE rotulo = 'forjada'  AND hit) AS tp,
       count(*) FILTER (WHERE rotulo = 'forjada'  AND NOT hit) AS fn,
       count(*) FILTER (WHERE rotulo = 'organica' AND hit) AS fp_custo,
       count(*) FILTER (WHERE rotulo = 'organica' AND NOT hit) AS tn,
       round(100.0 * count(*) FILTER (WHERE rotulo = 'forjada' AND hit)
             / nullif(count(*) FILTER (WHERE rotulo = 'forjada'), 0), 1) AS recall_pct,
       round(100.0 * count(*) FILTER (WHERE rotulo = 'forjada' AND hit)
             / nullif(count(*) FILTER (WHERE rotulo <> 'cinza' AND hit), 0), 1) AS precisao_pct,
       round(100.0 * count(*) FILTER (WHERE rotulo = 'organica' AND hit)
             / nullif(count(*) FILTER (WHERE rotulo = 'organica'), 0), 1) AS custo_pct_organicas
FROM aval GROUP BY nome ORDER BY nome;
