-- R27 q07 — quando o criterio de snipers do conjunto operator mudou de sinal: o contador
-- snipers_above_max (teto baixo, a porta antiga) some e snipers_below_min (piso 21, a porta
-- calibrada) aparece. meme_lab_ticks e o registro por tique; load_active_rule_sets roda a
-- cada tique, entao o contador espelha os params vigentes naquele segundo.
SET statement_timeout = 120000;
SELECT to_char(ticked_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS brt,
  COALESCE(o->>'snipers_above_max','0')::int AS snipers_above_max,
  COALESCE(o->>'snipers_below_min','0')::int AS snipers_below_min,
  COALESCE(o->>'snipers_unknown','0')::int AS snipers_unknown, proposals
FROM (SELECT ticked_at, proposals, (refusals::jsonb)->'operator' AS o FROM meme_lab_ticks
      WHERE ticked_at BETWEEN timestamptz '2026-09-16 19:17:00+00'
        AND timestamptz '2026-09-16 19:45:00+00') q
ORDER BY ticked_at;
