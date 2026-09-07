# Notas T3.4 — `hunter_core.execution` + `PaperExecutionAdapter` (2026-09-06)

Contrato: `docs/RISK_ENGINE.md` v2.1 (§4, §8, §10, §11), `docs/plans/M3.md` (linha T3.4 e
"Decisão conjunta Claude ⇄ Astra", item 3), `docs/DATABASE.md` §18.3–§18.5 (commit `11faba8`),
`.claude/state/directive-risk-engine-2026-09-06.md`, `.claude/state/notes-T3.0a.md` (§4 e §5).
Revisões da Astra nesta tarefa: `astra-review-T3.4-execution.md` (protocolo, **antes** do código),
`astra-review-T3.4-diff.md` (5 MUST-FIX) e `astra-review-T3.4-fixes.md` (2ª rodada, 4 achados).

## 1. A fronteira: o adaptador calcula, o ledger aplica

`ExecutionAdapter` é **puro**. Entram ordem/tentativa, livro, negócio, filtros, taxas e o instante;
sai um `ExecutionReport`. Não há relógio, Redis, Postgres nem saldo dentro dele. Quem aplica os dois
deltas (`net_base_delta`, `net_quote_delta`) é a **T3.5**, na mesma transação que move a intenção e
o ledger de participação, sob a trava da carteira; a T3.3 construiu o estado da carteira que esse
relatório vai alimentar, e **nada aplica relatório hoje** (item 4 da revisão de 2026-09-07). O cenário que essa divisão
evita é o de **dois escritores do mesmo saldo** — foi a primeira recomendação da Astra e ela vale
como regra: nada em `hunter_core/execution/**` escreve saldo.

Módulos (todos ≤ 350 linhas, `infra/scripts/check_file_size.py` verde para eles):

| Arquivo | O que decide |
|---|---|
| `adapter.py` (349) | protocolos (`ExecutionAdapter`, `SpotFilters`, `FeeSchedule`, `ExecutionJournal`), `ExecutionReport` e as três invariantes de construção |
| `book_walk.py` (196) | o livro é elegível? (mercado, lado, níveis positivos, latência, idade, sequência) e o que ele preenche numa única caminhada |
| `tape.py` (169) | a leitura de um lote de prints: `spot_last_trade_v1` (idade, recepção, sequência), `usable_trade` e o **defeito mais antigo** que o lote carrega (T3.4b) |
| `triggers.py` (309) | o que um cruzamento significa: stop/alvo, os três vereditos e as duas assimetrias (proteção primeiro; alvo espera pela cronologia) |
| `entries.py` (137) | a entrada: uma tentativa, identidade derivada da proposta, e a decisão aprovada como argumento obrigatório |
| `intents.py` (349) | a intenção durável de saída, as tentativas, a máquina de estados e a partilha da quantidade vendável |
| `idempotency.py` (155) | uma tentativa, uma execução: `guard_replay`, `decision_fingerprint`, `applied_attempts_from_execution_keys` e o jornal em memória (T3.4b) |
| `pricing.py` (293) | `ExecutionPolicy` e a aritmética de dinheiro (taxa, ajuste declarado, slippage vs plano, resíduo) |
| `paper.py` (343) | `PaperExecutionAdapter` — o fluxo de uma tentativa |
| `shadow.py` (118) | registra, nunca preenche |
| `live.py` (61) | levanta `LiveTradingDisabled`, sempre |

**Dois módulos além da lista do brief** (`pricing.py` e `entries.py`) existem por causa do
orçamento de 350 linhas, não por gosto: `paper.py` chegou a 481 linhas com a aritmética dentro, e
`intents.py` a 372 quando ainda carregava a ordem de entrada. O corte é o da própria §10 do
contrato — entrada (uma tentativa) e saída (intenção durável) são coisas diferentes.

## 2. Política de marcação SPOT versionada — `spot_last_trade_v1`

Gatilho pelo **último negócio SPOT válido**, nunca `mark_price` (conceito de perpétuo,
`docs/PIPELINE.md:205`). "Válido" está escrito e testado, e a política viaja em todo relatório
(`marking_policy_version`):

- **idade** `0 <= now − trade.ts <= max_trade_age_s`, medida no relógio da exchange, que o
  `aggTrade` de fato carrega (o livro spot **não** carrega: `ts == received_at`, T3.0a §4);
- **recepção** `trade.received_at <= now` — um print carimbado pela exchange que o nosso socket
  ainda não viu não decide stop nenhum (achado da 2ª rodada da Astra);
- **sequência** ids numéricos estritamente crescentes; regressão é replay e é descartada; uma
  repetição **não** renova frescor, mas o último aceito continua utilizável até vencer;
- **`unavailable` é o terceiro veredito**, distinto de `not_triggered`: fita que não vimos não prova
  que o stop não foi tocado. `tape_gap`, `no_trade`, `stale_trade`, `trade_from_the_future`,
  `trade_not_yet_received`, `trade_id_not_numeric`, `no_new_trade` e, desde a T3.4b,
  `already_reported` (o último utilizável cruza uma proteção mas está ≤ watermark — publicar
  `not_triggered` ali imprimia um preço **abaixo do stop** sob um veredito que se lê como "o stop
  não foi tocado");
- **um print ilegível não apaga os outros** (T3.4b): o lote é lido print a print, o cruzamento sai
  do que se pôde ler e o resto viaja em `undecided_reason` — no veredito `triggered` quando algo
  cruzou, como o próprio `unavailable` quando nada cruzou.

**10 s é um orçamento declarado, não medido.** A Astra recusou defender outro número sem histograma
de intervalo entre negócios e de atraso de recepção; a escolha honesta foi publicar o orçamento junto
com o veredito (`MarkingPolicy` viaja no relatório) em vez de escondê-lo. Medir isso é trabalho da
T3.M/T3.9.

**Cronologia, não preferência.** Um lote com 110 (alvo) e depois 94 (stop) reporta o **alvo**: foi o
que aconteceu primeiro. E a marca-d'água (`accepted_trade_id`) avança só até o negócio que cruzou, de
modo que a chamada seguinte reporta o **stop** das unidades restantes — sem isso o mesmo alvo era
reportado para sempre e o stop do restante nunca aparecia (achado 2 da 1ª revisão de diff).

`usable_trade()` é a **única** definição de negócio utilizável e é usada também fora do gatilho: com
`avgPriceMins == 0` o filtro `NOTIONAL` é julgado contra "o último preço", e um preço que não
recebemos não é um último preço.

## 3. Entrada: uma tentativa, e nenhuma sem decisão aprovada

`MarketEntryOrder` **carrega o objeto `RiskDecision`**, não um booleano. Com o booleano (primeira
versão) um chamador montava a ordem de uma proposta recusada, passava `True` e obtinha fill — a
Astra reproduziu. Agora não há o que virar: `RiskDecision` recusa `approved=True` com qualquer check
não passado, e o validador da ordem exige `approved`, `kind == "entry"`, `sizing` presente e
`qty <= sizing.qty` (teto, nunca sugestão).

- `client_order_id = entry:{proposal_id}` e `execution_key = entry:{proposal_id}` — derivados. É isso
  que faz a reentrega de `proposals.decided` bater em `uq_orders_client_order_id` em vez de abrir uma
  segunda posição (provado contra Postgres real).
- Fill parcial e **cancelamento terminal** do restante (`remaining_cancelled=True`), sem
  parcelamento automático.

## 4. Saída de proteção: a tentativa acaba, a intenção não

- a tentativa nunca cancela o restante (`remaining_cancelled` é recusado pelo validador para
  `kind="exit"`); a intenção permanece `open` com a quantidade remanescente;
- cada tentativa tem identidade própria: `exit:{attempt_id}`, um fill agregado por tentativa (com o
  custo por nível em `levels`). Chave por nível deixaria uma reentrega parcial órfã; chave por
  intenção engoliria a segunda tentativa legítima;
- `ExitIntent` espelha os CHECKs de `portfolio_exit_intents`, inclusive a bicondicional
  terminal ⟺ `closed_at`, e **intenção terminal recusa nova tentativa** no construtor de
  `ExitAttempt`, em `apply_attempt` e no próprio adaptador (achados 3 da 1ª e 3 da 2ª rodada);
- `allocate_sellable` reparte a quantidade da posição entre stop, alvo e fechamento manual em ordem
  de prioridade, e a soma nunca passa da posição. **A trava é da T3.5**: esta função serializa uma
  chamada, não duas sessões — está declarado aqui porque a Astra insistiu, com razão, que fórmula não
  substitui lock.

## 5. Sem fill fabricado — a invariante que o construtor impõe

`ExecutionReport` recusa, na construção: `filled_qty` diferente da soma dos níveis consumidos;
qualquer fill em status `rejected`/`pending_degraded`/`recorded`; `pending_degraded` sem
`degraded`+`alert`; entrada preenchida com restante não cancelado; saída com restante cancelado.

Sem livro utilizável a saída fica `pending_degraded`, com alerta, e a intenção guarda a quantidade —
**mesmo com o último negócio abaixo do stop**. Vela não entra em lugar nenhum: não existe parâmetro
de candle em nenhuma assinatura.

**Indisponibilidade não é resíduo** (achado 4): só `min_qty`/`min_notional` produzem `Residual`;
`avg_price_unavailable` (e qualquer outro motivo de filtro) degrada com alerta. Depois do fill, o
mesmo: `untradable_reason()` só chama de resíduo o que falha por **mínimo** — nove unidades sob um
teto de cinco são vendáveis em duas tentativas, não pó.

O resíduo é visível: `residual.qty`, `residual.value_quote` (nulo **com motivo** quando não há preço
válido), `valuation_price`, `valuation_source`, `reason`.

## 6. Taxa em ativo-base, e a quantidade vendável que encolhe

Compra spot paga a taxa **em BTC**: `net_base_delta = filled_qty − fee_base`, `net_quote_delta =
−gross_quote`. O `quote_equivalent` da taxa é **informativo** — lançá-lo também no quote cobraria
0,1 % duas vezes. Venda paga em USDT: `net_quote_delta = gross − fee_quote`, `net_base_delta =
−filled_qty`. Arredondamento da taxa é `ROUND_CEILING` (um custo arredondado "para o mais próximo" às
vezes fica mais barato que a realidade, e alimenta resultado simulado).

Propriedade testada com hypothesis: **a taxa é o único vazamento** — `gross_quote` é exatamente o que
os níveis cobraram e `net_base_delta = filled − fee`, para qualquer livro aleatório. É a identidade
sobre a qual `equity = caixa + Σ posições` do ledger se apoia.

## 7. Pior que o stop planejado — publicado, nunca corrigido

`slippage_vs_plan_quote` e `slippage_vs_plan_bps`, **positivo = adverso**. Caso do teste: stop
planejado 95, melhor bid 90, 5 unidades → fill a 90, `slippage_vs_plan_quote = 25,00`,
`bps = 526,31578947`. Nenhum caminho puxa o preço de volta ao stop.

## 8. Proveniência que o relatório publica (para a T3.5 e a T3.9)

`book_sequence`, `book_received_at`, `decision_at`, `eligible_at`, `executed_at`, `latency_ms`,
`marking_policy_version`, `book_policy_version`, `execution_policy_version`, `vwap`,
`vwap_before_adjustment`, `model_adjustment_bps`, `filter_reference_price`/`_source`,
`trigger_trade_id`/`trigger_trade_price`/`triggered_at`/`trigger_received_at`/`trigger_evaluated_at`
(a observação que **disparou**) e `observed_trade_id` (o negócio visto **na tentativa**) — a Astra
mostrou que confundir os dois atribui o disparo ao print errado quando a tentativa é repetida.

O que **não** está no relatório e a T3.5 tem de tirar das entidades travadas: `market_id`,
`organization_id`, `portfolio_id` (vêm da decisão, da posição e da intenção, que a T3.5 já lê sob
trava) e a marca-d'água do gatilho (`TriggerEvaluation.accepted_trade_id`, que é do ciclo do mercado,
não da tentativa). Declarado, não esquecido.

## 9. `ShadowExecutionAdapter` e `LiveExecutionAdapter`

- **Shadow** devolve `status="recorded"`, `filled_qty=0`, deltas zero, e guarda `submissions`. A
  diferença é **estrutural**, não uma convenção do chamador: não existe relatório dele que um ledger
  possa transformar em dinheiro. Gatilhos continuam sendo avaliados (observação não é efeito).
- **Live** recusa duas vezes: na construção enquanto `ENABLE_LIVE_TRADING=false`, e em **todos** os
  métodos mesmo com a flag ligada, porque não há implementação. Um teste lê o grafo de imports do
  módulo por AST e prova que ele só importa `collections`, `decimal`, `typing` e `hunter_core` — sem
  cliente HTTP, sem credencial, sem nome de venue.

## 10. Pendências e ressalvas honestas

1. **A trava é da T3.5.** `allocate_sellable` e a idempotência por `execution_key` não substituem
   `SELECT ... FOR UPDATE`: duas sessões que leiam o mesmo saldo antigo ainda podem alocar a mesma
   unidade. A ordem sistema → organização → portfolio e a releitura na mesma transação do efeito são
   dela.
2. **`ExecutionJournal` é um protocolo, e o único implementador aqui é em memória.** Em produção o
   jornal é `fills.execution_key`; o teste de integração mostra o caminho (INSERT idempotente), mas
   quem o implementa de verdade é a T3.5.
3. **Identidade de mercado só é comparada quando o chamador a fornece.** Entrada: sempre (vem da
   decisão). Saída: só quando `ExitIntent.market` está preenchido — a T3.5 deve preenchê-lo a partir
   de `portfolio_exit_intents.market_id`, senão a comparação não roda.
4. **10 s (negócio) e 10 s (livro) e 150 ms (latência) são valores declarados**, não medidos.
4b. **`PERCENT_PRICE_BY_SIDE` — decisão da T3.4b: aplicado, e assimétrico por escrito.** A revisão
   (item 15) pediu "aplicar ou declarar por quê com fonte". Aplicado, como
   `pricing.price_band_breach`, e a fonte é a mesma da T3.0a §5: na Binance esse filtro limita
   **preço de ordem limitada** e a exchange nunca recusa MARKET por causa dele — a banda aqui é
   **nossa**, guarda de sanidade do fill simulado que andou o livro. Três escolhas registradas:
   (a) a referência é o **`avgPrice` da exchange**, o preço que o próprio filtro nomeia, nunca o
   último negócio — que se move junto com o livro suspeito; (b) **entrada recusa**
   (`reason="price_band"`): entrada sempre pode ser recusada e falhar fechado é o padrão do
   contrato; (c) **saída de proteção nunca recusa** — publica `alert=True` e
   `reason="price_band_breached"` e preenche. O motivo de (c) é um cenário real: uma queda de 20 %
   em cinco minutos põe o fill abaixo de `ask_multiplier_down` exatamente quando o stop mais
   importa, e "travas não podem impedir saídas de proteção" (diretiva, regra 3). Um símbolo sem
   multiplicadores devolve `(avg, avg)`, que não é banda, e não recusa nada.
4c. **Dívida de coluna para a T3.1b/T3.10: `portfolio_exit_intents.applied_attempts`.**
   `apply_attempt` passou a ser idempotente por `attempt_id` (`ExitIntent.applied_attempts`), mas a
   tabela **não tem coluna** para essa lista — o espelho não existe. Enquanto não existir, a
   autoridade durável são **duas** fontes, não uma: `fills.execution_key` **e**
   `orders.client_order_id` — a mesma string `exit:{attempt_id}`. As duas porque uma tentativa que
   não achou livro é aplicada na intenção (marca a degradação) e **não escreve fill nenhum**: só
   `orders`. Derivar só dos fills perdia essa tentativa e, depois de um restart, a reentrega dela
   caía numa intenção já substituída e **levantava `ValueError`** — reentrega inofensiva virando
   worker derrubado (Astra, revisão T3.4b, MUST-FIX 2; teste
   `test_an_attempt_that_filled_nothing_is_recovered_from_its_order_not_its_fill`). Quem reconstrói
   a intenção depois de um restart chama
   `hunter_core.execution.idempotency.applied_attempts_from_execution_keys` sobre a **união** das
   duas — provado contra Postgres real em
   `test_a_redelivered_exit_report_never_fills_the_intention_twice`. Sem essa chamada, a intenção
   volta do banco com `applied_attempts = ()` e a reentrega volta a somar o fill. **Pedido à
   T3.1b/T3.10:** coluna `applied_attempts uuid[]` (ou tabela filha) em `portfolio_exit_intents`,
   escrita na mesma transação do efeito — inclusive para tentativas de fill zero.
4d. **Duas ressalvas abertas na banda de preço (Astra, T3.4b, NICE-TO-HAVE), sem correção nesta
   rodada.** (i) O relatório publica `filter_reference_price`, que é a referência do filtro
   `NOTIONAL` (último negócio válido, senão a média) — **não** a referência que a banda usou (a
   média). Numa recusa por banda com compra a 125, média 100 e teto 120, o relatório diz 125: a
   recusa está certa e a explicação, incompleta. Publicar média/limites/VWAP recusado exige campo
   novo no `ExecutionReport` e `adapter.py` está a 349/350 linhas — fica para a T3.5/T3.9, que já
   precisam mexer no relatório. (ii) `price_band_breach` devolve `False` tanto para "dentro da
   banda" quanto para "sem média, banda indisponível"; hoje isso só afeta a explicação, porque o
   caminho sem média já é recusado antes pelo `NOTIONAL` quando ele se aplica.
5. **`hunter_core` não importa `hunter_exchanges`** (a dependência corre no sentido inverso), então
   os filtros e a tabela de taxas entram por `Protocol` estrutural. A conformidade da
   `SpotMarketFilters`/`SPOT_VIP0` reais é provada em
   `packages/core/tests/unit/execution/test_spot_filters_compat.py`, que importa o pacote irmão
   **só no teste** (com `importorskip`).
6. **Fora do orçamento de 350 linhas, pré-existentes e não meus:**
   `packages/core/hunter_core/db/models/execution.py` (359, T3.1) e
   `packages/exchange-adapters/hunter_exchanges/binance/streams.py` (353, M1).
7. **Uma execução flaky observada:** numa rodada com vários agentes usando Docker ao mesmo tempo, o
   arquivo de integração abortou com `ConnectionResetError [WinError 64]` no container; reexecutado
   isolado, 6/6 verdes duas vezes.

## 11. Comandos e saída real (última rodada)

```
uv run pytest packages/core/tests/unit/execution -q     → 97 passed in 8.58s
uv run pytest packages/core/tests/unit -q               → 578 passed in 53.82s
uv run pytest packages/core/tests/integration/test_execution_intents.py -q → 6 passed in 64.27s
uv run ruff check <meus arquivos>                       → All checks passed!
uv run ruff format --check <meus arquivos>              → 21 files already formatted
uv run pyright <meus arquivos>                          → 0 errors, 0 warnings
uv run python infra/scripts/check_file_size.py          → 2 over budget, ambos pré-existentes
```

`uv run ruff check packages/core` e `ruff format --check packages/core` acusam 5 erros e 4 arquivos
em `hunter_core/risk/**`, `tests/unit/test_risk_daily.py` e `tests/integration/test_risk_kill_switch.py`
— arquivos **da T3.6, em voo**, que não toquei.

---

## 12. T3.4b — o que a revisão adversarial de 2026-09-07 fechou (itens de execução)

| Item | O que estava errado | O que passou a valer | Teste |
|---|---|---|---|
| Bloqueante 1 | `check_triggers` validava o lote **inteiro** antes de procurar cruzamento: `[100@90, 101 quebrado]` devolvia `unavailable` e descartava o 90; no ciclo seguinte o 90 estava `stale` e a posição ficava sem proteção | cada print é julgado sozinho (`_read_batch`); o cruzamento é avaliado sobre o que se pôde ler e o resto vira `undecided_reason` no veredito `triggered`, ou o `unavailable` quando nada cruzou | `test_one_broken_print_never_erases_a_stop_the_batch_already_showed` (3 variantes: `received_at` futuro, id não numérico, `ts` futuro) e `test_a_broken_print_still_makes_the_rest_of_the_batch_unavailable` |
| Bloqueante 2 | `apply_attempt` somava o mesmo relatório de novo (0,4 → 0,8) e fechava a intenção de 0,8 como `fulfilled` com 0,4 ainda na posição | `ExitIntent.applied_attempts` + reaplicação é **no-op**, inclusive quando a primeira aplicação já fechou a intenção; sem coluna no banco, o conjunto é derivado de `fills.execution_key` (§10.4c) | `test_replaying_one_attempt_report_never_counts_its_fill_twice`, `test_a_redelivery_after_the_intention_closed_is_a_no_op_not_an_exception`, `test_an_intention_rebuilt_from_postgres_is_made_idempotent_by_the_journal` e o de integração contra Postgres |
| Deve corrigir 4 | o docstring de `adapter.py` dizia que a **T3.3** aplica o relatório; ninguém aplica ainda | diz **T3.5**, e diz que nada aplica hoje | `test_the_boundary_docstring_names_the_task_that_really_applies_a_report` |
| Deve corrigir 8 | `not_triggered` publicado com preço **abaixo do stop** quando o negócio já estava ≤ watermark | `unavailable` com `reason="already_reported"` | `test_a_crossing_below_the_stop_already_reported_is_never_called_not_triggered` |
| Deve corrigir 9 | replay por `entry:{proposal_id}` devolvia o relatório antigo mesmo com `qty` ou decisão diferente | `ReplayMismatch` alto, publicando `recorded_qty`/`requested_qty` e a identidade das duas decisões (`decision_fingerprint`, hash canônico — `RiskDecision` não tem id próprio) | `test_a_replay_of_the_same_key_with_another_quantity_fails_loudly`, `test_a_replay_of_the_same_key_behind_another_decision_fails_loudly`, `test_a_replayed_attempt_with_another_quantity_fails_loudly` |
| Sugestão 10 | `mark_price` reimplementava a validade (sem `received_at <= now`) e precificava resíduo com print não recebido | usa `usable_trade`, a definição única | `packages/core/tests/unit/execution/test_pricing.py` (4 casos) |
| Sugestão 11 | `BookLevel.price` sem `gt=0`; nível a 0 explodia como `ValidationError` dentro do walk | `gt=0` no modelo **e** `eligible_book` recusa com `non_positive_level` (os parsers de stream usam `model_construct`, onde validador nenhum roda) | `test_a_price_of_zero_is_not_a_book_level_at_all`, `test_a_non_positive_level_is_refused_as_a_verdict_not_as_an_exception` |
| Sugestão 15 | `PERCENT_PRICE_BY_SIDE` parseado e nunca usado | aplicado como guarda de sanidade, assimétrico (§10.4b) | `test_a_fill_outside_the_percent_price_band_never_opens_a_position`, `test_a_symbol_without_published_multipliers_has_no_band_to_breach`, `test_a_protection_fills_outside_the_band_and_says_so_instead_of_refusing` |

**Fora do meu escopo nesta rodada** (itens 3, 5, 6, 7, 12, 13, 14, 16 da revisão): `portfolio/**`,
`db/repositories/**` e os testes de `opening` são da T3.3b/T3.6/T3.12.

**Dois campos novos no `ExecutionReport`** — `submitted_qty` (o que o chamador pediu, **antes** dos
filtros; `requested_qty` é pós-filtro e um arredondamento de passo leria como outra ordem) e
`decision_fingerprint`. **A T3.5 precisa gravá-los**: `guard_replay` falha fechado quando a
identidade não está lá (`submitted_qty is None` **não** é "igual"), porque um relatório reconstruído
sem esses campos casava com qualquer coisa e devolvia o fill de 3 para uma ordem de 2 — a chave
única de `fills` impede o segundo INSERT, mas não impede a **resposta errada** ao chamador (Astra,
revisão T3.4b, MUST-FIX 3).

### 12.1 Segunda rodada — o que a revisão da Astra sobre este diff (`astra-review-T3.4b-execution-fixes.md`) fechou

| Achado | Cenário reproduzido | Correção | Teste |
|---|---|---|---|
| MUST-FIX 1 (ALTA) | watermark 99; print `100@90` (stop) com `received_at = now+2s` e print `101@110` (alvo). A 1ª versão publicava o **alvo** e movia o watermark para 101; dois segundos depois o 90 virava regressão e **o stop nunca era reportado** | cronologia antes do alvo: um print indecidido **antes** de um cruzamento de alvo devolve `unavailable` e não move o watermark; um **stop** continua sendo publicado na hora (proteção primeiro), com `undecided_reason`. E um defeito mais velho que o orçamento de idade não bloqueia nada — ele nunca poderia decidir | `test_an_unread_print_before_a_target_never_lets_the_target_be_reported_first`, `test_a_stop_is_published_even_with_an_unread_print_before_it`, `test_a_broken_print_older_than_the_budget_blocks_nothing` |
| MUST-FIX 2 (ALTA) | tentativa degradada (fill zero) → aplicada → intenção substituída → restart → reentrega: como não há fill, o `attempt_id` sumia do conjunto derivado e `apply_attempt` levantava `ValueError` numa intenção terminal | a autoridade durável é `fills.execution_key` **∪** `orders.client_order_id` (§10.4c); o parser aceita as duas, e a integração deriva da união | `test_an_attempt_that_filled_nothing_is_recovered_from_its_order_not_its_fill` + `test_a_redelivered_exit_report_never_fills_the_intention_twice` |
| MUST-FIX 3 (MÉDIA) | relatório reconstruído sem `submitted_qty`/`decision_fingerprint`: replay divergente (3 gravado, 2 pedido, outra decisão) recebia o fill antigo **sem exceção** | identidade ausente falha fechado; a decisão é comparada quando o chamador nomeia uma (saída não nomeia) | `test_a_recorded_report_without_its_identity_is_never_taken_for_the_same_order` |
| NICE-TO-HAVE (banda) | recusa por banda publica a referência do `NOTIONAL`, não a média que a banda usou | **não corrigido** — registrado em §10.4d com o motivo (orçamento de linhas do `adapter.py`) e endereçado à T3.5/T3.9 | — |

### 12.2 Terceira rodada — os dois furos que a Astra achou **na minha própria correção**

| Achado | Cenário reproduzido | Correção | Teste |
|---|---|---|---|
| Round 2, MUST-FIX 1 (ALTA) | watermark 99; lote `[100 não recebido, 101@110 (alvo), 102@90 (stop)]`. Bloquear o alvo devolvia `unavailable` **na hora** e nunca olhava adiante: onze segundos depois o lote inteiro estava stale e o stop a 90 nunca fora reportado | quando o alvo não pode ser publicado, procura-se um **cruzamento de stop posterior**; se existir, ele é publicado (proteção primeiro), com `undecided_reason`; só sem stop nenhum o veredito é `unavailable` | `test_a_target_we_cannot_publish_never_hides_a_stop_that_printed_after_it` |
| Round 2, MUST-FIX 2 (ALTA) | prints fora de ordem `[103 do futuro, 100@90 não recebido, 101@110 (alvo)]`: guardava só o **primeiro** defeito visto (103, que fica depois do alvo), publicava o alvo e movia o watermark para 101 — o 90 virava regressão no ciclo seguinte e o stop sumia | `tape.earlier_defect` guarda o defeito **mais antigo** da fita (id menor vence; sem id numérico conta como o mais antigo de todos, porque não dá para posicioná-lo) | `test_the_earliest_unreadable_print_decides_whether_a_target_may_be_published` |

Essa rodada também partiu `triggers.py` em dois: `tape.py` (o que conseguimos **ler**) e `triggers.py`
(o que um cruzamento **significa**) — 348 linhas não cabiam mais no orçamento, e o corte é o mesmo
que a revisão sugeriu ao separar "print processado" de "gatilho publicado".

### 12.3 Rodadas 3 e 4 — mais três caminhos de stop perdido

| Achado | Cenário reproduzido | Correção | Teste |
|---|---|---|---|
| Round 3, MUST-FIX 1 (ALTA) | `tape_gap=True` devolvia `unavailable` **antes de olhar o lote**: com stop 95 e um print válido a 90 no mesmo lote, o stop nunca era publicado e, quando o gap fechava, o print já estava stale | o gap desconfia do **silêncio** e segura o **alvo**, mas não desvê um print que atravessou o stop: procura-se um cruzamento de stop entre os utilizáveis e publica-se com `undecided_reason="tape_gap"` | `test_a_known_gap_still_publishes_a_stop_we_can_actually_see`, `test_a_known_gap_still_holds_back_a_target_and_the_silence` |
| Round 4, MUST-FIX (ALTA) | lote `[100@110 (alvo), 101@90 (stop)]`, ambos carimbados 12:00:00 e **recebidos só às 12:00:09**; watermark 99. Às 12:00:10 publica o alvo e para o watermark em 100; às 12:00:11 o print do stop já está stale — o toque a 90 foi **observado e nunca acionado** | `TriggerEvaluation` publica `pending_stop_trade_id`/`pending_stop_price`/`pending_stop_ts`: o cruzamento de **stop** visto atrás do cruzamento publicado viaja junto do veredito, e a T3.5 abre as duas proteções na mesma transação em vez de depender de uma segunda chamada dentro do orçamento de idade. Só o stop viaja assim — proteção primeiro | `test_a_stop_seen_behind_a_target_is_published_as_pending_not_forgotten`, `test_a_verdict_without_a_second_crossing_carries_no_pending_stop` |
| Round 3, MUST-FIX 2 (ALTA) | `"--101"` passa em `raw.lstrip("-").isdigit()` e estoura `int()`: a leitura do lote inteiro morria com `ValueError` **subindo para o worker**, e o stop a 90 do mesmo lote nunca era reportado. Também travava alvos novos, porque a conversão acontecia antes do descarte por idade | `tape.numeric_id` converte em `try/except`: id ilegível é **veredito** (defeito, que expira pela idade), nunca traceback | `test_a_trade_id_that_is_not_a_number_at_all_is_a_defect_not_a_crash`, `test_a_malformed_id_already_past_the_budget_never_blocks_a_new_target` |

A Astra também **concordou** que a entrada recusada pela banda não cria posição desprotegida
(`paper.py`: zero fill, deltas zero), que a banda nunca bloqueia proteção, e que centralizar a
validade em `usable_trade` e recusar níveis não validados são as correções certas.

**`pending_stop` não autoriza vender duas vezes.** Ele é **informação**, não alocação: quem reparte a
quantidade entre stop, alvo e fechamento manual continua sendo `allocate_sellable` sob a trava da
T3.5, e a soma nunca passa da posição (contrato §10). Abrir as duas intenções é legítimo; vender as
mesmas unidades duas vezes continua impossível pela mesma regra de sempre.

**Limite honesto desta rodada:** a quinta rodada de confirmação com a Astra não rodou — a cota do
Codex acabou (`ERROR: You've hit your usage limit ... try again at Sep 12th`). As quatro rodadas
anteriores estão em `.claude/state/astra-review-T3.4b-*.md`, e todo MUST-FIX delas está fechado com
teste que falhava antes.
