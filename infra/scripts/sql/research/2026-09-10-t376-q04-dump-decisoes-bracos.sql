-- T3.76 q04 -- DUMP por decisao (CSV) dos bracos da EXP-0026 e do controle.
-- Irmao do `2026-09-10-t362b-q11-dump-decisoes.sql`, com tres colunas a mais:
--   `barra`  = `source_bar_close` (o `observation_ts` do envelope) -- e a chave
--              do pareamento por (mercado, barra) da condicao 5 da regra de
--              sucesso;
--   `rotulo` = o rotulo horario do BTC que o portao usaria nessa barra (ultima
--              hora FECHADA antes do corte, `end_time <= source_bar_close`);
--   `versao` = `<key> <version>`, porque ha `v11` em duas familias.
-- Coortes: os tres bracos novos (v15/v16/v17), o controle pre-declarado da
-- `mean_reversion` (`replay:c7d138eb-...`, T3.62b) e o braco `momentum v11`.
-- Eixo `r_exf`; `r_net` sai junto para quem quiser conferir a perna de funding.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset format unaligned
\pset fieldsep ','
\pset tuples_only off

select s.key || ' ' || sv.version                            as versao,
       (a.emitted_at at time zone 'UTC')::date               as dia,
       mk.symbol                                             as mercado,
       (mk.symbol in ('ETHUSDT','SOLUSDT','XRPUSDT','DOGEUSDT')) as original,
       case when a.emitted_at <  timestamptz '2026-07-12' then 'J1'
            when a.emitted_at <  timestamptz '2026-08-11' then 'J2'
            else 'J3' end                                    as janela,
       (a.supporting_features->>'observation_ts')            as barra,
       coalesce(g.regime::text, 'sem_linha')                 as rotulo,
       round((o.meta->>'r_ex_funding')::numeric, 6)          as r_exf,
       coalesce(round(o.r_multiple, 6)::text, '')            as r_net,
       round(((o.meta->'progress'->>'exit_base')::numeric
              - (o.meta->'progress'->>'entry')::numeric/1.0006)
             / nullif((o.meta->'excursions'->>'initial_risk')::numeric,0), 6) as r_bruto,
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
 where o.meta->>'cohort' in ('replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3',
                             'replay:3271f431-10f3-4fad-81f5-8fb96fa6bfac',
                             'replay:309144d2-c89b-4f1a-b417-c04f1c49df3c',
                             'replay:095d4772-d133-47de-82cb-189dc78bbade',
                             'replay:70f55430-2752-48d8-93db-3941d3b31bf8')
   and o.tracking_state::text = 'terminal'
   and (o.meta->>'r_ex_funding') is not null
 order by 1, a.emitted_at;

commit;
