\pset format aligned
-- 1. criadores das apostas: quantas moedas anteriores no nosso banco, e quantas delas o criador vendeu (fita) ou morreram
with bets as (
  select b.id, b.mint, t.creator, t.created_at, b.r_multiple, coalesce(b.exit->>'reason','open') as saida
  from meme_paper_bets b join meme_tokens t on t.mint=b.mint
  where b.status='closed' and b.outcome_quality='measured'
), hist as (
  select bt.id, bt.saida, bt.r_multiple,
    (select count(*) from meme_tokens p where p.creator=bt.creator and p.mint<>bt.mint and p.created_at < bt.created_at) as moedas_anteriores,
    (select count(*) from meme_tokens p where p.creator=bt.creator and p.mint<>bt.mint and p.created_at < bt.created_at
       and exists (select 1 from meme_features_1m f where f.mint=p.mint and f.creator_sold = true and f.end_time < bt.created_at)) as anteriores_com_venda_do_criador,
    (select count(*) from meme_tokens p where p.creator=bt.creator and p.mint<>bt.mint and p.created_at < bt.created_at
       and exists (select 1 from meme_paper_bets pb where pb.mint=p.mint and pb.exit->>'reason'='creator_dump' and pb.exit_at < bt.created_at)) as anteriores_que_nos_dumparam
  from bets bt
)
select
  count(*) as apostas,
  count(*) filter (where moedas_anteriores > 0) as criador_com_historico,
  count(*) filter (where anteriores_com_venda_do_criador > 0) as criador_ja_vendeu_antes,
  round(avg(r_multiple) filter (where anteriores_com_venda_do_criador > 0),3) as r_medio_ja_vendeu,
  round(avg(r_multiple) filter (where anteriores_com_venda_do_criador = 0),3) as r_medio_sem_historico_de_venda,
  count(*) filter (where saida='creator_dump' and anteriores_com_venda_do_criador > 0) as dumps_de_reincidente,
  count(*) filter (where saida='creator_dump') as dumps_total,
  count(*) filter (where anteriores_com_venda_do_criador > 0 and r_multiple > 0) as ganhas_de_reincidente,
  count(*) filter (where anteriores_com_venda_do_criador = 0 and r_multiple > 0) as ganhas_sem_historico
from hist;
-- 2. base: entre as moedas criadas nas últimas 24 h, fração de criadores com moeda anterior onde ele vendeu
with recent as (select mint, creator, created_at from meme_tokens where created_at >= now() - interval '24 hours' and creator is not null)
select count(*) as moedas_24h,
  count(*) filter (where exists (select 1 from meme_tokens p join meme_features_1m f on f.mint=p.mint
      where p.creator=r.creator and p.mint<>r.mint and p.created_at < r.created_at and f.creator_sold = true)) as criador_ja_vendeu_antes
from recent r;
