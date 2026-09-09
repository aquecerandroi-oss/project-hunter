-- T3.52d q10 — populacoes pai x filha-com-portao, mesma janela (31 d), mesmos 4 mercados.
-- Metodo identico ao da T3.54 q10 / T3.47 q01 (KB-0076 com a correcao da notes-T3.40 8b).
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;
with pop as (
  select s.key||' '||sv.version as versao,
         left(split_part(o.meta->>'cohort', ':', 2), 8) as coorte,
         m.symbol,
         (o.meta->'entry_plan'->>'source_bar_close')::timestamptz as bar,
         o.result::text as motivo,
         o.r_multiple as r_net,
         (o.meta->>'r_ex_funding')::numeric as r_exf,
         (o.meta->'progress'->>'entry')::numeric as p_entry,
         (o.meta->'progress'->>'exit_base')::numeric as exit_base,
         (o.meta->'excursions'->>'initial_risk')::numeric as risk,
         (o.meta->'entry_plan'->>'source_bar_close')::timestamptz::date as dia
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join markets m on m.id = a.market_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id
   where o.meta->>'cohort' in (
           'replay:9d99748b-21b9-44a7-8980-32c37b931e6e',
           'replay:5bcfbda1-9365-467e-ad14-583fcfa9ae4b',
           'replay:ee11d60b-3a4e-48be-94a3-1aecb8cf16fd',
           'replay:4a60a3dc-334c-4faa-9790-c321063ff23e',
           'replay:71c76d86-ceb0-4d48-b3be-88c3c055061e',
           'replay:fc9e2506-b812-4f07-a2fa-89ce4671a8bf')
     and o.tracking_state::text = 'terminal'
     and o.r_multiple is not null
), c as (
  select *, (exit_base - p_entry/1.0006)/nullif(risk, 0) as r_bruto,
            (exit_base - p_entry/1.0006)/nullif(risk, 0) - r_exf as custo_r,
            risk/nullif(p_entry, 0) as risco_pct
    from pop
)
select versao, coorte, count(*) as n, count(distinct dia) as dias,
       min(bar) as primeira_barra, max(bar) as ultima_barra,
       round(avg(custo_r), 4) as custo_r_medio,
       round(avg(r_bruto), 4) as exp_bruta_r,
       round(avg(r_net), 4) as exp_liquida_r,
       round(sum(r_net), 2) as soma_r,
       round(sum(r_net) filter (where r_net > 0)
             / nullif(-sum(r_net) filter (where r_net < 0), 0), 4) as pf_liquido,
       round(100.0 * count(*) filter (where r_net > 0) / count(*), 1) as acerto_pct,
       round((percentile_cont(0.5) within group (order by risco_pct))::numeric, 5) as risco_pct_p50
  from c
 group by 1, 2
 order by 1, 2;
commit;
