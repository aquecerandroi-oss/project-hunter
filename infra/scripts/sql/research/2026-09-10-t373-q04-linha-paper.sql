-- T3.73 q04 -- A LINHA PAPER: QUAIS VERSOES TEM `purpose = 'paper'`, EM QUE
-- TIPO DE MERCADO ELAS DECIDEM, E EM QUE MERCADO A CARTEIRA EXECUTOU.
-- (a ponte de execucao mapeia o perpetuo para o par SPOT -- bridge_universe.spot_pair_for)
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off

-- 1. catalogo por purpose
select s.key || ' ' || sv.version as versao, sv.purpose, sv.status::text as status,
       sv.activated_at
  from strategy_versions sv
  join strategies s on s.id = sv.strategy_id
 where sv.purpose <> 'research_only' or sv.status = 'active'
 order by sv.purpose, 1;

-- 2. sinais das versoes paper por tipo de mercado
select s.key || ' ' || sv.version as versao, mk.market_type::text as tipo, count(*) as sinais
  from agent_signals a
  join markets mk           on mk.id = a.market_id
  join strategy_versions sv on sv.id = a.strategy_version_id
  join strategies s         on s.id = sv.strategy_id
 where sv.purpose = 'paper'
 group by 1, 2 order by 1, 2;

-- 3. as operacoes da carteira paper por tipo de mercado
select mk.market_type::text as tipo, count(*) as trades,
       min(pt.opened_at) as primeiro, max(pt.opened_at) as ultimo
  from paper_trades pt
  join markets mk on mk.id = pt.market_id
 group by 1 order by 1;

commit;
