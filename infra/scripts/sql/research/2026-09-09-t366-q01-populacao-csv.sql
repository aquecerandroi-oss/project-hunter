-- T3.66 q01 — a população congelada do EXP-0024, uma linha por decisão, CSV no stdout.
-- SOMENTE LEITURA. Nada é escrito na VPS.
--
-- Corte (as_of): agent_signals.emitted_at < 2026-09-09T02:30:00Z (23:30 BRT), o mesmo
-- da T3.53, para que esta medida seja comparável às daquela tarefa.
--
-- O relógio é a barra de origem (meta->'entry_plan'->>'source_bar_close'); a barra de
-- entrada é meta->'entry_plan'->>'entry_bar_open' (= barra + 1 min, delay_s = 60).
--
-- Níveis congelados: agent_signals.stop e targets[0].price — os mesmos que o walker leu.
-- p_entry/risk/exit_base vêm de meta.progress/meta.excursions (o que foi persistido).
begin transaction isolation level repeatable read read only;
copy (
  select o.signal_id,
         sv.version                                                        as versao,
         case when coalesce(a.supporting_features->>'cohort', o.meta->>'cohort','') like 'replay:%'
              then 'replay' else 'prospective' end                         as coorte,
         a.market_id,
         m.symbol,
         to_char((o.meta->'entry_plan'->>'source_bar_close')::timestamptz at time zone 'UTC',
                 'YYYY-MM-DD"T"HH24:MI:SS"Z"')                             as bar_utc,
         to_char((o.meta->'entry_plan'->>'entry_bar_open')::timestamptz at time zone 'UTC',
                 'YYYY-MM-DD"T"HH24:MI:SS"Z"')                             as entrada_utc,
         to_char((o.meta->'entry_plan'->>'source_bar_close')::timestamptz at time zone 'America/Sao_Paulo',
                 'YYYY-MM-DD')                                             as dia_br,
         extract(hour from ((o.meta->'entry_plan'->>'source_bar_close')::timestamptz at time zone 'UTC'))::int as hora_utc,
         a.stop                                                            as stop,
         (a.targets->>0)::numeric                                 as alvo1,
         (o.meta->'progress'->>'entry')::numeric                           as p_entry,
         (o.meta->'excursions'->>'initial_risk')::numeric                  as risco,
         (o.meta->'progress'->>'exit_base')::numeric                       as exit_base,
         to_char((o.meta->'progress'->>'exit_ts')::timestamptz at time zone 'UTC',
                 'YYYY-MM-DD"T"HH24:MI:SS"Z"')                             as saida_utc,
         o.result::text                                                    as motivo,
         (o.meta->>'r_ex_funding')::numeric                                as r_exf,
         o.r_multiple                                                      as r_net,
         (o.meta->>'horizon_s')::int                                       as horizonte_s
    from signal_outcomes o
    join agent_signals a      on a.id  = o.signal_id
    join markets m            on m.id  = a.market_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id  = sv.strategy_id
   where s.key = 'mean_reversion'
     and sv.version in ('v1','v2','v6','v10')
     and a.emitted_at < timestamptz '2026-09-09 02:30:00+00'
     and o.tracking_state = 'terminal'
     and o.r_multiple is not null
   order by sv.version, o.signal_id
) to stdout with (format csv, header true);
commit;
