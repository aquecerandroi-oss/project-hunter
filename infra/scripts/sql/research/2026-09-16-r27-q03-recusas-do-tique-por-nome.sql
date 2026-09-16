-- R27 q03 — o contador de recusas do conjunto operator, tique a tique, na janela em que
-- Kintsugi (16:20:00-16:20:49), Grammuh (16:33:04-16:33:21) e HANNAH (16:38:51) estavam
-- limpas na porta. meme_lab_ticks.refusals e o mesmo dicionario do heartbeat.
SET statement_timeout = 240000;
SELECT to_char(ticked_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS brt,
       rows_evaluated, proposals, e.k AS recusa, e.v::int AS n
FROM meme_lab_ticks t, jsonb_each_text(COALESCE((t.refusals::jsonb)->'operator','{}'::jsonb)) AS e(k,v)
WHERE ticked_at >= timestamptz '2026-09-16 19:19:40+00' AND ticked_at <= timestamptz '2026-09-16 19:21:20+00'
ORDER BY ticked_at, e.v::int DESC;

-- as recusas de pedigree/identidade em toda a mesa (16:17-17:02), somadas
SELECT e.k AS recusa, sum(e.v::int) AS total, count(*) AS tiques
FROM meme_lab_ticks t, jsonb_each_text(COALESCE((t.refusals::jsonb)->'operator','{}'::jsonb)) AS e(k,v)
WHERE ticked_at >= timestamptz '2026-09-16 19:17:00+00' AND ticked_at <= timestamptz '2026-09-16 20:02:00+00'
  AND e.k IN ('pedigree_unknown','creator_unknown','symbol_unknown','creator_serial','symbol_clone',
              'creator_repeat_dumper','already_open','no_snapshot_for_quote','e2b_top_buyer_unknown')
GROUP BY e.k ORDER BY total DESC;

-- toda proposta, de qualquer conjunto, para as tres moedas
SELECT p.mint, rs.name||'/'||rs.version AS conjunto, p.status,
  to_char(p.proposed_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS brt,
  to_char(p.features_end_time AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS foto_brt
FROM meme_proposals p JOIN meme_rule_sets rs ON rs.id=p.rule_set_id
WHERE p.mint IN ('BiCp7NhzPJBMFeSaqzUuw6mW93n3uUj6ErreumShpump',
                 'FLz2Hvyi6mKracWNxo1tRsA9P1Ge7izjNd6ZKXco686M',
                 'DgFP1AyHaBEpxqw2dE8SsADDw7oLxMaFd26mC6Y5FngP')
ORDER BY p.proposed_at;
