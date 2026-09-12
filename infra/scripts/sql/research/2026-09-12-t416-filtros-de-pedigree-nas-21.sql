with bets as (
  select b.id, b.mint, r.name rule, b.entry_at, b.r_multiple, b.exit->>'reason' reason, p.features_end_time, t.created_at, t.pool_created_at, t.creator, t.symbol, t.name tname
  from meme_paper_bets b join meme_rule_sets r on r.id=b.rule_set_id
  left join meme_proposals p on p.id=b.proposal_id left join meme_tokens t on t.mint=b.mint
),
x as (
  select b.*,
    (b.pool_created_at is not null and b.pool_created_at - b.created_at <= interval '1 second') same_slot,
    (select count(*) from meme_tokens t2 where t2.creator = b.creator and t2.created_at < b.created_at and t2.created_at > b.created_at - interval '1 hour') creator_prior_1h,
    (select count(*) from meme_tokens t3 where t3.symbol = b.symbol and t3.created_at < b.created_at and t3.created_at > b.created_at - interval '24 hours') symbol_dup_24h,
    (select f.sells_1m::numeric / nullif(f.buys_1m,0) from meme_features_1m f where f.mint=b.mint and f.end_time=b.features_end_time order by f.features_version desc limit 1) sells_over_buys,
    (select f.holders from meme_features_1m f where f.mint=b.mint and f.end_time=b.features_end_time order by f.features_version desc limit 1) holders_now,
    (select f.holders from meme_features_1m f where f.mint=b.mint and f.end_time=b.features_end_time - interval '2 minutes' order by f.features_version desc limit 1) holders_2m_ago,
    (select f.snipers from meme_features_1m f where f.mint=b.mint and f.end_time=b.features_end_time order by f.features_version desc limit 1) snipers,
    (select max(o.top10_share) from meme_board_observations o where o.mint=b.mint and o.observed_at <= b.entry_at) top10_board,
    (select max(o.dev_share) from meme_board_observations o where o.mint=b.mint and o.observed_at <= b.entry_at) dev_board,
    (select count(*) from meme_board_observations o where o.mint=b.mint and o.board='new' and o.observed_at <= b.entry_at) seen_new_board
  from bets b
)
select to_char(entry_at at time zone 'America/Sao_Paulo','HH24:MI') hora, left(tname,14) moeda, rule, reason, round(r_multiple::numeric,2) r,
  same_slot, creator_prior_1h cp1h, symbol_dup_24h dup24, round(sells_over_buys,2) s_b, holders_2m_ago h2, holders_now h0, snipers sn, round(top10_board::numeric,2) t10, round(dev_board::numeric,2) dev, seen_new_board nb
from x order by entry_at;
