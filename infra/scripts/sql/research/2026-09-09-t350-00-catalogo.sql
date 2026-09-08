-- T3.50 Q0 — catalogo de operacoes CONCLUIDAS por versao, para saber o que ha
-- para tracar. SOMENTE LEITURA.
--
-- "Operacao concluida" = signal_outcomes.tracking_state = 'terminal' com
-- r_multiple conhecido: entrou, saiu e o R foi apurado. Sinais 'no_entry',
-- 'censored', 'pending_entry' e 'active' nao tem entrada/saida para desenhar.
begin transaction isolation level repeatable read read only;

select now() as read_at, current_database() as db;

select s.key                                        as strategy,
       sv.version,
       sv.purpose,
       case when o.meta->>'cohort' like 'replay:%' then 'replay'
            when a.supporting_features->>'cohort' like 'replay:%' then 'replay'
            else 'prospective' end                  as coorte,
       count(*)                                     as operacoes,
       count(distinct a.market_id)                  as mercados,
       min(a.emitted_at)                            as primeira,
       max(a.emitted_at)                            as ultima,
       round(avg(o.r_multiple), 4)                  as r_medio
  from signal_outcomes o
  join agent_signals a      on a.id  = o.signal_id
  join strategy_versions sv on sv.id = a.strategy_version_id
  join strategies s         on s.id  = sv.strategy_id
 where o.tracking_state = 'terminal'
   and o.r_multiple is not null
 group by 1, 2, 3, 4
 order by 1, 2, 4;

commit;
