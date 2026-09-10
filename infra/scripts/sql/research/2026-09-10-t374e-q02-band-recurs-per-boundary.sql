-- T3.74e q02: a banda de atraso por fronteira de barra compartilhada
-- (observation_ts), nas ultimas horas -- mostra que a banda estreita se
-- repete a cada fechamento de timeframe compartilhado (15/30/60 min), nao
-- so na amostra pontual do brief.
begin transaction isolation level repeatable read read only;
select
  (supporting_features->>'observation_ts')::timestamptz as observation_ts,
  count(*) as sinais,
  round(min(extract(epoch from (
    emitted_at - (supporting_features->>'observation_ts')::timestamptz
  )))::numeric, 1) as min_lag_s,
  round(max(extract(epoch from (
    emitted_at - (supporting_features->>'observation_ts')::timestamptz
  )))::numeric, 1) as max_lag_s
from agent_signals
where emitted_at >= now() - interval '3 hours'
  and supporting_features ? 'observation_ts'
group by 1
order by 1 desc;
commit;
