-- =====================================================================================
-- T3.34c q04 — recibos, isolamento da coorte e o roster depois da ativacao
-- SOMENTE LEITURA · a cerca da coorte de replay e o que impede o dia um de vazar
-- para o Lab prospectivo (`persist.is_published_cohort` recusa publicar replay).
-- =====================================================================================
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;

-- 1. os recibos de `replay_runs` desta tarefa (a sonda + as duas fatias)
select 'replay:'||left(r.run_id::text,8)                     as coorte,
       s.key||' '||sv.version                                as versao,
       r.window_from::date as de, r.window_to::date as ate,
       cardinality(r.markets) as mkts, r.bars_evaluated as bars,
       r.signals as sig, r.outcomes_resolved as out, r.outcomes_open as open,
       round(r.seconds::numeric, 3) as seg, r.workers as wk, r.decision_lag_s as lag,
       r.evaluations_by_state::text as estados, r.errors as err, r.finished_at
  from replay_runs r
  join strategy_versions sv on sv.id = r.strategy_version_id
  join strategies s on s.id = sv.strategy_id
 where s.key = 'trendline_breakout'
 order by r.finished_at;

-- 2. isolamento: NENHUMA linha de `shadow_outbox` pode existir para uma coorte de replay
select (select count(*) from shadow_outbox o
        where o.payload->>'cohort' in ('replay:d78c14d1-b4c5-424a-8f31-a43100744bb4',
                                       'replay:1c93e83f-396a-4c60-99a9-e7f1b7876d17')
           or o.payload->'signal'->>'cohort' in ('replay:d78c14d1-b4c5-424a-8f31-a43100744bb4',
                                                 'replay:1c93e83f-396a-4c60-99a9-e7f1b7876d17'))  as outbox_das_coortes,
       (select count(*) from shadow_outbox o where o.payload::text like '%trendline_breakout%')    as outbox_trendline_qualquer,
       (select count(*) from signal_outcomes so
          join agent_signals a on a.id = so.signal_id
          join strategy_versions sv on sv.id = a.strategy_version_id
          join strategies s on s.id = sv.strategy_id
         where s.key='trendline_breakout')                                            as sinais_trendline_total,
       (select count(*) from signal_outcomes so
          join agent_signals a on a.id = so.signal_id
          join strategy_versions sv on sv.id = a.strategy_version_id
          join strategies s on s.id = sv.strategy_id
         where s.key='trendline_breakout'
           and so.meta->>'cohort' <> 'replay:d78c14d1-b4c5-424a-8f31-a43100744bb4')   as sinais_fora_da_coorte,
       (select count(*) from signal_outcomes so
          join agent_signals a on a.id = so.signal_id
          join strategy_versions sv on sv.id = a.strategy_version_id
          join strategies s on s.id = sv.strategy_id
         where s.key='trendline_breakout' and so.tracking_state <> 'terminal')        as nao_terminais;

-- 3. o que a coorte prospectiva ja decidiu desde a ativacao (o Lab de verdade)
select coalesce(so.meta->>'cohort','(sem coorte)') as coorte, count(*) as sinais,
       min(a.emitted_at) as primeiro, max(a.emitted_at) as ultimo,
       count(distinct m.symbol) as mercados
  from signal_outcomes so
  join agent_signals a on a.id = so.signal_id
  join markets m on m.id = a.market_id
  join strategy_versions sv on sv.id = a.strategy_version_id
  join strategies s on s.id = sv.strategy_id
 where s.key = 'trendline_breakout'
 group by 1 order by 2 desc;

-- 4. `system_events` da janela desta tarefa
select level, component, event, left(message, 108) as mensagem, created_at
  from system_events
 where created_at >= timestamptz '2026-09-08 22:26:00+00'
   and (message ilike '%trendline%' or event like 'strategy_version%' or event like 'replay_run%'
        or event like 'seed%' or component in ('activate_strategy_version','seed'))
 order by created_at;

-- 5. o roster depois da ativacao, na ordem que o worker usa (a `paper` primeiro)
select row_number() over (order by s.key,
                          case when sv.purpose='paper' then 0 else 1 end,
                          coalesce(nullif(regexp_replace(sv.version,'^v',''),'')::int, 999999),
                          sv.version) as pos,
       s.key, sv.version, sv.purpose, sv.status, sv.activated_at
  from strategy_versions sv join strategies s on s.id = sv.strategy_id
 where sv.status = 'active' order by pos;
commit;
