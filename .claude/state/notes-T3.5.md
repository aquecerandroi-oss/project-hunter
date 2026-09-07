# Notas da T3.5 — `execution-worker`: do sinal admitido ao fill aplicado

**Autor:** backend-specialist, 2026-09-07. **Para:** Sexta-feira, risk-engine-guardian,
security-reviewer, code-reviewer, T3.8, T3.9, T3.13, T3.14.
**Não commitei.** **Não editei** `.env*`, `infra/migrations/**`, `apps/web/**`,
`services/{market,scanner,strategy}-worker/**`. Editei `packages/**` em dois lugares e os dois
estão declarados no §3. **Astra indisponível até 12/09** (cota do Codex esgotada em 2026-09-07):
nenhuma rodada de segunda opinião foi feita nesta tarefa — registrado como limite, não como
aprovação.

## 1. O que existe agora

`services/execution-worker/hunter_execution_worker/` — seis laços, cada passada uma transação, sob
a trava da carteira. Nada em memória é fonte de verdade.

| Arquivo | O que decide | Linhas |
|---|---|---|
| `main.py` | as seis tarefas do `TaskGroup`, `forever()`, as duas recusas de partida | 94 |
| `cycles.py` | uma passada de cada laço, o relógio injetado, as marcas do MTM | 232 |
| `config.py` | cadência e as duas flags; `ENABLE_LIVE_TRADING=true` é fatal | 112 |
| `wallet.py` | `WalletRef` e a lista de carteiras principais | 53 |
| `market_data.py` | `SpotMarketData`, o leitor real das chaves spot e o duplo rotulado | 226 |
| `reference.py` | `markets` → `SpotMarketFilters` + `MarketIdentity` + `SPOT_VIP0` | 144 |
| `entry.py` | o ciclo da ordem: adiar, recusar, tentar uma vez | 299 |
| `apply.py` | aplicar o relatório de **entrada** no ledger | 233 |
| `apply_exit.py` | aplicar a tentativa de **saída** e fechar o trade | 240 |
| `booking.py` | o preço que o ledger grava e o arredondamento que ele custa | 96 |
| `rows.py` | `orders`, `fills`, `participation_consumptions` | 276 |
| `positions.py` | abrir, reduzir, assentar e virar `trades` | 341 |
| `intents_repo.py` | ler/escrever a intenção durável e reconstruir `applied_attempts` | 202 |
| `protection.py` | o ciclo de proteção: o que uma tentativa faz | 291 |
| `triggering.py` | a marca-d'água, a geometria da posição e o que está vencido | 98 |
| `mtm.py` | ponto da curva → kill switch → `kill_switch.changed` | 221 |
| `guard.py` | cancelar pendentes sob BLOQUEADO; expirar reservas | 122 |
| `admission_cycle.py` | decidir o que a API arquivou; dizer o que não dá para decidir | 174 |
| `events.py` | outbox e auditoria | 199 |
| `health.py` / `heartbeat.py` / `metrics.py` / `state.py` | supervisão | 115/70/68/63 |

`services/execution-worker/proof/` — o roteiro da prova de 30 min (`venue.py`, `run_proof.py`).
`services/execution-worker/tests/` — 19 testes (5 arquivos de integração com testcontainers, 1
unitário de supervisão), mais 7 no teste unitário reescrito do adaptador da API. **Nada em `tests/integration/paper/`**: aquele diretório é da T3.9a.

## 2. As decisões que valem revisão

### 2.1 Uma tentativa é terminal, mas "ainda não vi livro" não é uma tentativa

O contrato diz "entrada: **uma** tentativa, cancelamento terminal do restante". Isso vale para o
*fill*, não para a espera pelo insumo. A entrada só é tentada contra um **livro elegível**
(`eligible_for` com a mesma política do adaptador); enquanto o livro está ausente, velho, anterior à
latência declarada ou é de outro mercado, a proposta é **adiada** — nada é escrito, a tentativa não
é gasta, e se o livro nunca chegar a reserva expira em 30 s e é liberada com o motivo.

**Isto foi encontrado pela prova, não pensado antes.** A primeira rodada de 30 min recusou a entrada
com `book_before_latency`: a decisão saiu às 06:48:23,857 e o livro mais novo no hot state era o de
06:48:22 — o *anterior* a ela. A ordem terminava `rejected` e a carteira ficava sem posição por uma
diferença de meio segundo entre duas cadências. O comportamento anterior está no relatório da prova
(`t35-proof.md` §2) exatamente como foi observado.

### 2.2 O preço que o ledger grava, e o resíduo de arredondamento que ele custa

`LedgerRepository.reconcile_cash` reconstrói o caixa como `Σ qty × price` sobre `fills`, e
`fills.price` é `NUMERIC(28,10)`. Então o preço gravado é `gross_quote / filled_qty` arredondado a
dez casas, e a diferença para o `gross_quote` que o adaptador caminhou é **publicada** no próprio
fill (`metadata.booking_residual_quote`), nunca absorvida. O limite é `filled_qty × 5e-11` e é
**exatamente zero** sempre que a caminhada tocou um nível só — o caso de todos os números fechados
da `spec-T3.9-verificacoes.md` e o da prova.

### 2.3 O pó é inevitável no spot, e ele fecha a posição sem quitá-la

Uma compra spot paga a taxa **em moeda**: a quantidade líquida é `qty × 0,999` e quase nunca é
múltiplo do `step_size`. Com `step = 0,001`, 18,499482 unidades vendem 18,499 e sobram **0,000482**,
abaixo do `min_qty` — invendáveis a qualquer preço. Isso não é um caso de borda, é o caso normal.

O que passou a valer: a posição fica com o pó, em `status = 'closing'` (continua valendo no
patrimônio e continua visível), a intenção termina em `blocked_residual` — **nunca** `fulfilled`, que
o banco define como `filled_qty = intended_qty` — e o `trades` é escrito nesse instante, com a
quantidade realmente liquidada e um preço de saída **efetivo**: `entrada + realizado/qty`, que é
exato por construção e faz `qty × (saída − entrada)` bater com o realizado acumulado (é essa a conta
que `LedgerRepository.daily_realized_pnl` refaz).

**Sem esse assentamento o `trades` nunca seria escrito em M3** e o realizado do dia ficaria zero para
sempre. Registrado como decisão, não como conveniência: quem discordar tem de dizer o que faz com o
pó, não só que não gosta do `closing`.

**Segundo defeito que isto fechou:** antes, uma intenção `blocked_residual` era tentada de novo a
cada segundo, gerando uma linha `orders` recusada por ciclo, para sempre, para uma quantidade que
nenhum preço torna vendável. Agora `blocked_residual` não é tentada (`triggering.due`).

### 2.4 O instante da decisão de uma proteção é o cruzamento, não "agora"

`eligible_book` exige `received_at >= decision_at + latência`. Datar a decisão de uma saída em "agora"
recusaria todo livro que temos — o que está na mão sempre foi recebido antes do ciclo que o lê. O
`decision_at` de uma tentativa é o instante em que o cruzamento **imprimiu** (ou, numa repetição,
quando a proteção ficou degradada). E o instante da *avaliação* é recarimbado **depois** da leitura
da fita (`run_protection_cycle(..., clock=...)`): a prova mostrou `trade_from_the_future` num print
que chegou entre o `now` do topo do ciclo e o retorno do Redis — um stop atrasado um ciclo pela nossa
própria contabilidade. Nos testes não há relógio: sem `clock`, o instante é exatamente o `now` dado.

### 2.5 A marca-d'água do gatilho é de propósito **não** durável

Perdê-la num restart causa uma **reavaliação**, nunca uma segunda venda: a quantidade é repartida sob
a trava a partir do que a posição e a intenção ainda têm (`allocate_sellable`). Uma marca durável
seria uma segunda fonte de verdade sobre uma proteção, e na primeira vez que discordasse da intenção
ninguém saberia qual vale.

## 3. Os dois lugares em que editei `packages/**`, e por quê

Ambos vieram das cinco condições do adendo, e ambos são inevitáveis:

1. **`hunter_core/admission/{sources,dedupe,record,decide,service}.py`** — condição 1.
   - `find_admitted` passou a casar **só linhas decididas** (`decided_at IS NOT NULL AND status <>
     'pending'`). Sem isso, no modelo da `0007` (a API arquiva, o motor decide), um pedido manual
     casaria consigo mesmo e `RiskDecision.model_validate({})` estouraria com dez erros.
   - `decide.py` é o módulo novo autorizado: `decide_pending` **decide a linha existente** por
     `UPDATE ... WHERE status='pending' AND decided_at IS NULL`, nunca insere uma segunda proposta,
     e o `decided_at` é o instante desta avaliação — o `utcnow()` fabricado do `_replay` saiu.
   - `request_digest` passou a ser **gravado** na admissão (inserida ou decidida) e **comparado** no
     replay, incluindo o de uma **recusa**, que era o buraco da pendência 1 da T3.12.
   - `record.py` ficou do mesmo tamanho de antes porque `decide_pending` nasceu em arquivo próprio
     (orçamento de 350 linhas).
2. **`packages/core/hunter_core/settings.py` — não precisou de mudança.** `Role` já tinha
   `"execution"` e `enable_live_trading` já existia. As cadências do worker são
   ambiente-locais (`hunter_execution_worker/config.py`), como no strategy-worker: número que decide
   dinheiro não mora em variável de ambiente.

`apps/api/hunter_api/services/admission.py` foi reescrito (condição 2) e é a **única** edição em
`apps/api` além do teste unitário que o acompanha.

## 4. As cinco condições do adendo, uma a uma

| # | Condição | Estado |
|---|---|---|
| 1 | dedupe só casa linhas decididas; o pedido pendente é decidido na própria linha; sem `decided_at` fabricado | **feito** (§3.1), com `request_digest` gravado e comparado |
| 2 | a API só registra o pedido | **feito estruturalmente** (`file_manual_order`), **bloqueado no schema** — ver §5.1 |
| 3 | `ReservationCycleClosed` no caminho do fill = "a reserva morreu, não liquide", nunca retentável | **feito**: `entry.py` fecha a reserva **antes** de aplicar o fill e a exceção sobe, abortando a transação inteira; nada é liquidado |
| 4 | publicar `kill_switch.changed` após `evaluate_and_persist` | **feito**: `evaluate_and_persist(publish=True)` + o evento próprio do worker, na mesma transação (só o motor pode) |
| 5 | fixtures escrevem `portfolio_equity_snapshots` como `hunter_worker` | **feito**: `tests/builders.open_wallet` abre como `hunter_worker`; nenhuma fixture minha escreve a curva como `hunter_app` |

## 5. Pendências e limites honestos

### 5.1 BLOQUEANTE — `trade_proposals` não tem onde guardar a geometria do pedido

A condição 2 pede que a API **só** arquive o pedido e que o worker o decida no ciclo de 1 s. A
primeira metade está feita e provada. A segunda **não pode existir hoje**: `trade_proposals` guarda
carteira, mercado, direção, origem, chave e digest, e **nenhuma** coluna para `entry_ref`, `stop`,
`requested_notional` ou `assumed_costs` — os insumos sem os quais o Risk Engine não decide nada.
`risk_decision` não serve (a trigger `trade_proposals_the_app_only_files_requests` recusa um INSERT
da API que o carregue, e seria uma decisão que ninguém tomou).

O que o worker faz enquanto isso: lista os pedidos pendentes, registra
`pending_request_without_geometry` com a chave, conta em
`hunter_execution_pending_requests{readable="false"}` e **não inventa número nenhum**. Nem recusa (o
pedido do operador não morre por causa de um buraco de schema) nem decide.

**Pedido à T3.1d / `database-architect`, com a T3.8 na mão:** uma coluna
`request_payload JSONB NULL` em `trade_proposals`, escrita pela API no INSERT do pedido, incluída na
forma que a trigger aceita, e coberta pelo `request_digest` que já existe. Sem ela, a ordem manual
não é ponta a ponta e a T3.8 não tem rota para entregar.

### 5.2 `avgPrice` não é coletado por ninguém (T3.0b)

O filtro `NOTIONAL` de uma ordem MARKET é julgado contra o `avgPrice` da exchange sobre
`avgPriceMins` minutos — **nunca** o último negócio, que se move junto com o livro suspeito (T3.0a
§5). Não existe chave para ele no hot state. `RedisSpotMarketData` devolve
`avg_price=None, avg_price_source="not_collected"`, e num mercado que exige a referência
(`avgPriceMins > 0`) a entrada é **adiada com motivo** até a reserva expirar. Mercados com
`avgPriceMins = 0` (o caso "use o último preço" da própria Binance) funcionam.
**Pedido à T3.0b:** publicar o `avgPrice` no hot state, ou dizer explicitamente que o par não o
exige.

### 5.3 O mercado SPOT ainda não está no hot state

Confirmado ao começar: `packages/core/hunter_core/redis.py` **já tem** `market_type` nas chaves
(T3.0c em voo, não commitado), então `RedisSpotMarketData` é o leitor **real** das chaves
`mkt:{exchange}:spot:{symbol}:{book,trades}` e decodifica exatamente o msgpack que
`hunter_market_worker.hot_state` escreve. Quem ainda não escreve essas chaves é o coletor spot
(T3.0b). A prova de 30 min alimentou as chaves reais com um venue **rotulado** (`exchange = "proof"`)
— nada que ela escreveu pode ser lido como Binance.

### 5.4 Streams: `orders.filled` e `positions.opened` viajam nas canônicas

`docs/PIPELINE.md` §10 e `hunter_core.events.streams.Streams` publicam `executions.completed` e
`positions.updated`; o brief nomeia `orders.filled` e `positions.opened`. Criar dois streams novos
seria editar `packages/core` fora do escopo e, mais importante, um nome de stream é contrato com
consumidores que o PIPELINE.md possui. Os dois eventos viajam nas canônicas com um campo `event`
que diz qual deles é (`events.py`). Desvio declarado.

### 5.5 Realizado parcial vive em `positions.realized_pnl`, não em `trades`

`trades` é uma linha por posição fechada (`UNIQUE (position_id)`). Uma saída parcial acumula em
`positions.realized_pnl` e só vira `trades` quando nada vendável sobra (§2.3). O realizado do dia
que a decomposição lê vem de `trades`, então uma posição meio fechada contribui para a curva
(patrimônio) e ainda não para `daily_realized_pnl`. Consequência do schema, declarada.

### 5.6 Uma posição por moeda

O ciclo de entrada recusa uma proposta cujo mercado já tem posição aberta (`position_exists`,
reserva liberada). A D3 e o teto de 10 % por moeda já proíbem a segunda posição; a guarda existe
porque somar a uma posição exigiria uma regra de preço médio que o contrato não tem. Se a T3.14
quiser escalonar entradas, é aqui que dói, de propósito.

### 5.7 O espelho `1h` da âncora do dia

`_daily_decomposition` procura o ponto da referência na faixa `1h`, na marca **exata** de
`day_reference_observed_at`; a curva operacional é `1m`. O `mtm` espelha o ponto que ancorou o dia
para a `1h` na virada (`ON CONFLICT DO NOTHING`), que é a dívida que a `notes-T3.3.md` §2 endereçou
a quem escrevesse a curva. Sem isso a decomposição diária ficaria indisponível a partir do segundo
dia de operação.

### 5.7b A `0008_paper_roles_2` chegou durante esta tarefa, e o worker roda nela

A T3.1d landou `infra/migrations/versions/0008_paper_roles_2.py` (não commitada) enquanto eu
trabalhava: ela **estreita** o DML do `hunter_app` em `orders`/`fills`/`positions`/`trades`,
acrescenta a trigger `portfolios_are_born_audited` e faz as guardas do kill switch olharem também o
`kill_switch_reason`. Nada disso limita o `hunter_worker`, que é o papel de todos os meus ciclos.

**Não é suposição:** o banco do stack local está em `0008_paper_roles_2` e a prova de 30 minutos
inteira rodou nele (`SELECT version_num FROM alembic_version` → `0008_paper_roles_2`), incluindo a
abertura da carteira, que é justamente o ato que a trigger nova vigia. A suíte de integração também:
o fixture roda `alembic upgrade head`, e head é a `0008`.

### 5.8 O que **não** verifiquei

- **Astra**: sem segunda opinião (cota esgotada até 12/09).
- **`_OBSERVED_EQUITY` conta snapshot de qualquer resolução** (achado 3 da revisão de 2026-09-07,
  endereçado à T3.1c e ainda aberto em `infra/migrations/ddl/paper.py:411`). Com o espelho `1h` da
  §5.7 escrevendo o **mesmo** número do ponto `1m`, o teto não sobe indevidamente hoje; um roll-up
  futuro com o máximo do período reabre exatamente o cenário descrito lá. Não é meu arquivo.
- **Crash real entre transições** (`spec` §10) só nas fronteiras que o worker controla: os testes
  provam a reconstrução a partir do banco com um grafo de objetos novo, não um `kill -9` do processo
  no meio de um `COMMIT`. O `kill -9` do contêiner rodou na prova (§ do `t35-proof.md`), depois da
  saída, não entre a escrita e o ACK.
- **`apps/api/tests/unit/test_system_workers_status.py` tem 3 falhas** (`'_StaticHgetallRedis' object
  has no attribute 'scan_iter'`) — as mesmas já registradas na `notes-T3.6.md`, em arquivo que não
  toquei.

## 6. Assinaturas para quem vem depois

```python
# services/execution-worker/hunter_execution_worker
await execute_approved_entries(session, *, wallet, data, now, scopes=None, adapter=None)
await run_protection_cycle(session, *, wallet, data, now, watermarks=None, adapter=None, clock=None)
await run_mtm_cycle(session, *, wallet, marks, betas, exit_cost_rate, now, limits=PAPER_V1, fx=None)
await cancel_pending_entries(session, *, wallet, now, scopes=None)
await expire_stale_reservations(session, *, wallet, now)
await decide_requests(session, *, wallet, requests, now, source="manual")   # ponto de extensão T3.14

# packages/core/hunter_core/admission
await find_pending(session, *, organization_id, idempotency_key) -> PendingRequest | None
await decide_pending(session, request, *, proposal_id, source, decision, scopes, as_of) -> bool
request_digest(request, source) -> str

# apps/api/hunter_api/services/admission
await file_manual_order(session, *, context, idempotency_key, portfolio_id, market_id, market,
                        direction, entry_ref, stop, assumed_costs, now, requested_notional=None)
```

**T3.14 (autonomia):** o ponto de extensão é `decide_requests`; a ponte monta `ProposalRequest` +
`RequestInputs` e o gate é `ENABLE_PAPER_AUTONOMY` (default `false`, lido em `config.load_config`).
Nada dela está implementado aqui.

**T3.8 (API/Web):** a rota manual precisa da coluna da §5.1. A leitura pode mostrar hoje: posições,
ordens, fills, trades, intenções (com `blocked_residual` e o pó), a curva `1m` com
`brl_unavailable_reason`/`marks_stale`, e o kill switch com a transição que o worker publicou.

**T3.13 (ops):** o serviço está nos dois composes com `restart`, healthcheck e `*prod-db-env`;
`ENABLE_LIVE_TRADING: "false"` é explícito nos dois. Nenhuma ativação de produção foi feita.

## 7. Comandos e saída real

```
uv run pytest services/execution-worker/tests -q          → 19 passed in 119.23s
uv run pytest packages/core/tests/integration/test_admission.py \
              packages/core/tests/integration/test_admission_reservation.py -q
                                                          → 27 passed in 157.69s
uv run pytest packages/core/tests/integration/test_admission_concurrency.py apps/api/tests/unit -q
                                                          → 380 passed, 3 failed (as 3 são de
                                                            test_system_workers_status.py, §5.8)
uv run pytest packages/core/tests/unit -q                 → 713 passed in 130.70s
uv run ruff check <meus arquivos>                         → All checks passed!
uv run ruff format <meus arquivos>                        → 13 files reformatted, 30 unchanged
uv run pyright <meus arquivos de produção>                → 0 errors, 0 warnings
uv run python infra/scripts/check_file_size.py            → scanned 452 files; 0 over budget
docker compose -f infra/docker/docker-compose.yml config  → válido
docker compose ... -f infra/vps/docker-compose.prod.yml config --services → execution-worker presente
```

A prova de 30 minutos, com a linha do tempo e os números, está em `.claude/state/t35-proof.md`.

---

# T3.5b — fechamento da revisão obrigatória (`review-T3.5.md`), 2026-09-07

**Autor:** backend-specialist. **Base:** `7ecafd2` + a revisão do risk-engine-guardian em
`.claude/state/review-T3.5.md`. **Não commitei.** **Astra continua indisponível** (cota do Codex
esgotada, retorno previsto 12/09): nenhuma segunda opinião foi feita nesta rodada — limite, não
aprovação. **T3.14 estava em voo** nos mesmos diretórios: não editei `bridge*.py`, `metrics.py` nem
`tests/builders.py`; o que precisei de compartilhado nasceu em `tests/scenarios.py`.

## 8. Dívida de coluna: `positions.is_residual` (para a T3.1e)

**Pedido, com o motivo e a forma exata.**

`positions.status = 'closing'` é hoje o **único** marcador de que o que a linha ainda segura é pó —
resíduo de arredondamento abaixo do `min_qty`, invendável a qualquer preço — e não posição. Ele
funciona porque `hunter_execution_worker.positions.reduce_position` só escreve `closing` nesse caso
(`settled and remaining > 0`), mas isso é uma **coincidência de escrita**, não um fato do schema:
`position_status` tem `closing` como estado genérico de "saindo", e no dia em que alguém escrever
uma saída parcial em andamento como `closing` — o significado natural da palavra — três leituras
passam a mentir de uma vez:

- `LedgerRepository.PositionRow.is_residual` (`packages/core/hunter_core/db/repositories/ledger.py`)
  → `hunter_core.portfolio.state.build_portfolio_state` deixa de contar a posição em `slots_used`,
  em `assets_held` e no risco planejado comprometido;
- `hunter_execution_worker.positions.load_open_position` → o ciclo de entrada deixa de ver a
  posição e aceita uma segunda ordem na mesma moeda, contra a D3;
- a T3.8c mostra a linha como "pó" na tela da carteira.

**Forma pedida:** `positions.is_residual BOOLEAN NOT NULL DEFAULT false`, escrita por
`reduce_position` no mesmo `UPDATE` que move `status` para `closing`, com o backfill
`UPDATE positions SET is_residual = true WHERE status = 'closing' AND qty > 0` (hoje é exatamente o
conjunto certo). Com ela, as três leituras acima trocam `status = 'closing'` por `is_residual`, e
`closing` volta a poder significar "saindo" sem quebrar dinheiro. Enquanto a coluna não existir, a
propriedade `PositionRow.is_residual` é o **único** lugar que sabe a diferença, e está documentada
como tal.

## 9. O que mudou nesta rodada, item a item

| # | Item da revisão | Onde | Teste que falhava antes |
|---|---|---|---|
| 1 | reserva vencida era executada | `entry.py` (`_Approved.reserved_until`, `_expire`) | `test_entry_guards.py::test_the_cycle_five_minutes_late_expires_it_instead_of_filling_it` |
| 2 | ciclo de proteção sem a trava da carteira | `protection.py` (`effective_state(lock=True)` no topo) + docstring | `test_wallet_lock.py` |
| 3 | pó matava a vaga e a moeda | `ledger.py` (`status`/`is_residual`), `portfolio/state.py` (filtro), `positions.py` (`load_open_position`) | `test_residual_dust.py`, `test_portfolio_state.py::TestDustIsMarkedButIsNotAPosition` |
| 4 | warning de geometria por segundo | `admission_cycle.report_unreadable(reported=…)`, `cycles.Cycles.geometry_reported` | `test_scheduling.py::TestAnUnreadableRequestIsNamedOncePerRow` |
| 5 | proteção degradada sem backoff | `triggering.DegradedRetries`, `protection.py` | `test_protection_backoff.py`, `test_scheduling.py::TestTheDegradedBackoff` |
| 6 | MTM fora da grade perdia a virada | `schedule.py` (novo), `cycles.every(plan=…)`, `main.py` | `test_scheduling.py::TestTheMarkToMarketSchedule` |
| 7 | expiração sem o motivo do adiamento | `entry._expire` grava `last deferral: <motivo>` na auditoria | `test_entry_guards.py::test_the_expiry_records_the_input_that_never_arrived` |
| 9 | testes: execução tardia e §11 no fill | `test_entry_guards.py` (3 cenários) | idem |

Itens **8** (digest da linha `pending`, que é da ponte T3.14) e **10** (flaky `WinError 64` no
teardown com dois arquivos testcontainers no mesmo processo) **não** foram tratados: o 8 é do dono
do `bridge*.py` e o 10 continua reproduzindo — `test_portfolio_state.py` inteiro falhou uma vez com
`ConnectionResetError` no teardown e passou (22/22) na repetição com `-p no:randomly`.

## 10. Arquivos novos desta rodada

- `services/execution-worker/hunter_execution_worker/entry_inputs.py` — "o insumo está pronto?",
  extraído de `entry.py` (orçamento de 350 linhas) e agora usado pelas duas pontas: adiar uma
  proposta viva e nomear, na expiração de uma morta, o insumo que nunca chegou.
- `services/execution-worker/hunter_execution_worker/settlement.py` — a linha `trades` de uma
  posição assentada, extraída de `positions.py` pelo mesmo motivo e pela linha que o docstring
  daquele módulo já traçava.
- `services/execution-worker/hunter_execution_worker/schedule.py` — a grade do minuto e a margem da
  virada em São Paulo.
- `services/execution-worker/tests/scenarios.py` — o roteiro compartilhado das suítes novas
  (admitir, entrar, proteger). Nenhum número mora nele; os números continuam em `builders.py`.

## 11. Duas observações que não são defeito meu, mas mudam número

1. **`reserved_until` é carimbado pelo relógio de parede**, não pelo `now` injetado: `admit(now=NOW)`
   com `NOW = 15:30:00` gravou `15:30:30,219`. Não afeta produção (lá o `now` é o relógio), mas
   qualquer teste que compare a tenure ao microssegundo vai piscar. `test_entry_guards.py` compara a
   janela, e diz por quê.
2. **`pyright services/execution-worker` acusa 160 erros pré-existentes** nos cinco arquivos de
   teste da T3.5 original (`test_mtm_and_kill_switch`, `test_protection_cycle`, `test_order_cycle`,
   `test_restart_recovery`, `test_concurrency`), todos vindos dos *helpers* anotados com
   `# type: ignore[no-untyped-def]`. Nenhum é de arquivo meu — os meus (produção e testes novos)
   estão em 0. Registrado como dívida de tipagem dos testes, não corrigido aqui para não misturar
   um refactor de 5 arquivos numa correção de revisão.
