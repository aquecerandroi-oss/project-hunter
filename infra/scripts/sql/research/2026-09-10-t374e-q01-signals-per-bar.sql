-- T3.74e q01: para a barra mais recente, todas as decisoes persistidas com o
-- atraso decisao-menos-barra individual -- prova a banda 34-61s numa unica
-- barra (mesmo observation_ts), nao um espalhamento entre barras diferentes.
begin transaction isolation level repeatable read read only;
select
  s.id,
  ex.code as exchange, m.symbol, m.market_type,
  (s.supporting_features->>'observation_ts')::timestamptz as observation_ts,
  s.emitted_at,
  round(extract(epoch from (
    s.emitted_at - (s.supporting_features->>'observation_ts')::timestamptz
  ))::numeric, 2) as lag_s
from agent_signals s
join markets m on m.id = s.market_id
join exchanges ex on ex.id = m.exchange_id
where s.emitted_at > now() - interval '25 minutes'
order by s.emitted_at desc
limit 30;
commit;
