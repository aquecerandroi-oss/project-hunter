-- T3.53 q03 — a junção de regime é sensível à convenção?
-- SOMENTE LEITURA. Duas leituras honestas da mesma série horária:
--   (a) `anterior`: última linha com `end_time <= source_bar_close` — a hora
--       inteira que já fechou antes da barra (a convenção desta nota);
--   (b) `contem` : a linha cuja janela [start_time, end_time) contém a barra
--       (a convenção de `2026-09-09-regime-split.sql`, honesta pelo PIPELINE §4b
--       porque o rótulo da hora sai de velas fechadas ANTES do início dela).
-- Se as duas quase nunca divergem, a escolha não muda nenhuma conclusão.
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at_utc;
with reg as (
  select start_time, end_time, regime::text as regime from market_regimes
   where scope='btc' and classifier_version like 'regime_hourly_v1%'
), base as (
  select (o.meta->'entry_plan'->>'source_bar_close')::timestamptz as bar
    from signal_outcomes o join agent_signals a on a.id=o.signal_id
   where a.emitted_at < timestamptz '2026-09-09 02:30:00+00'
     and o.tracking_state='terminal' and o.r_multiple is not null
), j as (
  select b.bar, ant.regime as anterior, cont.regime as contem
    from base b
    left join lateral (select r.regime from reg r where r.end_time <= b.bar
                        order by r.end_time desc limit 1) ant on true
    left join lateral (select r.regime from reg r
                        where b.bar >= r.start_time and b.bar < r.end_time limit 1) cont on true
)
select count(*) as n,
       count(*) filter (where anterior is distinct from contem) as divergem,
       round(100.0*count(*) filter (where anterior is distinct from contem)/count(*),2) as pct_divergem,
       count(*) filter (where anterior is null) as sem_anterior,
       count(*) filter (where contem is null) as sem_contem
  from j;
commit;
