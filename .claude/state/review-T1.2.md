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
