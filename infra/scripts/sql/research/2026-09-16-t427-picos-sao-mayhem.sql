\pset format aligned
-- moedas dos últimos 3 dias com pico de mcap ≥ 300 SOL na série de minuto: quando nasceram, quando chegaram a 100 SOL, quando ao pico, o que valiam no minuto 3 e 5
with peaks as (
  select f.mint, max(f.mcap_sol) as peak,
         (array_agg(f.end_time order by f.mcap_sol desc))[1] as peak_at
  from meme_features_1m f
  where f.end_time >= now() - interval '3 days'
  group by f.mint having max(f.mcap_sol) >= 300
), first100 as (
  select p.mint, min(f.end_time) as at_100
  from peaks p join meme_features_1m f on f.mint = p.mint and f.mcap_sol >= 100
  group by p.mint
), early as (
  select p.mint,
    (select f.mcap_sol from meme_features_1m f where f.mint=p.mint and f.end_time <= t.created_at + interval '3 minutes' order by f.end_time desc limit 1) as mcap_3m,
    (select f.mcap_sol from meme_features_1m f where f.mint=p.mint and f.end_time <= t.created_at + interval '10 minutes' order by f.end_time desc limit 1) as mcap_10m
  from peaks p join meme_tokens t on t.mint=p.mint
)
select t.symbol, round(p.peak) as pico_sol,
       round(extract(epoch from (f1.at_100 - t.created_at))/60) as min_ate_100,
       round(extract(epoch from (p.peak_at - t.created_at))/60) as min_ate_pico,
       round(e.mcap_3m) as mcap_3m, round(e.mcap_10m) as mcap_10m,
       round(p.peak / nullif(e.mcap_10m,0),1) as x_do_min10_ao_pico,
       t.completed_at is not null as graduou,
       (select count(*) from meme_paper_bets b where b.mint=p.mint) as apostas_nossas
from peaks p join meme_tokens t on t.mint=p.mint
left join first100 f1 on f1.mint=p.mint left join early e on e.mint=p.mint
where t.created_at is not null
order by p.peak desc limit 25;
select count(*) as moedas_3d, count(*) filter (where peak>=300) as pico_300, count(*) filter (where peak>=1000) as pico_1000
from (select mint, max(mcap_sol) as peak from meme_features_1m where end_time >= now() - interval '3 days' group by mint) x;
