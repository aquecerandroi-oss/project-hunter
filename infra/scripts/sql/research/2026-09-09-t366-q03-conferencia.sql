-- T3.66 q03 — conferência do congelamento. SOMENTE LEITURA.
-- A população da T3.66 foi exportada por q01 num instante; corridas de replay
-- continuam escrevendo decisões históricas, então a contagem "hoje" pode ser maior
-- que a do arquivo. Esta consulta diz (a) que horas são agora, (b) quanto a família
-- tem AGORA sob o mesmo corte e (c) se as decisões que o arquivo congelou mudaram.
begin transaction isolation level repeatable read read only;
select now() as read_at;
select sv.version, count(*) as agora
  from signal_outcomes o
  join agent_signals a      on a.id  = o.signal_id
  join strategy_versions sv on sv.id = a.strategy_version_id
  join strategies s         on s.id  = sv.strategy_id
 where s.key='mean_reversion' and sv.version in ('v1','v2','v6','v10')
   and a.emitted_at < timestamptz '2026-09-09 02:30:00+00'
   and o.tracking_state='terminal' and o.r_multiple is not null
 group by 1 order by 1;
commit;
