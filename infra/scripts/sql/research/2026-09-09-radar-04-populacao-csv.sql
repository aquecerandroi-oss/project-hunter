-- T3.46 — a mesma populacao da consulta 02 (desfechos do Lab cobertos pelo
-- Radar) exportada em CSV para o bootstrap por blocos.
--
-- SOMENTE LEITURA. Saida em CSV pelo psql (`--csv`), sem `\copy` para arquivo do
-- servidor: quem grava e o cliente.
--
-- COLUNAS
--   dia          data UTC da decisao          (bloco do bootstrap "por dia")
--   hora         hora UTC da decisao          (bloco do bootstrap "por hora")
--   versao/coorte/simbolo
--   anom_4b/16b/96b   1/0 — havia anomalia detectada nos 60/240/1440 min ANTES da decisao
--   score_dec    score de oportunidade da ultima amostra <= decisao (janela de 15 min)
--   r_net        signal_outcomes.r_multiple (custo + funding)
--   r_gross      (exit_base - p_entry/1.0006)/risk
--
-- So entram desfechos COBERTOS (score_dec nao nulo): fora deles "sem anomalia"
-- significa "o scanner nao olhava esse mercado".
select p.dia, p.hora, p.versao, p.coorte, p.symbol,
       (p.anom_4b)::int  as anom_4b,
       (p.anom_16b)::int as anom_16b,
       (p.anom_96b)::int as anom_96b,
       round(p.score_dec, 4) as score_dec,
       round(p.r_net, 6) as r_net,
       round(p.r_gross, 6) as r_gross
  from (
    select (a.supporting_features->>'decision_at')::timestamptz::date as dia,
           to_char(date_trunc('hour', (a.supporting_features->>'decision_at')::timestamptz),
                   'YYYY-MM-DD HH24') as hora,
           s.key || ' ' || sv.version as versao,
           case when o.meta->>'cohort' like 'replay:%' then 'replay' else 'prospective' end as coorte,
           m.symbol,
           exists (select 1 from anomalies an where an.market_id = a.market_id
                    and an.detected_at <= (a.supporting_features->>'decision_at')::timestamptz
                    and an.detected_at >  (a.supporting_features->>'decision_at')::timestamptz
                                          - interval '60 minutes')   as anom_4b,
           exists (select 1 from anomalies an where an.market_id = a.market_id
                    and an.detected_at <= (a.supporting_features->>'decision_at')::timestamptz
                    and an.detected_at >  (a.supporting_features->>'decision_at')::timestamptz
                                          - interval '240 minutes')  as anom_16b,
           exists (select 1 from anomalies an where an.market_id = a.market_id
                    and an.detected_at <= (a.supporting_features->>'decision_at')::timestamptz
                    and an.detected_at >  (a.supporting_features->>'decision_at')::timestamptz
                                          - interval '1440 minutes') as anom_96b,
           (select oh.score from opportunity_history oh
              join opportunities op on op.id = oh.opportunity_id
             where op.market_id = a.market_id
               and oh.ts <= (a.supporting_features->>'decision_at')::timestamptz
               and oh.ts >  (a.supporting_features->>'decision_at')::timestamptz - interval '15 minutes'
             order by oh.ts desc limit 1)                            as score_dec,
           o.r_multiple as r_net,
           case when (o.meta->'excursions'->>'initial_risk')::numeric > 0
                then ((o.meta->'progress'->>'exit_base')::numeric
                      - (o.meta->'progress'->>'entry')::numeric / 1.0006)
                     / (o.meta->'excursions'->>'initial_risk')::numeric end as r_gross
      from signal_outcomes o
      join agent_signals a on a.id = o.signal_id
      join markets m on m.id = a.market_id
      join strategy_versions sv on sv.id = a.strategy_version_id
      join strategies s on s.id = sv.strategy_id
     where o.tracking_state = 'terminal' and o.r_multiple is not null
       and (a.supporting_features->>'decision_at')::timestamptz
           >= (select min(detected_at) from anomalies)
  ) p
 where p.score_dec is not null
 order by p.dia, p.hora, p.versao;
