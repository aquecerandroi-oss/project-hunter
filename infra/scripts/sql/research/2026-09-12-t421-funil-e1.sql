with s as (
  select mint, as_of, snipers, holders, holders_prev, holders_rising, dev_share, creator_net_seller as cns, curve_progress_pct as p, progress_rising as pr, mcap_delta_60s as md,
    (age_s between 30 and 300 and net_sol_flow_60s > 0 and unique_buyers_60s >= 10 and buys_60s > 0 and sells_60s::numeric/buys_60s <= 0.6) as base
  from meme_features_15s where as_of >= now() - interval '30 minutes'
)
select
  count(*) filter (where base) as base_linhas, count(distinct mint) filter (where base) as base_mints,
  count(distinct mint) filter (where base and p >= 0.05) as prog5,
  count(distinct mint) filter (where base and p >= 0.05 and coalesce(pr,false)) as prog5_subindo,
  count(distinct mint) filter (where base and p >= 0.05 and (coalesce(pr,false) or coalesce(md,0) > 0)) as prog5_ou_mcap_subindo,
  count(distinct mint) filter (where base and p >= 0.05 and coalesce(holders_rising,false)) as holders_subindo,
  count(distinct mint) filter (where base and p >= 0.05 and holders >= 20 and holders >= coalesce(holders_prev, holders)) as holders_nao_caindo_20,
  count(distinct mint) filter (where base and p >= 0.05 and snipers is not null and snipers <= 2) as snipers_le_2,
  count(distinct mint) filter (where base and p >= 0.05 and snipers is not null and snipers <= 10) as snipers_le_10,
  count(distinct mint) filter (where base and p >= 0.05 and snipers is not null and snipers <= 25) as snipers_le_25,
  count(distinct mint) filter (where base and p >= 0.05 and dev_share is not null and dev_share <= 0.10) as dev_le_10,
  count(distinct mint) filter (where base and p >= 0.05 and cns = false) as criador_nao_vendeu,
  count(distinct mint) filter (where base and p >= 0.05 and cns is null) as criador_desconhecido,
  count(distinct mint) filter (where base and p >= 0.05 and (coalesce(pr,false) or coalesce(md,0) > 0) and holders >= 20 and holders >= coalesce(holders_prev, holders) and snipers <= 10 and dev_share <= 0.10 and cns = false) as candidato_v4_estrito,
  count(distinct mint) filter (where base and p >= 0.05 and (coalesce(pr,false) or coalesce(md,0) > 0) and holders >= 20 and holders >= coalesce(holders_prev, holders) and snipers <= 25 and dev_share <= 0.10 and cns is not true) as candidato_v4_folgado
from s;
