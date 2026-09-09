-- T3.47b q01 — o que fica congelado quando a versao sai do roster: os slots de shadow
-- com acompanhamento aberto das tres versoes a aposentar. Somente leitura.
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;

select s.key || ' ' || sv.version as versao,
       m.symbol,
       o.tracking_state::text as estado,
       coalesce(o.result::text, '-') as resultado,
       a.supporting_features->>'cohort' as coorte,
       to_char(a.emitted_at, 'YYYY-MM-DD HH24:MI:SS') as emitido_em,
       to_char(now() - a.emitted_at, 'HH24:MI:SS') as idade,
       to_char(a.expires_at, 'YYYY-MM-DD HH24:MI:SS') as expira_em,
       to_char(o.tracked_until, 'YYYY-MM-DD HH24:MI:SS') as acompanhado_ate
  from shadow_episodes e
  join strategy_versions sv on sv.id = e.strategy_version_id
  join strategies s on s.id = sv.strategy_id
  join markets m on m.id = e.market_id
  left join signal_outcomes o on o.signal_id = e.open_outcome_signal_id
  left join agent_signals a on a.id = e.open_outcome_signal_id
 where (s.key, sv.version) in (('momentum','v7'), ('mean_reversion','v4'), ('mean_reversion','v5'))
   and e.open_outcome_signal_id is not null
 order by s.key, sv.version, m.symbol;
commit;
