-- T3.53 q02 — as tabelas descritivas do mapa, direto no SQL (provenância das
-- células que o bootstrap depois julga em `.claude/state/exp-drafts/t353/`).
-- SOMENTE LEITURA. Executável sozinho: o bloco `pop` é repetido de propósito.
--
-- CORTE (as_of): agent_signals.emitted_at < 2026-09-09T02:30:00Z (23:30 BRT).
-- RELÓGIO: `meta->'entry_plan'->>'source_bar_close'` (a última vela fechada que a
-- estratégia leu), nunca `entry_ts` nem `emitted_at`.
-- REGIME: última linha horária do BTC com `end_time <= source_bar_close` — a hora
-- inteira que já fechou antes da barra, nunca a hora em curso.
-- PEDÁGIO: identidade da [[KB-0076]], custo_R = 0,0020 / (risco/preço), que é
-- quantidade pré-trade (só entrada e stop) e portanto filtrável de verdade.
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at_utc, now() at time zone 'America/Sao_Paulo' as read_at_brt;

\set pop 'with reg as (select start_time, end_time, regime::text as regime, supporting_features->>\'trend\' as trend, supporting_features->>\'vol_regime\' as vol from market_regimes where scope=\'btc\' and classifier_version like \'regime_hourly_v1%\'), base as (select s.key as familia, s.key||\' \'||sv.version as versao, case when coalesce(a.supporting_features->>\'cohort\', o.meta->>\'cohort\', \'\') like \'replay:%\' then \'replay\' else \'prospective\' end as coorte, m.symbol, (o.meta->\'entry_plan\'->>\'source_bar_close\')::timestamptz as bar, o.result::text as motivo, o.r_multiple as r_net, (o.meta->>\'r_ex_funding\')::numeric as r_exf, (o.meta->\'progress\'->>\'entry\')::numeric as p_entry, (o.meta->\'progress\'->>\'exit_base\')::numeric as exit_base, (o.meta->\'excursions\'->>\'initial_risk\')::numeric as risk from signal_outcomes o join agent_signals a on a.id=o.signal_id join markets m on m.id=a.market_id join strategy_versions sv on sv.id=a.strategy_version_id join strategies s on s.id=sv.strategy_id where a.emitted_at < timestamptz \'2026-09-09 02:30:00+00\' and o.tracking_state=\'terminal\' and o.r_multiple is not null) select b.*, coalesce(r.regime,\'SEM_LINHA\') as regime, coalesce(r.trend,\'sem_linha\')||\'/\'||coalesce(r.vol,\'sem_linha\') as trend_vol, extract(hour from (b.bar at time zone \'America/Sao_Paulo\'))::int as hora_br, extract(hour from (b.bar at time zone \'UTC\'))::int as hora_utc, extract(isodow from (b.bar at time zone \'America/Sao_Paulo\'))::int as dow_br, (b.bar at time zone \'America/Sao_Paulo\')::date as dia_br, 0.0020/nullif(b.risk/nullif(b.p_entry,0),0) as custo_id, (b.exit_base - b.p_entry/1.0006)/nullif(b.risk,0) as r_gross from base b left join lateral (select * from reg where reg.end_time <= b.bar order by reg.end_time desc limit 1) r on true'

\echo ''
\echo '== 2a. ITEM 4 DO BRIEF: expectancy por rotulo de regime, por familia x coorte =='
with pop as (:pop)
select familia, coorte, regime, count(*) as n,
       round(100.0*count(*)/sum(count(*)) over (partition by familia, coorte),1) as pct_da_pop,
       count(distinct dia_br) as dias,
       round(avg(r_net),4) as exp_liquida_r,
       round(avg(r_gross),4) as exp_bruta_r,
       round(avg(custo_id),4) as pedagio_r,
       round(sum(r_net),2) as soma_r,
       round(100.0*count(*) filter (where motivo='target')/count(*),1) as acerto_pct,
       round(sum(r_net) filter (where r_net>0)/nullif(-sum(r_net) filter (where r_net<0),0),3) as pf
  from pop group by 1,2,3 order by 1,2,4 desc;

\echo ''
\echo '== 2a2. fatia UNKNOWN por familia x coorte (o buraco de contexto, explicito) =='
with pop as (:pop)
select familia, coorte, count(*) as n,
       count(*) filter (where regime='UNKNOWN') as n_unknown,
       round(100.0*count(*) filter (where regime='UNKNOWN')/count(*),1) as pct_unknown,
       count(*) filter (where regime='SEM_LINHA') as n_sem_linha,
       min(dia_br) filter (where regime='UNKNOWN') as unknown_de,
       max(dia_br) filter (where regime='UNKNOWN') as unknown_ate
  from pop group by 1,2 order by 1,2;

\echo ''
\echo '== 2b. trend x vol por familia x coorte (a celula fina que o regime agrega) =='
with pop as (:pop)
select familia, coorte, trend_vol, count(*) as n, count(distinct dia_br) as dias,
       round(avg(r_net),4) as exp_liquida_r, round(avg(r_gross),4) as exp_bruta_r,
       round(sum(r_net),2) as soma_r
  from pop group by 1,2,3 having count(*) >= 10 order by 1,2,4 desc;

\echo ''
\echo '== 2c. hora do dia (UMA particao, dois relogios) — familias com coorte de replay =='
with pop as (:pop)
select familia, coorte, hora_br, hora_utc, count(*) as n, count(distinct dia_br) as dias,
       round(avg(r_net),4) as exp_liquida_r, round(sum(r_net),2) as soma_r
  from pop where coorte='replay'
 group by 1,2,3,4 having count(*) >= 20 order by 1,2,3;

\echo ''
\echo '== 2d. dia da semana (Brasilia) x coorte de replay =='
with pop as (:pop)
select familia, coorte, dow_br,
       case dow_br when 1 then 'seg' when 2 then 'ter' when 3 then 'qua' when 4 then 'qui'
                   when 5 then 'sex' when 6 then 'sab' else 'dom' end as dia,
       count(*) as n, count(distinct dia_br) as dias_distintos,
       round(avg(r_net),4) as exp_liquida_r, round(sum(r_net),2) as soma_r
  from pop where coorte='replay' group by 1,2,3 order by 1,2,3;

\echo ''
\echo '== 2e. faixa de pedagio (KB-0076) por familia x coorte =='
with pop as (:pop)
select familia, coorte,
       case when custo_id < 0.10 then 'a) < 0,10 R'
            when custo_id <= 0.20 then 'b) 0,10-0,20 R'
            else 'c) > 0,20 R' end as faixa,
       count(*) as n, count(distinct dia_br) as dias,
       round(avg(custo_id),4) as pedagio_medio,
       round(avg(r_net),4) as exp_liquida_r, round(avg(r_gross),4) as exp_bruta_r,
       round(sum(r_net),2) as soma_r
  from pop group by 1,2,3 order by 1,2,3;

\echo ''
\echo '== 2f. tamanho de celula: quantas celulas de cada dimensao alcancam n>=30 E >=7 dias =='
with pop as (:pop), c as (
  select versao, coorte, 'mercado' as dim, symbol as celula, count(*) n, count(distinct dia_br) d
    from pop group by 1,2,4
  union all
  select versao, coorte, 'hora', hora_br::text, count(*), count(distinct dia_br) from pop group by 1,2,4
  union all
  select versao, coorte, 'dia_semana', dow_br::text, count(*), count(distinct dia_br) from pop group by 1,2,4
  union all
  select versao, coorte, 'regime', regime, count(*), count(distinct dia_br) from pop group by 1,2,4
  union all
  select versao, coorte, 'trend_x_vol', trend_vol, count(*), count(distinct dia_br) from pop group by 1,2,4
  union all
  select versao, coorte, 'pedagio',
         case when custo_id < 0.10 then '<0,10' when custo_id <= 0.20 then '0,10-0,20' else '>0,20' end,
         count(*), count(distinct dia_br)
    from pop group by 1,2,4
), pops as (
  select versao, coorte, count(*) n_pop from pop group by 1,2
)
select c.versao, c.coorte, c.dim, count(*) as celulas,
       count(*) filter (where c.n >= 30) as com_n30,
       count(*) filter (where c.n >= 30 and c.d >= 7) as julgaveis
  from c join pops p on p.versao=c.versao and p.coorte=c.coorte and p.n_pop >= 100
 group by 1,2,3 order by 1,2,3;

\echo ''
\echo '== 2g. robustez da juncao de regime: end_time <= barra  VS  janela que contem a barra =='
with reg as (
  select start_time, end_time, regime::text as regime from market_regimes
   where scope='btc' and classifier_version like 'regime_hourly_v1%'
), base as (
  select (o.meta->'entry_plan'->>'source_bar_close')::timestamptz as bar
    from signal_outcomes o join agent_signals a on a.id=o.signal_id
   where a.emitted_at < timestamptz '2026-09-09 02:30:00+00'
     and o.tracking_state='terminal' and o.r_multiple is not null
), j as (
  select b.bar,
         (select r.regime from reg r where r.end_time <= b.bar order by r.end_time desc limit 1) as anterior,
         (select r.regime from reg r where b.bar >= r.start_time and b.bar < r.end_time) as contem
    from base b
)
select count(*) as n,
       count(*) filter (where anterior is distinct from contem) as divergem,
       round(100.0*count(*) filter (where anterior is distinct from contem)/count(*),2) as pct_divergem,
       count(*) filter (where anterior is null) as sem_anterior,
       count(*) filter (where contem is null) as sem_contem
  from j;
commit;
