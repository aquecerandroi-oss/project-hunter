-- T3.40 — o delta pareado por dia (bloco) e o intervalo t de 95% sobre as medias diarias.
\set pop 'select left(split_part(o.meta->>\'cohort\',\':\',2),8) as coorte, a.market_id, (o.meta->\'entry_plan\'->>\'source_bar_close\')::timestamptz as bar, o.r_multiple as r_net from signal_outcomes o join agent_signals a on a.id=o.signal_id where o.meta->>\'cohort\' in (\'replay:f8d8279c-1fba-42ae-95ef-202042f96c60\',\'replay:9a08835a-ae13-4c23-b521-734b2f60a3a2\')'
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;
with pop as (:pop),
     pares as (select p.bar::date as dia, v.r_net - p.r_net as delta
                 from pop p join pop v on v.market_id=p.market_id and v.bar=p.bar
                where p.coorte='f8d8279c' and v.coorte='9a08835a'
                  and p.r_net is not null and v.r_net is not null),
     dia as (select dia, count(*) n, avg(delta) media from pares group by 1)
select count(*) as blocos_dia,
       round(avg(media), 4) as media_das_medias_diarias,
       round(stddev_samp(media)::numeric, 4) as desvio,
       round((stddev_samp(media)/sqrt(count(*)))::numeric, 4) as erro_padrao,
       round((avg(media) - 2.069*stddev_samp(media)/sqrt(count(*)))::numeric, 4) as ic95_inferior,
       round((avg(media) + 2.069*stddev_samp(media)/sqrt(count(*)))::numeric, 4) as ic95_superior,
       count(*) filter (where media > 0) as dias_positivos,
       count(*) filter (where media < 0) as dias_negativos
  from dia;
with pop as (:pop),
     pares as (select p.bar::date as dia, v.r_net - p.r_net as delta
                 from pop p join pop v on v.market_id=p.market_id and v.bar=p.bar
                where p.coorte='f8d8279c' and v.coorte='9a08835a'
                  and p.r_net is not null and v.r_net is not null)
select dia, count(*) n, round(avg(delta),4) as delta_medio_r, round(sum(delta),3) as delta_soma_r
  from pares group by 1 order by 1;
commit;
