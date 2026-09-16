-- R39 16/09 19h33 BRT -- o R que o robo TERIA feito comprando TODAS as 58 ordens recusadas,
-- com a regra de saida da propria mesa (alvo_3x_trailing_35_apos_1_5x_tempo_30m v1):
-- alvo 3x, trailing 35 % armado a partir de 1,5x, tempo 30 min, piso -50 %, taxa 1,75 %/perna.
-- Preco = mcap_sol da foto da cadeia (invariante conferida no q02: 30,000 em todas as linhas
-- antes da graduacao, nenhuma Mayhem no conjunto); entrada na ultima foto <= received_at.
-- Convencao de R identica a do estudo R10: k = 0,9825/1,0175 e R = (mult*k - 1)/(1 - 0,5*k),
-- de modo que o piso -50 % vale exatamente -1,00 R e 3,0x vale +3,67 R.
-- Saida do alvo marcada em 3*mcap0 (ordem limite); piso e trailing marcados no mcap OBSERVADO
-- (conservador: a foto de 15 s ja esta abaixo do gatilho quando ele e visto).
-- gatilho = fim_serie quando a cadeia para de seguir a moeda antes dos 30 min (morte ou fim da
-- leitura): a saida vai na ultima foto disponivel, que e o melhor dado honesto que existe.
SET statement_timeout = 240000;

WITH o AS (
  SELECT o.id, o.received_at, p.mint
  FROM meme_live_orders o JOIN meme_proposals p ON p.id = o.proposal_id
  WHERE o.received_at >= timestamptz $$2026-09-16 11:46-03$$
), ent AS (
  SELECT DISTINCT ON (o.id) o.id, c.mcap_sol AS mcap0
  FROM o JOIN meme_curve_snapshots c ON c.mint = o.mint AND c.observed_at <= o.received_at
  ORDER BY o.id, c.observed_at DESC
), w AS (
  SELECT o.id, c.observed_at, c.mcap_sol, c.complete,
         max(c.mcap_sol) OVER (PARTITION BY o.id ORDER BY c.observed_at) AS peak
  FROM o JOIN meme_curve_snapshots c ON c.mint = o.mint
   AND c.observed_at > o.received_at
   AND c.observed_at <= o.received_at + make_interval(mins => 30)
), tg AS (
  SELECT DISTINCT ON (w.id) w.id, w.observed_at AS t_saida, w.peak,
    CASE WHEN w.mcap_sol >= 3*e.mcap0 THEN $$alvo3x$$
         WHEN w.mcap_sol <= 0.5*e.mcap0 THEN $$piso50$$
         ELSE $$trailing35$$ END AS gatilho,
    CASE WHEN w.mcap_sol >= 3*e.mcap0 THEN 3*e.mcap0 ELSE w.mcap_sol END AS mcap_saida
  FROM w JOIN ent e ON e.id = w.id
  WHERE w.mcap_sol >= 3*e.mcap0
     OR w.mcap_sol <= 0.5*e.mcap0
     OR (w.peak >= 1.5*e.mcap0 AND w.mcap_sol <= 0.65*w.peak)
  ORDER BY w.id, w.observed_at
), fim AS (
  SELECT DISTINCT ON (id) id, observed_at, mcap_sol, peak FROM w ORDER BY id, observed_at DESC
), sim AS (
  SELECT o.id, o.mint, o.received_at, e.mcap0,
    coalesce(tg.gatilho,$$fim_serie$$) AS gatilho,
    coalesce(tg.mcap_saida, f.mcap_sol) AS mcap_saida,
    coalesce(tg.t_saida, f.observed_at) AS t_saida, f.peak AS peak_30m
  FROM o JOIN ent e ON e.id = o.id
       LEFT JOIN tg ON tg.id = o.id LEFT JOIN fim f ON f.id = o.id
)
SELECT to_char(s.received_at AT TIME ZONE $$America/Sao_Paulo$$,$$HH24:MI:SS$$) AS hora_brt,
  coalesce(t.symbol,$$?$$) AS symbol, left(s.mint,6) AS mint6,
  round(s.mcap0,2) AS mcap_entrada, round(s.peak_30m,2) AS mcap_pico_30m,
  round(s.peak_30m/s.mcap0,2) AS multiplo_pico, s.gatilho, round(s.mcap_saida,2) AS mcap_saida,
  round(s.mcap_saida/s.mcap0,4) AS mult,
  extract(epoch FROM (s.t_saida - s.received_at))::int AS seg_ate_saida,
  round(((s.mcap_saida/s.mcap0)*(0.9825/1.0175) - 1)/(1 - 0.5*(0.9825/1.0175)), 3) AS r
FROM sim s LEFT JOIN meme_tokens t ON t.mint = s.mint
ORDER BY s.received_at;
