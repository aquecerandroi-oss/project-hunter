-- R27 q04 — o bit de Mayhem como o codigo o le (t.mayhem_enabled, senao o da foto de curva)
-- nas 4 fotos limpas da Kintsugi, e quando a linha do token foi escrita pela ultima vez.
SET statement_timeout = 120000;
SELECT to_char(f.as_of AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS brt,
  f.snapshot_source, to_char(f.snapshot_observed_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS foto_brt,
  s.mayhem_enabled AS foto_mayhem, s.virtual_sol_reserves, s.virtual_token_reserves,
  t.mayhem_enabled AS token_mayhem, t.mayhem_state,
  to_char(t.updated_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS token_updated_brt,
  to_char(t.first_seen_at AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS first_seen_brt,
  t.first_seen_source
FROM meme_features_15s f JOIN meme_tokens t ON t.mint=f.mint
LEFT JOIN meme_curve_snapshots s ON s.mint=f.mint AND s.observed_at=f.snapshot_observed_at
  AND s.source=f.snapshot_source
WHERE f.mint='BiCp7NhzPJBMFeSaqzUuw6mW93n3uUj6ErreumShpump'
  AND f.as_of BETWEEN timestamptz '2026-09-16 19:19:50+00' AND timestamptz '2026-09-16 19:21:00+00'
ORDER BY f.as_of;

-- quantas fotos de 15 s existem por instante na janela e quando entraram (lag de commit nao
-- e observavel: a tabela nao tem inserted_at; medimos a cadencia do produtor)
SELECT to_char(as_of AT TIME ZONE 'America/Sao_Paulo','HH24:MI:SS') AS brt, count(*) AS fotos
FROM meme_features_15s WHERE as_of BETWEEN timestamptz '2026-09-16 19:19:40+00'
  AND timestamptz '2026-09-16 19:21:10+00' GROUP BY 1 ORDER BY 1;

-- o conjunto operator estava ativo e com clock 15s durante a janela?
SELECT name||'/'||version, status, created_at AT TIME ZONE 'America/Sao_Paulo' AS criado_brt,
  retired_at AT TIME ZONE 'America/Sao_Paulo' AS aposentado_brt, params->>'clock' AS clock
FROM meme_rule_sets ORDER BY created_at DESC LIMIT 8;
