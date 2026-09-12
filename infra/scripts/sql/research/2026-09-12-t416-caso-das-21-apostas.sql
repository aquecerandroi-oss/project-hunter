with bets as (
  select b.id, b.mint, r.name rule, b.leg, b.status, b.entry_at, b.exit_at, b.r_multiple, b.pnl_sol,
         b.exit->>'reason' reason,
         (b.entry->>'sol_spent')::numeric spent,
         p.proposed_at, p.decided_at, p.features_end_time,
         t.created_at, t.pool_created_at,
         extract(epoch from (b.entry_at - p.decided_at)) fill_delay_s,
         extract(epoch from (b.entry_at - t.created_at)) age_at_entry_s,
         extract(epoch from (coalesce(b.exit_at, now()) - b.entry_at)) hold_s
  from meme_paper_bets b
  join meme_rule_sets r on r.id = b.rule_set_id
  left join meme_proposals p on p.id = b.proposal_id
  left join meme_tokens t on t.mint = b.mint
),
feat as (
  select f.mint, f.end_time, f.holders, f.snipers, f.dev_share, f.top10_share, f.buys_1m, f.sells_1m, f.creator_net_seller, f.curve_progress_pct, f.mcap_sol
  from meme_features_1m f
),
path as (
  select b.id,
         (select mcap_sol from meme_curve_snapshots s where s.mint = b.mint and s.observed_at >= b.entry_at order by s.observed_at limit 1) entry_mcap,
         (select max(mcap_sol) from meme_curve_snapshots s where s.mint = b.mint and s.observed_at > b.entry_at and s.observed_at <= b.entry_at + interval '30 minutes') max_mcap_30m,
         (select mcap_sol from meme_curve_snapshots s where s.mint = b.mint and s.observed_at <= coalesce(b.exit_at, now()) order by s.observed_at desc limit 1) exit_mcap,
         (select mcap_sol from meme_curve_snapshots s where s.mint = b.mint and s.observed_at <= b.entry_at + interval '30 minutes' order by s.observed_at desc limit 1) mcap_30m_after
  from bets b
)
select to_char(b.entry_at at time zone 'America/Sao_Paulo','HH24:MI:SS') entrada, b.rule, b.leg, b.reason, round(b.r_multiple::numeric,2) r,
       round(b.fill_delay_s) fill_s, round(b.age_at_entry_s) age_s, round(b.hold_s) hold_s,
       case when b.pool_created_at is not null and b.pool_created_at - b.created_at <= interval '1 second' then 'mesmo_slot' else '' end grad,
       f.holders, f.snipers, round(f.dev_share::numeric,3) dev, round(f.top10_share::numeric,3) top10, f.buys_1m b1, f.sells_1m s1, f.creator_net_seller cns,
       round(p.entry_mcap::numeric,1) mc_in, round(p.max_mcap_30m::numeric,1) mc_max30, round(p.exit_mcap::numeric,1) mc_out, round(p.mcap_30m_after::numeric,1) mc_30m
from bets b left join feat f on f.mint = b.mint and f.end_time = b.features_end_time
left join path p on p.id = b.id
order by b.entry_at;
