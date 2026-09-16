-- R39 16/09 19h33 BRT -- para CADA ordem do dia, o desfecho da moeda PELA CADEIA nos 30 min
-- seguintes: real_sol_reserves na hora da ordem (ultima foto <= received_at), minimo e maximo
-- da janela, e o INSTANTE da primeira queda de 50 % e da primeira alta de 50 % (a ordem entre
-- os dois e o que decide boa/ruim). Fonte de desfecho = meme_curve_snapshots, nunca mcap_sol
-- nem meme_trades -- KB-0115. A invariante virtual-real = 30 sai junto para conferencia
-- (quebra = Mayhem) e complete = true separa GRADUACAO de esvaziamento.
-- Executado via psql -Atc; $$...$$ no lugar de aspas simples.
SET statement_timeout = 240000;

WITH o AS (
  SELECT o.id, o.received_at, p.mint
  FROM meme_live_orders o JOIN meme_proposals p ON p.id = o.proposal_id
  WHERE o.received_at >= timestamptz $$2026-09-16 11:46-03$$
), ent AS (
  SELECT DISTINCT ON (o.id) o.id, c.real_sol_reserves AS rsol0, c.mcap_sol AS mcap0,
         c.virtual_sol_reserves - c.real_sol_reserves AS inv0, c.observed_at AS t0,
         c.mayhem_enabled AS mh0
  FROM o JOIN meme_curve_snapshots c ON c.mint = o.mint AND c.observed_at <= o.received_at
  ORDER BY o.id, c.observed_at DESC
), w AS (
  SELECT o.id, c.observed_at, c.real_sol_reserves AS rsol, c.mcap_sol, c.complete,
         c.virtual_sol_reserves - c.real_sol_reserves AS inv, c.mayhem_enabled
  FROM o JOIN meme_curve_snapshots c ON c.mint = o.mint
   AND c.observed_at > o.received_at
   AND c.observed_at <= o.received_at + make_interval(mins => 30)
), ag AS (
  SELECT id, count(*) AS n, min(rsol) AS rmin, max(rsol) AS rmax, max(observed_at) AS t_last,
         bool_or(complete) AS graduou, bool_or(mayhem_enabled) AS mayhem,
         min(inv) AS inv_min, max(inv) AS inv_max
  FROM w GROUP BY 1
), ev AS (
  SELECT w.id,
    min(CASE WHEN w.rsol <= 0.5*e.rsol0 THEN w.observed_at END) AS t_queda50,
    min(CASE WHEN w.rsol >= 1.5*e.rsol0 THEN w.observed_at END) AS t_alta50
  FROM w JOIN ent e ON e.id = w.id GROUP BY 1
), lastr AS (
  SELECT DISTINCT ON (id) id, rsol AS r_fim FROM w ORDER BY id, observed_at DESC
)
SELECT to_char(o.received_at AT TIME ZONE $$America/Sao_Paulo$$,$$HH24:MI:SS$$) AS hora_brt,
  coalesce(t.symbol,$$?$$) AS symbol, left(o.mint,6) AS mint6,
  round(e.rsol0,4) AS rsol_na_ordem, round(e.mcap0,2) AS mcap_na_ordem, round(e.inv0,3) AS invariante,
  extract(epoch FROM (o.received_at - e.t0))::int AS idade_da_foto_s,
  coalesce(ag.n,0) AS fotos_30m, round(ag.rmin,4) AS rsol_min_30m, round(ag.rmax,4) AS rsol_max_30m,
  round(l.r_fim,4) AS rsol_fim,
  round(100*(ag.rmin/nullif(e.rsol0,0)-1),1) AS d_min_pct,
  round(100*(ag.rmax/nullif(e.rsol0,0)-1),1) AS d_max_pct,
  coalesce(to_char(ev.t_queda50 AT TIME ZONE $$America/Sao_Paulo$$,$$HH24:MI:SS$$),$$-$$) AS t_queda50,
  coalesce(to_char(ev.t_alta50  AT TIME ZONE $$America/Sao_Paulo$$,$$HH24:MI:SS$$),$$-$$) AS t_alta50,
  coalesce(ag.graduou,false) AS graduou, coalesce(ag.mayhem,false) AS mayhem,
  round(ag.inv_min,3) AS inv_min, round(ag.inv_max,3) AS inv_max,
  -- janela ainda aberta no instante da medicao? (positivo = faltam N s de janela)
  extract(epoch FROM (o.received_at + make_interval(mins => 30) - now()))::int AS janela_restante_s
FROM o LEFT JOIN meme_tokens t ON t.mint = o.mint
       LEFT JOIN ent e ON e.id = o.id LEFT JOIN ag ON ag.id = o.id
       LEFT JOIN ev ON ev.id = o.id LEFT JOIN lastr l ON l.id = o.id
ORDER BY o.received_at;

-- classificacao aplicada sobre esta saida (fora do SQL, pela ordem cronologica dos gatilhos):
--   sem dado = fotos_30m = 0 (nao ocorreu: 58/58 tem cadeia)
--   graduou  = graduou = true (complete; rsol vai a 0 por MIGRACAO, nao por esvaziamento)
--   boa      = t_queda50 existe e vem antes de t_alta50
--   ruim     = t_alta50 existe e vem antes de t_queda50
--   neutra   = nenhum dos dois gatilhos
