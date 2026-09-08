-- T3.42 q19 — a ativacao preservou o conteudo proprio da linha derivada? e a linhagem?
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;
with mr as (
  select sv.version, sv.status, sv.purpose, sv.default_parameters as p, sv.parameters_schema as sch, sv.code_ref, sv.changelog
    from strategy_versions sv join strategies s on s.id=sv.strategy_id where s.key='mean_reversion'
), pai as (select * from mr where version='v1')
select mr.version, mr.status, mr.purpose,
       mr.p->>'atr_pct_min' as atr_pct_min, mr.p->>'atr_pct_max' as atr_pct_max,
       mr.p->>'stop_atr' as stop_atr, mr.p->>'target_atr' as target_atr,
       (mr.p - 'atr_pct_min') = (pai.p - 'atr_pct_min') as resto_igual_ao_pai,
       mr.sch = pai.sch as schema_igual,
       mr.code_ref = pai.code_ref as code_ref_igual
  from mr, pai order by mr.version;
select version, changelog from mr_cl;
commit;
