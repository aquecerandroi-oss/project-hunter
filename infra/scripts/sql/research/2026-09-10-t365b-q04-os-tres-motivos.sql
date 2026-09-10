-- T3.65b q04 -- OS TRES MOTIVOS QUE SOBRAM NO CODIGO ATUAL, um por um.
-- Depois da q02 (a coorte `d82356d9` e PRE-T3.65: leu 3600 onde a atual le 14400)
-- restam, nos tres mercados de 4 h e sob o codigo de hoje:
--   (i)  5x `funding_schedule_unknown` em PROMUSDT, prospective, 09/09;
--   (ii) 1x `funding_missing:2026-09-09T00:00:00.002` em TAOUSDT, prospective;
--   (iii)5x `funding_ambiguous_exit` em PROMUSDT, 2026-08-23 23:01 -> 00:01.
-- Esta consulta testa a explicacao de cada um SEM presumir nenhuma:
--   (i)  o mercado do sinal e PERPETUO ou SPOT? (spot nao tem funding_rates)
--   (ii) a linha real de 2026-09-09 00:00:00.005 dista 3 ms do instante nominal
--        cobrado -- dentro da tolerancia de 2 s -- logo ela NAO estava no banco
--        quando o desfecho liquidou (atraso de coleta), nao ha erro de cadencia;
--   (iii)ha assentamento dentro da barra de saida? (o guarda e por desenho)
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

-- (i) tipo de mercado dos desfechos `funding_schedule_unknown` de 09/09
select m.symbol, m.market_type, o.entry_ts, o.exit_ts,
       o.meta->>'r_net_reason' as motivo
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
  join markets m on m.id = a.market_id
 where o.tracking_state = 'terminal'
   and o.entry_ts >= timestamptz '2026-09-09 00:00+00'
   and m.symbol in ('PROMUSDT','SAHARAUSDT','TAOUSDT')
   and o.meta->>'r_net_reason' like 'funding_schedule_unknown%'
 order by o.entry_ts;

-- (i-b) o universo por tipo: quantos desfechos de cada tipo de mercado, e
--       quantos deles caem em `funding_schedule_unknown`
select m.market_type,
       count(*)                                                               as terminais,
       count(*) filter (where o.meta->>'r_net_reason' like 'funding_schedule%') as schedule_unknown
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
  join markets m on m.id = a.market_id
 where o.tracking_state = 'terminal'
   and m.symbol in ('PROMUSDT','SAHARAUSDT','TAOUSDT')
   and o.entry_ts >= timestamptz '2026-09-05 00:00+00'
 group by 1
 order by 1;

-- (iii) o assentamento dentro da barra de saida do `funding_ambiguous_exit`
select m.symbol, f.funding_time, f.rate, f.mark_price
  from funding_rates f
  join markets m on m.id = f.market_id
 where m.symbol = 'PROMUSDT'
   and f.funding_time >= timestamptz '2026-08-23 20:00+00'
   and f.funding_time <= timestamptz '2026-08-24 04:00+00'
 order by f.funding_time;

commit;
