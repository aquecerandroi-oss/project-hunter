-- R41 16/09 21h32 BRT -- perfil da NOITE (KB-0098 diz que 21-22 BRT e o pico): por hora BRT de hoje,
-- moedas criadas por minuto, moedas na janela do radar por minuto, propostas/h, ordens/h e
-- retratos de risco/h. Janela do radar = idade 30-300 s, prog 2-50 %, fita ok, fluxo > 0, nao-Mayhem.
SET statement_timeout = 200000;

-- (a) moedas criadas por hora BRT (e por minuto)
SELECT to_char(t.created_at AT TIME ZONE $$America/Sao_Paulo$$,$$HH24$$) AS hora_brt,
  count(*) AS moedas, round(count(*)/60.0,1) AS moedas_por_min
FROM meme_tokens t
WHERE t.created_at >= timestamptz $$2026-09-16 00:00-03$$
GROUP BY 1 ORDER BY 1;

-- (b) moedas distintas na janela do radar por hora BRT
WITH j AS (
  SELECT DISTINCT f.mint, date_trunc($$hour$$, f.as_of AT TIME ZONE $$America/Sao_Paulo$$) AS h
  FROM meme_features_15s f JOIN meme_tokens t ON t.mint=f.mint AND t.mayhem_mode IS NULL
  WHERE f.as_of >= timestamptz $$2026-09-16 12:00-03$$
    AND f.age_s BETWEEN 30 AND 300 AND f.curve_progress_pct BETWEEN 0.02 AND 0.50
    AND f.tape_reason IS NULL AND f.net_sol_flow_60s > 0
)
SELECT to_char(h,$$HH24$$) AS hora_brt, count(*) AS moedas_na_janela,
  round(count(*)/60.0,2) AS por_min
FROM j GROUP BY 1 ORDER BY 1;

-- (c) propostas, ordens e retratos por hora BRT
SELECT to_char(p.proposed_at AT TIME ZONE $$America/Sao_Paulo$$,$$HH24$$) AS hora_brt,
  count(*) FILTER (WHERE p.mode=$$live$$) AS propostas_live,
  count(DISTINCT p.mint) FILTER (WHERE p.mode=$$live$$) AS moedas_live,
  count(*) FILTER (WHERE p.mode=$$paper$$) AS propostas_paper
FROM meme_proposals p WHERE p.proposed_at >= timestamptz $$2026-09-16 12:00-03$$
GROUP BY 1 ORDER BY 1;

SELECT to_char(o.received_at AT TIME ZONE $$America/Sao_Paulo$$,$$HH24$$) AS hora_brt,
  count(*) AS ordens, count(*) FILTER (WHERE o.tx_signature IS NOT NULL) AS confirmadas
FROM meme_live_orders o WHERE o.received_at >= timestamptz $$2026-09-16 12:00-03$$
GROUP BY 1 ORDER BY 1;

SELECT to_char(s.observed_at AT TIME ZONE $$America/Sao_Paulo$$,$$HH24$$) AS hora_brt,
  count(*) AS retratos, count(DISTINCT s.mint) AS mints
FROM meme_risk_snapshots s WHERE s.observed_at >= timestamptz $$2026-09-16 12:00-03$$
GROUP BY 1 ORDER BY 1;

-- (d) graduacoes por hora BRT hoje (a cauda que a noite promete)
SELECT to_char(t.completed_at AT TIME ZONE $$America/Sao_Paulo$$,$$HH24$$) AS hora_brt,
  count(*) AS graduadas
FROM meme_tokens t WHERE t.completed_at >= timestamptz $$2026-09-16 00:00-03$$
GROUP BY 1 ORDER BY 1;
