-- T3.54 q12 — recibos (replay_runs, system_events) e isolamento: linhagem das
-- quatro versoes derivadas, conteudo proprio de cada linha contra o pai, e a
-- prova de que nenhuma coorte de replay produziu linha de outbox.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '120s';
\pset border 2
\pset numericlocale off
select now() as read_at;

\echo '--- replay_runs desta tarefa ---'
select r.run_id::text as run_id, s.key||' '||sv.version as versao, r.window_from::date as de, r.window_to::date as ate,
       cardinality(r.markets) as mercados, r.bars_evaluated, r.signals, r.outcomes_resolved,
       round(r.seconds::numeric, 1) as s,
       r.errors, r.finished_at
  from replay_runs r
  join strategy_versions sv on sv.id = r.strategy_version_id
  join strategies s on s.id = sv.strategy_id
 where r.finished_at >= timestamptz '2026-09-09 03:15:00+00'
 order by r.finished_at;

\echo '--- system_events desta tarefa ---'
select level::text, component, event, left(message, 100) as mensagem, created_at
  from system_events
 where created_at >= timestamptz '2026-09-09 03:15:00+00'
   and component in ('activate_strategy_version', 'replay_engine')
 order by created_at;

\echo '--- linhagem e conteudo proprio (v9/v10 contra os pais) ---'
select s.key||' '||sv.version as versao, sv.status::text as status, sv.purpose::text as purpose,
       sv.default_parameters->>'atr_timeframe' as atr_tf,
       sv.default_parameters->>'atr_bars' as atr_bars,
       sv.default_parameters->>'atr_pct_min' as atr_pct_min,
       sv.default_parameters->>'stop_atr' as stop_atr,
       sv.default_parameters->>'target_atr' as target_atr,
       left(sv.changelog, 96) as changelog
  from strategy_versions sv
  join strategies s on s.id = sv.strategy_id
 where (s.key = 'mean_reversion' and sv.version in ('v6', 'v9', 'v10'))
    or (s.key = 'momentum' and sv.version in ('v8', 'v9', 'v10'))
 order by s.key, length(sv.version), sv.version;

\echo '--- nenhuma coorte de replay virou outbox nem proposta ---'
select (select count(*) from shadow_outbox o
         join agent_signals a on a.id = (o.payload->>'signal_id')::uuid
        where a.supporting_features->>'cohort' in (
              'replay:71c76d86-ceb0-4d48-b3be-88c3c055061e',
              'replay:6eff77c0-566d-4a80-b580-0b0267b86f65')) as linhas_de_outbox,
       (select count(*) from trade_proposals p
         join agent_signals a on a.id = p.signal_id
        where a.supporting_features->>'cohort' in (
              'replay:71c76d86-ceb0-4d48-b3be-88c3c055061e',
              'replay:6eff77c0-566d-4a80-b580-0b0267b86f65')) as propostas;
commit;
