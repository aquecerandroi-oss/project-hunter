-- =====================================================================================
-- T3.34c q01 — o catálogo DEPOIS de `seed.py --only strategies` (trendline_breakout entra)
-- SOMENTE LEITURA · VPS (hunter-postgres-1) · transação `repeatable read read only`
--
-- Serve de metade do "diff do catálogo antes/depois" que o brief §4 exige. A consulta
-- gêmea (q01) é BYTE A BYTE esta, rodada depois da escrita: qualquer diferença entre as
-- duas saídas é, por construção, obra do seed.
--
-- O que se espera ANTES: `trendline_breakout` NÃO existe em `strategies`; existem 6 chaves
-- de família com módulo nesta build e N versões `active`.
-- =====================================================================================
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at, current_database() as db;

-- 1. o catálogo inteiro de famílias (`strategies`), com a contagem de versões de cada uma
select s.key, s.name, s.category,
       count(sv.id)                                              as versoes,
       count(*) filter (where sv.status = 'active')              as ativas,
       count(*) filter (where sv.status = 'draft')               as rascunhos,
       count(*) filter (where sv.activated_at is not null)       as congeladas
  from strategies s
  left join strategy_versions sv on sv.strategy_id = s.id
 group by s.key, s.name, s.category
 order by s.key;

-- 2. toda linha de `strategy_versions` (é o que o seed pode tocar), com o code_ref
select s.key, sv.version, sv.status, sv.purpose, sv.code_ref,
       sv.activated_at,
       substring(sv.changelog from 'params_hash=([0-9a-f]+)') as params_hash,
       case when sv.default_parameters is null then -1
            else (select count(*) from jsonb_object_keys(sv.default_parameters)) end as n_params
  from strategy_versions sv join strategies s on s.id = sv.strategy_id
 order by s.key, sv.version;
commit;
