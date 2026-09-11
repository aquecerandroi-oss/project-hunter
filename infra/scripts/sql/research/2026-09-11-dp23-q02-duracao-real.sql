-- D-P23 q02 -- QUANTO TEMPO a operacao REAL ficou aberta, nas duas coortes.
--
-- Por que este arquivo existe. A curva do q01 e um MTM **sem stop e sem alvo**:
-- ela responde "quanto o preco andou depois da entrada", que e exatamente o que
-- o brief pede. Mas o ponto de +240 min e, para a maioria das decisoes, um
-- CONTRAFACTUAL -- a operacao de verdade ja tinha saido por stop, alvo ou
-- horizonte muito antes. Sem esta tabela, a curva seria lida como "o que a
-- versao ganhou ao longo do tempo", que ela nao e.
--
-- `duracao_min` = (`exit_ts` - `entry_ts`) em minutos. `entry_ts` e o `open_time`
-- da barra de entrada (`walker.py:42`) e `exit_ts` e o instante do desfecho
-- terminal. Percentis por `percentile_cont` (interpolacao linear -- a mesma
-- convencao do `numpy.percentile` usada no Python, para que as duas leituras
-- sejam comparaveis).
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';

\echo '== §1 duracao real da operacao (minutos) =='
with d as (
  select o.meta->>'cohort'                                            as coorte,
         s.key || ' ' || sv.version                                   as versao,
         coalesce(o.meta->'progress'->>'result', '')                   as saida,
         extract(epoch from (o.exit_ts - o.entry_ts)) / 60.0           as duracao_min
    from signal_outcomes o
    join agent_signals a      on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id = sv.strategy_id
   where o.meta->>'cohort' in ('replay:fa005985-0b55-4820-904c-8ada589e441c',
                               'replay:92c8d080-6009-4a59-9868-31282b1bd493')
     and o.tracking_state::text = 'terminal'
)
select versao,
       count(*)                                                       as n,
       round(avg(duracao_min), 2)                                     as media_min,
       round(percentile_cont(0.25) within group (order by duracao_min)::numeric, 2) as p25,
       round(percentile_cont(0.50) within group (order by duracao_min)::numeric, 2) as p50,
       round(percentile_cont(0.75) within group (order by duracao_min)::numeric, 2) as p75,
       max(duracao_min)                                               as maximo,
       count(*) filter (where duracao_min >  80)                      as aberta_apos_80,
       count(*) filter (where duracao_min >= 240)                     as aberta_em_240
  from d
 group by versao order by versao;

\echo '== §2 por desfecho real =='
with d as (
  select s.key || ' ' || sv.version                                   as versao,
         coalesce(o.meta->'progress'->>'result', '')                   as saida,
         extract(epoch from (o.exit_ts - o.entry_ts)) / 60.0           as duracao_min
    from signal_outcomes o
    join agent_signals a      on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id = sv.strategy_id
   where o.meta->>'cohort' in ('replay:fa005985-0b55-4820-904c-8ada589e441c',
                               'replay:92c8d080-6009-4a59-9868-31282b1bd493')
     and o.tracking_state::text = 'terminal'
)
select versao, saida, count(*) as n,
       round(percentile_cont(0.50) within group (order by duracao_min)::numeric, 2) as p50_min
  from d group by 1, 2 order by 1, 3 desc;

commit;
