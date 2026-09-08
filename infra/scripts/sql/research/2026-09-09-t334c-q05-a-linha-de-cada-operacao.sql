-- =====================================================================================
-- T3.34c q05 — "cada operacao traca as linhas?" (a pergunta do Everton, §6 do brief)
-- SOMENTE LEITURA. Prova por dado, nao por afirmacao: uma decisao desta versao carrega
-- TUDO o que e preciso para redesenhar a linha exata que a produziu.
--   line_id, line_kind, slope_per_bar, first_idx/last_idx/valid_from_idx,
--   line_price_at_decision, pivot_low_price/idx, pattern_bars/pivots/lines/retired,
--   e o registro inteiro de parametros da geometria (`pattern_params`).
-- A ultima consulta mostra que NENHUMA outra versao viva persiste `line_id`.
-- =====================================================================================
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;

-- 1. tres decisoes, campo a campo (o que o overlay do Lab da T3.49 vai ler)
select m.symbol,
       (o.meta->'entry_plan'->>'source_bar_close')::timestamptz as bar,
       agg.j->>'event_kind'              as evento,
       agg.j->>'line_kind'               as tipo_da_linha,
       agg.j->>'line_id'                 as line_id,
       agg.j->>'line_slope_per_bar'      as inclinacao_por_barra,
       agg.j->>'line_first_idx'          as primeiro_idx,
       agg.j->>'line_last_idx'           as ultimo_idx,
       agg.j->>'line_valid_from_idx'     as valido_desde_idx,
       agg.j->>'line_touches'            as toques,
       agg.j->>'line_violations'         as violacoes,
       agg.j->>'line_price_at_decision'  as preco_da_linha_na_decisao,
       agg.j->>'pivot_low_price'         as pivo_de_baixa,
       agg.j->>'pivot_low_idx'           as pivo_idx,
       agg.j->>'pattern_bars'            as barras_do_padrao,
       agg.j->>'pattern_pivots'          as pivos,
       agg.j->>'pattern_lines'           as linhas,
       agg.j->>'pattern_retired_lines'   as aposentadas,
       agg.j->>'channel_width_atr'       as canal_atr
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
  join markets m on m.id = a.market_id
  cross join lateral (select jsonb_object_agg(e->>'name', e->>'value') as j
                        from jsonb_array_elements(a.supporting_features->'features') e) agg
 where o.meta->>'cohort' = 'replay:d78c14d1-b4c5-424a-8f31-a43100744bb4'
 order by bar limit 3;

-- 2. o registro de parametros da geometria de UMA decisao, inteiro
select agg.j->>'pattern_params' as pattern_params
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
  cross join lateral (select jsonb_object_agg(e->>'name', e->>'value') as j
                        from jsonb_array_elements(a.supporting_features->'features') e) agg
 where o.meta->>'cohort' = 'replay:d78c14d1-b4c5-424a-8f31-a43100744bb4'
 order by (o.meta->'entry_plan'->>'source_bar_close')::timestamptz limit 1;

-- 3. cobertura: quantas das 47 decisoes tem a linha inteira? (tem de ser 47)
select count(*) as decisoes,
       count(*) filter (where agg.j ? 'line_id')                  as com_line_id,
       count(*) filter (where agg.j ? 'line_slope_per_bar')       as com_inclinacao,
       count(*) filter (where agg.j ? 'line_price_at_decision')   as com_preco_da_linha,
       count(*) filter (where agg.j ? 'pivot_low_price')          as com_pivo,
       count(*) filter (where agg.j ? 'pattern_params')           as com_parametros,
       count(distinct agg.j->>'line_id')                          as linhas_distintas
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
  cross join lateral (select jsonb_object_agg(e->>'name', e->>'value') as j
                        from jsonb_array_elements(a.supporting_features->'features') e) agg
 where o.meta->>'cohort' = 'replay:d78c14d1-b4c5-424a-8f31-a43100744bb4';

-- 4. e as OUTRAS versoes vivas: nenhuma persiste `line_id` (a resposta honesta ao Everton)
select s.key||' '||sv.version as versao, count(*) as sinais,
       count(*) filter (where a.supporting_features::text like '%line_id%') as com_line_id
  from agent_signals a
  join strategy_versions sv on sv.id = a.strategy_version_id
  join strategies s on s.id = sv.strategy_id
 where a.emitted_at >= timestamptz '2026-09-01 00:00:00+00'
 group by 1 order by 2 desc;

-- 5. a invalidacao publicada em cada sinal (o nivel da linha, `close_below`)
select count(*) as decisoes,
       count(*) filter (where a.invalidations::text like '%close_below%') as com_close_below,
       min(jsonb_array_length(a.invalidations)) as min_invalidacoes,
       max(jsonb_array_length(a.invalidations)) as max_invalidacoes
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
 where o.meta->>'cohort' = 'replay:d78c14d1-b4c5-424a-8f31-a43100744bb4';
commit;
