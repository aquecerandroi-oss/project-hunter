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

---

# T3.5c — o execution-worker passa a usar as colunas da 0009, 2026-09-07

**Autor:** backend-specialist. **Base:** `12edda3` (T3.14/T3.5b) + `70acb6f` (`0009_paper_geometry`).
**Não commitei.** **Não editei** `.env*`, `infra/migrations/**`, `services/market-worker/**`,
`apps/web/**`, `docs/**`. **Astra indisponível até 12/09** — nenhuma segunda opinião nesta tarefa,
registrado como limite. Outra tarefa mexia em `tests/integration/paper/**` e `.claude/settings.json`
ao mesmo tempo — não são meus, não toquei.

## 1. Os seis itens do adendo, um a um

1. **`ledger.py`**: `PositionRow.is_residual` lê a coluna (`p.is_residual` no `SELECT`) em vez de
   derivar de `status`. **Desvio declarado**: `open_positions` **não** ganhou `AND NOT p.is_residual`
   — ver §2 abaixo, é a única divergência real do pedido literal.
2. **`positions.py`**: `reduce_position(dust=True)` grava `is_residual = true` no mesmo `UPDATE` que
   move `status` para `closing` (variável `residual = dust and remaining > 0`, escrita como
   `:is_residual`).
3. **"moeda comprometida / vagas" ganham `AND NOT p.is_residual`**: a consulta real de "vaga" é
   `positions.py::load_open_position` (usada por `entry.py`), não uma SQL dentro do próprio
   `entry.py`; a de "moeda comprometida" é `bridge_universe.py::coin_commitment` (usada por
   `bridge_screen.py`, não por `bridge_repo.py`). Editei as duas nos arquivos reais onde moram —
   **desvio de nome de arquivo em relação ao brief/§21.6, mesmo comportamento pedido**. Adicionei um
   teste novo (`test_bridge_eligibility.py::test_a_residual_position_in_the_same_coin_does_not_refuse`)
   provando que a ponte também para de recusar por pó, já que a doutrina ("não conta vaga, nem
   exposição, nem duplicidade") vale para os dois caminhos.
4. **`admission_cycle.py`**: `pending_requests` lê `request_payload`; `readable_and_unreadable`
   separa o que tem payload do que não tem; `rebuild_request` reconstrói o `ProposalRequest` (linha +
   payload + `markets`); `report_unreadable`/`pending_request_without_geometry` só nomeia mais a linha
   sem payload. `cycles.Cycles.admission()` foi reescrito para montar o retrato de mercado
   (`manual_inputs.manual_request_inputs`, arquivo novo) e chamar `decide_requests` — o pedido manual
   é decidido de verdade no ciclo seguinte, com deferimento (não recusa) quando falta livro/beta.
5. **`decide.py`**: `coalesce(request_digest, :digest)` → `:digest`. O motor sempre carimba o seu.
6. **`sources.py`**: `target: Decimal | None = Field(default=None, gt=0)` em `ProposalRequest`,
   incluído em `request_digest` e `request_payload` (antes hardcoded `None`); `bridge.py::_request`
   passa `target=screened.signal.target`. Provado em `test_bridge_cycle.py` com uma asserção nova
   lendo `request_payload->>'target'` de volta do Postgres.

## 2. Por que `ledger.open_positions` **não** ganhou o filtro que o §21.6 pede

A leitura literal de DATABASE.md §21.6 ("`open_positions` passa a filtrar `AND NOT p.is_residual`")
quebra `test_residual_dust.py` e `test_portfolio_state.py::TestDustIsMarkedButIsNotAPosition`, os dois
já verdes e explicitamente citados como "devem continuar verdes". O motivo: `open_positions` é a
**única** leitura que `build_portfolio_state` usa tanto para o `exposure_notional`/`equity` (que
**inclui** o pó, "visível e valorizado", doutrina do próprio §21.1) quanto para o `open_positions` do
motor (que **exclui** o pó, via `to_open_positions` filtrando `not item.row.is_residual` em Python,
já existente antes desta tarefa). Filtrar na SQL apagaria o pó da valorização também, regressão do
que o T3.5b já fechou. Fiz a leitura da coluna (`is_residual` real, não mais derivada) e documentei a
decisão no docstring do método; não toquei em `portfolio/state.py` (não listado, e não precisou
mudar). Quem quiser a leitura "só linhas realmente abertas" via índice `ix_positions_org_portfolio_live`
tem isso em `positions.py::load_open_position` (item 3) e `bridge_universe.py::coin_commitment`
(item 3) — os dois lugares que já precisavam responder "isto é uma posição?", que é uma pergunta
diferente de "quanto isto vale?".

## 3. Bug real encontrado pelo teste novo: `find_pending` e `FOR UPDATE` sob `hunter_app`

`test_manual_request_decided.py` é o primeiro teste de integração a exercitar
`apps/api/hunter_api/services/admission.file_manual_order` contra um Postgres real com os papéis
`hunter_app`/`hunter_worker` de verdade (antes só havia o unitário com `RecordingSession`, que não
aplica privilégio nenhum). `hunter_core.admission.dedupe.find_pending` sempre fazia
`SELECT ... FOR UPDATE`, e o Postgres exige o privilégio `UPDATE` (não só `SELECT`) para
`FOR UPDATE`/`FOR SHARE` — privilégio que `0007_paper_roles` **revogou** de `hunter_app` em
`trade_proposals` de propósito. Resultado, reproduzido com um script isolado antes de eu tocar em
qualquer arquivo: `permission denied for table trade_proposals`, não "zero linhas" — a rota manual da
API nunca poderia ter completado uma segunda chamada com a mesma chave (replay) sem estourar.

**Correção**: `find_pending(..., lock: bool = True)`. `hunter_core/admission/service.py::admit`
(papel `hunter_worker`, vai decidir a linha) continua com o lock, comportamento inalterado.
`apps/api/hunter_api/services/admission.py::file_manual_order` (papel `hunter_app`, só lê) passa
`lock=False`. Nenhum teste existente comparava a *shape* do SQL (`test_admission_adapter.py`
usa `monkeypatch`), então nada quebrou; os 9+17+10+6 testes de admissão seguem verdes. Isto não está
na lista dos seis itens do adendo — é uma correção que a própria tarefa pediu para provar (item de
teste "a API arquiva → o worker decide"), e sem ela o teste não passa nunca, em nenhuma tarefa futura
que exercite a rota manual de verdade.

## 4. `test_manual_request_decided.py` — o que ele prova e o que ele precisou

Usa `proof/venue.py` (rotulado, `exchange = "proof"`) para o mercado e os números — os mesmos da
prova de 30 min — e `services/execution-worker/tests/shadow_builders.py` para beta/candles/volume
(funções genéricas, não específicas de shadow). Fluxo: `file_manual_order` (papel `hunter_app`) →
`pending_requests` + `readable_and_unreadable` + `rebuild_request` + `manual_request_inputs` +
`decide_requests` (papel `hunter_worker`, transação **separada** da anterior) → `reservation_state ==
held` → `execute_approved_entries` → `filled`. Precisa de **dois** `SpotSnapshot` estáticos com
timestamps diferentes: um `<= as_of` da admissão (`hunter_risk.checks._data_quality`/`_book_depth`
exigem `0 <= age`, um livro "do futuro" reprova com `data_quality`/`book_depth`) e outro
`>= decided_at + latência` para o preenchimento (`entry.py`'s `book_before_latency`). Documentado no
docstring de `_snapshot()` porque não é óbvio e um teste futuro vai tropeçar do mesmo jeito se copiar
um helper existente sem notar a direção do tempo.

## 5. Comandos e saída real

```
uv run pytest services/execution-worker/tests -q (por arquivo, 13 arquivos) → todos verdes,
  incluindo test_manual_request_decided.py (novo, 1 passed) e
  test_bridge_eligibility.py (9 passed, era 8: +1 teste do pó não recusar)
uv run pytest packages/core/tests/integration/test_admission.py -q            → 17 passed
uv run pytest packages/core/tests/integration/test_portfolio_state.py -q      → 22 passed
uv run pytest packages/core/tests/integration/test_admission_reservation.py -q → 10 passed
uv run pytest packages/core/tests/integration/test_admission_concurrency.py -q → 6 passed
uv run pytest packages/core/tests/unit -q                                     → 704 passed
uv run pytest apps/api/tests/unit/test_admission_adapter.py -q                → 9 passed
uv run pytest apps/api/tests/unit -q                                          → 381 passed
uv run ruff check services/execution-worker packages/core apps/api            → All checks passed!
uv run ruff format --check ... (mesmos)                                       → 406 files already formatted
uv run pyright services/execution-worker/hunter_execution_worker
                packages/core/hunter_core                                     → 0 errors, 0 warnings
uv run pyright apps/api/hunter_api/services/admission.py                      → 0 errors, 0 warnings
uv run python infra/scripts/check_file_size.py                                → scanned 462 files;
                                                                                  0 over budget
```

## 6. Arquivos

**Novos**: `services/execution-worker/hunter_execution_worker/manual_inputs.py` (77 linhas),
`services/execution-worker/tests/test_manual_request_decided.py`.
**Modificados**: `packages/core/hunter_core/admission/{decide,dedupe,sources}.py`,
`packages/core/hunter_core/db/repositories/ledger.py`,
`apps/api/hunter_api/services/admission.py`,
`services/execution-worker/hunter_execution_worker/{admission_cycle,bridge,bridge_universe,cycles,
positions}.py`,
`services/execution-worker/tests/{test_bridge_cycle,test_bridge_eligibility,test_residual_dust,
test_scheduling}.py`,
`packages/core/tests/integration/test_portfolio_state.py`,
`packages/core/tests/unit/portfolio/test_marking.py`.

## 7. Pendências e limites honestos

- **A identidade de quem filed um pedido manual não sobrevive à decisão.** `trade_proposals` não tem
  coluna para isso; `rebuild_request` audita a decisão como o próprio worker
  (`actor_id=PRODUCER, actor_type="worker"`), mesma convenção do `bridge.py`. Se um dia isso importar
  (ex.: painel de auditoria mostrando "decidido em nome de fulano"), precisa de uma coluna ou de um
  `audit_logs` na hora da filiação que a decisão possa ler de volta — nenhum dos dois existe hoje e
  nenhum é meu para criar (migração).
- **`manual_request_inputs` nunca substitui o candidato**: se o retrato de mercado não puder ser
  montado (`spot_market_unknown`, `beta_unavailable`, `spot_price_unavailable`,
  `spot_book_unavailable`), a linha é simplesmente relida no próximo ciclo — nada é escrito. Não há
  contador dedicado a esse deferimento (o gauge `hunter_execution_pending_requests{readable="true"}`
  já cobre "quantas linhas ainda esperam"); um contador por motivo, no padrão de
  `hunter_bridge_candidates_total`, é uma extensão natural para quem pegar T3.8/observabilidade.
- **`Astra`**: sem segunda opinião (cota esgotada até 12/09).
- **Não verifiquei** a rota HTTP de T3.8 em si (não existe ainda — só o serviço); o teste novo chama
  `file_manual_order` diretamente, como a própria `notes-T3.5.md` §5.1 previu para "o script do
  operador hoje".

---

# T3.5d — `kill_switch.changed`: um formato, uma publicação, e a retomada chega ao stream, 2026-09-07

**Autor:** backend-specialist. **Base:** `90f1862`. **Não commitei.** **Não editei**
`packages/core/hunter_core/risk/**` nem `apps/api/**` (só **chamei** `resume`/`record_transition` de
dentro de um teste novo do execution-worker). **Astra indisponível até 12/09** — sem segunda opinião,
limite registrado.

## Os dois achados, um a um

### 1. Publicação dupla, dois formatos — corrigido removendo a segunda

`mtm.py::run_mtm_cycle` chamava `evaluate_and_persist(..., publish=True)` — que já enfileira, **na
mesma transação da latch**, `hunter_core.risk.transitions.record_transition`'s próprio evento
(`{scope, scope_id, organization_id, from_state, to_state, reason, actor_type, evidence}`,
`event_id = transition_id`) — e **depois**, se `evaluation.changed`, chamava
`events.publish_kill_switch`, um **segundo** evento, formato próprio do worker (`{event,
organization_id, portfolio_id, scope, previous, state, effective, reason, ts}`, `event_id` derivado
de `(portfolio_id, latched, ts)`). Um consumidor via dois eventos por transição automática, em dois
formatos.

**Correção:** a chamada a `events.publish_kill_switch` saiu de `mtm.py` (o `logger.warning("kill_switch_moved")`
ficou); a função `publish_kill_switch` em si **não sobrou** — virou `publish_resumed_transitions`
(achado 2, abaixo), porque as duas coisas resolvem o mesmo problema (um formato só) e o brief
autorizava "some ou vira delegação". `KILL_SWITCH_CHANGED` (o nome do stream) continua declarado em
`events.py` para quem precisar dele.

**Consumidores verificados**: nenhum em `apps/api` nem `apps/web` lê `kill_switch.changed` hoje
(`grep` nos dois diretórios não encontrou nada) — nada para adaptar. `docs/PIPELINE.md` §8 item 6 e
a tabela de streams (§10) documentam o formato único e quem de fato publica.

**Prova**: `test_mtm_and_kill_switch.py`'s teste de crash já existia; **estendido** para contar as
linhas do outbox (`stream = 'kill_switch.changed'` **e** `payload->>'key'`) — `len(rows) == 1`, não
"in" uma lista — e para decodificar o corpo (`payload->>'payload'`, o campo aninhado do envelope) e
provar o formato do core (`scope`, `scope_id`, `from_state`, `to_state`, `actor_type`, `evidence`) e a
**ausência** do campo `event` que só o formato retirado tinha.

### 2. Retomada pela API nunca chegava ao stream — o worker publica em nome dela

`apps/api/hunter_api/routers/risk.py::resume_kill_switch` chama `resume(..., publish=False)` (o
default; a rota nem passa `publish`) porque roda como `hunter_app`, a quem a `0007_paper_roles` nega
`INSERT` em `outbox_events` — de propósito (SECURITY.md: a API nunca fala com o transporte
diretamente). A transição é escrita, auditada, a trava move — e nada é enfileirado. O adendo da T3.5
original pedia o worker publicar "ao processar uma retomada"; não tinha sido entregue.

**Entregue:** `events.publish_resumed_transitions(session, *, wallet, now)`, nova, chamada no fim do
laço de 10 s do kill switch (`Cycles.kill_switch`, depois de `cancel_pending_entries`). A consulta:

```sql
SELECT id, organization_id, from_state::text, to_state::text, reason, actor_type, evidence, created_at
FROM kill_switch_transitions kt
WHERE scope = 'portfolio' AND scope_id = :pf AND actor_type = 'user'
  AND created_at >= :cutoff   -- 24h de lookback, sobre o índice (scope, scope_id, created_at)
  AND NOT EXISTS (SELECT 1 FROM outbox_events oe WHERE oe.event_id = kt.id)
ORDER BY created_at
```

Cada linha encontrada é enfileirada com `event_id = transition_id`, no **mesmo formato** de
`record_transition` (`scope/scope_id/organization_id/from_state/to_state/reason/actor_type/evidence`)
— um formato único, venha a transição do lado automático ou do lado manual.

**Idempotência: por `event_id`, não por cursor em memória.** `enqueue`'s `ON CONFLICT (event_id) DO
NOTHING` faz uma releitura da mesma linha (segundo ciclo, ou um processo reiniciado) um no-op; um
processo morto **entre** a leitura e o `enqueue` não deixa nada meio-escrito, porque a leitura e o
`enqueue` estão na mesma transação do ciclo — ou committam os dois, ou nenhum, e o próximo ciclo relê
exatamente a mesma linha "ainda não publicada".

**O marcador durável, decidido e documentado (o brief pedia exatamente isto).** "Ainda não publicada"
é testado com `NOT EXISTS` contra `outbox_events` — durável **até** aquela linha ser podada
(`outbox_store.prune_dispatched`, 7 dias após o **despacho**, `DATABASE.md` §1.3, um job que a
stack do M3 ainda não roda em lugar nenhum). Só um worker que perdesse o ciclo de 10 s por uma semana
inteira reenfileiraria uma retomada já entregue, sob o **mesmo** `event_id` — uma redelivery
redundante e inofensiva para um consumidor que o CLAUDE.md já exige ser idempotente por `event_id`,
nunca uma segunda transição. Documentado no próprio docstring de `publish_resumed_transitions`, não
resolvido com uma coluna nova (fora do escopo: nenhuma migração).

## Arquivos

**Modificados:** `services/execution-worker/hunter_execution_worker/{mtm,events,cycles}.py`,
`services/execution-worker/tests/test_mtm_and_kill_switch.py`, `docs/PIPELINE.md` (§8 item 6, §10).
**Novos:** `services/execution-worker/tests/test_kill_switch_resume_publish.py` (3 testes de
integração: primeiro ciclo publica, segundo ciclo nada, e um "crash" simulado — a transação do ciclo
é revertida de propósito, como um `kill -9` deixaria — que não publica nada e o ciclo seguinte
publica exatamente uma vez).

## O que a suíte prova, literalmente

1. **Primeiro ciclo enfileira um evento** (`test_the_first_cycle_publishes_the_unreachable_resume`):
   `resume()` como `hunter_app`, `publish=False` — outbox vazio confirmado antes; depois de
   `publish_resumed_transitions` como `hunter_worker`, exatamente uma linha, no formato do core,
   `actor_type = "user"`, `from_state/to_state = WARNING/ACTIVE`.
2. **Segundo ciclo, nenhum** (`test_a_second_cycle_publishes_nothing_more`): duas chamadas seguidas,
   a segunda devolve `0`, o outbox continua com uma linha só.
3. **Processo morto entre a leitura e o `enqueue`, ainda um só**
   (`test_a_process_killed_between_the_read_and_the_enqueue_still_leaves_exactly_one`): a chamada
   roda dentro de uma transação que **nunca comita** (uma exceção forçada depois dela, capturada
   fora do `async with`) — o outbox continua vazio depois disso — e só a chamada seguinte, numa
   transação que comita de verdade, produz a única linha.

Nenhum dos três precisou fabricar a lógica de negócio da retomada: `resume()` e `record_transition`
são os reais de `packages/core`, chamados exatamente como a rota e o motor automático os chamam. O
que é sintético é a *evidência* que a retomada usa (`PortfolioState` construído à mão, totalmente
recuperado — `equity == day_start_equity == peak_equity`), o mesmo parâmetro (`state=`) que um chamador
real com um estado fresco calculado usaria; a escada de elegibilidade do `resume` em si já tem uma
suíte extensa em `packages/core/tests/integration/test_risk_kill_switch.py`, não duplicada aqui.

## Pendências e limites honestos

- **Astra**: sem segunda opinião (cota esgotada até 12/09).
- **A pruning do outbox não roda em lugar nenhum do M3** (achado, não meu de resolver): o risco do
  marcador `NOT EXISTS` documentado acima é teórico enquanto isso for verdade. Registrado para quem
  ligar o job do M5.
- **`test_kill_switch_resume_publish.py` não testa duas instâncias do worker correndo o mesmo ciclo
  ao mesmo tempo** — coberto por construção (idempotência por `event_id`), não por um teste de
  concorrência real; o mesmo padrão que `notes-T3.14.md` §2.2b já registrou para a ponte.

## Comandos e saída real

```
uv run pytest services/execution-worker/tests/test_kill_switch_resume_publish.py -q → 3 passed in 29.59s
uv run pytest services/execution-worker/tests/test_mtm_and_kill_switch.py -q        → 2 passed in 37.65s
uv run pytest services/execution-worker/tests -q  (por arquivo, 17 arquivos)        → 132 testes, todos
  verdes (dois flakes conhecidos, WinError 64, verdes na repetição — notas T3.5b §9 item 10)
uv run ruff check services/execution-worker packages/core apps/api                  → All checks passed!
uv run ruff format --check services/execution-worker packages/core apps/api         → 1 arquivo alheio
  (test_schema_privileges.py, outra tarefa em voo) precisa reformatar; nada meu
uv run pyright services/execution-worker/hunter_execution_worker                    → 0 errors
uv run pyright services/execution-worker/tests/test_kill_switch_resume_publish.py
                services/execution-worker/tests/test_mtm_and_kill_switch.py         → 0 errors / 54
  erros pré-existentes em test_mtm_and_kill_switch.py (helpers `# type: ignore[no-untyped-def]`,
  nenhum em linha que toquei — mesma dívida da notas-T3.5b §11 item 2)
uv run python infra/scripts/check_file_size.py                                     → scanned 463 files;
                                                                                       0 over budget
```
