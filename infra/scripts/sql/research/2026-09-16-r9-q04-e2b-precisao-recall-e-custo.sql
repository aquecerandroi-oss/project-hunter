-- R9/Q04 (KB-0103) — matriz de confusao das regras candidatas contra o ROTULO da fita.
-- ROTULO (escrito antes de olhar as regras): entre as graduadas de 14-16/09 (BRT) com cobertura de
--   meme_trades e >= 20 SOL comprados ate encher,
--     forjada  = <= 30 compradores unicos distintos na subida;
--     organica = >= 100 compradores unicos distintos (a faixa 31-99 fica de fora, cinza).
-- CUSTO = quantas organicas a regra recusaria.
SET statement_timeout = 240000;
WITH g AS (
  SELECT t.mint, upper(t.symbol) AS sym, t.creator, t.created_at, t.completed_at,
         (t.twitter IS NULL AND t.website IS NULL) AS sem_social,
         (extract(epoch FROM t.completed_at - t.created_at) <= 60) AS encheu_em_60s
  FROM meme_tokens t
  WHERE t.created_at >= (date '2026-09-14' AT TIME ZONE 'America/Sao_Paulo')
    AND t.created_at <  (date '2026-09-17' AT TIME ZONE 'America/Sao_Paulo')
    AND t.completed_at IS NOT NULL
),
ped AS (  -- pedigree v1 replicado: creator_serial e symbol_clone
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
  SELECT mint, count(*) AS compradores, sum(sol) AS sol_comprado, max(sol) / nullif(sum(sol), 0) AS fatia_do_maior
  FROM tr GROUP BY 1 HAVING sum(sol) >= 20
),
base AS (
  SELECT g.*, p.cr1h, p.sd24, f.compradores, f.sol_comprado, f.fatia_do_maior,
         CASE WHEN f.compradores <= 30 THEN 'forjada' WHEN f.compradores >= 100 THEN 'organica' ELSE 'cinza' END AS rotulo,
         EXISTS (SELECT 1 FROM meme_features_15s s WHERE s.mint = g.mint) AS tem_15s
  FROM g JOIN ped p ON p.mint = g.mint JOIN fita f ON f.mint = g.mint
),
aval AS (
  SELECT r.nome, b.rotulo, r.hit
  FROM base b
  CROSS JOIN LATERAL (VALUES
    ('A. E2 hoje: creator_serial (cr1h>=2) OR symbol_clone (sd24>=3)', (b.cr1h >= 2 OR b.sd24 >= 3)),
    ('B. so sem twitter/website',                                      b.sem_social),
    ('C. so >= 2 moedas do mesmo simbolo em 24 h',                     (b.sd24 >= 2)),
    ('D. so encheu <= 60 s do mint',                                   b.encheu_em_60s),
    ('E. so maior comprador >= 20 % do SOL da subida',                 (b.fatia_do_maior >= 0.20)),
    ('F. so nunca teve serie de 15 s',                                 (NOT b.tem_15s)),
    ('G. E2-b = D OR (maior comprador >= 35 %)',                       (b.encheu_em_60s OR b.fatia_do_maior >= 0.35)),
    ('H. E2-b estreita = D OR F',                                      (b.encheu_em_60s OR NOT b.tem_15s))
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
