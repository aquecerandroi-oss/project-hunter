-- R12/Q03 (KB-0104) — (a) decomposicao da perna F (o radar nunca a viu subir) e (b) o que muda nas decisoes.
SET statement_timeout = 60000;
-- (a) Perna F separada: "nenhuma linha de 15 s" (cobertura) x "tem linhas de 15 s, todas >= 0,9" (viu so cheia).
WITH g AS (
  SELECT t.mint, t.created_at, t.completed_at,
         (t.created_at AT TIME ZONE 'America/Sao_Paulo')::date AS dia_brt
  FROM meme_tokens t
  WHERE t.created_at >= (date '2026-09-12' AT TIME ZONE 'America/Sao_Paulo')
    AND t.created_at <  (date '2026-09-17' AT TIME ZONE 'America/Sao_Paulo')
    AND t.completed_at IS NOT NULL AND coalesce(t.mayhem_enabled, false) = false
), lab AS (
  SELECT g.*,
    (g.completed_at - g.created_at <= interval '60 seconds') AS d60,
    (SELECT count(*) FROM meme_features_15s f
      WHERE f.mint = g.mint AND f.as_of >= g.created_at AND f.as_of <= g.completed_at) AS linhas_15s,
    (SELECT count(*) FROM meme_features_15s f
      WHERE f.mint = g.mint AND f.as_of >= g.created_at AND f.as_of <= g.completed_at
        AND f.curve_progress_pct IS NOT NULL AND f.curve_progress_pct < 0.9) AS linhas_subida
  FROM g
)
SELECT 'a_perna_f' AS bloco, dia_brt::text AS k1, count(*)::text AS graduadas,
  count(*) FILTER (WHERE d60)::text AS d60,
  count(*) FILTER (WHERE linhas_15s = 0)::text AS sem_nenhuma_linha_15s,
  count(*) FILTER (WHERE linhas_15s > 0 AND linhas_subida = 0)::text AS so_linhas_ge_09,
  count(*) FILTER (WHERE NOT d60 AND linhas_subida = 0)::text AS f_sem_d60,
  count(*) FILTER (WHERE d60 AND linhas_subida > 0)::text AS d60_mas_viu_subir
FROM lab GROUP BY 1,2 ORDER BY 2;

-- (b) T4.29b: os minutos-moeda que admitem 0,25 SOL vivem acima de 53,1 % de progresso. Quantos deles pertencem
--     a moedas graduadas nascidas cheias? (dia BRT 15/09, nao-Mayhem, idade 0-30 min, na curva — mesmo recorte do estudo)
WITH m AS (
  SELECT f.mint, f.end_time, f.curve_progress_pct
  FROM meme_features_1m f
  WHERE f.end_time >= (date '2026-09-15' AT TIME ZONE 'America/Sao_Paulo')
    AND f.end_time <  (date '2026-09-16' AT TIME ZONE 'America/Sao_Paulo')
    AND f.age_minutes <= 30 AND f.curve_progress_pct >= 0.531 AND f.curve_progress_pct < 1.0
), j AS (
  SELECT m.*, t.created_at, t.completed_at,
         (t.completed_at IS NOT NULL AND t.completed_at - t.created_at <= interval '60 seconds') AS d60
  FROM m JOIN meme_tokens t ON t.mint = m.mint AND coalesce(t.mayhem_enabled, false) = false
)
SELECT 'b_t429b' AS bloco, '2026-09-15' AS k1, count(*)::text AS minutos_moeda_ge_531,
  count(DISTINCT mint)::text AS moedas,
  count(*) FILTER (WHERE d60)::text AS minutos_de_nascidas_cheias,
  count(DISTINCT mint) FILTER (WHERE d60)::text AS moedas_nascidas_cheias,
  '' , ''
FROM j;
