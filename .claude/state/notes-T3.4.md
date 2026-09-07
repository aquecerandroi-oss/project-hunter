# Notas T3.4 — `hunter_core.execution` + `PaperExecutionAdapter` (2026-09-06)

Contrato: `docs/RISK_ENGINE.md` v2.1 (§4, §8, §10, §11), `docs/plans/M3.md` (linha T3.4 e
"Decisão conjunta Claude ⇄ Astra", item 3), `docs/DATABASE.md` §18.3–§18.5 (commit `11faba8`),
`.claude/state/directive-risk-engine-2026-09-06.md`, `.claude/state/notes-T3.0a.md` (§4 e §5).
Revisões da Astra nesta tarefa: `astra-review-T3.4-execution.md` (protocolo, **antes** do código),
`astra-review-T3.4-diff.md` (5 MUST-FIX) e `astra-review-T3.4-fixes.md` (2ª rodada, 4 achados).

## 1. A fronteira: o adaptador calcula, o ledger aplica

`ExecutionAdapter` é **puro**. Entram ordem/tentativa, livro, negócio, filtros, taxas e o instante;
sai um `ExecutionReport`. Não há relógio, Redis, Postgres nem saldo dentro dele. Quem aplica os dois
deltas (`net_base_delta`, `net_quote_delta`) é o ledger da T3.3, na mesma transação que move a
intenção e o ledger de participação, sob a trava da carteira (T3.5). O cenário que essa divisão
evita é o de **dois escritores do mesmo saldo** — foi a primeira recomendação da Astra e ela vale
como regra: nada em `hunter_core/execution/**` escreve saldo.

Módulos (todos ≤ 350 linhas, `infra/scripts/check_file_size.py` verde para eles):

| Arquivo | O que decide |
|---|---|
| `adapter.py` (348) | protocolos (`ExecutionAdapter`, `SpotFilters`, `FeeSchedule`, `ExecutionJournal`), `ExecutionReport` e as três invariantes de construção |
| `book_walk.py` (180) | o livro é elegível? (mercado, latência, idade, sequência) e o que ele preenche numa única caminhada |
| `triggers.py` (260) | política de marcação SPOT `spot_last_trade_v1`: o que é um negócio **válido** e o que dispara stop/alvo |
| `entries.py` (134) | a entrada: uma tentativa, identidade derivada da proposta, e a decisão aprovada como argumento obrigatório |
| `intents.py` (325) | a intenção durável de saída, as tentativas, a máquina de estados e a partilha da quantidade vendável |
| `pricing.py` (203) | `ExecutionPolicy` e a aritmética de dinheiro (taxa, ajuste declarado, slippage vs plano, resíduo) |
| `paper.py` (350) | `PaperExecutionAdapter` — o fluxo de uma tentativa |
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
  `trade_not_yet_received`, `trade_id_not_numeric`, `no_new_trade`.

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
