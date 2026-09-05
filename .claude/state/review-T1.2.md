# Kit de revisão — T1.2 · `hunter_exchanges` (Binance USDS-M público: REST + WS)

**Owner:** `exchange-integration-specialist` (Claude, sonnet) · **Estado:** em voo em 2026-09-05
**Files (do plano):** `packages/exchange-adapters/**`
**Depends-on:** T1.1 (commitado em `415cc83`)
**Commit esperado:** `feat(exchanges): Binance USDS-M public REST + WS adapter with rate limit and fixtures`

> Regra do supervisor: este kit só roda **depois** que a entrega da tarefa chegar ao orquestrador e o diff estiver na árvore. Não commitar nada de outra tarefa junto.

---

## (a) Checklist da decisão conjunta Claude ⇄ Astra que se aplica a T1.2
Copiada literalmente de `.claude/state/dialogue-M1.md` → `## Astra (rodada 4)`.

- [ ] T1.2 — Validar payloads dos seis canais nas rotas acordadas: `/public/stream` para `@depth20` e `@bookTicker`; `/market/stream` para `@aggTrade`, `@kline_1m`, `@markPrice@1s` e `@forceOrder`. Usar `@depth20` sem sufixo e contar streams por conexão: 200 símbolos correspondem a 400 public e 800 market, dentro do limite acordado de 1024; ACK sozinho não comprova recebimento de dados.
- [ ] T1.2 — Tratar cada book como substituição integral do snapshot top 20, sem livro local nem acumulação de deltas; testar remoção dos níveis ausentes no segundo snapshot, preservar `kind="book"` e `is_snapshot` internos, reconciliar profundidade REST e projetar `book.kind="snapshot"`, `book.depth=20` na API.
- [ ] T1.2 — Preservar `ts` da fonte e `received_at` desde a normalização, incluindo timestamp da atualização WS para ordenar parciais de candle; demonstrar que atualizações atrasadas ou duplicadas não rejuvenescem dados em conexões sobrepostas.

Itens da segunda opinião da Astra sobre o plano (`docs/plans/M1.md` → "Segunda opinião (Astra)") que valem como aceite aqui:

- [ ] Limite é por **streams** (1024 por conexão), não por símbolos — o código conta streams, não símbolos.
- [ ] Rotação de conexão antes das 24 h com jitter e sobreposição curta.
- [ ] Orçamento REST centralizado por IP consumindo os headers de peso; parar retries em `429` **antes** de chegar ao `418`.

## (b) Critérios da linha da tarefa em `docs/plans/M1.md`
Entregáveis exigidos pela linha T1.2:
- [ ] `base.py`: `ExchangeAdapter` Protocol conforme `docs/ARCHITECTURE.md` §6, `ExchangeError`, `RateLimited`. (Já parcialmente commitado em `f71059e`; o diff atual modifica `base.py` — verificar que não quebrou o contrato já commitado.)
- [ ] `rate_limit.py`: token bucket em Redis `rl:binance:{bucket}`, pesos oficiais, 2400/min; `429/418` → backoff + evento.
- [ ] `binance/rest.py`: `exchangeInfo`, `klines`, `ticker/24hr`, `depth`, `premiumIndex`, `fundingRate`, `openInterest`.
- [ ] `binance/ws.py`: combined streams `aggTrade`, `bookTicker`, `depth20` (rota `/public/stream`), `kline_1m`, `markPrice@1s`, `forceOrder`; ≤ 200 símbolos por conexão; ping/pong; reconexão antes de 24 h; backoff 1 s → 60 s com jitter; resubscribe.
- [ ] `binance/normalize.py`: nenhum campo cru sai de `hunter_exchanges` — tudo vira `Normalized*` de `hunter_core.domain.market`.
- [ ] `testing/fixtures/*.json` gravadas da API pública **real** + `testing/fake_adapter.py` usado pelo worker (T1.3).
- [ ] Testes cobrem: parse de cada fixture, símbolo delistado, candle duplicado, mensagem malformada, reconexão com resubscribe.
- [ ] Teste marcado `live` (opcional, fora do CI) que busca 1 ticker real.

## (c) Regras do `CLAUDE.md` que mais pegam aqui
- [ ] `Decimal` para todo preço/quantidade/notional; nunca `float` no caminho de normalização.
- [ ] UTC em todo timestamp; `ts` da exchange preservado, `received_at` separado.
- [ ] Nenhum arquivo acima de 350 linhas (`uv run python infra/scripts/check_file_size.py`).
- [ ] `structlog`, nunca `print`.
- [ ] Sem dado falso: fixture é payload real gravado, não JSON inventado à mão. Erro de exchange vira `ExchangeError`/`UNAVAILABLE`, nunca número plausível.
- [ ] Sem segredos: adapter é 100 % público, não lê API key nem `.env`.
- [ ] `async` em todo caminho de IO; pytest markers `unit` / `live` corretos (`live` nunca no CI).

## (d) Comandos de verificação exatos
```bash
export PATH="/c/Program Files/nodejs:/c/Users/evert/AppData/Roaming/npm:/c/Users/evert/AppData/Local/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe:/c/Users/evert/.local/bin:$PATH"
cd /c/dev/project-hunter
uv run pytest packages/exchange-adapters -q -m "not live"
uv run pyright packages/exchange-adapters
uv run ruff check packages/exchange-adapters
uv run ruff format --check packages/exchange-adapters
uv run python infra/scripts/check_file_size.py
git diff --stat -- packages/exchange-adapters
```
Prova de canal (o item "ACK sozinho não comprova recebimento"): o teste `live` (ou uma execução manual de ≤ 60 s) tem de mostrar **payload de dado** recebido em cada uma das duas rotas, não só a resposta de subscribe.

## (e) Revisores a despachar (em paralelo)
| Revisor | Escopo |
|---|---|
| `code-reviewer` | conformidade com a linha T1.2 do plano, bugs, tratamento de erro, testes faltando, orçamento de linhas/lint |
| `exchange-integration-specialist` | **não** (é o autor) — a revisão cruzada dele é sobre T1.3 |
| `security-reviewer` | não obrigatório em T1.2 (sem auth, sem chave); dispensado salvo se o diff introduzir leitura de credencial |
| `database-architect` | não se aplica |
| `risk-engine-guardian` | não se aplica no M1 |

## (f) Segunda opinião da Astra (obrigatória, depois do `code-reviewer`)
```bash
bash infra/scripts/astra.sh ask review-T1.2 "Review packages/exchange-adapters/** against docs/plans/M1.md (linha T1.2) e a checklist T1.2 da DECISÃO CONJUNTA em .claude/state/dialogue-M1.md. Confira: rotas /public/stream vs /market/stream por canal; contagem de streams por conexão (limite 1024); @depth20 tratado como substituição integral do snapshot top 20 (níveis ausentes removidos); ts da fonte e received_at preservados na normalização, sem rejuvenescer dado em conexão sobreposta; Decimal e UTC; rate limit por peso com parada de retry em 429 antes do 418; rotação de conexão antes de 24h com jitter. Must-fix com cenário de falha, nice-to-have, concordâncias. Não modifique arquivos."
```
Registrar o resultado: concordâncias absorvidas em silêncio; discordâncias escritas em `docs/reports/M1.md` sob "Segunda opinião (Astra)" com a decisão e o motivo. Achado sem cenário de falha é descartado, venha de quem vier.

## (g) Commit esperado
```
feat(exchanges): Binance USDS-M public REST + WS adapter with rate limit and fixtures

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```
`git -c commit.gpgsign=false commit` · só os arquivos de `packages/exchange-adapters/**` · `git push origin main`.

---

## Pendências vindas da T1.3 (revisão de 2026-09-05)

Levantadas na revisão da T1.3 por `exchange-integration-specialist` (revisão cruzada), `code-reviewer` e pela segunda opinião adversarial da Astra (`.claude/state/astra-review-review-T1.3.md`). O worker já está escrito contra estes contratos e **degrada honestamente** sem eles (warning + `system_events`, nunca dado falso), mas o M1 não fecha até que existam. Cada item traz o cenário de falha concreto.

| # | O que T1.2 precisa entregar | Severidade | Cenário de falha se faltar |
|---|---|---|---|
| 1 | `async def update_subscriptions(added, removed, channels)` em `BinanceWsClient`/`BinanceAdapter` | CRITICAL | `streaming.py:50` levanta `RuntimeError` quando o método não existe. Com `MARKET_UNIVERSE_SIZE=200` ranqueado por volume, a composição muda no primeiro refresh (`market_universe_refresh_s`, 900 s). O `RuntimeError` sobe por `forever("ingest")` até o `TaskGroup`, que cancela **todas** as tarefas e derruba o processo. Com `restart: unless-stopped` (T1.6) o container reinicia e bate na mesma parede a cada ~15 min, indefinidamente. Forma natural: recalcular o conjunto monitorado, reagrupar em grupos de ≤200 símbolos por rota e reconectar **apenas** a(s) conexão(ões) cujo grupo mudou, preservando as assinaturas dos mercados mantidos. |
| 2 | `parse_kline_ws` deve preencher `NormalizedCandle.event_ts` a partir do `E` (event time) do frame | CRITICAL | O campo `event_ts` já existe no domínio, mas o parser nunca o preenche, então chega `None`. O worker (que também tinha um bug próprio, corrigido nesta rodada) não consegue ordenar parciais da mesma abertura e as rejeita todas — `mkt:{ex}:{sym}:candles:1m` nunca recebe candle parcial em produção, só finais. As duas correções são necessárias: só o worker ou só o parser não resolve. |
| 3 | `async def fetch_realized_funding(symbol, start, end) -> list[NormalizedFunding]` (`GET /fapi/v1/fundingRate`, peso 1; `ts` = instante do settlement; `funding_kind="realized"`) | CRITICAL | `funding.py:71` checa `callable(getattr(adapter, "fetch_realized_funding", None))`; ausente, o produtor registra um warning, insere um `system_events` e fica em `await asyncio.Event().wait()` para sempre. A tabela `funding_rates` (realizado) nunca é populada. O comportamento é honesto (nunca promove estimativa WS a taxa realizada), mas a linha T1.3 do plano exige esse histórico. |
| 4 | Limitar a fila interna do adapter (`asyncio.Queue()` sem `maxsize` em `binance/ws.py:139`, alimentada por `put_nowait` nos leitores) | HIGH | Redis/Postgres ficam lentos, o consumidor do worker desacelera, mas os leitores WS continuam empilhando eventos sem limite de itens, bytes ou idade. O processo pode estourar memória **antes** que a política de descarte da fila do worker (`queues.py`, limitada e observável) chegue a agir — o limite do worker só protege depois do gargalo, não antes. |
| 5 | `restart_connection(key: str)` no `BinanceWsClient` | MEDIUM (não bloqueante no M1) | Sem ele, o watchdog do worker cai no fallback `restart_stream = True`; `stream.aclose()` cancela **todas** as tarefas do cliente. Se só `market:0` silencia, a conexão `public:0` (book + bid/ask dos 200 símbolos) saudável é derrubada junto, criando um buraco evitável de book/ticker em todo o universo. Fallback autorizado no brief do M1; a correção mínima é reabrir só a conexão faltante. |
| 6 | Propagação imediata de falha dos leitores privados (`asyncio.ensure_future` em `binance/ws.py:151`, fora do `TaskGroup` do worker) | LOW (aceito no M1, registrar no relatório) | Hoje todo erro de conexão/recebimento é capturado por um `except Exception` amplo e vira backoff+reconnect, então um leitor morto silenciosamente é praticamente inalcançável. A janela real de não-detecção é de até ~31 s (1 s de poll + 30 s de limiar do watchdog), escalando para fatal após 3 reinícios (~90 s). Dentro do contrato 30 s/3 reinícios: **aceito no M1**, registrado pelo número, não pedimos mudança. |
| 7 | Semântica de progresso do `last_data_event_monotonic` | MEDIUM (decisão M1 registrada) | O adapter avança esse campo a cada frame reconhecido, inclusive duplicatas que o worker rejeita. A checklist diz que duplicata não conta como progresso, mas o adapter não tem como saber o que o worker aceitou. **Decisão M1:** o token do adapter permanece com o significado "a conexão está viva" (frames estão chegando) e o gate de "progresso aceito" fica no worker, na readiness (sem evento aceito há 60 s → `/ready` falso). Uma exchange que transmite dado congelado aparece como *not ready*, não como conexão reiniciada. Canal de progresso aceito por conexão fica para o M2. |

Verificação de orçamento de rate limit feita nesta revisão (peso Binance USDS-M, 2400/min): regime estacionário com 200 mercados ≈ **84 peso/min (3,5 % do orçamento)** — universo 2,7/min + OI 40/min + funding realizado 40/min + `server_time` 1/min. Rajada única de cold start: 200 × `fetch_candles(limit=1500)` a peso 10 = **2000 peso** num só burst (~83 % de uma janela de refill), servida pelo token bucket sem 429. Conclusão: **200 mercados não estouram o orçamento de peso.**

---

## Resultado final da revisão (2026-09-05, orquestrador) — commit `97c36ff`

Revisores despachados: `code-reviewer`, `exchange-integration-specialist` (revisão cruzada, rotas conferidas contra a doc oficial + `ccxt` + `python-binance`) e Astra adversarial (`.claude/state/astra-review-review-T1.2-final.md`). 16 achados com cenário de falha reconciliados no brief `.claude/state/fix-brief-T1.2.md` e corrigidos antes do commit.

### (a) Checklist da decisão conjunta
- ✔ Seis canais nas rotas acordadas (`/public` para `@depth20` e `@bookTicker`; `/market` para `@aggTrade`, `@kline_1m`, `@markPrice@1s`, `@forceOrder`); 200 símbolos = 400 public + 800 market.
- ✔ `@depth20` sem sufixo, substituição integral do snapshot top 20 (teste novo com níveis diferentes entre snapshots, não só `u` diferente).
- ✔ `ts` da fonte e `received_at` separados; `event_ts` do `E` nas velas WS; frame atrasado/duplicado não rejuvenesce dado.
- ✔ Limite contado em **streams** (1024), agora com constante e assert que levanta em vez de truncar.
- ✘/aceito Rotação com jitter **sem sobreposição** — o `recv()` passou a ter deadline (rotação dispara em socket silencioso), mas a substituta só abre depois que a antiga fecha. Limitação registrada em `docs/plans/M1.md`.
- ✔ Orçamento REST por IP consumindo o header de peso, parada de retry em `429` antes do `418`; header só pode tirar orçamento, nunca devolver reserva em voo; gate de IP com `Retry-After` cobrindo os dois buckets.

### (b) Entregáveis da linha T1.2
- ✔ `base.py` (Protocol intacto; `ExchangeAdapterExtras` aditivo) · ✔ `rate_limit.py` · ✔ `binance/rest.py` (sete rotas + `serverTime`) · ✔ `binance/ws.py` (+ `connection.py`, `subscriptions.py`, `subscription_plan.py`, `streams.py`, `event_queue.py`) · ✔ `binance/normalize.py` · ✔ fixtures reais + `testing/fake_adapter.py` · ✔ testes (delistado, candle duplicado, malformado, reconexão com resubscribe, diff de assinatura, limites de fila, funding paginado) · ✔ testes `live` fora do CI.

### (c) Regras do CLAUDE.md
- ✔ `Decimal` (o parser rejeita `float`), ✔ UTC, ✔ 0 arquivo acima de 350 linhas (`ws.py` 349 → 272 com a extração de `connection.py`), ✔ `structlog` sem `print`, ✔ fixtures gravadas da API real, ✔ sem segredos e sem `.env`, ✔ `async` no IO, ✔ markers `unit`/`live`.

### (d) Verificação executada pelo orquestrador
```
uv run pytest packages/exchange-adapters -q -p no:cacheprovider        -> 189 passed, 3 skipped
HUNTER_LIVE_TESTS=1 uv run pytest packages/exchange-adapters -m live   -> 3 passed, 189 deselected
uv run ruff check / ruff format --check packages/exchange-adapters     -> All checks passed / 35 files already formatted
uv run pyright packages/exchange-adapters                              -> 0 errors, 0 warnings
uv run python infra/scripts/check_file_size.py                         -> scanned 127 files; 0 over budget
```
Prova de canal: o teste `live` novo abre o stream real e exige payload de **dado** nas duas rotas (ticker na public, trade na market), não só o ACK.

### Pendências vindas da T1.3 — uma a uma
| # | Item | Estado |
|---|---|---|
| 1 | `update_subscriptions` | ✔ fechado (diff-only, grupos estáveis, ACK, catch-up; `UNSUBSCRIBE` antes de `SUBSCRIBE`) |
| 2 | `event_ts` do frame `E` | ✔ fechado |
| 3 | `fetch_realized_funding` | ✔ fechado, agora **paginado**, bucket próprio, `funding_kind="realized"` |
| 4 | Fila interna limitada | ✔ fechado (nunca descarta kline final; limita por itens) |
| 5 | `restart_connection(key)` | ✔ fechado (era MEDIUM não bloqueante; implementado nesta revisão) |
| 6 | Propagação de falha do leitor | ✔ fechado para exceção; retorno normal inesperado segue coberto pelo watchdog do worker (janela ~31 s, aceita) |
| 7 | Semântica de `last_data_event_monotonic` | ✔ decisão M1 mantida (token = conexão viva; gate de progresso aceito no worker) |

Commit: `97c36ff` · push em `main`.
