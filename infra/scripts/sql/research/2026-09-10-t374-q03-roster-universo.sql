begin transaction isolation level repeatable read read only;
select count(*) as versoes_ativas
from strategy_versions where status='active' and activated_at is not null;

select market_type, count(*) filter (where is_monitored) as monitorados, count(*) as linhas
from markets group by 1;
commit;
