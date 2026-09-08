# Brief (database-architect) — `market_regimes` precisa de `exchange` e de uma chave por hora

**Origem:** T3.43 (produtor horário de regime, `regime_hourly_v1`). **Quem pede:**
quant-engineer. **Nenhuma migração foi escrita nesta tarefa** — a T3.43 tem
`infra/migrations/**` fora de escopo, e o job funciona sem estas mudanças. Isto é o
registro do que ele teve de compensar em código, para que a decisão seja de quem é dona
do esquema.

## O que a T3.43 escreve hoje

Uma linha de `market_regimes` por hora fechada, por exchange:

| coluna | valor |
|---|---|
| `scope` | `btc` (o `regime_v0` vivo ocupa `global` com intervalos abertos) |
| `regime` | projeção do par `{trend, vol_regime}` sobre `market_regime` |
| `confidence` | fração do peso do score que teve componente disponível |
| `start_time` / `end_time` | `ts` e `ts + 1h` — **sempre fechada** |
| `classifier_version` | `regime_hourly_v1` (ou `regime_hourly_v1+<digest>` com limiar sobrescrito) |
| `supporting_features` | o snapshot inteiro: par, cinco componentes com `raw`/`normalized`/`weight`/`contribution`, entradas, limiares, `exchange`, `digest` |

## O que falta no esquema, e como o job compensa

1. **Não há coluna `exchange`.** A identidade de uma hora é `(exchange, ts)`, e hoje o
   exchange vive dentro do JSONB. O job procura a hora com
   `supporting_features ->> 'exchange' = :exchange`, o que funciona e **não é indexável
   por igualdade barata** (hoje é aceitável: uma exchange, 744 linhas por backfill).
   *Pedido:* `exchange_id UUID REFERENCES exchanges(id)`, `NULL` para as linhas do
   `regime_v0` (que é global por construção).
2. **Não há unicidade por hora.** Sem índice, dois produtores no mesmo segundo inserem a
   mesma hora duas vezes, e qualquer leitura por contenção de intervalo passa a contar
   em dobro. O job fecha essa corrida com a trava Redis
   `regime:producer:{exchange}:{corte}` — economia de banco não é integridade, e está
   dito assim no módulo. *Pedido:* índice único parcial
   `(scope, classifier_version, exchange_id, start_time) WHERE end_time IS NOT NULL`,
   que deixa o `uq_market_regimes_open_per_scope` do `regime_v0` intacto.
3. **`supporting_features` não tem índice.** As consultas de pesquisa filtram por
   `scope`/`classifier_version` (já há `ix_market_regimes_scope_start`) e juntam por
   `start_time <= entry_ts < end_time`. Um `GIN` no JSONB **não** é pedido: nenhuma
   consulta atual filtra por chave interna. Se a API passar a listar por `trend`, aí sim.

## O que **não** muda

- Nada é apagado nem reescrito: a T3.43 atualiza a linha no lugar quando o digest muda
  (backfill de velas), justamente porque `agent_signals.regime_id`,
  `trade_proposals.regime_id` e `paper_trades.regime_id` apontam para esses ids com
  `ON DELETE SET NULL`;
- `regime_v0` continua dono de `scope = 'global'` e da linha aberta. As duas séries
  convivem e são separadas por `scope` + `classifier_version`.

## Consequência de não fazer nada

Funciona, com dois custos declarados: a idempotência depende de uma trava em vez de uma
constraint (uma corrida rara duplicaria uma hora, e a consulta de pesquisa passaria a
contar aquela hora duas vezes), e uma segunda exchange produzindo a mesma série teria de
ser distinguida por um `->>` em vez de por uma coluna.

## 4. Consequência de UI que o esquema poderia resolver (decisão de quem manda)

`RegimeRepository.current_per_scope` devolve a linha mais recente **de cada escopo**, e
`is_stale = end_time is not None or not scanner_alive`. Como toda linha horária é fechada
por construção, depois do deploy o tile "Regime atual" do dashboard passa a mostrar uma
segunda linha — `BTC · <rótulo>` — **sempre com o selo `stale`**. O rótulo é honesto (a
hora passada não é o regime vivo), mas o selo permanente pode ser lido como defeito.

Três saídas, nenhuma delas nesta tarefa (`apps/**` e `infra/migrations/**` fora de escopo):

1. um valor novo em `regime_scope` (`btc_hourly`) separando série histórica de estado
   vivo — **migração**, e resolve na origem;
2. a API filtrar `classifier_version` em `current_per_scope` (uma linha em `apps/api`);
3. aceitar como está: duas linhas, uma viva e uma histórica marcada `stale`.
