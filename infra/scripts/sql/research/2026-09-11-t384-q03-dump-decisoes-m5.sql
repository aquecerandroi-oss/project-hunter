-- T3.84 q03 -- DUMP por decisao (CSV) da coorte de 90 d da `mean_reversion_m5 v1`
-- (EXP-0028) e do controle PRE-DECLARADO da pagina: a mae `mean_reversion v1`,
-- coorte `replay:fa005985-...` da T3.62b/EXP-0025, que NAO e re-rodada.
--
-- Irmao de `2026-09-10-t376-q04-dump-decisoes-bracos.sql`, com duas colunas a
-- mais que esta pagina precisa:
--   `atr_pct`  = `supporting_features->atr->>percent` -- o ATR% REALIZADO da
--                barra de decisao (fracao, nao %); e com ele que o pedagio
--                medido da KB-0076 (`0,0020/(stop_atr x ATR%)`) deixa de ser
--                extrapolacao da distribuicao de barras e passa a ser medido
--                nas decisoes que existiram;
--   `saida`    = o desfecho da saida (`progress->>result`: stop/target/expired),
--                para o funil de saida.
-- `barra` = `source_bar_close` (o `observation_ts` do envelope); `janela` usa as
-- MESMAS tres fronteiras de 30 d da EXP-0025 (06-12/07-12/08-11/09-10).
-- Eixo primario `r_exf` (= `meta->>r_ex_funding`); `r_net` sai ao lado para quem
-- quiser conferir a perna de funding (cobertura de K5).
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset format unaligned
\pset fieldsep ','
\pset tuples_only off

select s.key || ' ' || sv.version                            as versao,
       (a.emitted_at at time zone 'UTC')::date               as dia,
       mk.symbol                                             as mercado,
       case when a.emitted_at <  timestamptz '2026-07-12' then 'J1'
            when a.emitted_at <  timestamptz '2026-08-11' then 'J2'
            else 'J3' end                                    as janela,
       (a.supporting_features->>'observation_ts')            as barra,
       round((o.meta->>'r_ex_funding')::numeric, 6)          as r_exf,
       coalesce(round(o.r_multiple, 6)::text, '')            as r_net,
       round(((o.meta->'progress'->>'exit_base')::numeric
              - (o.meta->'progress'->>'entry')::numeric/1.0006)
             / nullif((o.meta->'excursions'->>'initial_risk')::numeric,0), 6) as r_bruto,
       round((o.meta->'excursions'->>'initial_risk')::numeric
             / nullif((o.meta->'progress'->>'entry')::numeric,0), 6)          as risco_pct,
       round((a.supporting_features->'atr'->>'percent')::numeric, 8)          as atr_pct,
       coalesce(o.meta->'progress'->>'result', '')                            as saida
  from signal_outcomes o
  join agent_signals a       on a.id = o.signal_id
  join strategy_versions sv  on sv.id = a.strategy_version_id
  join strategies s          on s.id = sv.strategy_id
  join markets mk            on mk.id = a.market_id
 where o.meta->>'cohort' in ('replay:92c8d080-6009-4a59-9868-31282b1bd493',
                             'replay:fa005985-0b55-4820-904c-8ada589e441c')
   and o.tracking_state::text = 'terminal'
   and (o.meta->>'r_ex_funding') is not null
 order by 1, a.emitted_at;

commit;
