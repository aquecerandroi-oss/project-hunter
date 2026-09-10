-- T3.73 q00 -- QUANTAS DECISOES E DESFECHOS DO SHADOW LAB CAEM EM LINHA `spot`
-- E QUANTAS EM LINHA `perpetual`, POR VERSAO, DESDE 2026-09-01.
-- Contexto: `markets` tem ate duas linhas por simbolo (T3.0b/T3.0c) e o
-- consumidor do strategy-worker avalia a vela que chegar, seja qual for o tipo.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off

-- 1. o universo de `markets`: quantas linhas de cada tipo estao monitoradas
select market_type::text as tipo, count(*) as linhas,
       count(*) filter (where is_monitored) as monitoradas,
       count(distinct symbol) as simbolos
  from markets
 group by 1 order by 1;

-- 2. sinais por tipo de mercado e por versao (todas as coortes), desde 09/01
select s.key || ' ' || sv.version as versao,
       mk.market_type::text as tipo,
       count(*) as sinais,
       count(distinct mk.symbol) as simbolos,
       min(a.emitted_at) as primeiro,
       max(a.emitted_at) as ultimo
  from agent_signals a
  join markets mk           on mk.id = a.market_id
  join strategy_versions sv on sv.id = a.strategy_version_id
  join strategies s         on s.id = sv.strategy_id
 where a.emitted_at >= '2026-09-01 00:00:00+00'
 group by 1, 2
 order by 1, 2;

-- 3. o mesmo agregado, so o total por tipo e por coorte
select coalesce(o.meta->>'cohort', '(sem coorte)') as coorte,
       mk.market_type::text as tipo,
       count(*) as desfechos,
       count(*) filter (where o.tracking_state = 'terminal') as terminais,
       count(*) filter (where o.tracking_state = 'terminal' and o.r_multiple is null) as terminais_sem_r
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
  join markets mk      on mk.id = a.market_id
 where a.emitted_at >= '2026-09-01 00:00:00+00'
 group by 1, 2
 order by 1, 2;

-- 4. desfechos terminais por versao e tipo, com a soma de R
select s.key || ' ' || sv.version as versao,
       mk.market_type::text as tipo,
       count(*) as terminais,
       count(o.r_multiple) as com_r,
       count(*) filter (where o.r_multiple is null) as sem_r,
       round(sum(o.r_multiple), 4) as soma_r
  from signal_outcomes o
  join agent_signals a      on a.id = o.signal_id
  join markets mk           on mk.id = a.market_id
  join strategy_versions sv on sv.id = a.strategy_version_id
  join strategies s         on s.id = sv.strategy_id
 where a.emitted_at >= '2026-09-01 00:00:00+00'
   and o.tracking_state = 'terminal'
 group by 1, 2
 order by 1, 2;

commit;
