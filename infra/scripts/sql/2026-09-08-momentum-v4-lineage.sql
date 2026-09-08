-- Pendência operacional 2026-09-08 (T3.26 concern 1, nota obsidian/00-INBOX/2026-09-08-linhagem-...):
-- a imagem da VPS anterior a `keep_lineage` apagou o prefixo `derived_from=v2` do changelog de
-- momentum v4 ao ativar. Idempotente: o AND impede repetir. Rodar na VPS, em /opt/project-hunter:
--   docker exec -i hunter-postgres-1 psql -U hunter -d hunter -At < infra/scripts/sql/2026-09-08-momentum-v4-lineage.sql
select strategy_key, version, status, purpose, left(changelog, 90) as antes
  from strategy_versions where id = '44d106b6-bb87-40a7-85e4-fa3cb80c8060';
UPDATE strategy_versions
   SET changelog = 'variante de v2 | derived_from=v2 | overrides=atr_pct_min=0.0089 '
                || '| params_hash=46635ed2bff2 | ' || changelog
 WHERE id = '44d106b6-bb87-40a7-85e4-fa3cb80c8060'
   AND changelog NOT LIKE 'variante de v%';
select strategy_key, version, left(changelog, 140) as depois
  from strategy_versions where id = '44d106b6-bb87-40a7-85e4-fa3cb80c8060';
