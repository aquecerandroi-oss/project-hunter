# Especificação executável — T3.9 (as nove verificações + fronteiras + concorrência)

**Data:** 2026-09-06. **Autor:** test-engineer, preparatória à T3.9. **Sem código de teste
ainda** — isto é o roteiro fechado a partir do qual a T3.9 escreve os testes, e contra o qual
T3.3 (ledger), T3.4 (simulador), T3.6 (kill switch) e T3.1b (correções do schema) podem ser
conferidas enquanto ainda estão em voo.

**Fontes, na ordem em que fecham cada número usado abaixo:**
`.claude/state/directive-risk-engine-2026-09-06.md` (a regra), `docs/plans/M3.md` (o escopo da
T3.9 e o checklist de aceite por tarefa — é dali que vem a lista canônica das nove verificações,
que o texto solto da diretiva funde em oito), `docs/RISK_ENGINE.md` v2.1 (o contrato), `docs/DATABASE.md`
§18 (o schema que precisa segurar cada garantia), `.claude/state/review-T3.2-risk-core.md` e
`.claude/state/review-T3.1-security.md` (os achados bloqueantes cujos números eu reaproveito),
`.claude/state/notes-T3.0a.md` (SPOT real: filtros do BTCUSDT, book sem timestamp),
`packages/risk-core/tests/unit/{test_review_findings.py,test_sizing.py,test_kill_switch.py,factories.py}`
(os números fechados abaixo em negrito **já são verdes no núcleo puro** — cito o teste exato que
prova cada um; a T3.9 não os reprova, prova que **sobrevivem** ao caminho persistido completo:
banco, admissão, execução, API).

**O que este documento não é:** não é a implementação de T3.3/T3.4/T3.6, e não afirma que elas
estão prontas. Onde citei arquivos de `packages/core/hunter_core/{portfolio,execution}/**` e
`packages/core/hunter_core/risk/**`, é porque já existem no repositório *em voo* (confirmado por
leitura direta em 2026-09-06); onde a assinatura ou o comportamento exato não está fechado, digo
isso explicitamente em vez de inventar.

---

## §0. Fixture base — reaproveitada em todas as seções, não redeclarada em cada uma

### Carteira

- Câmbio de teste fixo: **5,00 BRL/USDT**, fonte `source="test_fixed"`, par `USDTBRL`
  (`fx_observations.pair`, `packages/core/hunter_core/portfolio/attribution.py:FX_PAIR`). Este
  valor não é inventado aqui: é o mesmo da convenção já em uso em
  `packages/risk-core/tests/unit/test_sizing.py::TestTheWorkedExample` ("R$100,000 at a test rate
  of 5.00 BRL/USDT = 20,000 USDT of equity") — reaproveitado para que os números desta nota e os
  do núcleo puro já provado sejam o mesmo número, não uma coincidência de casas decimais.
- `origin_amount = 100.000,0000000000` BRL, `rate = 5,0000000000`, `credited_amount =
  20.000,0000000000` USDT, `conversion_residual = 0,0000000000` (100.000 = 20.000 × 5 exato, sem
  resíduo — a fixture canônica deliberadamente não exercita a política de arredondamento de
  `convert_opening`; um caso à parte com resíduo não-zero é responsabilidade da T3.11, não desta
  nota, que só herda o número aberto).
- Preset `paper_v1` (`docs/RISK_ENGINE.md` §2), copiado para a organização no onboarding.
- `equity = cash = peak_equity = day_start_equity = 20.000,0000000000` USDT no instante `NOW`
  (mesmo `NOW` de `factories.py`: `2026-09-06T18:30:00Z`), sem posições nem pendências abertas —
  o "dia zero" da carteira.

### Mercados sintéticos, rotulados com filtros reais

| Mercado | Papel na spec | Filtros | Proveniência |
|---|---|---|---|
| `binance:spot:BTCUSDT` | mercado "grande" (participação nunca limita) | `LOT_SIZE`/`MARKET_LOT_SIZE` `minQty = stepSize = 0,00001000`; `NOTIONAL` `minNotional = 5` USDT, `applyMinToMarket = true` | medido ao vivo em 2026-09-06 (`.claude/state/notes-T3.0a.md` §10: `BTCUSDT min_qty=0.00001000 ... reason='min_notional'` para notional 0,80 USDT) |
| `binance:spot:ETHUSDT` | segundo mercado, para concorrência/agregação entre mercados | `LOT_SIZE`/`NOTIONAL` — **decisão pendente:** os valores exatos não foram medidos nesta nota; o teste real lê `spot_exchange_info.json` (fixture gravada por `record_spot.py`, `.claude/state/notes-T3.0a.md` §7) em vez de um número que eu não verifiquei | fixture gravada, não lida por mim nesta tarefa |
| um mercado sintético genérico "SOL" (`SOLUSDT`) | usado nos cenários herdados do núcleo puro (§1, §2), porque é o mercado de `factories.py` | `step_size = 0,001`; `min_notional = 5`; `tick_size = 0,01` | `packages/risk-core/tests/unit/factories.py::spec()` |

Preço de referência sintético do BTCUSDT nos cenários de filtro (§7): **80.000,00** USDT — rotulado
como sintético (não é o preço ao vivo do dia da medição, que era ≈80.182,86); a escolha de um
número redondo é deliberada para o teste não acoplar a um preço de mercado que muda todo dia.

### Custos assumidos (Risk Engine) vs taxa real (execução)

Dois números diferentes, nunca confundidos (`.claude/state/notes-T3.0a.md` §6):

- **`AssumedCosts`** (hipótese do Risk Engine para o sizing, `packages/core/hunter_core/strategies/envelope.py`):
  `spread_bps=2`, `slippage_bps=5`, `fee_bps=4` — é o `COSTS` de `factories.py`, e é o que produz
  os números de §1/§2 abaixo.
- **Taxa SPOT real** (`hunter_exchanges/binance_spot/fees.py:SPOT_VIP0`): **10 bps** maker e taker
  (0,10 %/0,10 %), sem desconto BNB — é o que a T3.4 realmente debita da quantidade em fills. É a
  taxa usada em §5 (reconciliação), nunca a hipótese de §1.

### Camadas e onde cada uma já está provada

| Camada | O que já prova | Onde |
|---|---|---|
| núcleo puro (`hunter_risk`) | sizing, exposição, kill switch, tie-break, `unavailable` | `packages/risk-core/tests/unit/**`, **verde hoje** |
| ledger/execução (`hunter_core.portfolio`, `hunter_core.execution`) | atribuição BRL, arredondamento da abertura, forma do `ExecutionReport` | `packages/core/hunter_core/{portfolio,execution}/**`, **em voo, parcial** (T3.3/T3.4) |
| schema (`0006_paper_wallet`) | RLS, permanência, FKs compostas, auditoria do kill switch | `infra/migrations/versions/0006_*.py`, `packages/core/tests/integration/test_schema_paper.py`, **com dois bloqueantes abertos** (`review-T3.1-security.md`) |
| worker (`execution-worker`) | ciclo de ordem, MTM, recuperação após restart | `services/execution-worker/**`, **inexistente ainda** (só o esqueleto do pacote) |
| API/Web (T3.8) | ordem manual, Risk Center, isolamento de tenant | `apps/api/hunter_api/routers/{portfolio,orders,risk,proposals}.py`, **inexistente ainda** |

A T3.9 não pode rodar as camadas "em voo/inexistente" antes delas existirem — cada seção abaixo
declara a dependência exata, e o "arquivo-alvo" é onde o teste **vai morar**, não uma alegação de
que ele já roda.

---

## V1. Cálculo de tamanho, exposição e risco agregado

**Objetivo:** provar que o tamanho final aprovado, publicado e persistido é o mínimo entre os nove
tetos do contrato (§4), com o limitante vencedor e os dois contrafactuais gravados — não recalculado
diferente em cada camada.

**Pré-condições:** carteira do §0; proposta LONG `entry_ref=100`, `stop=97,5` (2,5 % de distância),
`AssumedCosts` = `COSTS` do §0, mercado sintético "SOL" (`step_size=0,001`, `min_notional=5`),
liquidez com `last_price=mid=100`, book fundo (nunca limita), `quote_volume_24h ≥ 50.000.000`.

**Passos:**
1. Submeter a proposta por ordem manual paper (rota da T3.8), sem kill switch ativo, sem posições
   nem pendências.
2. Ler `trade_proposals.risk_decision` persistida e comparar com o que `hunter_risk.evaluate()`
   calcularia isoladamente com os mesmos insumos.
3. Repetir com `last_minute_quote_volume = median_30m_quote_volume = 4.605,10` USDT (a mediana
   histórica medida em KB-0067/0071) para forçar o teto de participação a vencer.
4. Repetir com caixa `500` e uma pendência já reservando `400` (`reserved_notional=400`,
   `planned_risk_quote=0`) no mesmo portfolio, mercado diferente (ETHUSDT), para forçar o teto de
   caixa a vencer.

**Números esperados (fechados):**
- Passo 2 — cenário base: `stop_distance_pct = 0,025`; `cost_pct = 0,0020` (2 bps spread + 2×5 bps
  slippage + 2×4 bps fee); `binding_constraint = "risk_per_trade"`; `qty = 18,518`;
  **`notional = 1.851,800`**; `planned_risk_quote = 49,9986`. *(já verde em
  `test_sizing.py::TestTheWorkedExample::test_risk_per_trade_wins_and_produces_the_expected_notional`
  — V1 prova que o mesmo número sai do banco depois da T3.12, não recalcula.)*
- Passo 3 — participação vence: `binding_constraint = "market_participation"`;
  **`notional = 46,000`**; `size_without_participation.notional = 1.851,800` (o contrafactual não
  muda: é o mesmo cenário sem o teto). *(verde em
  `test_sizing.py::test_the_counterfactual_of_participation_measures_how_much_the_rule_bites`.)*
- Passo 4 — caixa vence: `available_cash = 99,599904` (500 − 400 × 1,00100024);
  `binding_constraint = "cash"`; `notional < 100` e `notional + 400 < 500`. *(verde em
  `test_review_findings.py::TestFinding4CashIsNetOfPendingReservations`.)*
- `risk_planejado_agregado` depois do passo 1: `planned_risk_open + planned_risk_pending` deve
  refletir a soma **não assinada** por posição (`docs/DATABASE.md` §18.3: "nunca `max(0, Σ
  assinado)`") — cenário adicional: uma posição com risco planejado −80 (lucro parcial já
  realizado no papel) e uma pendente com +100 têm de somar **20**, não 20 líquido nem `max(0, 20)`
  disfarçando um caso em que a soma seria diferente com sinais opostos maiores (ex.: −150 e +100 →
  agregado tem de ser lido como **−50 nunca vira 0**; a regra do contrato é que o agregado é sobre
  o **módulo dos riscos individuais somados**, não a soma assinada — decisão pendente abaixo).

**O que refuta:** o teste falha se o `notional` gravado no banco divergir do valor do núcleo puro
para os mesmos insumos; se `binding_constraint` publicado não bater com o teto que matematicamente
venceu; se os contrafactuais (`size_without_multipliers`, `size_without_participation`) forem iguais
entre si quando deveriam divergir; se o agregado de risco compensar uma posição lucrativa contra uma
perdedora para abrir espaço artificial.

**Camada:** integração (Postgres real) — depende de a `RiskDecision` sair do núcleo puro (T3.2,
pronto) e chegar ao banco pela admissão (T3.12) e pela ordem manual (T3.8).
**Arquivo-alvo:** `apps/api/tests/integration/test_orders_manual_sizing.py` (chamada HTTP → decisão
persistida) e `packages/core/tests/integration/test_admission_sizing.py` (se a T3.12 expuser uma
função chamável sem HTTP).
**Dependência:** T3.1 (colunas de reserva), T3.2 (pronto), T3.3 (montagem do `PortfolioState` a
partir do banco), T3.12 (caminho único de admissão), T3.8 (rota manual).

**Decisão pendente:** o contrato (`docs/RISK_ENGINE.md` §1, `planned_risk_open`) não escreve a
fórmula de agregação com o sinal explícito — `docs/DATABASE.md` §18.3 diz "nunca `max(0, Σ
assinado)`" mas não fixa se é `Σ |risco_i|` ou `Σ risco_i` com risco sempre não-negativo por
construção (uma posição *não pode* ter risco planejado negativo, já que é "perda planejada no
stop" — um número que não é lucro). Pergunta: existe algum caminho em que `planned_risk_quote` de
uma posição fica negativo (ex.: stop já movido para o breakeven, risco residual zero ou negativo por
trailing)? Se nunca, a ressalva acima é vácua e o agregado é sempre uma soma de não-negativos — quem
tocar T3.3/T3.5 deve confirmar isso antes da T3.9 escrever o teste de módulo vs. soma assinada.

---

## V2. Redução efetiva das entradas no modo aviso (AVISO)

**Objetivo:** provar que o multiplicador de AVISO (0,5) reduz o **tamanho final aprovado e
persistido** — não um orçamento intermediário que outro teto pode anular — no caminho completo
(kill switch lido do banco sob a mesma trava da decisão).

**Pré-condições:** carteira do §0, mas com uma perda de dia já registrada que a leve a **exatamente**
1 % (`equity = 19.800,0000000000`, `day_start_equity = 20.000`, `peak_equity = 20.000` — só a perda
diária dispara, não o drawdown, para isolar a causa). Proposta idêntica à do V1 passo 2 (a que sai
`1.851,800` em `ACTIVE`).

**Passos:**
1. Assentar a perda de dia por um MTM real (não escrever o campo à mão): uma posição existente ou
   uma sequência de fills que levem `equity` a 19.800, e então avaliar o kill switch
   (`hunter_core.risk` — `assess`/persistência da T3.6) e confirmar `effective = WARNING` antes de
   submeter a nova proposta.
2. Submeter a mesma proposta do V1 (entry_ref=100, stop=97,5) sob esse estado.
3. Repetir com `size_multiplier` vindo do **estado persistido**, não passado à mão no teste — o
   objetivo é provar que a leitura do kill switch pela admissão é a mesma leitura que o Risk Center
   mostra (T3.8), não duas fontes que podem discordar.

**Números esperados (fechados):**
- `entry_size_multiplier = 0,5` (`hunter_risk.kill_switch.entry_size_multiplier(WARNING, PAPER_V1)`
  — já verde em `test_kill_switch.py::test_one_percent_daily_loss_raises_the_warning`).
- `notional_before_multiplier = 1.851,800`; **`qty_final = 9,259`**; **`notional_after_multiplier =
  925,900`** (metade de 1.851,800 — floor ao `step_size=0,001` depois da divisão). *(já verde em
  `test_sizing.py::TestKillSwitchMultiplier::test_the_multiplier_halves_the_final_size_after_every_ceiling`.)*
- Repetindo o cenário do V1-passo-3 (participação vencendo, `notional=46,000` em `ACTIVE`) sob
  AVISO: o vencedor continua sendo `market_participation` e o `notional` cai (R-KS-1: o
  multiplicador morde **qualquer** teto vencedor, não só o de risco) — o número exato depende do
  `qty_by_participation` já calculado; o teste deve provar `notional_after < notional_before` e
  `binding_constraint` inalterado, sem fixar um terceiro número que ninguém mediu ainda.

**O que refuta:** o teste falha se o tamanho persistido em `ACTIVE` for igual ao de `WARNING` para a
mesma proposta e o mesmo teto vencedor (o defeito exato que a v1 do contrato tinha, R-KS-1); se o
multiplicador for lido de um cache desatualizado em vez do estado durável no momento da decisão; se
o `min_notional` pós-multiplicador não for revalidado (uma redução que deixasse `qty_final` abaixo
do piso deveria **rejeitar**, não arredondar para cima).

**Camada:** integração. **Arquivo-alvo:**
`apps/api/tests/integration/test_kill_switch_sizing.py`.
**Dependência:** T3.6 (persistência do kill switch), T3.3 (equity real via MTM, não escrita à mão),
T3.12 (admissão lendo o estado efetivo na mesma transação).

---

## V3. Bloqueio de entradas sem desligar as proteções (BLOQUEADO)

**Objetivo:** provar que `TRADING_DISABLED` bloqueia entradas novas e cancela pendentes, mas nunca
impede uma saída de proteção — a regra 3 da diretiva ("travas de entrada não podem impedir saídas
de proteção") em código, não em prosa.

**Pré-condições:** carteira do §0 com `equity = 19.600,0000000000` (perda de dia de exatamente 2 %,
mesmo cenário de `test_kill_switch.py::test_two_percent_daily_loss_blocks`), **uma posição aberta**
com stop já armado (proteção durável, `portfolio_exit_intents` em `open`) e **uma entrada pendente**
com reserva ativa (`reservation_state='held'`) num mercado diferente.

**Passos:**
1. Avaliar o kill switch: confirmar `effective = TRADING_DISABLED`, `blocks_entries = True`,
   `cancel_pending = True`, `entry_size_multiplier = 0` (já verde em
   `test_kill_switch.py::test_two_percent_daily_loss_blocks`).
2. Tentar submeter uma proposta de entrada nova → esperar recusa pelo check `kill_switch` (§3.1
   check 1), `approved=False`, sem `orders` criada.
3. Confirmar que a pendência existente é cancelada (o worker de execução, ou a rota de admissão,
   transiciona `reservation_state: held → released`, libera vaga e caixa) — **não** apagada; a
   linha de `trade_proposals` continua existindo com o rótulo `status` antigo intacto (vigência
   separada do rótulo, `docs/DATABASE.md` §18.3).
4. Disparar o último negócio do mercado da posição aberta cruzando o preço de stop → o
   `PaperExecutionAdapter.check_triggers` deve gerar um gatilho, e `submit_protection_exit` deve
   executar contra o livro elegível, produzindo um `ExecutionReport` com `kind="exit"`.
5. Confirmar que nenhuma liquidação automática de **outras** posições ocorreu (a diretiva proíbe
   liquidar tudo) e que o estado permanece `TRADING_DISABLED` até um `resume` explícito.

**Números esperados (fechados):**
- `effective = TRADING_DISABLED`; `entry_size_multiplier = 0` (não é "aviso reforçado", é bloqueio
  total de entrada nova).
- A pendência cancelada libera exatamente `reserved_notional` e `reserved_cash` que ela segurava —
  nenhuma fração retida "por segurança".
- A saída de proteção do passo 4 tem `status ∈ {"filled","partially_filled","pending_degraded"}`
  nunca `"rejected"` por causa do kill switch — o motivo de rejeição, se houver, só pode vir de
  livro ausente/degradado, nunca do estado do kill switch (checks de admissibilidade §3.1 não se
  aplicam a `evaluate_exit`).

**O que refuta:** o teste falha se a saída do passo 4 for recusada, atrasada ou exigir qualquer
aprovação do Risk Engine de entrada; se a pendência cancelada continuar contando para exposição,
participação ou risco agregado depois do cancelamento; se o `resume` acontecer sozinho (sem ato
autenticado) quando `daily_loss` cair abaixo de 2 % no mesmo dia.

**Camada:** integração. **Arquivo-alvo:**
`services/execution-worker/tests/integration/test_kill_switch_reaction.py` (o worker reagindo,
T3.5) e `apps/api/tests/integration/test_kill_switch_blocks_entries.py` (a rota recusando).
**Dependência:** T3.4 (`check_triggers`/`submit_protection_exit`, hoje `adapter.py` existe mas
`intents.py`/`triggers.py` — importados só sob `TYPE_CHECKING` em `adapter.py:45-46` — ainda não
existem como arquivos no repositório em 2026-09-06), T3.5 (o worker que reage em < 1 s), T3.6.

---

## V4. Ordens simultâneas e fills duplicados

**Objetivo:** provar que dois preenchimentos concorrentes da mesma intenção nunca vendem/compram a
mesma unidade duas vezes, e que o reenvio do mesmo evento de fill é absorvido sem segundo efeito.

**Pré-condições:** uma posição de **10 unidades** com duas proteções concorrentes disputando a
mesma quantidade vendável: um stop (`protection_key="stop"`) e um alvo parcial
(`protection_key="target:1"`, `intended_qty=6`) — cenário do §10 do contrato reproduzido
literalmente: "um stop de 10 unidades encontra 4 vendáveis".

**Passos:**
1. Disparar o gatilho de stop e o gatilho de alvo **na mesma janela**, cada um tentando vender
   contra o livro sob o mesmo lock de posição.
2. Reentregar (replay) o mesmo evento de fill do stop com o mesmo `execution_key`
   (`entry:{proposal_id}` ou `exit:{attempt_id}`, conforme `adapter.py:131-132`) uma segunda vez.
3. Reentregar o mesmo `fill` via um segundo consumidor concorrente (duas transações abrindo ao
   mesmo tempo, ver §11 desta nota para o padrão de duas sessões).

**Números esperados (fechados):**
- A soma das quantidades vendidas pelas duas proteções nunca excede **10** (a posição inteira) —
  não 10 + 6 = 16 nem qualquer soma que ignore a disputa pela mesma quantidade vendável.
- O reenvio do passo 2 produz **zero** linhas novas em `fills` (`uq_fills_execution_key` recusa o
  `INSERT`, `docs/DATABASE.md` §18.3) e **zero** segunda aplicação de `net_base_delta`/`net_quote_delta`
  no ledger — o caixa e a quantidade depois do replay são **idênticos** aos de antes dele, byte a
  byte (`Decimal` comparado exato, nunca por tolerância).
- O `participation_consumptions` do fill não duplica: `UNIQUE (fill_id) WHERE kind='executed'`
  (`docs/DATABASE.md` §18.5) garante que o orçamento de participação daquele mercado não é debitado
  duas vezes pelo mesmo fill.
- Se o stop consumir a posição inteira (10 de 10) antes do alvo tentar, o alvo termina em
  `state='voided'` (não `'fulfilled'` com um fill fictício) — a bicondicional
  `fulfilled = (filled_qty = intended_qty)` de `docs/DATABASE.md` §18.4 barra qualquer atalho.

**O que refuta:** o teste falha se a soma vendida ultrapassar 10; se o replay do fill criar uma
segunda linha ou mover o caixa uma segunda vez; se duas transações concorrentes conseguirem, cada
uma vendo "4 vendáveis", vender 4 + 4 = 8 de uma posição que só tinha 6 restantes depois da primeira
(a corrida clássica de leitura-e-escrita sem lock); se `voided` nunca aparecer e a intenção
sobrevivente for forçada a `fulfilled` com uma quantidade que não foi de fato vendida.

**Camada:** integração, com duas conexões/transações reais (não `asyncio.gather` sobre a mesma
sessão — isso não testa nada de concorrência real). **Arquivo-alvo:**
`services/execution-worker/tests/integration/test_concurrent_exits.py`.
**Dependência:** T3.1 (FKs compostas, `uq_fills_execution_key`, unicidade de
`portfolio_exit_intents` por `protection_key`), T3.4 (a lógica de disputa da mesma quantidade
vendável — ainda não implementada: `intents.py`/`triggers.py` pendentes), T3.5 (o worker que aplica
fills sob lock).

---

## V5. Reconciliação de saldos, taxas e PnL

**Objetivo:** provar, fill a fill, que `equity = cash + Σ valor_de_mercado(posições)` nunca diverge
por mais que o erro de arredondamento declarado, e que a taxa em ativo-base reduz exatamente a
quantidade vendável — nunca o caixa (Risk Engine e execução usam moedas diferentes para a taxa por
desenho, `.claude/state/notes-T3.0a.md` §6 e `adapter.py:91-105`).

**Pré-condições:** carteira do §0. Compra a mercado de **18,518** unidades a **100** (mesmo
`notional=1.851,800` do V1), taxa **taker real 10 bps** (`SPOT_VIP0`, não os 4 bps de
`AssumedCosts` — distinção de §0), cobrada em ativo-base.

**Passos:**
1. Aplicar o fill: `gross_quote = 1.851,800`; `cash_after = cash_before − gross_quote`;
   `fee_qty = qty × 0,0010`; `net_base_delta = qty − fee_qty` (posição recebida líquida de taxa).
2. Marcar a posição ao mesmo preço de entrada (sem movimento de mercado) e recalcular `equity`.
3. Repetir com o preço subindo para 101 antes da marcação, e confirmar que o PnL não realizado
   aparece **separado** do custo da taxa (a queda de equity do passo 2 é só taxa; o passo 3 soma
   ganho de preço menos a mesma taxa).
4. Property test (Hypothesis): para uma sequência arbitrária de fills de compra/venda parciais
   sobre uma mesma posição, com preços e quantidades geradas dentro dos filtros do mercado,
   `equity_calculada = cash + Σ (qty_i × mark_price)` bate com o `equity` mantido incrementalmente
   pelo ledger a cada fill — a mesma invariante que `test_properties.py` já aplica ao *sizing*
   (`hunter_risk`), estendida aqui ao *ledger* (`hunter_core.portfolio`), que é outro código.

**Números esperados (fechados) — trabalhados nesta nota, não ainda providos por um teste verde
(a T3.9 precisa reproduzi-los, não só confiar nesta conta):**
- `cash_after = 20.000,0000000000 − 1.851,800 = 18.148,2000000000`.
- `fee_qty = 18,518 × 0,0010 = 0,0185180000` (arredondamento `ROUND_CEILING` 8 casas por
  `fee_for()`, `.claude/state/notes-T3.0a.md` §9 item 4 — aqui já exato em 8 casas, sem efeito do
  arredondamento).
- `net_base_delta = 18,518 − 0,018518 = 18,499482` unidades líquidas recebidas.
- Passo 2 (mark = 100): `posição_valor = 18,499482 × 100 = 1.849,9482`;
  `equity_após = 18.148,2000000000 + 1.849,9482 = 19.998,1482000000`; queda de equity =
  **1,8518** = `fee_qty × price` exatamente — a única perda é a taxa, não um erro de arredondamento
  escondido.
- Passo 3 (mark = 101): `posição_valor = 18,499482 × 101 = 1.868,447682`; `equity_após =
  18.148,2000000000 + 1.868,447682 = 20.016,647682`; ganho sobre a equity de abertura = **16,647682**
  = ganho de preço (18,499482 × 1 = 18,499482) menos a taxa em quote-equivalente (1,8518 na
  entrada) → 18,499482 − 1,8518 ≈ 16,647682 (a pequena diferença entre "taxa em quote-equivalente"
  e "taxa multiplicada pelo preço novo" é exatamente o que `FeeCharge.quote_equivalent` existe para
  declarar, `adapter.py:104`, informativo, nunca lançado uma segunda vez).

**O que refuta:** o teste falha se `equity` divergir de `cash + Σ posições` por mais que o épsilon
de arredondamento declarado (nenhuma tolerância "boa o bastante" sem número); se a taxa em
ativo-base for debitada do caixa **e** da quantidade (dupla cobrança); se `fee.quote_equivalent`
influenciar `net_quote_delta` (a nota de `adapter.py:97` é explícita: "booking it as well would
charge the trade twice"); se a property de Hypothesis encontrar uma sequência de fills onde o
ledger incremental diverge do recálculo do zero.

**Camada:** unit (property, sem I/O) para o passo 4; integração (Postgres real, fills persistidos)
para os passos 1–3. **Arquivo-alvo:**
`packages/core/tests/unit/portfolio/test_ledger_reconciliation.py` (property, `hypothesis`) e
`packages/core/tests/integration/test_portfolio_ledger.py` (fill a fill contra o banco).
**Dependência:** T3.3 (o ledger que aplica `ExecutionReport` → cash/quantidade/taxas —
hoje só `attribution.py`/`opening.py` existem; a aplicação de fills ao ledger ainda não foi
localizada no repositório em 2026-09-06), T3.4 (o `ExecutionReport` como está definido em
`adapter.py`, já lido e citado acima).

---

## V6. Dados atrasados, reconexões e reinícios

**Objetivo:** provar que um insumo velho, uma perda de conexão ou um restart do worker nunca
produzem uma aprovação silenciosa — o padrão "falha fechada" do contrato (§7) sobrevivendo à
infraestrutura real, não só ao argumento passado à mão no núcleo puro.

**Pré-condições:** carteira do §0; `max_volume_age_s = 120`, `max_price_age_s`/`max_book_age_s`
(nomes exatos a confirmar contra `hunter_risk.limits.PAPER_V1` — citados como faltantes em
`review-T3.1-security.md` achado 7: "faltam `max_entry_deviation_pct`, `max_price_age_s`,
`max_book_age_s`, `max_volume_age_s`, `max_beta_age_s`" na comparação seed vs. motor — **decisão
pendente:** essa divergência bloqueante precisa estar fechada antes da T3.9 rodar qualquer cenário
de idade de insumo, porque hoje há duas fontes que discordam sobre quais campos existem).

**Passos e números esperados:**
1. **Volume do minuto de 45 min atrás** → `liquidity_24h` e `participation` viram `unavailable`,
   `approved=False`, `sizing=None`. *(já verde em `test_review_findings.py::TestFinding3` no
   núcleo puro — V6 prova que o `MarketLiquidity` que chega ao motor a partir do hot state/Redis
   real carrega o `volume_ts` certo, não que o motor sabe rejeitar quando alguém já filtrou.)*
2. **Book spot sem timestamp de exchange** (`.claude/state/notes-T3.0a.md` §4: `@bookTicker` e
   `@depth20` não trazem `ts`; o carimbo é `received_at`) — forçar `received_at` antigo (> idade
   máxima declarada) e confirmar `spread`/`book_depth`/`slippage_estimate` em `unavailable`, nunca
   um `ts` inventado a partir de outra fonte.
3. **Queda de WebSocket com gap** (o cenário já gravado offline em `.claude/state/notes-T3.0a.md`
   §7: "socket cai, cliente reconecta sozinho, o minuto do meio não aparece e
   `connection_generation()` avança") — confirmar que o minuto ausente vira lacuna
   (`ingestion_gaps`), que `market_gap` (check 5) reprova a proposta enquanto a lacuna não for
   recuperada, e que nenhuma vela sintética preenche o buraco.
4. **Perda do Redis** durante uma operação: o estado durável (Postgres) continua a autoridade
   (§5 do contrato: "o Redis e o evento são projeções"); matar o container Redis no meio de uma
   decisão em andamento não deve impedir a **persistência** da decisão (que não depende de Redis),
   só atrasar a **propagação** (`kill_switch.changed`) — o worker deve recuperar o estado efetivo
   relendo Postgres quando o Redis voltar, sem uma janela em que a proteção para de ser avaliada.
5. **Restart do `execution-worker` com uma saída parcialmente preenchida:** matar o processo entre
   o fill parcial do passo do V4 (stop pega 4 de 10) e a criação da nova tentativa para os 6
   restantes; ao subir de novo, o worker deve reconstruir a intenção `open` com `filled_qty=4`,
   `intended_qty=10`, e emitir uma nova tentativa com identidade própria para os 6 restantes — nunca
   uma posição de 6 unidades "esquecida" sem proteção.

**O que refuta:** qualquer aprovação, fill ou marcação a mercado que use um dado além da idade
declarada; qualquer vela usada como fill retroativo para um gap; qualquer janela, por menor que
seja, em que o `execution-worker` reiniciado trata uma posição parcialmente protegida como
totalmente protegida ou como sem proteção nenhuma (as duas fabricam uma garantia que não existe).

**Camada:** integração (testcontainers Postgres+Redis, com `docker stop`/`docker start` reais no
container de Redis e `kill -9`/reinício real do processo do worker — não um mock que "simula"
reinício sem de fato perder estado em memória).
**Arquivo-alvo:** `services/execution-worker/tests/integration/test_restart_recovery.py`,
`services/market-worker/tests/integration/test_spot_gap_recovery.py` (reaproveitando os casos já
gravados em `.claude/state/notes-T3.0a.md` §7).
**Dependência:** T3.0 (integração do adaptador SPOT ao market-worker — pendência bloqueante
registrada na própria nota T3.0a §1: "o adaptador spot está pronto como componente isolado e NÃO
deve ser ligado ao market-worker antes de T3.0b"), T3.5 (recuperação do worker), T3.6 (referência
diária reconstruível ou estado indisponível).

---

## V7. Mínimos e incrementos de ordem da exchange

**Objetivo:** provar que o piso de notional e o passo de quantidade da exchange são respeitados na
ponta de execução real (não só no sizing do núcleo puro) — arredondamento sempre para baixo, nunca
para cima, e recusa explícita quando o tamanho não alcança o mínimo negociável.

**Pré-condições:** `binance:spot:BTCUSDT` do §0 (`minQty=stepSize=0,00001`, `minNotional=5`),
preço sintético fixo **80.000,00** USDT.

**Passos e números esperados (fechados):**
1. Quantidade na quantidade mínima de `LOT_SIZE` (**0,00001** BTC) a 80.000,00 → notional =
   **0,80** USDT — abaixo do piso de 5 → `MarketOrderVerdict.ok=False`,
   `reason='min_notional'`, **rejeitado, nunca arredondado para cima** para alcançar o piso.
   *(reproduz literalmente `.claude/state/notes-T3.0a.md` §10, com preço sintético fixo em vez do
   preço ao vivo do dia da medição.)*
2. Quantidade que cai exatamente entre dois múltiplos de `stepSize` (ex.: `0,123456` BTC pedido) →
   arredondada para **0,12345** (para baixo), nunca `0,12346`.
3. O sizing do Risk Engine (V1) que produzir `qty_final` já arredondado por `floor_to_step` deve
   chegar ao `PaperExecutionAdapter` e sair com a **mesma** quantidade depois de
   `filters.round_qty_down()` — provar que os dois arredondamentos (Risk Engine e execução) usam o
   mesmo `step_size` e concordam, em vez de cada camada aplicar o seu próprio e por acaso baterem.
4. Referência de preço do filtro `NOTIONAL` para ordem MARKET é `avgPrice` dos últimos
   `avgPriceMins` minutos, **nunca** o último trade (`.claude/state/notes-T3.0a.md` §5) — sem
   `avgPrice` disponível, a checagem recusa com `reason='avg_price_unavailable'`, nunca substitui
   por `last_price`.
5. Resíduo abaixo do mínimo depois de uma venda parcial (ex.: posição de 0,00001 BTC restante após
   um stop parcial, valendo 0,80 USDT a 80.000) → `Residual(qty=0,00001, reason='below_min_qty',
   value_quote=0,80, valuation_source=...)` — contabilizado e **visível**, nunca "quitado" como se
   tivesse sido vendido.

**O que refuta:** qualquer arredondamento para cima (o mutante "arredondar para cima" já reprova 20
testes no núcleo puro, `review-T3.2-risk-core.md` linha 3 — V7 prova que o mesmo mutante reprova na
ponta de execução real); qualquer notional abaixo do piso aprovado; qualquer resíduo silenciosamente
descartado do balanço.

**Camada:** unit (checagem de filtros, `hunter_exchanges/binance_spot/filters.py`, já parcialmente
provada — confirmar) + integração (o `PaperExecutionAdapter` completo contra a fixture
`spot_exchange_info.json`).
**Arquivo-alvo:** `packages/exchange-adapters/tests/unit/test_market_order_filters_btcusdt.py`
(se ainda não existir com este cenário exato) e
`packages/core/tests/integration/test_execution_exchange_minimums.py`.
**Dependência:** T3.0 (pronto como pacote isolado), T3.4 (`SpotFilters`/`MarketOrderVerdict`
protocolos já definidos em `adapter.py:208-244`, implementação concreta em `filters.py`).

---

## V8. Execução pior que o stop planejado em cenário de gap

**Objetivo:** provar que um gap adverso produz um fill **pior** que o stop planejado sem o sistema
fabricar uma proteção perfeita que não existiu — `slippage_vs_plan_bps` publicado, positivo,
**nunca corrigido**.

**Pré-condições:** posição aberta com stop em **97,5** (mesma geometria do §0); o próximo negócio
válido do mercado **salta** de acima do stop para **95,00** sem negociar nos preços intermediários
(gap real de mercado, não um preço interpolado pelo teste).

**Passos:**
1. `check_triggers` detecta o gatilho de stop a partir do negócio em 95,00 (abaixo do stop
   planejado de 97,5).
2. `submit_protection_exit` caminha o livro elegível **depois** da latência declarada, a partir do
   preço real disponível (que pode ser ainda pior que 95,00 se o livro também tiver gapeado).
3. Publicar `planned_price=97,5`, `slippage_vs_plan_quote` e `slippage_vs_plan_bps` **positivos**
   (adversos) — sem nenhum campo "perda dentro do esperado" que reescreva o resultado.

**Números esperados (fechados, ilustrativos com o preço de gap declarado acima — o VWAP real
depende do livro walked no cenário, que o teste deve fixar por fixture, não por preço único):**
- Se o fill inteiro ocorrer a 95,00 (VWAP = 95,00, sem mais deslizamento no livro):
  `slippage_vs_plan_quote = (97,5 − 95,00) × qty`; para `qty = 18,518` (a posição do V1):
  `slippage_vs_plan_quote = 2,5 × 18,518 = 46,295`; `slippage_vs_plan_bps = (2,5 / 97,5) × 10.000 ≈
  256,41` bps — mais de 2,5 % pior que o planejado, e o número é **publicado**, não escondido atrás
  de um "stop executado como esperado".
- Perda real realizada nessa saída: `(entry_price − 95,00) × qty − custos`, que pode exceder o
  orçamento de risco de 0,25 % da equity **sem que isso seja um bug** — é exatamente o que
  `docs/plans/M3.md` declara fora de escopo prometer: "perda realizada limitada ao stop planejado".

**O que refuta:** qualquer código que substitua o preço de fill real por `stop` para "honrar" o
plano; qualquer `slippage_vs_plan_bps` negativo quando o fill foi pior (sinal invertido escondendo
o problema); qualquer teste que **não** force um gap real (ver armadilha "fill retroativo por vela"
em §12) — um mock que sempre preenche exatamente no stop não prova nada sobre este cenário.

**Camada:** unit (o `ExecutionAdapter` contra um livro de fixture com gap deliberado — sem precisar
de Postgres, já que `submit_protection_exit` é função pura de book+trade+filtros+now).
**Arquivo-alvo:** `packages/core/tests/unit/execution/test_adverse_gap.py`.
**Dependência:** T3.4 (`submit_protection_exit`, `check_triggers` — `book_walk.py` existe,
`triggers.py` ainda não).

---

## V9. Ausência de fill fabricado (sem livro utilizável)

**Objetivo:** provar que, sem livro elegível, a saída de proteção **nunca** inventa um fill — fica
`pending_degraded`, com `degraded=True`, `alert=True`, e a intenção durável permanece `open` ou vira
`blocked_residual`, nunca `fulfilled` por um preço de vela ou de última cotação.

**Pré-condições:** posição aberta com stop armado; simular a ausência total de livro válido no
instante do gatilho (book vazio, ou vencido além da idade máxima declarada — reaproveitando o
mecanismo de idade do V6).

**Passos:**
1. Disparar o gatilho de stop com `book=None` (ou vencido).
2. Confirmar que `ExecutionReport.status = "pending_degraded"`, `degraded=True`, `alert=True`,
   `filled_qty=0` — o `model_validator` de `adapter.py:183-201` já recusa a **construção** de um
   relatório que viole isso (`"a degraded exit is marked degraded and raises an alert"`), então o
   teste também deve provar que tentar construir um `ExecutionReport` com `filled_qty>0` e
   `status="pending_degraded"` levanta `ValueError` — a garantia está na **impossibilidade de
   representar** o estado errado, não numa checagem que alguém pode esquecer de chamar.
3. Confirmar que uma vela do minuto que contém o preço do stop (ex.: a vela de 1 min tocou 96,00,
   abaixo do stop de 97,5) **não** é usada como evidência de fill — o `book_walk`/`check_triggers`
   só aceita negócios reais (`NormalizedTrade`) e livro real (`NormalizedOrderBook`), nunca uma
   `NormalizedCandle`.
4. Restaurar o livro (reconectar) e confirmar que uma **nova tentativa**, com identidade própria,
   é gerada para a mesma intenção `open` — sem duplicar consumo do que já foi tentado.

**O que refuta:** qualquer `ExecutionReport` com `filled_qty>0` e `levels=()` (o
`_cannot_fabricate` de `adapter.py:184-189` já é a defesa em código: `sum(level.qty for level in
levels) != filled_qty` levanta `ValueError` — o teste prova que esse validador está de fato no
caminho, não que existe em algum lugar do arquivo); qualquer caminho que leia
`NormalizedCandle.low` como preço de fill; qualquer segunda tentativa que reative a mesma
quantidade já contabilizada como tentada (ver V4 para a disputa de quantidade vendável).

**Camada:** unit (o validador já existe e é testável sem I/O — `adapter.py:183-201`) +
integração (o caminho completo: livro cai → intenção fica `open`/degradada → livro volta → nova
tentativa).
**Arquivo-alvo:** `packages/core/tests/unit/execution/test_no_fabricated_fill.py` (unit,
reproduzindo o `ValueError` do validador com um caso de tabela) e
`services/execution-worker/tests/integration/test_degraded_exit_recovers.py` (integração, o ciclo
completo).
**Dependência:** T3.4 (o `_cannot_fabricate` já existe hoje em `adapter.py`, então a parte unit
desta verificação **pode começar antes das outras**), T3.5 (a parte de recuperação/nova tentativa).

---

## §10. Crash em cada fronteira (requisito adicional da T3.9, além das nove)

**Objetivo:** para cada ponto do pipeline onde um efeito é gravado, matar o processo **entre** dois
efeitos que deveriam ser atômicos e provar que o restart nunca deixa o sistema num estado em que uma
proteção desapareceu, um risco deixou de ser contado, ou um dinheiro foi criado ou destruído.

**Fronteiras identificadas** (cada uma é uma dependência ainda não implementada até 2026-09-06 —
a lista é o roteiro, não uma alegação de cobertura já possível):

| # | Fronteira | Invariante que tem de sobreviver | Depende de |
|---|---|---|---|
| 1 | entre `RiskDecision` persistida e a reserva (`reservation_state → held`) | uma decisão aprovada sem reserva nunca vira ordem (§8 do contrato); ou os dois no mesmo commit, ou nenhum | T3.12 |
| 2 | entre a reserva e a criação da `orders` | a vaga/risco/participação reservados não ficam "presos" para sempre nem liberam sozinhos antes da expiração declarada | T3.5, T3.12 |
| 3 | entre o fill e a aplicação no ledger (cash/qty/taxas) | `fills.execution_key` já gravado, mas cash ainda não movido → no restart, o worker detecta o fill "órfão" e aplica exatamente uma vez, nunca duas nem zero | T3.3, T3.5 |
| 4 | entre a aplicação no ledger e o consumo do orçamento de participação | um fill aplicado ao caixa mas não lançado em `participation_consumptions` não pode permitir uma segunda entrada no mesmo mercado além do teto — o worker tem de fechar os dois na mesma transação, e o teste mata o processo entre eles para provar que não há uma versão do código em que isso é dois `COMMIT`s | T3.5 |
| 5 | entre um fill parcial de saída e a criação da nova tentativa para o restante | o cenário do V4/V6-passo-5: 4 de 10 vendidos, processo morre antes da nova tentativa nascer — a intenção continua `open` com `filled_qty=4`, nunca perde os 6 restantes | T3.4, T3.5 |
| 6 | entre a transição do kill switch em `kill_switch_transitions` e a atualização de `portfolios.kill_switch_state` | a constraint trigger adiada (`portfolios_kill_switch_is_audited`, `docs/DATABASE.md` §18.7) já torna isso atômico **no banco** — o teste de crash aqui é sobre o **caminho de aplicação** (o worker), não sobre a possibilidade de a transação ficar pela metade, que o Postgres já impede | T3.6 |
| 7 | entre o `INSERT` em `market_betas` e a marca `superseded_at` da revisão anterior | `uq_market_betas_current` (`docs/DATABASE.md` §18.6) recusa a revisão nova sem aposentar a anterior na mesma transação — de novo, atômico por construção; o teste de crash prova que o scanner-worker não deixa a revisão nova "pela metade" num retry | T3.7 |
| 8 | entre a expiração de uma reserva e a liberação de caixa/participação | reserva expirada por tempo (`reserved_until`) sob a trava do portfolio; matar o processo que expira no meio não pode deixar a reserva "meio liberada" (caixa livre mas participação ainda contada, ou vice-versa) | T3.5 |

**O que refuta cada uma:** rodar o processo até logo antes da fronteira, matar (`kill -9`, nunca
`SIGTERM` gracioso — o teste é sobre a ausência de graça), religar, e comparar o estado contra o
estado esperado de "a transação nunca aconteceu" ou "a transação aconteceu inteira" — qualquer
estado intermediário observável refuta.

**Camada:** integração, testcontainers, processo real morto e religado (não um mock de crash).
**Arquivo-alvo:** `services/execution-worker/tests/integration/test_crash_boundaries.py`, um teste
parametrizado por fronteira (a matriz da tabela acima), no espírito do teste de isolamento de tenant
parametrizado sobre toda rota de listagem que `apps/api/tests/integration/` já usa em outras
suítes.
**Dependência:** todas as fronteiras exigem que a peça correspondente já exista — a matriz é
utilizável incrementalmente: as fronteiras 6 e 7 já têm a garantia no schema hoje (T3.1/T3.7 em
voo), então o teste de crash nelas pode ser escrito assim que T3.6/T3.7 tiverem processo, mesmo
antes do resto.

---

## §11. Duas sessões concorrentes

**Objetivo:** provar a ordem de travas **sistema → organização → portfolio** (decisão conjunta
Claude ⇄ Astra, `docs/plans/M3.md`) sob concorrência real — duas conexões de banco distintas, cada
uma na sua transação, correndo de propósito para a mesma linha.

**Cenário canônico** (já nomeado no contrato §5, "teste obrigatório em duas sessões reais"): a
sessão A lê `ACTIVE` para o portfolio, começa a montar uma entrada; a sessão B commita
`TRADING_DISABLED` na **organização** (escopo diferente do que A leu) antes de A tentar gravar a
ordem. A releitura do estado efetivo tem de acontecer **na mesma transação** que aplica o efeito de
entrada — então A, ao tentar comitar, tem de ver o `TRADING_DISABLED` da organização e recusar,
mesmo tendo lido `ACTIVE` no portfolio no início.

**Passos:**
1. Abrir duas conexões (`AsyncSession` distintas, não a mesma sessão em duas `Task`s do mesmo
   `asyncio.gather` — isso não exercitaria duas transações reais de Postgres) contra o mesmo
   `pipeline_db_url` (padrão de `tests/integration/conftest.py`).
2. Sessão A: `BEGIN`; ler `kill_switch_state` efetivo (sistema+organização+portfolio, o mais
   restritivo); montar a `RiskDecision` com esse estado; **não commitar ainda**.
3. Sessão B: `BEGIN`; escrever a transição da organização para `TRADING_DISABLED` em
   `kill_switch_transitions` e `organizations.kill_switch_state`; `COMMIT`.
4. Sessão A: tentar persistir a decisão e a reserva; a releitura obrigatória (dentro da mesma
   transação de A, com a ordem de travas sistema → organização → portfolio) tem de enxergar o
   `TRADING_DISABLED` que B já commitou — a decisão de A muda de aprovada para recusada **antes**
   do commit de A, ou o commit de A falha explicitamente por conflito de serialização.
5. Variante com a **mesma** fronteira, mas para orçamento de participação: sessão A reserva 30 do
   teto de 46,000 USDT (V1 passo 3) para BTCUSDT; sessão B, concorrente, tenta reservar outros 30
   no mesmo mercado; a soma de reservas aprovadas nunca pode exceder o disponível na janela móvel
   de 60 s — uma das duas tem de ver o orçamento já consumido pela outra, nunca as duas passarem
   com `30+30=60 > 46`.
6. Variante com FIFO: duas sessões submetendo a mesma solicitação (mesmo `idempotency_key`/conteúdo)
   ao mesmo tempo — exatamente **uma** abertura de vaga (`admission_seq`) e a segunda recupera a
   identidade da primeira, nunca duas.

**Números esperados (fechados):** para a variante de participação (passo 5), com
`max_participation_pct=0,01` e `volume_referencia=4.605,10` (o cenário do V1 passo 3, teto
`46,000`): a soma das duas reservas aprovadas nunca excede **46,000**; se a primeira sessão a
commitar reservar 30,000, a segunda só pode aprovar até **16,000** (46,000 − 30,000), nunca 30,000.

**O que refuta:** qualquer combinação em que as duas sessões terminem com um estado agregado que
excede o teto (participação, caixa, risco agregado, exposição, vagas); qualquer segunda abertura de
vaga FIFO para a mesma solicitação; a ordem de aquisição de travas sendo, na prática, portfolio
antes de organização (o inverso do declarado) — detectável forçando um deadlock artificial entre
duas transações que peguem as travas em ordens opostas e observando que uma delas é sempre
abortada pelo Postgres antes de qualquer corrupção, nunca as duas avançando.

**Camada:** integração, testcontainers, duas `AsyncSession`/conexões reais coordenadas por
`asyncio.Event`/barreira explícita (para garantir a ordem "B commita antes de A tentar comitar",
não confiar em timing implícito — um `sleep` aqui seria a armadilha "relógio de parede" de §12).
**Arquivo-alvo:** `services/execution-worker/tests/integration/test_two_sessions.py` (ou
`packages/core/tests/integration/test_lock_ordering.py`, se a trava viver inteiramente em
repositórios de `packages/core` antes de o worker existir).
**Dependência:** T3.1 (a linha `portfolio_risk_state` como trava, `docs/DATABASE.md` §18.7), T3.12
(admissão com a ordem de travas e a releitura na mesma transação — hoje inexistente).

---

## §12. Armadilhas de teste que fabricam proteção

Uma lista de coisas que fariam um teste desta suíte **passar por engano** — cada uma é um motivo
para revisar o teste, não o código, se aparecer:

1. **`sleep` real para simular passagem de tempo.** Um `await asyncio.sleep(65)` para testar a
   janela móvel de 60 s do orçamento de participação (§4 do contrato) torna a suíte lenta e ainda
   assim não prova nada sobre a virada exata do limite — usar `as_of` explícito e um relógio
   injetado (o motor já não tem relógio próprio; o teste não deveria precisar de um).
2. **Relógio de parede (`datetime.now()`/`datetime.utcnow()`) em qualquer parte do teste ou do
   código sob teste.** Todo `as_of` vem de um argumento explícito — um teste que lê o relógio do
   sistema operacional para montar `as_of` é não determinístico por construção e vai falhar de
   forma intermitente e não reproduzível meses depois.
3. **Fill retroativo por vela.** Usar `NormalizedCandle.low`/`high` como evidência de que um preço
   "passou por ali" e portanto o stop "deveria ter" executado é exatamente o que o contrato proíbe
   (§10, "vela nunca fornece fill retroativo") — um teste que constrói o cenário adverso a partir de
   uma vela em vez de uma sequência de `NormalizedTrade`/`NormalizedOrderBook` reais estaria
   validando o comportamento errado como se fosse o certo.
4. **Mocks que sempre preenchem.** Um `FakeExecutionAdapter`/`ExecutionJournal` de teste cujo
   `submit_protection_exit` sempre devolve `status="filled"` esconde justamente os cenários que
   V8/V9 existem para provar (gap adverso, livro ausente) — qualquer duplo de teste para a
   execução tem de conseguir devolver `pending_degraded` e um VWAP pior que o planejado, ou não é
   um duplo, é uma alegação.
5. **`float` em qualquer parte do cenário — inclusive nos parâmetros do teste.** `Decimal("100.4")`
   e não `100.4`; um teste que passa `100.4` (float) para uma função que aceita `Decimal` só não
   quebra porque o Pydantic converte silenciosamente — e essa conversão silenciosa é exatamente o
   bug que `docs/RISK_ENGINE.md` §8 documenta como pendência aberta em `AssumedCosts`
   (`packages/core/hunter_core/strategies/envelope.py:45`). Um teste desta suíte que introduzisse
   `float` estaria testando o bug, não a correção.
6. **Tolerância numérica sem número.** `assert abs(a - b) < 0.01` sem que `0.01` tenha uma origem
   declarada (arredondamento de qual coluna, de qual `SCALE`) é uma forma de "quase certo" que
   esconde exatamente o tipo de erro que `docs/RISK_ENGINE.md`/`docs/DATABASE.md` gastam páginas
   evitando (`Decimal("0.1") != Decimal(0.1)`) — toda comparação de dinheiro nesta suíte é exata,
   ou a tolerância vem de uma política nomeada e testada à parte (como `OPENING_ROUNDING_POLICY`).
7. **Crash simulado sem perda de estado real.** "Simular" um restart chamando de novo a mesma
   função Python no mesmo processo, com as mesmas variáveis ainda na memória, não prova nada sobre
   recuperação — o worker tem de ser um processo (ou pelo menos um objeto) genuinamente destruído e
   reconstruído a partir só do que está no Postgres/Redis.
8. **Duas tarefas do mesmo `asyncio.gather` sobre a mesma `AsyncSession`.** Isso serializa dentro
   do driver e não exercita nenhuma disputa de trava real de Postgres — §11 exige conexões
   distintas.
9. **Ordem de asserção que esconde o motivo.** Um teste que só verifica `approved=False` sem
   verificar **qual** check reprovou (`state_of(decision, "nome_do_check")`) pode passar mesmo
   quando o check errado reprovou — o padrão desta suíte (herdado de `test_review_findings.py`) é
   sempre nomear o check.
10. **Seed/fixture que já nasce em `WARNING`/`TRADING_DISABLED` "para simplificar".** Todo cenário
    de kill switch nesta nota parte de `ACTIVE` e o *estado é produzido pelo próprio movimento de
    equity/tempo do teste* (MTM real, avaliação real) — nunca escrito direto na coluna, que é a
    exata falha que a auditoria da T3.1 (`review-T3.1-security.md` achado 1) fechou para a coluna
    efetiva e que um teste "de conveniência" reabriria por outra porta.

---

## §13. Decisões pendentes encontradas nesta preparação (consolidado)

1. **Agregação de risco planejado: soma assinada, soma em módulo, ou soma de não-negativos por
   construção?** (§V1). O contrato diz "nunca `max(0, Σ assinado)`" mas não fixa a fórmula
   positiva, e não está claro se `planned_risk_quote` pode ser negativo na prática. Pergunta para
   quem tocar T3.3/T3.5: existe algum caminho em que uma posição tem risco planejado negativo?
2. **Nomes exatos dos campos de idade máxima por insumo no perfil `paper_v1` persistido**
   (§V6). `review-T3.1-security.md` achado 7 registra que `seed_reference.py` e
   `hunter_risk/limits.py` discordam sobre `max_entry_deviation_pct`, `max_price_age_s`,
   `max_book_age_s`, `max_volume_age_s`, `max_beta_age_s` — a T3.9 não pode escrever o teste de
   idade de insumo para preço/book/β enquanto essa divergência (bloqueante da revisão de segurança)
   não estiver fechada, porque não há uma fonte única a testar contra.
3. **Valores exatos de `LOT_SIZE`/`NOTIONAL` do ETHUSDT spot** (§0, §V1 passo 4). Não medidos nesta
   nota; o teste real deve ler `spot_exchange_info.json` (fixture gravada) em vez de um número
   hard-codificado que eu não verifiquei.
4. **VWAP exato do cenário de gap adverso (§V8).** Os números apresentados assumem um fill inteiro
   a 95,00 sem deslizamento adicional no livro — o cenário real depende de uma fixture de livro
   específica que a T3.9 ainda vai desenhar; os números desta nota são o método de cálculo
   (`planned_price`, `slippage_vs_plan_bps`), não uma fixture fechada.
5. **Se a permanência do índice único parcial já foi corrigida para `(organization_id)` em vez de
   `(organization_id, workspace_id)`** (§V11, indiretamente — a segunda carteira principal via
   workspace novo é o bloqueante 2 de `review-T3.1-security.md`). Se ainda não, um teste de
   permanência que assuma a correção falharia contra o schema atual por um motivo diferente do que
   pretende provar — a T3.9 deve verificar o estado desse bloqueante antes de escrever o teste de
   permanência (fora do escopo das nove verificações, mas é pré-requisito de qualquer teste de
   tenant isolation sobre `portfolios`).
6. **Se `resume` (retomada) já está ligado a uma identidade autenticada real do Everton** (não
   qualquer `ADMIN`) — o contrato (§5, decisão conjunta ponto 5) exige isso, mas o mecanismo de
   autenticação (não apenas RBAC de papel) não foi localizado nesta leitura; V3/§11 não podem testar
   "retomada recusada para um ADMIN qualquer" enquanto essa identidade não estiver definida em
   T3.6/T3.8.

---

## §13b. T3.9b (2026-09-06/07) — V4 a V9 e §10 pelo caminho persistido, atualização

Item 2 acima está **fechado**: `hunter_risk.limits.PAPER_V1` hoje carrega `max_price_age_s=10`,
`max_book_age_s=10`, `max_volume_age_s=120` como campos reais e lidos (`checks.py`,
`observations.py`), e `risk_profiles.limits` é gravado a partir do mesmo `RiskLimits.model_dump()`
(nota do §9.3 v2.2 do `docs/RISK_ENGINE.md`) — uma fonte única. V6 pôde ser escrito.

Divergências e limites novos, com o teste que os prova ou o motivo de não existir teste:

1. **V7 item 5 — o rótulo do resíduo é `below_min_notional`, não `below_min_qty`.** A spec supôs que
   um resíduo de 0,00001 BTC (o próprio piso de `LOT_SIZE`) seria barrado pela quantidade. O código
   mede `effective_min_qty` primeiro e 0,00001 **não é menor** que 0,00001 (são iguais) — quem barra
   é o piso de `NOTIONAL` (0,80 USDT < 5 USDT). A quantidade, o preço e "nunca quitado" da spec
   continuam corretos; só o rótulo diverge. Provado por
   `test_v7_exchange_minimums.py::TestAResidualBelowTheFloorIsAccountedAndVisibleNeverQuietlySettled`:
   o comportamento real passa, a alegação literal da spec é `xfail(strict=True)`.
2. **V6 itens 3 e 4 (queda de WS com gap, perda de Redis durante uma decisão) não são
   entregáveis nesta tarefa.** Os dois dependem do coletor SPOT ligado ao hot state do
   `market-worker` (T3.0b) e do `RedisSpotMarketData` real lendo-o; `notes-T3.5.md` §5.3 registra
   essa ligação como inexistente em 2026-09-07, e todo teste desta suíte usa `StaticSpotMarketData`
   (o duplo rotulado), que nunca toca Redis. Não há gap nem queda para simular honestamente sem
   inventar um caminho que não existe — nenhum teste foi escrito para eles (nem `xfail`: não há
   código a chamar). Registrado no docstring de `test_v6_stale_data_reconnect_restart.py`.
3. **V4's "um stop de 10 unidades encontra 4 vendáveis" (RISK_ENGINE.md §10) não é o cenário
   stop-vs-target da própria V4** — reler a citação no contrato mostra que ela descreve **book raso**
   limitando um único stop (exatamente o que `test_restart_recovery.py` do T3.5 já prova, com
   4/10 reais), não uma disputa entre duas proteções. A disputa que V4 pede (stop vs. target) é
   provada à parte, e o achado é: com o stop cobrindo o `intended_qty` inteiro da posição,
   `allocate_sellable` dá zero ao alvo **mesmo que o alvo nunca tenha dado o seu próprio gatilho** —
   não é preciso as duas dispararem na mesma janela para o alvo acabar `voided`; qualquer fechamento
   do stop já o faz. `test_v4_concurrent_orders_and_duplicate_fills.py` prova essa versão, mais forte
   que a literal.
4. **Os números de V8 usados aqui são os de `.claude/state/t35-proof.md` (entrada a 100,01), não os
   da spec (entrada a 100,00).** A tarefa que dispachou esta nota pediu explicitamente os números
   reais da prova de 30 minutos; o método (`slippage_vs_plan_bps` publicado, positivo, nunca
   corrigido) é o mesmo da spec, só a fixture de preço de entrada muda. `SLIPPAGE_BPS =
   256,41025641` bate nos dois casos porque a razão `(stop − preço)/stop` não depende da quantidade.
