-- D-P24 q02 -- DUMP (CSV) do CAMINHO minuto a minuto das 542 decisoes da mae:
-- uma linha por (decisao, minuto), 542 x 240 = 130 080 linhas se a fita estiver
-- inteira (o q00 §4 mediu: 542/542 com os 240 minutos, 0 faltando).
--
-- Por que este arquivo existe, sendo que o q01 ja traz os extremos. Porque as
-- excursoes sao ARITMETICA, e a aritmetica desta tarefa tem de rodar no modulo
-- testado (`.claude/state/exp-drafts/dp24/decomp.py`, 36 testes com valores
-- calculados a mao), nao dentro de um `filter (where ...)` que ninguem consegue
-- testar. O q01 calcula os mesmos extremos em SQL e o `analise.py` compara as
-- duas leituras decisao a decisao: DUAS IMPLEMENTACOES INDEPENDENTES da mesma
-- definicao, que e o substituto empirico honesto para o teste de antecipacao
-- contra Postgres (`test_replay_lookahead.py`) que este brief nao autoriza
-- (ele e `@pytest.mark.integration` e precisa de testcontainer).
--
-- `m` = o minuto em que a vela FECHA, contado da entrada: a vela `m` abre em
-- `entry_ts + (m-1) min` e fecha em `entry_ts + m min`. `m` vai de 1 a 240.
-- E a mesma convencao de `curva.endpoint_open_time` do D-P23, escrita do outro
-- lado -- la o indice era o `open_time`, aqui e o fechamento -- e e o que faz o
-- ponto de "+80 min" ser a vela que FECHA aos 80, nunca a que ABRE aos 80 (que
-- fecharia aos 81 e, no instante medido, ainda estava em formacao).
--
-- Vela obrigatoriamente `is_final` e `timeframe = '1m'` (PIPELINE §2). Minuto
-- ausente simplesmente NAO APARECE -- nunca preenchido com o fechamento
-- anterior -- e o consumidor declara a cobertura.
-- Juncao por `agent_signals.market_id` (o defeito do D-P23: `markets` tem duas
-- linhas por simbolo na binance).
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset format unaligned
\pset fieldsep ','
\pset tuples_only off

with base as (
  select o.signal_id, a.market_id, o.entry_ts
    from signal_outcomes o
    join agent_signals a      on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id = sv.strategy_id
   where o.meta->>'cohort' = 'replay:fa005985-0b55-4820-904c-8ada589e441c'
     and s.key = 'mean_reversion' and sv.version = 'v1'
     and o.tracking_state::text = 'terminal'
)
select b.signal_id                                                        as decisao,
       ((extract(epoch from (c.open_time - b.entry_ts)) / 60.0)::int + 1) as m,
       c.close                                                            as fechamento
  from base b
  join candles c on c.market_id = b.market_id and c.timeframe = '1m' and c.is_final
                and c.open_time >= b.entry_ts
                and c.open_time <  b.entry_ts + interval '240 min'
 order by b.signal_id, m;

commit;
