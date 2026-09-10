-- T3.73 q01 -- POR QUE OS DESFECHOS EM LINHA `spot` SAEM SEM R, E QUANTA
-- DUPLICACAO (spot + perpetuo do mesmo simbolo na mesma barra) EXISTE.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off

-- 1. motivo de R nulo por tipo de mercado (coorte prospectiva, terminais)
select mk.market_type::text as tipo,
       coalesce(o.meta->>'r_net_reason', '(sem motivo)') as motivo,
       count(*) as desfechos,
       count(o.r_multiple) as com_r
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
  join markets mk      on mk.id = a.market_id
 where o.meta->>'cohort' = 'prospective'
   and o.tracking_state = 'terminal'
   and a.emitted_at >= '2026-09-01 00:00:00+00'
 group by 1, 2
 order by 1, 3 desc;

-- 2. existe alguma linha de funding para um mercado spot?
select mk.market_type::text as tipo, count(*) as linhas_funding,
       count(distinct f.market_id) as mercados
  from funding_rates f
  join markets mk on mk.id = f.market_id
 group by 1 order by 1;

-- 3. quando as linhas spot entraram no Lab (por dia UTC de decisao)
select date_trunc('day', a.emitted_at)::date as dia,
       count(*) filter (where mk.market_type = 'spot')      as sinais_spot,
       count(*) filter (where mk.market_type = 'perpetual') as sinais_perp,
       count(distinct mk.symbol) filter (where mk.market_type = 'spot') as simbolos_spot
  from agent_signals a
  join markets mk on mk.id = a.market_id
 where a.emitted_at >= '2026-09-01 00:00:00+00'
 group by 1 order by 1;

-- 4. duplicacao: mesma (versao, simbolo, barra de observacao) decidida nas
--    DUAS linhas de markets -- a "aposta" contada duas vezes
with dec as (
  select a.strategy_version_id, mk.symbol, mk.market_type::text as tipo,
         (a.supporting_features->>'observation_ts')::timestamptz as barra
    from agent_signals a
    join markets mk on mk.id = a.market_id
   where a.emitted_at >= '2026-09-01 00:00:00+00'
     and mk.symbol in (select symbol from markets group by symbol having count(*) > 1)
)
select count(*) as pares_versao_simbolo_barra_nos_dois_tipos
  from (select strategy_version_id, symbol, barra
          from dec group by 1,2,3 having count(distinct tipo) = 2) x;

-- 5. os pares em detalhe (ate 40)
with dec as (
  select s.key || ' ' || sv.version as versao, mk.symbol, mk.market_type::text as tipo,
         (a.supporting_features->>'observation_ts')::timestamptz as barra
    from agent_signals a
    join markets mk           on mk.id = a.market_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id = sv.strategy_id
   where a.emitted_at >= '2026-09-01 00:00:00+00'
)
select versao, symbol, barra, count(distinct tipo) as tipos
  from dec group by 1,2,3 having count(distinct tipo) = 2
 order by barra desc limit 40;

commit;
