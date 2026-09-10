-- T3.79 q03: admission (agent_signals.emitted_at -> trade_proposals.decided_at)
-- and fill (trade_proposals.decided_at -> a fill's own ts) hops. Written to
-- run even when the tables are empty (they are, as of this task -- see
-- notes-T3.79.md): a query that assumes at least one row would silently
-- error on the exact gap it exists to name.
begin transaction isolation level repeatable read read only;

select count(*) as candidate_rows,
       round(percentile_cont(0.5) within group (
         order by extract(epoch from (p.decided_at - s.emitted_at))
       )::numeric, 3) as admission_mediana_s,
       round(percentile_cont(0.95) within group (
         order by extract(epoch from (p.decided_at - s.emitted_at))
       )::numeric, 3) as admission_p95_s
from trade_proposals p
join agent_signals s on s.id = p.signal_id
where p.decided_at is not null
  and p.decided_at >= now() - interval '24 hours';

select count(*) as candidate_rows,
       round(percentile_cont(0.5) within group (
         order by extract(epoch from (f.ts - p.decided_at))
       )::numeric, 3) as fill_mediana_s,
       round(percentile_cont(0.95) within group (
         order by extract(epoch from (f.ts - p.decided_at))
       )::numeric, 3) as fill_p95_s
from fills f
join orders o on o.id = f.order_id
join trade_proposals p on p.id = o.proposal_id
where p.decided_at is not null
  and f.ts >= now() - interval '24 hours';

commit;
