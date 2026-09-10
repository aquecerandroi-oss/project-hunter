-- T3.62b q11 -- DUMP por decisao (CSV) das tres coortes, para o bootstrap de
-- blocos de dia rodar localmente em NumPy (`.claude/state/exp-drafts/t362b/`).
-- Por que dump e nao bootstrap em SQL: o bloco e o DIA INTEIRO -- reamostrar
-- dias com reposicao 20 000 vezes e um laco, nao uma agregacao, e faze-lo em
-- SQL custaria uma sessao longa no banco de producao por nenhum ganho.
--
-- Uma linha por desfecho terminal. `r_exf` (sem funding) e o eixo, porque
-- `r_net` so existe onde ha `funding_rates` (>= 2026-08-08 16:00 UTC) e usar
-- so ele reduziria a leitura de 90 d a agosto+setembro de novo -- ver o
-- cabecalho do q10. O arrasto medido de funding onde ele e conhecido e
-- -0,0011 R na v10 (q10 secao 6), ou seja, os dois eixos praticamente coincidem.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset format unaligned
\pset fieldsep ','
\pset tuples_only off

select sv.version                                            as versao,
       (a.emitted_at at time zone 'UTC')::date               as dia,
       mk.symbol                                             as mercado,
       (mk.symbol in ('ETHUSDT','SOLUSDT','XRPUSDT','DOGEUSDT')) as original,
       case when a.emitted_at <  timestamptz '2026-07-12' then 'J1'
            when a.emitted_at <  timestamptz '2026-08-11' then 'J2'
            else 'J3' end                                    as janela,
       round((o.meta->>'r_ex_funding')::numeric, 6)          as r_exf,
       coalesce(round(o.r_multiple, 6)::text, '')            as r_net,
       round(((o.meta->'progress'->>'exit_base')::numeric
              - (o.meta->'progress'->>'entry')::numeric/1.0006)
             / nullif((o.meta->'excursions'->>'initial_risk')::numeric,0), 6) as r_bruto,
       round((o.meta->'excursions'->>'initial_risk')::numeric
             / nullif((o.meta->'progress'->>'entry')::numeric,0), 6)          as risco_pct,
       coalesce(round((a.supporting_features->'atr'->>'percent')::numeric,6)::text,'') as atr_pct
  from signal_outcomes o
  join agent_signals a       on a.id = o.signal_id
  join strategy_versions sv  on sv.id = a.strategy_version_id
  join markets mk            on mk.id = a.market_id
 where o.meta->>'cohort' in ('replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3',
                             'replay:fa005985-0b55-4820-904c-8ada589e441c',
                             'replay:da706026-319a-451e-950e-7728ca9ae563')
   and o.tracking_state::text = 'terminal'
   and (o.meta->>'r_ex_funding') is not null
 order by sv.version, a.emitted_at;

commit;
