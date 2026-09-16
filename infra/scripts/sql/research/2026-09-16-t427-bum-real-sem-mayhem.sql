\pset format aligned
-- SOL REAL na curva (real_sol_reserves), moedas NÃO Mayhem, 3 dias: quantas passam de cada patamar e em quanto tempo
with nm as (
  select t.mint, t.symbol, t.created_at, t.completed_at
  from meme_tokens t where t.created_at >= now() - interval '3 days' and coalesce(t.mayhem_enabled,false) = false
), r as (
  select nm.mint, nm.symbol, nm.created_at, nm.completed_at,
    max(cs.real_sol_reserves) as peak_real_sol,
    min(cs.observed_at) filter (where cs.real_sol_reserves >= 30) as at_30,
    min(cs.observed_at) filter (where cs.real_sol_reserves >= 60) as at_60,
    (array_agg(cs.observed_at order by cs.real_sol_reserves desc))[1] as peak_at
  from nm join meme_curve_snapshots cs on cs.mint = nm.mint
  group by 1,2,3,4
)
select count(*) as nao_mayhem_com_fotos,
  count(*) filter (where peak_real_sol >= 10) as passou_10_sol,
  count(*) filter (where peak_real_sol >= 30) as passou_30_sol,
  count(*) filter (where peak_real_sol >= 60) as passou_60_sol,
  count(*) filter (where completed_at is not null) as graduou,
  round(percentile_cont(0.5) within group (order by extract(epoch from (at_30 - created_at))/60) filter (where at_30 is not null)) as mediana_min_ate_30sol,
  round(percentile_cont(0.5) within group (order by extract(epoch from (at_60 - created_at))/60) filter (where at_60 is not null)) as mediana_min_ate_60sol,
  count(*) filter (where at_30 is not null and at_30 - created_at >= interval '3 minutes') as chegou_a_30_depois_de_3min,
  count(*) filter (where at_30 is not null and at_30 - created_at >= interval '10 minutes') as chegou_a_30_depois_de_10min
from r;
-- as que chegaram a 30 SOL reais DEPOIS de 3 min (as "lentas", onde há tempo de agir): quantas graduaram, e o Lab viu?
with nm as (
  select t.mint, t.symbol, t.created_at, t.completed_at from meme_tokens t
  where t.created_at >= now() - interval '3 days' and coalesce(t.mayhem_enabled,false) = false
), r as (
  select nm.*, min(cs.observed_at) filter (where cs.real_sol_reserves >= 30) as at_30, max(cs.real_sol_reserves) as peak
  from nm join meme_curve_snapshots cs on cs.mint = nm.mint group by 1,2,3,4
)
select count(*) as lentas_30sol_apos_3min, count(*) filter (where completed_at is not null) as graduaram,
  count(*) filter (where exists (select 1 from meme_proposals p where p.mint=r.mint)) as lab_propos,
  count(*) filter (where exists (select 1 from meme_paper_bets b where b.mint=r.mint)) as lab_apostou,
  round(avg(extract(epoch from (at_30 - created_at))/60)) as media_min_ate_30
from r where at_30 is not null and at_30 - created_at >= interval '3 minutes';
