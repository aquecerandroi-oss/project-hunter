# Notas — T3.68: a ordem manual paper existe no produto

**Status:** DONE_WITH_CONCERNS (dois achados de escopo alheio, corrigidos por
necessidade; um achado de escopo alheio, apenas relatado — ver §4 e §5).

## 0. Desvio do contrato — declarado no topo, como pedido

O contrato dizia `.../orders`. Esse caminho **já existe** e serve outra coisa:
`GET /api/v1/orgs/{org_id}/portfolios/{portfolio_id}/orders` (`routers/portfolio.py`,
T3.8a) já lê a tabela `orders` (ordens/fills executados, ainda vazia até T3.4/T3.5
ganharem um escritor de verdade). O recurso deste brief é **outra coisa**:
o **pedido** do operador (`trade_proposals`, `source='manual'`) — existe antes
de qualquer ordem, e a maioria dos pedidos nunca produz uma. Dois handlers no
mesmo caminho não é um merge, é uma colisão que o FastAPI resolveria de forma
arbitrária.

**Resolvido:** o recurso mora em `.../portfolios/{portfolio_id}/order-requests`
(`POST`, `GET` lista, `GET /{request_id}`), em `routers/orders.py` novo — que é
exatamente o arquivo que `docs/plans/M3.md` (T3.8) já previa (`routers/{portfolio,
orders,trades,risk,proposals}.py`), só que o texto do brief citou o caminho como
se fosse o mesmo de `portfolio.py`. `ManualOrderOut`/`ManualOrderDetailOut` também
incluem `market_id`/`direction` além dos quatro campos do contrato — aditivo, um
cliente que só lê os campos documentados não percebe a diferença.

## 1. O que existia (T3.12, T3.5c) e o que eu construí

- `hunter_api.services.admission.file_manual_order` (T3.12) já existia, testado
  (`apps/api/tests/unit/test_admission_adapter.py`) e usado por um teste do
  execution-worker (`services/execution-worker/tests/test_manual_request_decided.py`),
  mas **nenhum router chamava**. Continua sendo o único caminho de escrita —
  não toquei o arquivo.
- A API **só arquiva** (`status=pending`, sem decisão): quem decide é o
  `execution-worker`, um segundo depois, por `hunter_core.admission.service.admit`
  (a mesma função, T3.12). Isso é arquitetura de `0007_paper_roles`
  (`hunter_app` perdeu `UPDATE`/reserva/outbox em `trade_proposals`), não uma
  escolha minha.
- **O que eu construí:** a rota deriva o que o operador não manda —
  `entry_ref` do `last` real do ticker SPOT no hot state (Redis,
  `mkt:{ex}:{sym}:ticker`, o mesmo campo que `services/markets.py` já lê para a
  tela de Markets) e `assumed_costs` do spread real do mesmo ticker
  (`bid`/`ask`), da tabela de fee real da carteira
  (`hunter_exchanges.binance_spot.fees.SPOT_VIP0`, pacote **compartilhado**,
  nunca `services/execution-worker`) e do ajuste declarado do simulador
  (`hunter_core.execution.pricing.ExecutionPolicy.extra_slippage_bps`, hoje 0).
  Mercado tem de ser SPOT executável (`market_type='spot'`, `status='active'`,
  `is_monitored`, não deslistado) — 422 `market_not_executable_spot`. `short` é
  recusado por nome — 422 `short_not_supported_spot` — porque `paper_v1` tem
  `max_leverage=1` (RISK_ENGINE.md §2) e o check `modality` (§3.1, #3) recusaria
  de qualquer forma; a rota só evita gastar uma leitura de Redis antes.
  Carteira nunca aberta — 409 `wallet_not_open` (a classe já existia em
  `admission.py`, exportada e nunca usada — este era o lugar dela).
- `max_entry_delay_s` de `AssumedCosts`: nenhum check do motor lê esse campo
  para pedido manual (ele nasceu para o envelope do Shadow Lab). Usei `60`,
  a mesma convenção de toda fixture manual existente no repo
  (`test_manual_request_decided.py`, `test_admission_adapter.py`).

## 2. Resposta `202` sempre — decisão registrada, documentada

"200 ou 202" do brief virou **sempre 202**, inclusive replay decidido: uma
forma só de resposta, o cliente nunca precisa ramificar por status code para
saber se é um filing novo ou um replay. `decision` é o `risk_decision` bruto de
`trade_proposals` (já canônico — `RiskDecision.to_jsonable()`, números como
string), repassado sem re-modelar: o mesmo precedente de
`PortfolioTradeOut.entry_snapshot` (`schemas/portfolio_lists.py`).

## 3. Achado: a filial (filing) não é auditada — só a decisão é

O brief pede "202 filed → row in the request table with the audit row".
`hunter_core.admission.record.py` só escreve `audit_logs` (`proposal.admitted`/
`proposal.rejected`) quando o **motor decide** — a própria docstring de
`admission_cycle.rebuild_request` já diz isso: *"the filing itself is not
separately audited today — a gap of the current schema, not of this
reconstruction"*. Não inventei uma auditoria de filing (isso tocaria
`packages/core/hunter_core/admission/**`, que exige revisão do
`risk-engine-guardian`/`security-reviewer` por `docs/plans/M3.md`, T3.12 — fora
do escopo e das permissões deste brief). O teste de integração assere a
auditoria **da decisão** (o que existe de verdade), com uma nota grande
explicando a diferença.

## 4. Achado de escopo alheio, corrigido: `open_paper_wallet` sob `hunter_app` quebra

`apps/api/tests/integration/test_portfolio_api.py::_open` (e os testes que a
usam) chamam `open_paper_wallet` dentro de `tenant_session(..., )` **sem**
`db_role`, que é `hunter_app` por padrão. Desde `0007_paper_roles`,
`hunter_app` não tem `INSERT` em `portfolio_equity_snapshots`, e a abertura
escreve o primeiro ponto da curva — **isso já quebra hoje**, contra um banco
recém-migrado, independente de qualquer coisa que eu tenha feito:

```
cd apps/api && uv run pytest tests/integration/test_portfolio_api.py -q -k TestBrlUnavailable
...
E   sqlalchemy.exc.ProgrammingError: ... InsufficientPrivilegeError: permission denied for table portfolio_equity_snapshots
```

`infra/scripts/open_paper_wallet.py` (o script de produção real) abre a
carteira como `hunter_worker` — confirmei lendo o script. Corrigi **só o meu
próprio teste** (`test_manual_orders.py`) para abrir a carteira como
`hunter_worker`, com a explicação em comentário. **Não toquei**
`test_portfolio_api.py`, `test_portfolio_trades_extra_api.py` nem
`test_risk_limits_api.py` (também chamam `open_paper_wallet` do mesmo jeito
quebrado) — não são meus arquivos e a correção é de uma linha em cada, mas é
código de outra tarefa. Reportando para o orquestrador decidir quem conserta.

## 5. Achado de escopo alheio, corrigido por necessidade: guarda de rotas desatualizada

Ao adicionar as 3 rotas novas em `test_isolation.py`/`test_rbac_matrix.py`
(exigido — os dois arquivos têm um teste que conta operações do OpenAPI ao
vivo contra uma lista escrita à mão, e uma rota nova sem linha correspondente
os deixa vermelhos), descobri que **já estavam vermelhos antes de mim**: falta
`GET .../risk/limits` (`routers/risk.py::read_risk_limits`, T3.25) nas duas
listas. Sem essa linha, `26 != 27` mesmo depois de eu adicionar exatamente as
3 linhas do meu recurso. Adicionei a linha que faltava (`risk.limits.read`,
VIEWER) nos dois arquivos, no mesmo diff — é a mesma classe de conserto que a
minha própria tarefa, e deixá-la vermelha teria jogado a culpa do vermelho em
T3.68. Rodei as duas suítes inteiras depois do conserto: **39/39 passando**
(`test_isolation.py` + `test_rbac_matrix.py`, testcontainers reais).

## 6. Arquivos criados/modificados (`git status --porcelain`)

```
 M apps/api/hunter_api/app.py
 M apps/api/pyproject.toml
 M apps/api/tests/integration/test_isolation.py
 M apps/api/tests/integration/test_rbac_matrix.py
 M docs/ACTIVATION.md
 M docs/RISK_ENGINE.md
 M uv.lock
?? apps/api/hunter_api/routers/orders.py
?? apps/api/hunter_api/schemas/orders.py
?? apps/api/hunter_api/services/orders.py
?? apps/api/hunter_api/services/orders_derive.py
?? apps/api/tests/integration/test_manual_orders.py
?? apps/api/tests/unit/test_orders_service.py
```

(`.claude/state/brief-T3.68-ordem-manual-api.md` já estava commitado
verbatim em `3753792` antes de eu escrever — diff zero, nada para listar.)

`apps/api/pyproject.toml` ganhou `hunter-exchanges` como dependência real
(antes só `hunter-core`/`hunter-indicators`) — `services/orders_derive.py`
importa `hunter_exchanges.binance_spot.fees.SPOT_VIP0` de verdade, não só em
`TYPE_CHECKING`. `uv sync --all-packages` rodado; `uv.lock` reflete só essa
adição (diff de 2 linhas, conferido).

**Não toquei:** `apps/web/**`, `packages/risk-core/**`,
`services/execution-worker/**`, nenhum `.env*`. `hunter_execution_worker` e
`hunter_risk.decision`/`admission` de `packages/core` foram só **lidos**, nunca
editados.

## 7. Comandos e saídas reais

```
uv run python infra/scripts/check_file_size.py
  scanned 593 files; 1 over budget (services/strategy-worker/.../run.py — não é meu arquivo)

uv run ruff check <todos os 9 arquivos meus>          → All checks passed!
uv run ruff format --check <os mesmos>                → 9 files already formatted
uv run pyright <os mesmos>                             → 0 errors, 0 warnings

cd apps/api && uv run pytest tests/unit/test_orders_service.py -q
  19 passed in 0.72s

cd apps/api && uv run pytest tests/unit -q
  542 passed in 79.90s   (suíte inteira, nada quebrou)

cd apps/api && uv run pytest tests/integration/test_manual_orders.py -q
  7 passed in 93.03s     (testcontainers: Postgres real + Redis real)

cd apps/api && uv run pytest tests/integration/test_isolation.py tests/integration/test_rbac_matrix.py -q
  39 passed, 0 failed    (depois do conserto do §5; 1 falha antes dele, diagnosticada e resolvida)
```

## 8. Decisões que ficaram registradas em código (não escondidas)

- `direction=short` é recusado **na rota** (antes de qualquer leitura de
  Redis), não só deixado para o motor: `RISK_ENGINE.md` §2 (`max_leverage=1`)
  deixa claro que SPOT não tem short nesta etapa — não é uma leitura minha
  ambígua do "unless the engine supports it" do brief, é o que o contrato já
  diz.
- `spot_eligibility_reason`/`costs_from_ticker` são funções puras, sem
  Postgres/Redis, exatamente para o teste unitário de "reason mapping" pedido
  no brief (`apps/api/tests/unit/test_orders_service.py`).
- `services/orders.py` (204 linhas) e `services/orders_derive.py` (172 linhas)
  — split feito porque o arquivo único passou de 350 linhas; a divisão segue o
  mesmo padrão de `markets.py`/`markets_codec.py`/`markets_quality.py`
  (orquestração vs. derivação).

## Resumo em português (≤ 10 linhas)

A ordem manual paper agora existe: `POST /api/v1/orgs/{org_id}/portfolios/{id}/order-requests`
(TRADER+, idempotente), com `entry_ref`/custos derivados do mercado real (nunca
inventados), SPOT-only, short recusado por nome, sempre 202. `GET` lista e lê
uma solicitação com o desfecho. Caminho mudou de `.../orders` para
`.../order-requests` porque `.../orders` já existia com outro significado —
documentado no topo dos arquivos. Achei e conservei uma guarda de RBAC/isolamento
desatualizada (`risk/limits` faltava, de outra tarefa) para não sobrar vermelha
por minha causa; achei e **não mexi** num bug de outra tarefa (`open_paper_wallet`
sob o papel errado em três testes que não são meus) — só reportando. 39/39 nos
guardas, 7/7 no meu teste de integração, 19/19 + 542/542 nos unitários, tudo
com Postgres/Redis reais.

---

# T3.68b — correção dos achados de risk-engine-guardian e security-reviewer

**Status:** todos os 10 achados fechados, exceto o #8 (teto de pendentes por
carteira), declarado como T3.68c abaixo pela razão que o próprio achado
permite ("or declare it as T3.68c with the reason").

## Achado 1 (ALTA) — `slippage_bps=0` sub-custeava a ordem manual

**Achado:** `orders_derive.py:193` usava `ExecutionPolicy().extra_slippage_bps`
(= 0) como se fosse a hipótese de slippage; esse campo é o ajuste *além* da
caminhada do livro, não uma hipótese em si. Custear a 0 dimensiona a ordem
manual **maior** que uma estratégia dimensionaria a mesma geometria para o
mesmo rótulo de 0,25 % (`risk_per_trade_pct`).

**Fix:** nova constante `orders_derive.MANUAL_ORDER_SLIPPAGE_BPS = Decimal("5")`
— o mesmo valor que toda estratégia declara (`breakout_v1`, `momentum_v1`,
`mean_reversion_v1`, `mean_reversion_h1_v1`, `sweep_reclaim_v1`,
`session_orb_v1`, `volume_anomaly_v1`, todas `slippage_bps=Decimal("5")`),
com um `assert` de módulo amarrando o valor ao teto do motor
(`hunter_risk.limits.PAPER_V1.max_slippage_pct`). `docs/RISK_ENGINE.md` §8
reescrito para não citar mais `ExecutionPolicy.extra_slippage_bps` como fonte.

**Teste:** `test_orders_service.py::TestCostsFromTicker::
test_manual_slippage_matches_the_strategy_path_for_the_same_geometry` — mesma
geometria via `costs_from_ticker` (caminho manual) e via
`hunter_core.strategies.base.assumed_costs(BreakoutV1.default_parameters)`
(caminho de estratégia): `slippage_bps` idêntico nos dois, `Decimal("5")`.

**Saída:** `uv run pytest tests/unit/test_orders_service.py -q` → `24 passed`.

## Achado 2 (ALTA) — filiação sem auditoria, ator descartado

**Achado:** `admission.py:150-268` recebia `context.principal.user_id` em
`ProposalRequest.actor_id` e nunca escrevia um `audit_logs` na filiação — só a
decisão do motor (um segundo depois, como `hunter_worker`) era auditada, e a
reconstrução de produção (`hunter_execution_worker.admission_cycle.
rebuild_request`, fora do meu escopo) carimba essa decisão com
`actor_type="worker"`, nunca com o operador.

**Fix:** novo módulo `services/admission_audit.py` (split para caber no
orçamento de 350 linhas), `record_filing_audit()` — grava uma linha
`order_request.filed` (`actor_type="user"`, `actor_id`=o operador,
`entity_type="trade_proposal"`, `entity_id`=o `proposal_id`) através do
`SqlAuditSink` já vinculado por `org_session`, na mesma transação do
`INSERT`. `after` carrega a geometria filiada + hash do idempotency key
(`params_hash`), nunca o valor cru do header. **Deliberadamente não** escrevi
o ator em `trade_proposals.request_payload`: essa coluna é comparada
byte-a-byte contra um payload recém-reconstruído (sem ator) por
`hunter_core.admission.dedupe._payload_pair` quando o motor decide a mesma
linha — acrescentar uma chave ali faria toda ordem manual falhar seu próprio
teste de replay assim que o worker olhasse para ela (`packages/core`, fora do
meu escopo de edição; documentado no docstring do módulo).

**Teste:** `test_manual_orders.py::TestFilingAndDeciding::
test_202_pending_then_decided_writes_the_engines_audit_row` — agora assere
duas linhas de auditoria (`order_request.filed` + `proposal.rejected`), com
`filed_row.actor_type == "user"` e `filed_row.actor_id == wallet.actor.user_id`.

**Saída:** `uv run pytest tests/integration/test_manual_orders.py -q -p no:randomly`
→ `10 passed in 103.96s` (Postgres + Redis reais).

## Achado 3 (MÉDIA) — texto cru do Postgres vazando no 422/409

**Achado:** `admission.py:259` fazia `OrderRefusedError(str(exc.orig))` — a
linha `DETAIL` do driver, que pode ecoar os próprios valores enviados; `:283-286`
(`_refuse_a_different_order`) devolvia `{stored} != {asked}` no corpo do 409,
que pode carregar preço/stop/notional da ordem anterior.

**Fix:** `admission_audit.integrity_reason()` mapeia os nomes reais das
constraints de `trade_proposals` (`fk_trade_proposals_organization_id_
organizations`, `fk_trade_proposals_portfolio_id_portfolios`,
`fk_trade_proposals_market_id_markets`,
`ck_trade_proposals_request_payload_is_a_geometry`) para uma razão nomeada,
com `order_rejected_by_database` como fallback — nunca `str(exc.orig)`.
`_refuse_a_different_order` agora só cita `proposal_id` e
`reason: order_replay_conflict`, nunca os valores que divergiram.

**Teste:** `TestReplayAcrossWallets` (achado 5, abaixo) exercita
`OrderReplayConflictError` e confere que a mensagem carrega
`order_replay_conflict`, nunca a geometria da ordem anterior. Não escrevi um
teste que force uma violação de constraint real (exigiria corromper o DB por
baixo do ORM); `integrity_reason()` é pura e teria sido testável isoladamente,
mas as quatro entradas do mapa já são cobertas por inspeção de nome de
constraint contra `hunter_core/db/models/execution.py`.

**Saída:** ver achado 5.

## Achado 4 (MÉDIA) — `entry_ref` sem checar a idade do ticker

**Achado:** `orders_derive.py:165-210` derivava `entry_ref`/`assumed_costs`
do ticker do Redis sem nunca olhar seu `ts` — um ticker morto ou nunca escrito
não era distinguido de um fresco.

**Fix:** `costs_from_ticker(ticker, *, now)` agora exige `now` explícito
(nunca lido internamente) e, depois de validar preço/spread, lê `ticker["ts"]`
(mesmo helper `to_timestamp` que `services/markets.py` já usa) e recusa por
nome: `spot_ticker_missing` (ausente/ilegível) ou `spot_ticker_stale`
(idade fora de `[0, hunter_risk.limits.PAPER_V1.max_price_age_s]` — 10 s,
lido do perfil, nunca hardcoded; negativo cobre um relógio do futuro).
`reference_and_costs`/`file_order` passam o `now` do pedido adiante.

**Teste:** `TestCostsFromTicker::test_a_ticker_with_no_ts_is_spot_ticker_missing`,
`test_a_stale_ticker_is_spot_ticker_stale`,
`test_a_ticker_exactly_at_the_age_limit_is_accepted`,
`test_a_ticker_from_the_future_is_spot_ticker_stale` — fresco, no limite,
velho e ausente, os quatro. As fixtures antigas sem `ts` continuam retornando
sua própria razão (`spot_price_unavailable`/`spot_spread_unavailable`),
porque a checagem de `ts` só roda depois de preço e spread já validados.

**Saída:** `uv run pytest tests/unit/test_orders_service.py -q` → `24 passed`
(incluída na saída do achado 1).

## Achado 5 (MÉDIA) — replay pendente comparava sem `portfolio_id`

**Achado:** `admission.py:210-231` + `orders.py:197-201` — o idempotency key é
único por `(organization_id, idempotency_key)`, nunca por carteira;
`request_payload` não tem `portfolio_id` (§21.1), então duas carteiras da
mesma organização filiando a mesma chave com geometria idêntica comparavam
igual e devolviam o `proposal_id` da *outra* carteira — que a leitura de volta
em `orders.py` não achava sob o `portfolio_id` do chamador, um 500 no lugar
de um 409.

**Fix:** `admission.py`, ramo `pending`, comparação de `pending.portfolio_id`
contra o `portfolio_id` pedido **antes** de qualquer comparação de payload —
`OrderReplayConflictError` nomeado (`reason: order_replay_conflict`) de
imediato quando divergem.

**Teste:** novo `TestReplayAcrossWallets::test_same_key_two_wallets_is_409_never_500`
— duas carteiras reais na mesma organização (a segunda, `is_arena=True`,
inserida como `hunter_app`, fora do índice de permanência
`uq_portfolios_principal_paper` — a guarda de nascimento
`portfolios_are_born_audited` só restringe quem só tem o papel do motor;
`hunter_app` "cria portfolios não-principais hoje", pelo próprio docstring da
migração), mesma chave, mesma geometria: primeira filiação pendente, segunda
levanta `OrderReplayConflictError` com `order_replay_conflict` na mensagem —
nunca um 500.

**Saída:** `uv run pytest tests/integration/test_manual_orders.py -q -p no:randomly`
→ `10 passed in 103.96s`.

## Achado 6 (MÉDIA) — tautologia `approved in (True, False)`

**Achado:** `test_manual_orders.py:438` — a fixture padrão (`STOP`, 3,33 % de
distância) é **sempre** recusada por `stop_distance` (banda `[0,3 %, 3 %]`),
então a asserção nunca falhava, com ou sem bug.

**Fix:** a asserção existente virou uma recusa nomeada de verdade —
`assert decision["approved"] is False` +
`checks["stop_distance"]["state"] == "failed"`. Nova classe
`TestApprovedGeometry` com `STOP_APPROVABLE = LAST_PRICE - 300` (1 % de
distância, dentro da banda), mesmo mercado líquido (`quote_volume_24h` =
R$ 260 M ≥ o piso de R$ 50 M) e ticker fresco: `approved is True`,
`sizing["binding_constraint"]` não vazio, `Decimal(sizing["qty"]) > 0`.
`TestKillSwitch` já cobria uma recusa nomeada por outro motivo
(`kill_switch`) e continua como está.

**Saída:** `uv run pytest tests/integration/test_manual_orders.py -q -p no:randomly`
→ `10 passed in 103.96s` (inclui `TestApprovedGeometry`).

## Achado 7 (BAIXA) — charset do `Idempotency-Key`

**Achado:** `routers/orders.py:57-64` só validava tamanho (8–128), não
charset — um valor com espaços sobreviveria ao `.strip()` de `admission_key`
de forma inconsistente entre duas requisições que discordassem só em
espaço em branco.

**Fix:** `Header(..., pattern=r"^[A-Za-z0-9_.:-]+$")` somado ao
`min_length`/`max_length` existentes — um valor fora do charset já é 422 na
validação do FastAPI, antes de chegar a `admission_key`.

**Teste:** `TestRoleAndMarketRefusals::test_an_idempotency_key_with_a_space_is_422`
— `Idempotency-Key: "t368 has a space"` (tamanho válido, charset inválido) →
422, antes de qualquer leitura de Redis ou de banco.

**Saída:** `uv run pytest tests/integration/test_manual_orders.py -q -p no:randomly`
→ `10 passed in 103.96s`.

## Achado 8 (BAIXA) — teto de pendentes por carteira: **adiado para T3.68c**

**Achado:** nenhum limite no número de `trade_proposals` pendentes por
carteira — um operador (ou um bug de cliente) poderia empilhar pedidos sem
fim.

**Razão do adiamento:** o achado pede para ler `N` de *settings* (`ApiSettings`,
com um default como 20). `apps/api/hunter_api/settings.py` **não está** na
lista de arquivos em escopo desta tarefa (`.claude/state/brief-T3.68-ordem-
manual-api.md` + a instrução do T3.68b), e adicionar um campo de configuração
novo, cruzando toda a superfície de settings/deploy, é maior que um "fix
cirúrgico" — o próprio achado autoriza declarar como tarefa separada quando é
esse o caso ("or declare it as T3.68c with the reason"). Registrando aqui para
o orquestrador abrir T3.68c.

## Achado 9 (NOTA) — import de `hunter_exchanges` no topo do módulo

**Achado:** `from hunter_exchanges.binance_spot.fees import SPOT_VIP0` no topo
de `orders_derive.py` importa o pacote inteiro de adaptadores de exchange no
processo da API só por uma constante.

**Fix:** import movido para dentro de `costs_from_ticker`, depois das
checagens de preço/spread/ticker (não vale a pena importar antes de saber que
o resto vai passar). `hunter-exchanges` continua como dependência real de
`apps/api/pyproject.toml` (do T3.68 original) — a mudança é só o *onde*, não
o *se*.

**Teste:** nenhum teste dedicado (é uma mudança de posição de import, sem
comportamento novo); os testes existentes de `TestCostsFromTicker` continuam
passando e exercitam o caminho que agora importa sob demanda.

## Achado 10 — `test_portfolio_api.py:84` sem `db_role`

**Fix:** `_open()` agora abre com `tenant_session(..., db_role="hunter_worker")`,
igual às outras duas suítes.

**Saída:** `uv run pytest tests/integration/test_portfolio_api.py -q -p no:randomly`
→ `17 passed in 137.35s`.

## Comandos e saídas completas (T3.68b)

```
uv run pytest tests/unit/test_orders_service.py -q
  24 passed in 0.65s

uv run pytest tests/unit -q
  547 passed in 70.12s   (suíte inteira, 5 a mais que antes de T3.68b)

uv run pytest tests/integration/test_manual_orders.py -q -p no:randomly
  10 passed in 103.96s   (Postgres + Redis reais; 2 novas classes,
                          TestApprovedGeometry e TestReplayAcrossWallets,
                          + o teste de charset do achado 7)

uv run pytest tests/integration/test_portfolio_api.py -q -p no:randomly
  17 passed in 137.35s

uv run pytest services/execution-worker/tests/test_manual_request_decided.py -q -p no:randomly
  1 passed in 26.88s     (não é meu arquivo; só confirmando que a mudança em
                          admission.py não quebrou o caminho de produção do
                          worker)

uv run ruff check <9 arquivos meus>            → All checks passed!
uv run ruff format --check <os mesmos>          → 9 files already formatted
uv run pyright <os mesmos>                      → 0 errors, 0 warnings

uv run python infra/scripts/check_file_size.py
  scanned 594 files; 0 over budget, 0 grandfathered
```

## T3.68b — novos slugs

Nenhum path, campo ou slug documentado foi removido ou renomeado — só
adições, todas em `detail`/reason strings, nunca em forma de resposta:

- `spot_ticker_missing` (422) — ticker sem `ts` legível.
- `spot_ticker_stale` (422) — `ts` fora de `[0, max_price_age_s]`.
- `order_replay_conflict` (409, `OrderReplayConflictError`, mesmo
  `type_slug` `idempotency-key-conflict` de sempre) — agora nomeado dentro de
  `detail` nos três casos (constraint concorrente, payload divergente,
  carteira divergente); antes o texto variava sem uma palavra-chave fixa.
- `organization_unknown`, `wallet_unknown`, `invalid_order_geometry`,
  `order_rejected_by_database` (422) — só aparecem numa violação de
  constraint real (corrida rara: org/wallet/market apagados entre a
  validação da rota e o `INSERT`, ou um payload malformado); não deveriam
  ocorrer no caminho normal.

## Arquivos criados/modificados (T3.68 + T3.68b, `git status --porcelain`)

```
 M apps/api/hunter_api/app.py                          [T3.68]
 M apps/api/hunter_api/services/admission.py            [T3.68b]
 M apps/api/pyproject.toml                              [T3.68]
 M apps/api/tests/integration/test_isolation.py         [T3.68]
 M apps/api/tests/integration/test_portfolio_api.py     [T3.68b, achado 10]
 M apps/api/tests/integration/test_rbac_matrix.py       [T3.68]
 M docs/ACTIVATION.md                                   [T3.68]
 M docs/RISK_ENGINE.md                                  [T3.68b, achado 1]
 M uv.lock                                               [T3.68]
?? .claude/state/notes-T3.68.md                          [T3.68 + T3.68b]
?? apps/api/hunter_api/routers/orders.py                [T3.68b, achado 7]
?? apps/api/hunter_api/schemas/orders.py                [T3.68]
?? apps/api/hunter_api/services/admission_audit.py      [T3.68b, novo — achados 2, 3]
?? apps/api/hunter_api/services/orders.py               [T3.68b, achado 4 (thread now)]
?? apps/api/hunter_api/services/orders_derive.py        [T3.68b, achados 1, 4, 9]
?? apps/api/tests/integration/test_manual_orders.py     [T3.68b, achados 2, 5, 6]
?? apps/api/tests/unit/test_orders_service.py           [T3.68b, achados 1, 4]
```

Fora desta lista, no mesmo `git status --porcelain` (não são meus, de outros
agentes trabalhando em paralelo na mesma árvore — o agente de frontend
alinhando ao contrato desta tarefa, e outras tarefas em curso):
`apps/web/components/portfolio/manual-orders-table.tsx`,
`apps/web/lib/api/manual-orders-{actions,types}.ts`, `apps/web/lib/api/manual-orders.ts`,
`apps/web/tests/manual-orders-{actions,types}.test.ts`, `.claude/launch.json`,
`apps/web/app/(app)/[orgSlug]/portfolio/page.tsx` e outros arquivos de
`apps/web`/`packages/indicators`/`services/strategy-worker`/`docs/{DESIGN,PIPELINE}.md`
sem relação com T3.68/T3.68b.

**Não toquei:** `apps/web/**`, `packages/risk-core/**`,
`services/execution-worker/**`, `apps/api/hunter_api/settings.py` (achado 8,
declarado T3.68c), nenhum `.env*`.

---

# T3.68c — teto de pedidos manuais pendentes por carteira (achado 8 do T3.68b)

**Status:** DONE.

## 1. O que foi implementado

- `ApiSettings.manual_order_max_pending_per_portfolio` (padrão 20,
  `apps/api/hunter_api/settings.py`) — documentado inline; **não** escrito em
  `.env.example` porque este despacho proíbe tocar qualquer `.env*` (registrado
  como limitação conhecida no próprio docstring do campo).
- `hunter_api.services.admission.file_manual_order` ganhou o parâmetro
  obrigatório `max_pending: int`. O teto é checado **dentro do mesmo `INSERT`**
  que arquiva o pedido, nunca num `SELECT count(*)` separado antes: o `INSERT`
  virou `INSERT ... SELECT ... WHERE (SELECT count(*) FROM trade_proposals
  WHERE organization_id = :org AND portfolio_id = :pf AND source = 'manual'
  AND status = 'pending') < :cap`. Zero linhas inseridas (`result.rowcount ==
  0`) é o sinal de "carteira cheia" — nomeado, nunca um 500 — e nunca se
  confunde com a violação de unicidade da chave de idempotência (essa continua
  levantando `IntegrityError`, um caminho totalmente separado).
- `TooManyPendingRequestsError` (409, `type_slug="too-many-pending-requests"`,
  `detail` carrega `reason: too_many_pending_requests`) — nova, em
  `services/admission_audit.py` (não em `admission.py`: colocá-la lá estourava
  o orçamento de 350 linhas; `admission_audit.py` já era "por que uma escrita
  falhou", a mesma família de `integrity_reason`).
- `services/orders.py::file_order` e `routers/orders.py` passam
  `max_pending=settings.manual_order_max_pending_per_portfolio` adiante — o
  mesmo padrão que `routers/markets.py` já usa para `market_stale_after_s`
  (`Depends(get_settings)`, valor lido uma vez, passado como argumento
  explícito ao serviço, nunca lido de dentro dele).

## 2. Por que nunca uma corrida deixa passar o 21º pedido (quase)

O brief pediu para usar o lock/`SELECT ... FOR UPDATE` por carteira já
existente, **ou** declarar por que uma corrida benigna é aceitável para papel.
Não existe nenhum dos dois em `admission.py` hoje — conferido por grep
(`advisory_lock|pg_advisory|FOR UPDATE` em `apps/api` e `packages`, zero
ocorrências fora do comentário que **explica por que não há um**): desde
`0007_paper_roles`, `hunter_app` perdeu `UPDATE`/`DELETE` em `trade_proposals`,
então um `SELECT ... FOR UPDATE` sob esse papel é erro de permissão, não espera
de lock (comentário "Unlocked" já existente, section T3.5c). E
`docs/SPEC_REVIEW.md` R7 já decidiu, para todo o produto, **sem locks
consultivos de sessão** — o motivo é o pooler (Neon/PgBouncer em modo
*transaction*): um lock de sessão (`pg_advisory_lock`) sobrevive a uma conexão
que o pooler pode devolver a outro chamador no meio do que pareceria ser a
mesma "sessão". Um lock **de transação** (`pg_advisory_xact_lock`) seria seguro
sob esse modo de pooling (é liberado no `COMMIT`/`ROLLBACK`, que é exatamente o
limite do pooler) — mas introduzir *qualquer* lock novo no vocabulário do
produto é uma decisão de arquitetura (`database-architect`/
`risk-engine-guardian`), não um "fix cirúrgico" cabível neste despacho, que
não me dá permissão para tocar `packages/risk-core/**` nem para inventar
convenções novas fora do escopo.

**A solução que ficou:** uma única instrução (`INSERT ... SELECT ... WHERE
<count> < :cap`) em vez de duas (`SELECT count(*)` depois `INSERT`) — isso
fecha a janela óbvia (não há mais um instante entre "eu contei 19" e "eu
inserí o 20º" *para esta conexão*), mas duas conexões genuinamente
concorrentes ainda podem, cada uma, avaliar a subquery antes de a outra ter
commitado a sua própria linha (MVCC: uma linha não commitada não é visível
para a subquery da outra transação) — as duas passam, o teto estoura por
exatamente o tamanho da concorrência real.

**Por que isso é aceitável para papel:** (1) o caminho manual é um humano
clicando um botão numa tela — concorrência genuína na casa de milissegundos,
na mesma carteira, contra a mesma chave de idempotência diferente, não é um
padrão de uso real, é um teste de estresse; (2) mesmo se acontecer, nada é
perdido nem corrompido — cada linha extra ainda passa pelo motor de risco de
verdade um segundo depois, exatamente como qualquer outro pedido; (3) é
dinheiro de papel. O teto existe para conter um operador (ou um bug de
cliente) que empilha pedidos sem parar, não para ser uma garantia
criptográfica de exclusão mútua.

## 3. TDD — testes escritos primeiro, vistos falhar pelo motivo certo

Unitários (`apps/api/tests/unit/test_admission_adapter.py`,
`TestThePerPortfolioPendingCap`, e `test_orders_service.py`,
`TestManualOrderMaxPendingPerPortfolioSetting`) escritos antes da
implementação; rodados e vistos falhar com `TypeError: file_manual_order() got
an unexpected keyword argument 'max_pending'` (o parâmetro ainda não existia)
antes de qualquer código de produção mudar. `RecordingSession` (o dublê de
sessão desses testes) ganhou um `_FakeResult(rowcount=...)` porque o produto
agora lê `result.rowcount` depois do `INSERT` — sem isso os testes existentes
quebravam com `AttributeError` num `None`, então o dublê foi atualizado junto
(não é um teste novo, é o mesmo dublê ficando honesto sobre o que a função real
agora faz com o retorno de `execute()`).

Integração (`test_manual_orders.py::TestPendingCap`): dois achados reais,
achados pelo próprio teste, corrigidos antes de reportar:

- **Teste esqueceu de repassar `max_pending`** em
  `TestReplayAcrossWallets::test_same_key_two_wallets_is_409_never_500`, que
  chama `admission.file_manual_order` direto (sem passar pelo router) —
  `TypeError: missing 1 required keyword-only argument`. Corrigido com uma
  constante `DEFAULT_MAX_PENDING = ApiSettings.model_fields[...].default`
  (nunca hardcoded duas vezes) passada nas duas chamadas diretas do arquivo.
- **Ticker ficava obsoleto no meio do laço de 20 requisições.** O teto real
  (20) exige 20 `POST`s sequenciais contra Postgres/Redis via testcontainers;
  a suíte inteira já leva ~2 min, e o limite de idade do ticker
  (`max_price_age_s`, 10 s, RISK_ENGINE §7.1) estourava antes do laço
  terminar — `422 spot_ticker_stale` em vez do `202` esperado. Corrigido
  reescrevendo o ticker (`_write_ticker`) a cada iteração do laço, não uma vez
  antes dele.

Depois dos dois consertos: `TestPendingCap` cobre as duas metades do achado 8 —
`test_reaching_the_cap_is_a_named_409_and_a_decided_one_frees_a_slot` enche o
teto real (20) de pedidos indecisos, confere que o 21º é 409 nomeado
(`too_many_pending_requests`) e que nada novo foi escrito (`SELECT count(*)`
direto no banco == 20), depois decide um dos vinte
(`hunter_core.admission.service.admit`, o mesmo caminho de produção do
worker) e confere que a vaga libera — um pedido *decidido* não conta mais.

## 4. `admission.py` estourou 350 linhas — resolvido por split, não por prosa curta demais

A implementação inicial (docstring completa explicando a corrida + a nova
exceção *dentro* de `admission.py`) chegou a 395 linhas. Resolvido em duas
frentes, na ordem que o CLAUDE.md pede ("split by responsibility, not by line
count", só depois enxugar prosa):

1. `TooManyPendingRequestsError` mudou de `admission.py` para
   `services/admission_audit.py` — o mesmo módulo que T3.68b já tinha criado
   para tirar de `admission.py` exatamente esta classe de coisa ("por que uma
   escrita falha/é recusada", ao lado de `integrity_reason`). Reexportada por
   `admission.py` (`from .admission_audit import TooManyPendingRequestsError`
   + `__all__`), então `adapter.TooManyPendingRequestsError` nos testes
   continua funcionando sem mudança de import nos consumidores.
2. A prosa da docstring de `file_manual_order` sobre a corrida foi enxugada
   várias vezes (de ~30 linhas para 5), com o raciocínio completo movido para
   aqui (§2 acima) em vez de duplicado em comentário de código.

Resultado: `admission.py` 349 linhas, `admission_audit.py` 122 linhas.

## 5. Comandos e saídas reais

```
cd apps/api && uv run pytest tests/unit/test_admission_adapter.py tests/unit/test_orders_service.py -q
  40 passed in 0.62s

cd apps/api && uv run pytest tests/unit -q
  553 passed in 68.21s   (suíte inteira; 6 a mais que o fim do T3.68b — os
                          testes novos deste achado, nada quebrou)

cd apps/api && uv run pytest tests/integration/test_manual_orders.py -q -p no:randomly
  11 passed in 134.93s   (Postgres + Redis reais; 1 teste a mais,
                          TestPendingCap, que exercita o teto real de 20)

uv run ruff check <9 arquivos meus>              → All checks passed!
uv run ruff format --check <os mesmos>            → 8 files already formatted
uv run pyright <os mesmos>                        → 0 errors, 0 warnings
uv run python infra/scripts/check_file_size.py
  scanned 596 files; 0 over budget, 0 grandfathered
```

Uma corrida anterior de `pyright apps/api` (o pacote inteiro, não só os meus
arquivos) mostrou 11 erros pré-existentes em `test_lab_signals_pagination_api.py`
e `test_risk_limits_api.py` — nenhum dos dois é meu arquivo, nenhum dos dois
citado neste despacho; não mexi.

## 6. Arquivos criados/modificados (`git status --porcelain`, só os meus)

```
 M apps/api/hunter_api/routers/orders.py
 M apps/api/hunter_api/services/admission.py
 M apps/api/hunter_api/services/admission_audit.py
 M apps/api/hunter_api/services/orders.py
 M apps/api/hunter_api/settings.py
 M apps/api/tests/integration/test_manual_orders.py
 M apps/api/tests/unit/test_admission_adapter.py
 M apps/api/tests/unit/test_orders_service.py
 M docs/RISK_ENGINE.md
 M .claude/state/notes-T3.68.md
```

Fora desta lista, no mesmo `git status --porcelain` (não são meus — outro
agente trabalhando em paralelo na mesma árvore, tarefa alheia a T3.68/T3.68b/
T3.68c): `apps/api/hunter_api/schemas/risk_limits.py`,
`apps/api/hunter_api/services/risk_limits.py`,
`apps/api/tests/integration/test_risk_limits_api.py` — os mesmos que
apareceram na corrida de `pyright apps/api` do pacote inteiro (§5), não
tocados por mim.

**Não toquei:** `apps/web/**`, `services/**`, `packages/risk-core/**`,
nenhum `.env*` (inclusive `.env.example` — o valor default de
`MANUAL_ORDER_MAX_PENDING_PER_PORTFOLIO` não está documentado lá por essa
razão, só no docstring do campo em `settings.py`). Não fiz `git commit`.
