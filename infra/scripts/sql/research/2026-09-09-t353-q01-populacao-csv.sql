-- T3.53 q01 — a população, uma linha por desfecho, em CSV no stdout do psql.
-- SOMENTE LEITURA. Nada é escrito na VPS; o CSV volta pelo ssh e é analisado
-- em `.claude/state/exp-drafts/t353/`.
--
-- CORTE (as_of): agent_signals.emitted_at < 2026-09-09T02:30:00Z (23:30 BRT).
--
-- O RELÓGIO É A BARRA DE ORIGEM (`meta->'entry_plan'->>'source_bar_close'`), a
-- última vela fechada que a estratégia leu — não `entry_ts` (que é posterior) e
-- não `emitted_at` (que carrega latência de fila). Hora do dia, dia da semana e
-- junção com regime saem todos dela.
--
-- REGIME SEM ANTECIPAÇÃO: a linha horária escolhida é a ÚLTIMA com
-- `end_time <= source_bar_close` — a hora inteira que já fechou antes da barra,
-- nunca a hora em curso. É mais conservador que a junção por contenção
-- (`start_time <= bar < end_time`) usada em `2026-09-09-regime-split.sql`:
-- aquela também é honesta pelo PIPELINE §4b (o rótulo da hora sai de velas
-- fechadas ANTES do início dela), esta não depende dessa garantia.
--
-- PEDÁGIO (`custo_id`): identidade da [[KB-0076]], custo_R = 0,0020 / (risco/preço).
-- É uma quantidade PRÉ-TRADE (só preço de entrada e stop), então um filtro sobre
-- ela é implementável. `custo_medido` = r_gross - r_ex_funding é a verificação.
--
-- Colunas: signal_id,familia,versao,coorte,symbol,bar_utc,dia_br,hora_br,hora_utc,
--          dow_br,regime,trend,vol,custo_id,custo_medido,r_gross,r_exf,r_net,motivo,
--          p_entry,risk,risco_pct
begin transaction isolation level repeatable read read only;

copy (
  with reg as (
    select start_time, end_time, regime::text as regime,
           supporting_features->>'trend' as trend,
           supporting_features->>'vol_regime' as vol
      from market_regimes
     where scope = 'btc' and classifier_version like 'regime_hourly_v1%'
  ), pop as (
    select o.signal_id,
           s.key as familia,
           s.key || ' ' || sv.version as versao,
           case when coalesce(a.supporting_features->>'cohort', o.meta->>'cohort', '') like 'replay:%'
                then 'replay' else 'prospective' end as coorte,
           m.symbol,
           (o.meta->'entry_plan'->>'source_bar_close')::timestamptz as bar,
           o.result::text as motivo,
           o.r_multiple as r_net,
           (o.meta->>'r_ex_funding')::numeric as r_exf,
           (o.meta->'progress'->>'entry')::numeric as p_entry,
           (o.meta->'progress'->>'exit_base')::numeric as exit_base,
           (o.meta->'excursions'->>'initial_risk')::numeric as risk
      from signal_outcomes o
      join agent_signals a      on a.id  = o.signal_id
      join markets m            on m.id  = a.market_id
      join strategy_versions sv on sv.id = a.strategy_version_id
      join strategies s         on s.id  = sv.strategy_id
     where a.emitted_at < timestamptz '2026-09-09 02:30:00+00'
       and o.tracking_state = 'terminal'
       and o.r_multiple is not null
  )
  select p.signal_id, p.familia, p.versao, p.coorte, p.symbol,
         to_char(p.bar at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as bar_utc,
         to_char(p.bar at time zone 'America/Sao_Paulo', 'YYYY-MM-DD')   as dia_br,
         extract(hour from (p.bar at time zone 'America/Sao_Paulo'))::int as hora_br,
         extract(hour from (p.bar at time zone 'UTC'))::int               as hora_utc,
         extract(isodow from (p.bar at time zone 'America/Sao_Paulo'))::int as dow_br,
         coalesce(r.regime, 'SEM_LINHA') as regime,
         coalesce(r.trend, 'sem_linha')  as trend,
         coalesce(r.vol, 'sem_linha')    as vol,
         round(0.0020 / nullif(p.risk / nullif(p.p_entry, 0), 0), 6)                     as custo_id,
         round((p.exit_base - p.p_entry / 1.0006) / nullif(p.risk, 0) - p.r_exf, 6)      as custo_medido,
         round((p.exit_base - p.p_entry / 1.0006) / nullif(p.risk, 0), 6)                as r_gross,
         round(p.r_exf, 6) as r_exf,
         round(p.r_net, 6) as r_net,
         p.motivo,
         p.p_entry, p.risk,
         round(p.risk / nullif(p.p_entry, 0), 6) as risco_pct
    from pop p
    left join lateral (
      select * from reg where reg.end_time <= p.bar order by reg.end_time desc limit 1
    ) r on true
   order by p.versao, p.coorte, p.bar
) to stdout with (format csv, header true);

commit;
