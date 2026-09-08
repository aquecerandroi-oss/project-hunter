-- T3.50 Q1 — catalogo COMPLETO de versoes (inclusive as sem operacao concluida),
-- para nomear as variantes da T3.47 e provar que trendline_breakout v1 nao tem
-- nada tracavel ainda. SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;

select now() as read_at;

select s.key as strategy, sv.version, sv.status, sv.purpose,
       sv.activated_at,
       left(coalesce(sv.code_ref, ''), 16) as code_ref,
       (select count(*) from agent_signals a where a.strategy_version_id = sv.id) as sinais,
       (select count(*) from agent_signals a join signal_outcomes o on o.signal_id = a.id
         where a.strategy_version_id = sv.id and o.tracking_state = 'terminal'
           and o.r_multiple is not null)                                          as concluidas
  from strategy_versions sv
  join strategies s on s.id = sv.strategy_id
 order by s.key, sv.version;

commit;
