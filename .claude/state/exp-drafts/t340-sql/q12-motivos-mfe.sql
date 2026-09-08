-- T3.40 — V2: motivos de saida vs pai, MFE capturado e o delta pareado por dia.
\set pop 'select s.key||\' \'||sv.version as versao, left(split_part(o.meta->>\'cohort\',\':\',2),8) as coorte, a.market_id, (o.meta->\'entry_plan\'->>\'source_bar_close\')::timestamptz as bar, o.result::text as motivo, o.tracking_state::text as estado, o.r_multiple as r_net, (o.meta->>\'r_ex_funding\')::numeric as r_exf, (o.meta->\'progress\'->>\'entry\')::numeric as p_entry, (o.meta->\'progress\'->>\'exit_base\')::numeric as exit_base, (o.meta->\'excursions\'->>\'initial_risk\')::numeric as risk, (o.meta->\'excursions\'->>\'mfe\')::numeric as mfe_px, (o.meta->\'excursions\'->>\'ambiguous\')::boolean as mfe_ambiguo from signal_outcomes o join agent_signals a on a.id=o.signal_id join strategy_versions sv on sv.id=a.strategy_version_id join strategies s on s.id=sv.strategy_id where o.meta->>\'cohort\' in (\'replay:f8d8279c-1fba-42ae-95ef-202042f96c60\',\'replay:9a08835a-ae13-4c23-b521-734b2f60a3a2\')'
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;

-- 1. motivos de saida: pai vs variante (populacao inteira de cada coorte)
with pop as (:pop)
select coorte, motivo, count(*) as n,
       round(100.0*count(*)/sum(count(*)) over (partition by coorte), 1) as pct,
       round(avg(r_net), 4) as r_liq_medio, round(sum(r_net), 2) as r_liq_soma,
       round(avg((exit_base - p_entry/1.0006)/risk), 4) as r_bruto_medio
  from pop group by 1,2 order by 1, 3 desc;

-- 2. motivos de saida SO nos 193 pares (mesma barra, mesmo mercado)
with pop as (:pop),
     pares as (select p.motivo as motivo_pai, v.motivo as motivo_var, p.r_net as r_pai, v.r_net as r_var
                 from pop p join pop v on v.market_id=p.market_id and v.bar=p.bar
                where p.coorte='f8d8279c' and v.coorte='9a08835a')
select motivo_pai, motivo_var, count(*) as n,
       round(avg(r_var - r_pai), 4) as delta_liq_medio_r, round(sum(r_var - r_pai), 2) as delta_soma_r
  from pares group by 1,2 order by 3 desc;

-- 3. MFE capturado (em R do risco inicial congelado)
with pop as (:pop)
select coorte, count(*) as n,
       count(*) filter (where mfe_ambiguo) as mfe_ambiguos,
       round(avg(mfe_px/risk), 4) as mfe_medio_r,
       round(percentile_cont(0.5) within group (order by mfe_px/risk)::numeric, 4) as mfe_p50_r,
       round(percentile_cont(0.9) within group (order by mfe_px/risk)::numeric, 4) as mfe_p90_r,
       round(avg((exit_base - p_entry/1.0006)/risk), 4) as r_bruto_medio,
       round(avg((exit_base - p_entry/1.0006)/risk)/nullif(avg(mfe_px/risk),0), 4) as fracao_do_mfe_capturada,
       round(100.0*count(*) filter (where mfe_px/risk >= 2.0)/count(*), 1) as pct_mfe_maior_2r,
       round(100.0*count(*) filter (where mfe_px/risk >= 1.0)/count(*), 1) as pct_mfe_maior_1r
  from pop where risk > 0 group by 1 order by 1;

-- 4. o delta pareado por dia (bloco), e o intervalo t de 95% sobre as medias diarias
with pop as (:pop),
     pares as (select p.bar::date as dia, v.r_net - p.r_net as delta
                 from pop p join pop v on v.market_id=p.market_id and v.bar=p.bar
                where p.coorte='f8d8279c' and v.coorte='9a08835a'
                  and p.r_net is not null and v.r_net is not null),
     dia as (select dia, count(*) n, avg(delta) media from pares group by 1)
select count(*) as blocos_dia, round(avg(media), 4) as media_das_medias_diarias,
       round(stddev_samp(media), 4) as desvio, round(stddev_samp(media)/sqrt(count(*)), 4) as erro_padrao,
       round(avg(media) - 2.069*stddev_samp(media)/sqrt(count(*)), 4) as ic95_inferior,
       round(avg(media) + 2.069*stddev_samp(media)/sqrt(count(*)), 4) as ic95_superior,
       count(*) filter (where media > 0) as dias_positivos
  from dia;
commit;
