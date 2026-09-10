-- T3.62b q00 -- ACHAR A COORTE DA v10 QUE O AGENTE ANTERIOR JA RODOU.
-- O brief diz: "nao refaca a v10". Entao a primeira coisa a fazer nao e rodar
-- nada, e sim provar qual coorte e a dele: a mais nova coorte de replay da
-- mean_reversion v10 cujo digest de mercados cobre os 16, com ~798 decisoes em
-- ~12 fatias e 0 erro. Tres leituras, nesta ordem:
--   1. system_events/replay_run_finished -- o recibo COMPLETO de cada corrida
--      (replay_runs so guarda a primeira fatia de cada janela: ON CONFLICT
--      (run_id, window_from, window_to) DO NOTHING nao inclui os mercados --
--      CONCERN 1 da notes-T3.62 SS2.3). E daqui que sai o "12 fatias, 0 erro".
--   2. a populacao persistida por coorte em signal_outcomes.meta->>'cohort'.
--   3. o catalogo das tres versoes que esta tarefa compara (v10, v1, v2), para
--      que o contraste seja sobre PARAMETRO e nao sobre codigo.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

-- 1. recibos por coorte a partir de system_events (o recibo completo)
select e.data->>'cohort'                                as coorte,
       e.data->>'version'                               as versao,
       count(*)                                         as fatias,
       sum((e.data->>'bars_evaluated')::bigint)         as barras,
       sum((e.data->>'errors')::bigint)                 as erros,
       count(distinct m.mkt)                            as mercados_distintos,
       min((e.data->>'window_from')::timestamptz)       as janela_de,
       max((e.data->>'window_to')::timestamptz)         as janela_ate,
       min(e.occurred_at)                               as primeira_corrida,
       max(e.occurred_at)                               as ultima_corrida
  from system_events e
  left join lateral jsonb_array_elements_text(
         case when jsonb_typeof(e.data->'markets') = 'array'
              then e.data->'markets' else '[]'::jsonb end) as m(mkt) on true
 where e.source = 'replay_engine'
   and e.event_type = 'replay_run_finished'
   and e.data->>'version' like 'mean_reversion%'
   and e.occurred_at > now() - interval '3 days'
 group by 1, 2
 order by max(e.occurred_at) desc;

-- 2. populacao persistida por coorte (a fonte da analise)
select sv.version,
       o.meta->>'cohort'       as coorte,
       count(*)                as decisoes,
       count(*) filter (where o.meta->>'r_net' is not null
                          or o.meta ? 'r_multiple')     as com_r,
       min(a.emitted_at)::date as primeiro_dia,
       max(a.emitted_at)::date as ultimo_dia,
       count(distinct a.emitted_at::date) as dias_distintos,
       count(distinct a.market_id)        as mercados
  from signal_outcomes o
  join agent_signals a      on a.id = o.signal_id
  join strategy_versions sv on sv.id = a.strategy_version_id
  join strategies s         on s.id = sv.strategy_id
 where s.key = 'mean_reversion'
   and o.meta->>'cohort' like 'replay:%'
 group by 1, 2
 having count(*) > 50
 order by max(a.emitted_at) desc, 3 desc;

-- 3. catalogo das versoes desta tarefa
select sv.version,
       sv.status::text  as estado,
       sv.purpose::text as proposito,
       sv.default_parameters->>'atr_pct_min'   as atr_pct_min,
       sv.default_parameters->>'stop_atr'      as stop_atr,
       sv.default_parameters->>'target_atr'    as alvo1,
       sv.default_parameters->>'target2_atr'   as alvo2,
       sv.default_parameters->>'atr_timeframe' as atr_tf,
       sv.default_parameters->>'atr_bars'      as atr_bars,
       coalesce(sv.eligibility_policy::text, '-') as politica,
       right(sv.code_ref, 16) as code_ref_sufixo
  from strategy_versions sv
  join strategies s on s.id = sv.strategy_id
 where s.key = 'mean_reversion' and sv.version in ('v1','v2','v10')
 order by (regexp_replace(sv.version, '\D', '', 'g'))::int;

commit;
