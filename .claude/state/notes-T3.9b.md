# Notas T3.9b — V4 a V9 e §10 pelo caminho persistido

**Data:** 2026-09-07. **Autor:** test-engineer. **Escopo:** as verificações V4-V9 e §10 de
`.claude/state/spec-T3.9-verificacoes.md`, contra o `execution-worker` real (`7ecafd2`, `12edda3`)
e as correções do T3.5b (`review-T3.5.md`) já mescladas. **Astra:** indisponível até 12/09 —
nenhuma segunda opinião foi obtida; as divergências abaixo estão registradas para revisão humana.
**Não commitado.** Base: `tests/integration/paper/conftest.py` de T3.9a, **estendida, não
duplicada** — o §0 (carteira, taxa de câmbio, mercados) não mudou nenhum número; o que foi
acrescentado é o que V4-V9/§10 precisavam e §0 não tinha: filtros reais gravados na tabela
`markets` (antes só a identidade), construtores de livro/negócio, e os `runners` dos ciclos reais
do worker (`execute_approved_entries`, `run_protection_cycle`, `cancel_pending_entries`,
`expire_stale_reservations`).

Entregue em `tests/integration/paper/`:

- `test_v4_concurrent_orders_and_duplicate_fills.py` (3 testes)
- `test_v5_reconciliation.py` (3 testes, um deles Hypothesis)
- `test_v6_stale_data_reconnect_restart.py` (3 testes)
- `test_v7_exchange_minimums.py` (10 testes, incluindo 1 `xfail`)
- `test_v8_adverse_gap.py` (2 testes)
- `test_v9_no_fabricated_fill.py` (5 testes)
- `test_s10_crash_boundaries.py` (4 testes)

Total: **30 testes novos**, todos verdes exceto o `xfail(strict=True)` esperado.

---

## 1. Extensão do conftest.py (§0 mantido, nada duplicado)

`_reference_data` agora grava `tick_size`/`step_size`/`min_notional` e
`metadata.spot_market_filters` em cada linha de `markets` (antes só a identidade) — porque
`hunter_execution_worker.reference.load_market` lê os filtros **da linha**, nunca do `MarketSpec`
que a admissão usa (esse já vinha de `recorded_filters()` desde T3.9a). Sem isso, todo mercado do
worker apareceria sem filtro nenhum (`min_notional=None`, `avg_price_mins=None`), e nenhuma entrada
jamais preencheria — um buraco que só aparece quando se tenta rodar o ciclo real, não a admissão
isolada.

Consequência que todo teste desta rodada carrega: **os três mercados do §0 (BTC/ETH/SOL) têm
`avgPriceMins = 5`** (medido, `.claude/state/notes-T3.0a.md` §5) — nenhum deles é o caso
"`avgPriceMins = 0`, use o último preço". Todo `SpotSnapshot` construído aqui passa `avg_price`
explicitamente; sem ele, `check_market_order` recusa com `avg_price_unavailable` (V7 item 4, provado
à parte).

Duas funções novas merecem nota:

- `open_fresh_wallet(engine, factory)` — o corpo da fixture `wallet`, extraído para ser chamável
  direto. Necessário porque o teste de propriedade de V5 (Hypothesis) precisa de uma carteira **por
  exemplo gerado**, e uma fixture pytest é resolvida uma vez por item de teste, não uma vez por
  exemplo do Hypothesis (`@given` reinvoca o corpo da função várias vezes reaproveitando os mesmos
  argumentos de fixture já vinculados).
- `open_position_directly` / `insert_intent_directly` — os escritores reais
  (`hunter_execution_worker.positions.open_position`, `...intents_repo.insert_intent`) chamados
  fora do ciclo de entrada, só onde o cenário é sobre **proteção** (V4, e poderia servir V8/V9) e a
  aritmética de uma entrada real (18,518 @ 100,01 → 18,499482 líquido) seria ruído em torno do
  número que o teste realmente mede (dez unidades redondas). Não é um stub: são os mesmos módulos de
  produção, só chamados sem passar pela entrada.

## 2. Divergências encontradas (a spec §13 foi atualizada com o mesmo texto)

### 2.1 V7 item 5 — o rótulo é `below_min_notional`, não `below_min_qty`

**Número da spec:** resíduo de 0,00001 BTC → `Residual(reason='below_min_qty', value_quote=0,80)`.
**Medido:** `untradable_reason(Decimal("0.00001"), FILTERS, 80000)` → `'below_min_notional'`.

**Por que não é ajuste de número, é leitura da ordem dos filtros.** `untradable_reason` mede
`effective_min_qty` primeiro: `rounded = filters.round_qty_down(qty)`, e só barra por quantidade se
`rounded < effective_min_qty`. Para `qty = effective_min_qty = 0,00001` isso é falso (são iguais,
não um menor que o outro) — a checagem de quantidade **passa**. Quem barra é
`check_market_order`'s `NOTIONAL`: `0,00001 × 80.000 = 0,80 < 5`. O valor, o preço e "nunca quitado"
da spec continuam corretos; só o rótulo diverge.

**O que ficou no arquivo:** `test_the_residual_is_below_min_notional_not_below_min_qty` (passa, fixa
o rótulo medido) e `test_v7_step5_the_spec_reason_below_min_qty` (`xfail(strict=True)`, falha em
`== 'below_min_qty'`), mais `test_the_residual_is_visible_on_the_report_never_silently_dropped` que
prova o mesmo número (0,00001 BTC, 0,80 USDT) num `ExecutionReport.residual` real, via
`submit_protection_exit`.

### 2.2 V6 itens 3 e 4 — não entregáveis nesta tarefa (dependência, não divergência)

Queda de WebSocket com lacuna (`ingestion_gaps`, `market_gap`) e perda de Redis durante uma decisão
dependem do coletor SPOT ligado ao hot state do `market-worker` (T3.0b) e do `RedisSpotMarketData`
real lendo essas chaves. `notes-T3.5.md` §5.3 registra essa ligação como **inexistente** em
2026-09-07: o `execution-worker` está pronto para ler `mkt:{exchange}:spot:{symbol}:{book,trades}`,
mas ninguém escreve essas chaves para SPOT ainda. Todo teste desta suíte usa `StaticSpotMarketData`
(o duplo rotulado que `hunter_execution_worker.market_data` define para exatamente esta situação),
que não tem noção de Redis, WebSocket ou lacuna — não há gap nem queda para "simular" sem inventar
um caminho de código que não existe. Nenhum teste foi escrito para os dois itens; não é um `xfail`
(não há uma chamada real para falhar), é uma dependência registrada no docstring do módulo
(`test_v6_stale_data_reconnect_restart.py`) e aqui.

### 2.3 V4 — a citação do contrato usada como motivação não é o cenário que V4 pede

"Um stop de 10 unidades encontra 4 vendáveis" (`docs/RISK_ENGINE.md` §10) é sobre **profundidade de
livro** limitando um único stop — o cenário exato que
`services/execution-worker/tests/test_restart_recovery.py::test_a_partial_exit_is_finished_by_a_new_attempt_after_a_restart`
já prova, com números reais (4 de 18,499482). Não é uma disputa entre duas proteções. A disputa que
V4 de fato pede (stop vs. alvo) foi escrita à parte, e o achado vale registrar: com o stop cobrindo o
`intended_qty` inteiro da posição, `allocate_sellable` (RISK_ENGINE.md §10, ordem de prioridade) dá
**zero** ao alvo mesmo que o alvo **nunca tenha disparado** — não é preciso as duas proteções
dispararem na mesma janela para o alvo terminar `voided`; qualquer fechamento do stop já o faz, via
`_void_the_other_protections`. `test_v4_concurrent_orders_and_duplicate_fills.py` prova essa versão
(mais forte, porque não depende de uma coincidência de tempo) em vez da versão literal do texto.

### 2.4 V8 — números da prova real (entrada a 100,01), não os da spec (entrada a 100,00)

A tarefa que despachou esta nota pediu explicitamente os números reais da prova de 30 minutos
(`.claude/state/t35-proof.md`): entrada 18,518 @ 100,01, taxa 0,018518, stop 97,5, gap 95,00,
slippage 256,41 bps, PnL −96,28938018, patrimônio 19.903,708205. A spec V5 usa entrada a 100,00 (para
isolar a taxa de qualquer deslizamento de entrada); V8 aqui usa 100,01 porque foi isso que a
dispatch pediu e é isso que a prova de 30 minutos realmente rodou. O método (`slippage_vs_plan_bps`
publicado, positivo, nunca corrigido) é idêntico nos dois casos — `256,41025641` bate com qualquer
uma das duas quantidades de entrada, porque a razão `(stop − preço)/stop` não depende de `qty`.

## 3. Números da spec × números medidos

| Número da spec/dispatch | Medido | Onde |
|---|---|---|
| V4: soma vendida nunca excede 10 | `10` exatamente (stop leva tudo) | `test_v4_...::TestAStopThatClosesThePositionVoidsTheCompetingTarget` |
| V4: alvo nunca "fulfilled" com fill fictício | `state='voided'`, `filled_qty=0` | idem |
| V4: replay não escreve segunda linha | `fills`/`orders` idênticos antes/depois | `TestARedeliveredExitReportMovesNothingASecondTime` |
| V4 (§11-style): duas sessões reais nunca vendem >10 juntas | `sold == 10`, uma das duas `"filled"` | `TestTwoRealSessionsNeverOversellOnePosition` |
| V5: `cash_after = 18.148,2000000000` | idêntico | `test_v5_reconciliation.py::TestOneFillReconciledExactly` |
| V5: `fee_qty = 0,0185180000` | idêntico | idem |
| V5: `net_base_delta = 18,499482` | idêntico | idem |
| V5: `equity` a mark 100 = `19.998,1482000000` | idêntico | idem |
| V5: `equity` a mark 101 = `20.016,6476820000` | idêntico | `TestThePriceMoveAndTheFeeAreNeverConfused` |
| V5: `equity = cash + Σ qty×mark` (propriedade) | verdadeiro em 8 exemplos Hypothesis, 1-3 vendas parciais cada | `test_v5_property_equity_always_equals_cash_plus_marked_positions` |
| V6: volume de 45 min → `liquidity_24h` unavailable, `sizing=None` | idêntico | `test_v6_...::TestAMinuteOldVolumeFortyFiveMinutesAgoNeverApproves` |
| V6: livro nunca observado → `book_depth` unavailable | idêntico | `TestAnUnobservedBookNeverInventsATimestamp` |
| V6: restart recompõe intenção parcial (4 de 18,499482) e nova tentativa | `filled=4` após o parcial, identidade nova na 2ª tentativa, dust final `status='closing'` | `TestARestartRecoversAPartiallyFilledProtectionFromPostgresAlone` |
| V7: `0,00001 BTC @ 80.000 = 0,80 USDT`, recusado | idêntico, `reason='min_notional'` | `test_v7_exchange_minimums.py::TestTheMinimumLotSizeIsBelowTheNotionalFloor` |
| V7: `0,123456 → 0,12345` (nunca `0,12346`) | idêntico | `TestAQuantityBetweenTwoStepsRoundsDownNeverUp` |
| V7: Risk Engine e execução usam o mesmo step | idêntico em 4 quantidades | `TestTheRiskEngineAndTheExecutionAdapterAgreeOnTheSameStep` |
| V7: sem `avgPrice`, recusa `avg_price_unavailable` | idêntico, nunca usa `last_price` | `TestTheNotionalReferenceIsTheExchangeAverageNeverTheLastTrade` |
| V7: resíduo 0,00001 BTC = 0,80 USDT, visível | idêntico; rótulo `below_min_notional` (§2.1) | `TestAResidualBelowTheFloorIsAccountedAndVisibleNeverQuietlySettled` |
| V8: fill a 95,00 (nunca 97,5) | idêntico | `test_v8_adverse_gap.py::TestTheGapFillIsPublishedWorseThanPlannedAndNeverCorrected` |
| V8: `slippage_vs_plan_bps = 256,41025641`, positivo | idêntico | idem |
| V8: `pnl = -96,28938018` | idêntico | `TestTheRealizedLossIsNotClampedToTheRiskBudget` |
| V8: patrimônio final `19.903,708205` = caixa `19.903,662415` + pó `0,04579` | idêntico nos três | idem |
| V9: sem livro → `pending_degraded`, zero `fills` | idêntico | `test_v9_no_fabricated_fill.py::TestNoUsableBookNeverFabricatesAFill` |
| V9: `ExecutionReport` não constrói com fill sob status sem fill | `ValidationError` (subclasse de `ValueError`) nos dois casos do validador | `TestTheValidatorRefusesToRepresentAFabricatedFill` |
| V9: vela nunca dispara um gatilho | `AttributeError` ao tentar (`candle.ts` não existe) | `TestACandleNeverSuppliesARetroactiveFill` |
| V9: livro restaurado → nova tentativa, sem duplicar consumo | identidade nova, `filled_qty=18,499`, 2 fills totais (entrada+saída) | `TestARestoredBookGetsANewAttemptForTheSameIntention` |
| §10: fill+intenção numa transação | zero linhas em `orders/fills/positions/portfolio_exit_intents` após a "morte" | `test_s10_crash_boundaries.py::TestAFillAndItsProtectionAreOneTransactionNeverTwoCommits` |
| §10: reentrega de entrada após "morte" antes do ACK | 1 `positions`, 1 `orders`, 1 `fills` — antes e depois do replay | `TestARedeliveredEntryAfterADeathBeforeTheAckAppliesOnceNotTwice` |
| §10: transição do kill switch sem `UPDATE` audita → recusa do banco | `DBAPIError` na hora do `COMMIT` (trigger `DEFERRABLE INITIALLY DEFERRED`); a mesma transição **com** o registro de auditoria comita normalmente | `TestAKillSwitchTransitionWithoutAnAuditRowIsRefusedByThePostgresConstraint` (2 testes) |

## 4. Armadilhas do §12 viradas em asserção negativa

| Armadilha | Onde é negada |
|---|---|
| 1/2 `sleep` e relógio de parede | nenhum `sleep`/`datetime.now()` em nenhum arquivo novo; todo instante vem de `at(...)` ou de somas explícitas sobre `NOW`; `run_protection`/`run_entries` nunca recebem um relógio, só o `now` do teste |
| 3 fill retroativo por vela | `test_v9_no_fabricated_fill.py::TestACandleNeverSuppliesARetroactiveFill` — uma `NormalizedCandle` real, passada a `check_triggers`, quebra com `AttributeError` em vez de disparar |
| 4 mocks que sempre preenchem | `StaticSpotMarketData` é o único duplo usado, e em V6/V9 ele devolve `book=None` de propósito; quem decide o preenchimento é sempre o `PaperExecutionAdapter` real |
| 5 `float` em qualquer ponto | todo número em todo arquivo novo é `Decimal` construído de string ou inteiro; nenhum literal `float` aparece |
| 6 tolerância sem número | toda comparação de dinheiro é `Decimal ==`, nunca `abs(a-b) < ε`; a única "tolerância" citada (`booking_residual_quote`) é zero em todo cenário aqui porque cada caminhada toca um nível só |
| 7 crash simulado sem perda de estado | §10's dois primeiros testes usam uma exceção real dentro da transação que teria comitado o efeito — o Postgres é quem desfaz, verificado por uma conexão nova; V6/V9's "restart" nunca reaproveita `TriggerWatermarks`/`DegradedRetries` da chamada anterior |
| 8 duas tarefas na mesma sessão | `TestTwoRealSessionsNeverOversellOnePosition` (V4) abre duas transações reais via `asyncio.gather` sobre duas chamadas de `run_protection`, cada uma com sua própria `tenant_session` |
| 9 esconder qual checagem reprovou | V6 sempre nomeia o check (`check_of(..., "liquidity_24h")`, `"book_depth"`) |
| 10 fixture que já nasce travada | nenhum teste escreve `kill_switch_state`/`degraded_since` à mão; ambos nascem de ciclos reais (S10's teste de auditoria é a única exceção deliberada, e é sobre a trava do banco em si, não uma conveniência de teste) |

## 5. Como cada arquivo foi visto falhando (mutação em runtime, nunca em arquivo de produção)

**Nota de escopo:** a dispatch desta tarefa proíbe tocar `packages/**`, `services/**`, `infra/**`.
Toda "mutação" abaixo foi um monkeypatch em tempo de execução (`unittest.mock.patch`), aplicado por
um teste descartável rodado uma vez e apagado em seguida — nunca uma edição em disco de um arquivo de
produção, nem mesmo temporária.

| Arquivo | Mutação (runtime) | Resultado |
|---|---|---|
| `test_v4_...` | `apply_exit._void_the_other_protections` → no-op | `1 failed` (`'open' == 'voided'`) |
| `test_v5_reconciliation.py` | `taker_fee` dobrado (base asset) | `1 failed` (`19996,2964 == 19998,1482`) |
| `test_v6_...` | `ExitAttempt.for_intent` sempre devolve o mesmo `attempt_id` | `1 failed` (`'exit:...ff' != 'exit:...ff'`, na verdade o segundo virou replay) |
| `test_v7_exchange_minimums.py` | `round_qty_down` arredondando para cima | `1 failed` (`0,12346 == 0,12345`) |
| `test_v8_adverse_gap.py` | `slippage_vs_plan` com sinal invertido | `1 failed` (`-256,41... == 256,41...`) |
| `test_v9_no_fabricated_fill.py` | `eligible_for` forçado a `eligible=True` mesmo sem livro | **não pegou** — `book is None` é checado separadamente por `submit_protection_exit`, defesa em profundidade; registrado como achado positivo, não repetido |
| `test_s10_crash_boundaries.py` | (a auditoria "positiva" — sem `kill_switch_transitions` — já é o próprio teste) | prova diferencial: a mesma transição **com** auditoria comita |

Todas as mutações foram descartadas depois do teste (arquivos `zz_mutant_check_*.py` apagados);
`git status` não mostra nenhuma alteração em `packages/**`/`services/**`/`infra/**`.

## 6. Dívidas que este trabalho deixa (não são divergências)

1. **V6 itens 3/4** — ver §2.2. Pré-requisito: T3.0b (coletor SPOT no hot state).
2. **A rota HTTP manual (T3.8)** continua não exercitada por nenhum teste desta rodada — como em
   T3.9a, a admissão é chamada como o `execution-worker`/o operador a chamarão hoje
   (`hunter_core.admission.service.admit` direto, `source='manual'`), porque a API só arquiva o
   pedido (`notes-T3.5.md` §5.1: falta `request_payload` em `trade_proposals`).
3. **§10 não cobre as oito fronteiras da tabela da spec**, só as três que a dispatch pediu
   explicitamente (fill+intenção, reentrega de entrada, transição de kill switch sem auditoria). As
   fronteiras 6/7 (kill switch de organização, `market_betas`) já têm a garantia no schema hoje
   (constraint triggers/índices únicos parciais) e poderiam ganhar um teste de "recusa do banco"
   no mesmo espírito do que este arquivo já prova para a fronteira 6 de portfólio; as fronteiras
   1/2/8 (reserva ↔ ordem, expiração ↔ liberação) dependem de matar um **processo** de verdade
   (`kill -9`), não uma exceção dentro da mesma transação — isso é o que `t35-proof.md` já fez uma
   vez (§4, o `docker kill` de 07:06:28), mas não é reproduzido aqui como teste automatizado.
4. **A propriedade de V5 (Hypothesis) só exercita saídas parciais**, nunca uma sequência de
   compras — o schema só permite uma entrada por mercado (`position_exists`), então "uma sequência
   arbitrária de fills de compra/venda" da spec é, na prática, uma compra seguida de vendas
   parciais. Declarado no docstring do teste, não escondido.

## 7. Comandos e saída real

```
uv run ruff check tests/integration/paper                    → All checks passed!
uv run ruff format --check tests/integration/paper           → 13 files already formatted
uv run pyright tests/integration/paper                       → 0 errors, 0 warnings, 0 informations

uv run pytest tests/integration/paper/test_v1_sizing.py -q                        → 10 passed, 1 xfailed in 72.18s
uv run pytest tests/integration/paper/test_v2_warning_halves.py \
              tests/integration/paper/test_v3_blocked_keeps_protections.py -q     → 10 passed, 1 xfailed in 100.07s
uv run pytest tests/integration/paper/test_s11_concurrent_sessions.py -q          → 5 passed, 1 xfailed in 54.59s
uv run pytest tests/integration/paper/test_v4_concurrent_orders_and_duplicate_fills.py -q → 3 passed in 35.82s
uv run pytest tests/integration/paper/test_v5_reconciliation.py -q                → 3 passed in 113.26s
uv run pytest tests/integration/paper/test_v6_stale_data_reconnect_restart.py -q  → 3 passed in 34.81s
uv run pytest tests/integration/paper/test_v7_exchange_minimums.py -q             → 9 passed, 1 xfailed in 1.32s
uv run pytest tests/integration/paper/test_v8_adverse_gap.py -q                   → 2 passed in 34.13s
uv run pytest tests/integration/paper/test_v9_no_fabricated_fill.py -q            → 5 passed in 37.31s
uv run pytest tests/integration/paper/test_s10_crash_boundaries.py -q             → 4 passed in 36.57s
```

Todos os testes pré-existentes de T3.9a (`test_v1..v3`, `test_s11`) permanecem verdes, com os
mesmos três `xfail` que T3.9a já havia registrado — a extensão do conftest não moveu nenhum número
deles. O único erro observado em qualquer rodada foi um `ConnectionResetError [WinError 64]`
esporádico do testcontainers no Windows durante o setup/teardown, já documentado como flaky conhecido
em `review-T3.5.md` item 10; toda ocorrência desapareceu numa nova tentativa do mesmo arquivo.
