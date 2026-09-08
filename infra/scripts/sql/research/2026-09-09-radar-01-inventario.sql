-- T3.46 Q1 — inventário do Radar: quantas anomalias e quantos scores existem,
-- desde quando, em que mercados, e como o score se distribui.
--
-- SOMENTE LEITURA (repeatable read read only). Executável sozinho.
--
-- O QUE ESTA CONSULTA USA
--   `anomalies`            (PIPELINE §3) — um episódio por (market, type) enquanto ativo.
--   `opportunities`        (PIPELINE §5) — um episódio aberto por mercado (uq ... WHERE expired_at IS NULL).
--   `opportunity_history`  — a série de amostras do score (>= 3 pontos de mudança ou troca de status).
--   `feature_baselines`    — mediana + MAD por (mercado, feature, hora do dia), a base dos detectores.
--
-- LEITURA HONESTA. O `Radar` é jovem: o que a tabela não tem não é "nada
-- aconteceu", é "ninguém estava medindo". Por isso a primeira coluna de tudo
-- aqui é a data, e a janela do estudo é a interseção — nunca a união.
\pset border 2
\pset numericlocale off

begin transaction isolation level repeatable read read only;

\echo '== 0. corte da leitura =='
select now() as read_at, current_database() as db;

\echo ''
\echo '== 1a. anomalias por dia (UTC) =='
select date_trunc('day', detected_at)::date as dia,
       count(*) as anomalias,
       count(distinct market_id) as mercados,
       count(distinct type) as tipos,
       round(avg(severity), 1) as sev_media,
       max(severity) as sev_max
  from anomalies
 group by 1 order by 1;

\echo ''
\echo '== 1b. anomalias por tipo (janela inteira) =='
select type::text as tipo,
       count(*) as n,
       count(distinct market_id) as mercados,
       round(avg(severity), 1) as sev_media,
       round(percentile_cont(0.5) within group (order by severity)::numeric, 1) as sev_p50,
       max(severity) as sev_max,
       round(avg(confidence), 3) as conf_media,
       count(*) filter (where status = 'active') as ativas,
       count(*) filter (where status = 'resolved') as resolvidas,
       count(*) filter (where status = 'expired') as expiradas,
       count(*) filter (where evaluation_state <> 'ok') as dado_suspeito
  from anomalies
 group by 1 order by 2 desc;

\echo ''
\echo '== 1c. concentração por mercado (top 15 + cauda) =='
with por_mercado as (
  select m.symbol, count(*) n
    from anomalies a join markets m on m.id = a.market_id
   group by 1
)
select symbol, n, round(100.0 * n / sum(n) over (), 2) as pct
  from por_mercado
 order by n desc limit 15;

\echo ''
\echo '== 1d. cobertura: mercados monitorados x mercados com anomalia x com score =='
select (select count(*) from markets where is_monitored) as monitorados,
       (select count(distinct market_id) from anomalies) as com_anomalia,
       (select count(distinct market_id) from opportunities) as com_oportunidade,
       (select count(distinct market_id) from feature_baselines) as com_baseline;

\echo ''
\echo '== 2a. episódios de oportunidade por dia e por status vigente =='
select date_trunc('day', first_seen_at)::date as dia,
       count(*) as episodios,
       count(distinct market_id) as mercados,
       count(*) filter (where expired_at is null) as abertos,
       round(avg(score), 1) as score_medio,
       round(max(peak_score), 1) as pico
  from opportunities
 group by 1 order by 1;

\echo ''
\echo '== 2b. amostras de score (opportunity_history) por dia e por status =='
select date_trunc('day', ts)::date as dia,
       status::text as status,
       count(*) as amostras,
       round(avg(score), 1) as score_medio
  from opportunity_history
 group by 1, 2 order by 1, 2;

\echo ''
\echo '== 2c. estágio (opportunity_stage) das amostras =='
select stage::text as estagio, count(*) as amostras,
       round(avg(score), 1) as score_medio, round(avg(confidence), 3) as conf_media
  from opportunity_history group by 1 order by 2 desc;

\echo ''
\echo '== 3. decis do score (sobre opportunity_history, a série completa) =='
with d as (
  select score, ntile(10) over (order by score) as decil from opportunity_history
)
select decil, count(*) as amostras,
       round(min(score), 2) as score_min,
       round(max(score), 2) as score_max,
       round(avg(score), 2) as score_medio
  from d group by 1 order by 1;

\echo ''
\echo '== 3b. o score é ranqueado? faixas do Radar (PIPELINE §5) =='
select case when score < 40 then 'a) <40 NORMAL'
            when score < 60 then 'b) 40-60 WATCHING'
            when score < 75 then 'c) 60-75'
            when score < 80 then 'd) 75-80 HOT'
            else 'e) >=80 ENTRY_CANDIDATE' end as faixa,
       count(*) as amostras,
       round(100.0 * count(*) / sum(count(*)) over (), 2) as pct
  from opportunity_history group by 1 order by 1;

\echo ''
\echo '== 4. pesos vigentes (opportunity_weights) =='
select version, is_active, weights::text as pesos from opportunity_weights order by is_active desc, version;

\echo ''
\echo '== 5. baselines: cobertura e maturidade =='
select algo_version, sampling::text as amostragem, source::text as fonte,
       count(*) as linhas, count(distinct market_id) as mercados, count(distinct feature) as features,
       round(avg(coverage), 3) as cobertura_media,
       round(avg(distinct_days), 2) as dias_distintos_media
  from feature_baselines group by 1,2,3 order by 4 desc;

commit;
