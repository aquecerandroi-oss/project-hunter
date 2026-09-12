-- T3.89 q11 -- DUMP por decisao (CSV) do pai (v10, cortado no inicio de breadth_v2,
-- 2026-06-14) e dos dois bracos (v18/v19), com a chave de pareamento por
-- (mercado, barra) e o rotulo de regime_hourly_v1 para a clausula de
-- falsificacao (cortar o pai por regime em vez de breadth_v2).
-- Irmao de `2026-09-10-t376-q04-dump-decisoes-bracos.sql`.
-- Eixo `r_exf`; `r_net` sai junto para conferencia. SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset format unaligned
\pset fieldsep ','
\pset tuples_only off

select s.key || ' ' || sv.version                            as versao,
       (a.emitted_at at time zone 'UTC')::date               as dia,
       mk.symbol                                             as mercado,
       case when a.emitted_at <  timestamptz '2026-07-14' then 'J1'
            when a.emitted_at <  timestamptz '2026-08-13' then 'J2'
            else 'J3' end                                    as janela,
       (a.supporting_features->>'observation_ts')            as barra,
       coalesce(g.regime::text, 'sem_linha')                 as rotulo,
       round((o.meta->>'r_ex_funding')::numeric, 6)          as r_exf,
       coalesce(round(o.r_multiple, 6)::text, '')            as r_net,
       (a.supporting_features->'atr'->>'percent')            as atr_pct,
       round((o.meta->'excursions'->>'initial_risk')::numeric
             / nullif((o.meta->'progress'->>'entry')::numeric,0), 6)          as risco_pct
  from signal_outcomes o
  join agent_signals a       on a.id = o.signal_id
  join strategy_versions sv  on sv.id = a.strategy_version_id
  join strategies s          on s.id = sv.strategy_id
  join markets mk            on mk.id = a.market_id
  left join lateral (
    select r.regime from market_regimes r
     where r.scope = 'btc' and r.classifier_version = 'regime_hourly_v1'
       and r.end_time <= (a.supporting_features->>'observation_ts')::timestamptz
     order by r.start_time desc limit 1
  ) g on true
 where (o.meta->>'cohort' in ('replay:f2c44f18-5f63-435f-97bb-5f5aaf31cea7',
                              'replay:a94701c9-3459-463e-8922-c1403e91d60a')
        or (o.meta->>'cohort' = 'replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3'
            and a.emitted_at >= timestamptz '2026-06-14'))
   and o.tracking_state::text = 'terminal'
   and (o.meta->>'r_ex_funding') is not null
 order by 1, a.emitted_at;

commit;
