# Notas da T3.14 — ponte shadow → admissão (`ENABLE_PAPER_AUTONOMY`)

**Autor:** backend-specialist, 2026-09-07. **Para:** Sexta-feira, risk-engine-guardian,
code-reviewer, T3.1e, T3.8, T3.9.
**Não commitei.** **Não editei** `.env*`, `infra/migrations/**`,
`services/{market,scanner,strategy}-worker/**`, `apps/**`, `docs/**`. Em `packages/**` editei
**um** arquivo, `hunter_core/settings.py`, exatamente para a flag (§4).
**Astra indisponível até 12/09** (cota do Codex esgotada em 2026-09-07): nenhuma segunda opinião
nesta tarefa — registrado como limite, não como aprovação.

## 1. O que existe agora

Seis módulos novos em `services/execution-worker/hunter_execution_worker/`, divididos por
responsabilidade (nenhum acima de 350 linhas):

| Arquivo | O que decide | Linhas |
|---|---|---|
| `bridge_repo.py` | a **fila durável**: quais decisões do Lab ainda são candidatas | 176 |
| `bridge_universe.py` | o que o mercado e a carteira dizem sobre uma candidata: par SPOT (D1), β vigente, moeda já comprometida, score do Radar na barra fonte | 221 |
| `bridge_screen.py` | a elegibilidade inteira, cada recusa com nome | 201 |
| `bridge_inputs.py` | o retrato do mercado que vira `MarketLiquidity` + marcas + β | 204 |
| `bridge.py` | o ciclo: ordenar pela D3 e submeter **uma** proposta | 321 |
| `bridge_consumer.py` | o consumidor de `shadow.signals.emitted` e o portão da flag | 179 |

Alterados: `cycles.py` (laço `bridge` + `_marks` delegando a `bridge_inputs`), `main.py` (as tarefas
de autonomia e o `status_details["autonomy"]`), `metrics.py` (`hunter_bridge_candidates_total`),
`state.py` (`bridge_at`, `bridge_events`, `bridge_candidates`),
`packages/core/hunter_core/settings.py` (`enable_paper_autonomy: bool = False`).

Testes: `tests/{shadow_builders,test_bridge_eligibility,test_bridge_cycle,test_bridge_consumer}.py`
(16 testes de integração com testcontainers). `tests/builders.py` ganhou duas coisas mínimas:
`filters_metadata` deixou de ser privado e `add_market` recebeu `suffix` (o `assets.symbol` é único
global e a suíte precisa de três moedas no mesmo tenant).

## 2. As decisões que valem revisão

### 2.1 A fila é uma **query**, não memória

`pending_signals` devolve, a cada passada, os sinais das últimas duas janelas de entrada para os
quais **esta carteira** ainda não arquivou proposta (`NOT EXISTS ... trade_proposals.signal_id`).
Com isso o item 4 do brief ("os não escolhidos continuam elegíveis no próximo ciclo") sai de graça,
um restart no meio do ciclo não perde candidato nenhum, e não existe estado em memória para duas
instâncias discordarem. O evento do stream é **despertador**, não candidato.

### 2.2 A flag é decisão de **fiação**, não `if` dentro do laço

Com `ENABLE_PAPER_AUTONOMY=false`, `bridge_tasks()` devolve lista vazia: nenhuma tarefa é criada,
`XGROUP CREATE` nunca é chamado e o grupo `execution-worker.bridge` **não existe** no stream. Isso é
mais forte do que um guard no handler — um grupo que existe acumula pendências e, para quem lê
`XINFO GROUPS`, parece uma autonomia rodando. O teste assere o **stream**, não um booleano.
`/ready` publica `autonomy: off|on` como `status_details` (diagnóstico, nunca veredito: autonomia
desligada é o estado normal e correto deste worker e não pode deixar o `/ready` vermelho).

### 2.2b Dois motores, uma fila — e por que isso é seguro

Uma passada acontece (a) quando um sinal chega no stream (latência: a janela é de 120 s) e (b) na
cadência de admissão, pelo laço `Cycles.bridge` (vivacidade: quem perdeu a vaga é reavaliado sem
depender de outro evento). Eles não compartilham memória — a fila é uma query —, então o pior que
fazem é rodar a mesma passada duas vezes. Cada passada continua submetendo **uma** proposta; o que
impede a segunda passada de comprometer capital que a primeira já comprometeu **não é este módulo**:
é o `admit` pegando a trava da carteira, relendo o estado dentro dela e enxergando a primeira reserva
(decisão conjunta do M3, item 4). Não coloquei um lock de processo entre os dois: o trabalho
duplicado é uma query por segundo e o efeito duplicado é impossível pela chave de idempotência.

### 2.3 Hoje, com a árvore como está, a ponte **não admite nada** — e isso é o desenho

Todo sinal do Shadow Lab carrega `purpose = research_only` (SHADOW-LAB §2/§10), e a primeira recusa
da elegibilidade é exatamente essa, contada em `hunter_bridge_candidates_total{outcome="research_only"}`.
Ou seja: mesmo com a flag ligada, nenhuma proposta nasce enquanto uma `strategy_version` não passar a
emitir com `purpose = live`. Essa é a forma mais forte da garantia "nunca em produção antes do aceite
da T3.9": não depende de alguém lembrar de manter a variável em `false`.

Os testes exercitam o caminho aprovado com sinais `purpose = live` criados pela suíte — rotulados
como fixture, em um venue rotulado (`exchange` = slug do tenant de teste, nunca "binance").

### 2.4 `agent_id` é obrigatório e a ponte **não o inventa**

`admission.sources.ProposalRequest.origin()` recusa uma proposta `source='agent'` sem `agent_id`. A
ponte resolve o agente lendo `agents` da própria carteira por `strategy_version_id` com
`status='enabled'`; sem ele a recusa é `agent_unavailable`. Uma versão sem agente habilitado nesta
carteira é uma versão que **esta carteira não autorizou** — e o brief não previa esse elo, então
está aqui explícito para revisão. Consequência operacional: **ligar a autonomia exige criar a linha
`agents` (org, workspace, portfolio, strategy_version) com `status='enabled'`.**

A query de candidatas também exige um `agents` da versão (sem filtrar `status`), e isso é escopo, não
silêncio: `agent_signals` é global, e sem essa cláusula toda carteira varreria — e logaria recusa
para — os sinais de toda versão, a uma passada por segundo. Agente pausado continua produzindo
`agent_unavailable` contado; agente inexistente simplesmente não é público daquele sinal.

### 2.5 D3 implementada como ordem **total**

`(tem score?, −score, tem custo?, custo, chegada, signal_id)`. Sinal sem score entra depois dos com
score (não é recusado — o classificador está em warm-up, D3). O **custo de entrada em R** é
`(meia-spread observada do livro spot + entry_ref × (slippage_bps + fee_bps)/10⁴) / (entry_ref − stop)`:
o livro responde a parte que ele sabe (o spread agora), e a hipótese declarada do experimento
responde a parte que nenhum livro responde sem um tamanho — e tamanho é do motor, não da ponte.
O desempate final pelo `signal_id` existe para que dois workers ordenando o mesmo ciclo não possam
discordar de quem vai primeiro.

### 2.6 A escolhida **não** é substituída quando falta insumo

Se o retrato de mercado da candidata escolhida não puder ser montado (sem livro, sem último negócio),
o ciclo **defere**: nada é escrito, a vaga não é gasta, e ela volta na passada seguinte enquanto a
janela estiver aberta. Promover a vice significaria que quem recebeu capital foi decidido por uma
leitura transitória do hot state e não pela D3. O custo aceito: uma candidata de topo com livro
permanentemente ilegível segura a vaga até a janela dela fechar (≤ 120 s).

### 2.7 Nada de retrato de mercado inventado

`MarketLiquidity` é montada de fontes declaradas, e cada desconhecido chega ao motor como `None`
(que recusa), nunca como um número plausível:

- preço e livro: hot state SPOT, pelo mesmo `SpotMarketData` do ciclo de entrada;
- participação: `candles` 1m **do mercado spot** — último minuto completo e mediana dos 30;
  janela incompleta ⇒ `volume_window_complete=False` ⇒ referência de participação desconhecida ⇒
  recusa com motivo;
- continuidade: `ingestion_gaps` sem linha aberta ⇒ `ok`, com linha aberta ⇒ `open_gap` (R-OPS-3);
- universo: `markets.is_monitored`, escrito pela T3.0c (R-OPS-4);
- 24 h: `markets.volume_24h_usd`, medido **no spot** pela T3.0c. Nulo ⇒ `spot_volume_unavailable`
  (uma permissão nunca é concedida por uma leitura que falhou — mesma doutrina de
  `spot_universe.tradable_symbols`).

### 2.8 Ponto no tempo, sempre

O score do Radar é lido **na barra fonte**: a amostra mais nova de `opportunity_history` (ou da linha
de `opportunities`) com `ts <= source_bar_close`. O ZSET `radar:scores` **não** é consultado de
propósito: ele guarda o *agora*, e ordenar uma decisão das 12:00 por um score publicado às 12:03 é
look-ahead com passos a mais. O β idem: `available_at <= as_of`, `window_end <= as_of`,
`valid_until > as_of` — as três condições juntas (RISK_ENGINE.md §6).

### 2.9 Idempotência em duas camadas

`client_key = f"shadow:{signal_id}"` ⇒ `idempotency_key = "agent:shadow:{signal_id}"`, único por
organização. Então reentrega do evento, restart no meio do ciclo e dois workers correndo convergem
para **uma** proposta: a segunda tentativa recebe a decisão da primeira em vez de tomar um segundo
lugar na FIFO. O guard de `event_id` do `hunter_core.events.consume` é a primeira camada; o ACK só
acontece depois da transação que tornou o efeito durável.

## 3. Recusas: nomes, e onde elas ficam

Não criei tabela: uma migração está fora do meu escopo, e o motivo de uma recusa é um **fato de um
instante**, não estado durável de que a carteira dependa. Cada recusa sai em log estruturado
(`bridge_candidate_refused`, com `signal_id`, `market_id`, `reason`) e no contador
`hunter_bridge_candidates_total{outcome}`.

`outcome` ∈ `research_only` · `version_inactive` · `source_bar_unavailable` · `entry_window_closed` ·
`geometry_unavailable` · `assumed_costs_unavailable` · `direction_unsupported` · `stop_geometry` ·
`spot_pair_unavailable` · `spot_not_monitored` · `spot_volume_unavailable` ·
`spot_volume_below_floor` · `beta_unavailable` · `duplicate_position` · `agent_unavailable` ·
`spot_market_unknown` · `spot_price_unavailable` · `spot_book_unavailable` (deferimento) ·
`waiting` · `approved` · `rejected`.

## 4. O que toquei em `packages/**`, e por quê

`packages/core/hunter_core/settings.py`: `enable_paper_autonomy: bool = False`. O brief autoriza
exatamente isso. O `hunter_execution_worker/config.py` continua lendo a **mesma** variável
`ENABLE_PAPER_AUTONOMY` com o **mesmo** default (ele não constrói `Settings`, que exigiria
`database_url` etc.); o campo em `Settings` existe para que qualquer papel *veja* em que modo o
deploy está. Os dois composes já traziam `ENABLE_PAPER_AUTONOMY: ${ENABLE_PAPER_AUTONOMY:-false}`
desde a T3.5/T3.13 — não precisei mexer em `infra/**`.

## 5. Pendências e limites honestos

### 5.1 A admissão precisa de **um** campo: `target`

`ProposalRequest` é `extra="forbid"` e não tem campo de alvo, então o alvo do sinal **não viaja**. A
`0009_paper_geometry` (T3.1e, que chegou durante esta tarefa) já reservou a chave `target` em
`trade_proposals.request_payload`, e o docstring de `admission.sources.request_payload` diz
textualmente que ela existe "so T3.8's form and T3.14's bridge can fill it without another
migration" — mas preencher exige o campo em `ProposalRequest`, que é `packages/core` e está fora do
meu escopo. **Pedido à T3.1e/T3.8:** `target: Decimal | None = None` em `ProposalRequest`, incluído
no `request_digest` e no `request_payload`. Até lá o alvo continua recuperável por
`trade_proposals.signal_id → agent_signals.targets[0]` (uma junção), que é o que a ponte grava hoje.

### 5.2 `request_payload` não é escrito no caminho da ponte

`request_payload(request)` só é usado em `dedupe.py`, para comparar uma linha **pendente** arquivada
pela API. `insert_proposal` — o caminho de quem já traz a geometria na mão, que é a ponte — não
escreve a coluna. Não é meu arquivo; registrado para a T3.1e.

### 5.3 O piso de 50 M está duplicado

`SPOT_VOLUME_FLOOR_USDT` existe em `hunter_market_worker.spot_universe` e agora em
`hunter_execution_worker.bridge_universe`, porque o execution-worker não depende do pacote do
market-worker. É um número do Everton em dois lugares — o certo é movê-lo para `packages/core`
(`hunter_core.domain` ou `hunter_risk.limits`) numa tarefa que possa editar `packages/**`.

### 5.4 O que **não** verifiquei

- **Astra**: sem segunda opinião (cota esgotada até 12/09).
- **Prova operacional com dado real**: não rodei os 30 minutos da T3.5 com a ponte ligada. Os testes
  são de integração com Postgres/Redis reais e o `PaperExecutionAdapter` real, mas o livro e a fita
  são doubles rotulados. A prova de ponta a ponta com a autonomia ligada pertence à T3.9.
- **Concorrência entre duas instâncias da ponte**: coberta por construção (chave de idempotência +
  trava da carteira dentro do `admit`), **não** por um teste que rode duas instâncias.
- **`packages/core/tests/integration/test_schema_paper.py:2523` está com `F821 Undefined name
  `_geometry``** — arquivo da T3.1e, que chegou na árvore durante esta tarefa. Não é meu e não toquei.
  `uv run ruff check packages/core` falha por causa dele; `uv run ruff check services/execution-worker
  packages/core/hunter_core` passa.
- **Outra tarefa estava editando `services/execution-worker/**` ao mesmo tempo que eu.** Entre a
  minha penúltima e a minha última rodada do `check_file_size.py`, `positions.py` foi de 341 para
  **352 linhas** (estoura o orçamento de 350), `protection.py` de 291 para 332 e `entry.py` de 299
  para 320 — nenhum dos três foi tocado por mim (só importei `load_open_positions`). A
  `0009_paper_geometry` e a reescrita de `hunter_core/admission/sources.py` (com `request_payload`)
  também chegaram durante a tarefa. **Consequência:** `uv run python infra/scripts/check_file_size.py`
  hoje acusa `positions.py 352 > 350`, e isso **não é meu**; quem estiver na T3.1e/T3.9 precisa
  dividi-lo. Minha última passada limpa do gate (`0 over budget`) foi imediatamente após eu dividir
  `bridge_repo.py`.
- **pyright**: 165 erros em `services/execution-worker/tests/*` são **pré-existentes** (arquivos da
  T3.5: `test_mtm_and_kill_switch` 46, `test_protection_cycle` 38, `test_order_cycle` 35,
  `test_restart_recovery` 27, `test_concurrency` 14, `scenarios` 5). Meus seis módulos de produção e
  meus quatro arquivos de teste somam **0**.

## 6. Assinaturas para quem vem depois

```python
# hunter_execution_worker.bridge
await run_bridge_cycle(session, *, wallet, data, now, exit_cost_rate, adapter=None) -> BridgeOutcome
entry_cost_r(screened, snapshot) -> Decimal | None

# hunter_execution_worker.bridge_consumer
bridge_tasks(config, *, redis, factory, data, health, consumer) -> list[tuple[str, Coroutine]]
await handle_signal_event(factory, *, data, config, health, now, payload=None) -> int
await run_bridge_consumer(redis, factory, *, data, config, health, consumer, clock=utcnow)
autonomy_status(config) -> "on" | "off"

# hunter_execution_worker.bridge_repo / bridge_universe
await pending_signals(session, *, wallet, now, limit=50) -> tuple[ShadowSignal, ...]
await spot_pair_for(session, signal) -> SpotPair | None
await current_beta(session, *, market_id, now) -> BetaEstimate | None
await beta_map(session, *, market_ids, now) -> dict[uuid.UUID, BetaEstimate]
await coin_commitment(session, *, wallet, base_asset_id) -> CoinCommitment | None
await radar_score(session, *, market_id, at) -> Decimal | None

# hunter_execution_worker.bridge_screen
await screen_signal(session, *, wallet, signal, now) -> Screened
```

**Para a T3.9:** ligar a autonomia numa verificação exige, além de `ENABLE_PAPER_AUTONOMY=true`,
(a) uma `strategy_version` ativa emitindo com `purpose != research_only`, (b) uma linha `agents`
habilitada dessa versão na carteira, (c) β vigente no mercado **spot**, (d) `markets.volume_24h_usd`
medido no spot ≥ 50 M e `is_monitored`, (e) candles 1m spot completas dos últimos 30 minutos. Falta
qualquer uma e a recusa aparece nomeada no contador — que é exatamente o que a verificação deve ler.

## 7. Comandos e saída real

```
uv run pytest services/execution-worker/tests/test_bridge_eligibility.py -q  → 8 passed in 44.08s
uv run pytest services/execution-worker/tests/test_bridge_cycle.py -q        → 5 passed in 59.20s
uv run pytest services/execution-worker/tests/test_bridge_consumer.py -q     → 3 passed in 37.12s
uv run pytest services/execution-worker/tests/test_supervision.py -q         → 9 passed in 3.76s
uv run pytest services/execution-worker/tests/test_order_cycle.py -q         → 2 passed in 58.36s
uv run pytest services/execution-worker/tests/test_protection_cycle.py -q    → 2 passed in 87.24s
uv run pytest services/execution-worker/tests/test_mtm_and_kill_switch.py -q → 2 passed in 68.94s
uv run pytest services/execution-worker/tests/test_concurrency.py -q         → 2 passed in 45.69s
uv run pytest services/execution-worker/tests/test_restart_recovery.py -q    → 2 passed in 42.76s
uv run ruff check services/execution-worker packages/core/hunter_core        → All checks passed!
uv run ruff format --check services/execution-worker packages/core           → 233 files already formatted
uv run pyright services/execution-worker/hunter_execution_worker
                                    packages/core/hunter_core/settings.py    → 0 errors
uv run python infra/scripts/check_file_size.py  → scanned 459 files; 0 over budget, 0 grandfathered
                                                  (logo após dividir bridge_repo.py; na última
                                                   rodada acusa `positions.py 352 > 350`, arquivo
                                                   de outra tarefa — §5.4)
```

`uv run ruff check services/execution-worker packages/core` acusa **1 erro**, em
`packages/core/tests/integration/test_schema_paper.py` (T3.1e) — §5.4.
