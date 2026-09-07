# Notas T3.9a — V1, V2, V3 e §11 pelo caminho persistido

**Data:** 2026-09-07. **Autor:** test-engineer. **Escopo:** as quatro verificações da
`.claude/state/spec-T3.9-verificacoes.md` que já têm código embaixo, provadas de ponta a ponta
(abertura real → MTM real → kill switch durável → admissão real → linhas no banco).
**Astra:** indisponível até 12/09 — nenhuma segunda opinião foi obtida; as três divergências abaixo
estão registradas para revisão humana. **Não commitado.**

Entregue em `tests/integration/paper/`: `conftest.py` (fixture base §0), `test_v1_sizing.py`,
`test_v2_warning_halves.py`, `test_v3_blocked_keeps_protections.py`,
`test_s11_concurrent_sessions.py`. Banco próprio (`hunter_paper_t39a`) no contêiner da sessão, com
`0006` corrigida e **`0007_paper_roles` aplicada**: toda fixture de estado de risco, curva,
execução e admissão escreve como `hunter_worker`; nada escreve como `hunter_app` a não ser o
bloqueio da organização (§11), que é ato da API.

---

## 1. Divergência — V1 passo 4: o teto de caixa não pode vencer neste ledger

**Número da spec:** `available_cash = 99,599904` (500 − 400 × 1,00100024) com
`binding_constraint = "cash"`.
**Medido:** `available_cash = 99,599904` — **bate exatamente**, lido de
`trade_proposals.risk_decision` e de `PortfolioState.available_cash`. O `binding_constraint`
medido é **`total_exposure`**, não `cash`.

**Por que não é ajuste de número, é impossibilidade aritmética.** No ledger real
`equity = caixa + posições` (a reserva não move caixa). Escrevendo `C` = caixa, `X` = posições,
`N` = notional reservado, `R = N × 1,00100024`:

- teto de caixa = `(C − R) / 1,00100024`
- teto de exposição total = `0,40 × (C + X) − (X + N)`, com piso em 0

Para o caixa vencer seria preciso `C/1,001 < 0,40·C − 0,60·X`, ou seja `0,999·C < 0,40·C`, falso
para qualquer `C > 0`. Com alavancagem 1 e teto total de 40 % (paper_v1), **`cash` nunca é o menor
teto num estado alcançável pelo ledger**. O cenário puro de `test_review_findings.py` só existe
porque `portfolio(cash=500)` mantém `equity=20.000` sem posições que expliquem a diferença — um
estado que o `PortfolioState` aceita e o ledger não produz.

**O que ficou no suite:** `test_v1_step4_the_cash_ceiling_wins_with_500_of_cash_and_400_reserved`,
`xfail(strict=True)`. Ele **passa** nas asserções de `cash == 500` e `available_cash == 99,599904`
e falha exatamente em `binding_constraint == "cash"` (medido `total_exposure`) — verificado com
`--runxfail`. A regra de finding 4 (caixa líquido de reservas) está provada no caminho persistido
por `test_the_wallet_cash_is_untouched_and_the_curve_still_shows_the_opening` e por
`test_the_second_admission_decides_against_the_first_committed_reservation` (§11).

**Pergunta para quem tocar T3.2/T3.5:** o teto de caixa é hoje inalcançável em SPOT. Ou é um teto
que só existirá com margem (M4+), ou o teto de exposição total deveria ser medido sobre caixa livre
e não sobre patrimônio. Não mexi em nenhum dos dois.

## 2. Divergência — V2: 925,900 e "equity 19.800" não podem valer juntos

**Números da spec:** pré-condição `equity = 19.800` (perda de dia de exatamente 1 %) **e**
`notional_after_multiplier = 925,900`, `qty_final = 9,259`.
**Medido com a equity de 19.800:** `notional_before_multiplier = 1.833,333333…`,
`qty = 9,166`, **`notional = 916,600`**, `planned_risk_quote = 24,7482`.

925,900 é metade de 1.851,851851…, que é o orçamento de risco de uma carteira de **20.000**
(0,25 % = 50 / 0,027). Com a equity em 19.800 o orçamento é 49,50 e o teto cai para 1.833,33. A
spec herdou o número do teste puro `TestKillSwitchMultiplier`, que injeta `WARNING` numa carteira
intacta; a pré-condição de perda real muda a equity e portanto o teto.

**O que ficou no suite, sem ajustar número:**
- `test_the_halved_size_at_an_equity_of_19_800_is_916_600` — **passa**, fixa o número medido;
- `test_v2_the_spec_number_925_900_at_an_equity_of_19_800` — `xfail(strict=True)`, falha em
  `Decimal('916.60000000') == Decimal('925.900')`;
- `test_the_latched_warning_halves_the_final_size_to_925_900` — **passa**, e prova o 925,900 da
  spec pelo caminho que o preserva: perda real de 1 % (AVISO travado) **seguida de recuperação a
  20.000 no mesmo dia**. Aí a avaliação automática diz `ACTIVE`, o latch durável continua `WARNING`
  e o multiplicador 0,5 só pode ter vindo da linha — que é a garantia do V2 (R-KS-1 + "duas fontes
  não discordam"), com `notional_before = 1.851,851851…` e `notional = 925,900`.

## 3. Divergência — §11 passo 5: 30 + 16,051 não é alcançável numa carteira

**Número da spec:** com o teto de 46,0510 e uma primeira reserva de 30, a segunda sessão pode
aprovar **até 16,0510** (medido 16,000 depois do passo de lote).
**Medido:** a segunda admissão no mesmo mercado é **recusada** por `duplicate_position` (D3: nunca
duas posições/reservas na mesma moeda). O invariante que a spec queria ("a soma nunca passa de
46,0510") vale — mas por outra regra, e a subtração de participação entre duas propostas da mesma
carteira nunca chega a ser exercitada.

Confirma a observação 12 da revisão T3.1b/T3.6/T3.12: o orçamento de participação é chaveado por
**carteira**, então a disputa real por esse teto é entre carteiras/arenas, não dentro de uma. Hoje
só existe uma carteira principal, então o teto de participação é, na prática, um teto por proposta.

**O que ficou no suite:** `test_two_concurrent_entries_never_reserve_more_than_the_minute_allows`
(passa, prova o invariante e nomeia o mecanismo real) e
`test_s11_step5_the_second_session_takes_the_remaining_16_051` (`xfail(strict=True)`, falha em
`approved is True`).

---

## 4. Números da spec × números medidos (todos lidos do banco)

| Número da spec | Medido | Onde |
|---|---|---|
| `notional = 1.851,800`, `qty = 18,518`, `binding = risk_per_trade` | idêntico | `test_v1_sizing.py::test_the_row_carries_1851_800_...` |
| `planned_risk_quote = 49,9986` = 0,24999 % da equity | `49,9986`; `planned_risk_pct = 0,00249993` | idem |
| `stop_distance_pct = 0,025`, `cost_pct = 0,0020` | idênticos | idem |
| reserva: `reserved_cash = notional × 1,00100024` | `1.853,652244432` (= 1.851,800 × 1,00100024) | idem |
| decisão persistida == motor puro nos mesmos insumos | `Sizing` igual campo a campo | `test_the_persisted_decision_equals_the_pure_engine_...` |
| minuto mediano 4.605,10 → teto 46,0510, `notional = 46,000` | idênticos | `test_the_median_minute_makes_participation_win_at_46_000` |
| contrafactuais divergem (`sem participação` = 1.851,800) | `46,000` vs `1.851,800` | `test_the_two_counterfactuals_are_persisted_and_differ` |
| `entry_ref` 100 contra mercado 110 → recusado | recusado por `signal_validity`, desvio `0,090909` > `0,005` | `test_a_reference_of_100_against_a_market_at_110_...` |
| caixa 500 com 400 reservados → `99,599904` | `99,599904` (teto vencedor: `total_exposure`, §1) | `test_v1_step4_...` (xfail) |
| AVISO: multiplicador `0,5`, `925,900`, `qty 9,259` | idênticos (rota "perda real de 1 % → recuperação"; §2) | `test_the_latched_warning_halves_the_final_size_to_925_900` |
| AVISO com equity 19.800 → 925,900 | **916,600** (§2) | `test_the_halved_size_at_an_equity_of_19_800_is_916_600` |
| AVISO morde qualquer teto vencedor (participação) | `binding` continua `market_participation`, `46,000 → 23,000` | `test_the_multiplier_bites_the_participation_ceiling_too` |
| −2,5 % no dia → BLOQUEADO com PnL realizado zero | `daily_loss_pct = 0,025`, `realized_pnl_cum = 0`, latch `TRADING_DISABLED` | `test_a_two_and_a_half_percent_day_blocks_...` |
| BLOQUEADO: `entry_size_multiplier = 0`, entrada recusada sem reserva | idênticos; recusa nomeada `kill_switch`, `cancel_pending = true` | `test_a_new_entry_is_refused_by_the_kill_switch_...` |
| cancelamento devolve exatamente `reserved_notional`/`reserved_cash` | exposição volta a 500 (posição) e caixa livre a 19.000; `participation_consumptions` recebe `released = 1.851,800`; linha continua `status='approved'` | `test_cancelling_the_pending_entry_gives_back_exactly_what_it_held` |
| `evaluate_exit` continua aprovado sob BLOQUEADO | `approved=True`, `approved_qty = 10`, sem check `kill_switch` na decisão de saída | `test_the_protective_exit_is_still_approved_...` |
| duas admissões simultâneas → uma reserva, a segunda revalida | 1 proposta, 1 `held`, `admission_seq = 1`, `replayed = {False, True}`, 1 consumo de participação | `test_the_same_request_from_two_sessions_...` |
| soma de reservas ≤ 46,0510 no minuto | `30,000` (segunda recusada, §3) | `test_two_concurrent_entries_never_reserve_more_...` |
| §11 passo 5: segunda sessão aprova 16,000 | recusada por `duplicate_position` (§3) | `test_s11_step5_...` (xfail) |

Números **novos**, medidos aqui pela primeira vez (a spec não os fixava):

| Situação | Medido |
|---|---|
| AVISO sobre o teto de participação (46,0510 × 0,5, piso 0,001) | `23,000` |
| ETHUSDT com o passo de lote gravado (0,0001) no mesmo cenário do SOL | `1.851,850` (contra `1.851,800` do SOL, passo 0,001) |
| orçamento agregado visto pela segunda admissão | `200 − 49,9986 = 150,0014` (SOL primeiro) |

## 5. Armadilhas do §12 viradas em asserção negativa

| Armadilha | Onde é negada |
|---|---|
| 1/2 `sleep` e relógio de parede | não há `sleep` nem `datetime.now` em nenhum arquivo; todo instante vem de `at(minutes=…, seconds=…)` sobre `NOW`. A única espera é o `lock_timeout` do próprio Postgres em §11 |
| 5 `float` em qualquer ponto | `test_no_float_survives_anywhere_in_the_persisted_decision` varre o JSON inteiro de `risk_decision`; `ProposalRequest` recusa float na entrada; colunas de dinheiro conferidas como `Decimal` |
| 6 tolerância sem número | nenhuma comparação usa `abs(a-b) < ε`; toda comparação de dinheiro é `Decimal` exata |
| 8 duas tarefas na mesma sessão | §11 abre uma `AsyncSession` por lado, cada uma com sua conexão; a ordem é forçada por lock ou por `asyncio.Event` |
| 9 asserção que esconde o motivo | toda recusa nomeia o check (`check_of(...)`, `rejection_reasons`) |
| 10 fixture que nasce em AVISO/BLOQUEADO | nenhum teste escreve `kill_switch_state`; os três estados são produzidos por MTM real + `evaluate_and_persist`, com transição auditada verificada em `kill_switch_transitions` |
| "fill fabricado" | nenhum fill é criado por vela ou por preço de conveniência; o único fill escrito à mão é uma compra explícita (`buy_filled`), rotulada, escrita como `hunter_worker`, e nenhuma saída é simulada |

## 6. Como cada arquivo foi visto falhando (mutação, revertida em seguida)

| Arquivo | Mutação aplicada | Resultado |
|---|---|---|
| `test_v1_sizing.py` | `sizing.py`: `qty = after / price` (sem `floor_to_step`) | `1 failed` (`1851.851851… != 1851.800`) |
| `test_v2_warning_halves.py` | `kill_switch.py`: `entry_size_multiplier(WARNING) → 1` | `4 failed, 1 error` |
| `test_v3_blocked_keeps_protections.py` | `evaluate.py`: `evaluate_exit(approved=not blocks_entries(...))` | `1 failed` ("a protective exit is never refused by the kill switch") |
| `test_s11_concurrent_sessions.py` | `scopes.py`: `if lock:` → `if False:` | `1 failed` (`DID NOT RAISE DBAPIError` — o bloqueio da organização passou por cima da admissão) |

As quatro mutações foram revertidas byte a byte; `git status` dos quatro arquivos ficou limpo e
`grep -rn "MUTANT T3.9a"` não devolve nada.

## 7. Dívidas que este trabalho deixa (não são divergências)

1. **V1 passo 1 pela rota HTTP (T3.8) não foi exercitado**: a admissão aqui é chamada como o
   execution-worker a chamará (`admit` numa transação `hunter_worker`), porque no modelo da 0007 a
   API só registra o pedido. Quando a T3.5/T3.8 existirem, o mesmo cenário deve ser repetido pela
   rota manual — o número não muda, o caminho sim.
2. **`request_digest` e o dedupe de pedido pendente** não são exercitados (defeito conhecido,
   must-fix 1 da revisão): §11 usa `source='agent'` com decisão direta, como o brief pede.
3. **Cancelamento de pendentes é chamado explicitamente** (`close_reservation(target=released)`):
   quem *dispara* esse cancelamento ao entrar em BLOQUEADO é a T3.5, que não existe. O teste prova o
   efeito (devolve tudo, não apaga a linha) e a ordem (`cancel_pending=true` na decisão persistida),
   não o gatilho automático.
4. **`portfolio_exit_intents`** não foi usado: a proteção durável do V3 é o `stop_price` da posição.
   Quando a T3.5 criar intenções, o V3 deve passar a assertar `state='open'` na intenção também.
5. **`evaluate_exit` é chamado direto** (função pura sobre estado lido do banco); não há ainda
   `submit_protection_exit` persistido para provar o fill da saída — é V8/V9, fora deste escopo.
