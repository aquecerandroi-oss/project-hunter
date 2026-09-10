-- T3.74f q01: pg_stat_activity snapshot at a burst peak (read-only, no writes).
-- Groups by state/wait_event so a burst's shape (idle vs. actually blocked on
-- a lock/IO) is visible without dumping every row.
begin transaction isolation level repeatable read read only;
select state,
       wait_event_type,
       wait_event,
       count(*) as backends
from pg_stat_activity
where pid <> pg_backend_pid()
group by 1, 2, 3
order by backends desc;
commit;
