# Kit de revisão — T1.7 · Testes de integração e E2E do M1

**Owner:** `test-engineer` (Claude, sonnet) · **Estado:** não iniciado — onda 3
**Files (do plano):** `tests/integration/**`, `tests/e2e/markets.spec.ts`
**Depends-on:** T1.3, T1.4, T1.5
**Commit esperado:** `test(m1): market pipeline integration and e2e`

---

## (a) Itens da decisão conjunta que T1.7 tem de **provar de ponta a ponta**
A decisão conjunta não abriu uma seção `T1.7`; T1.7 é a prova integrada dos contratos de T1.2/T1.3/T1.4. Estes são os itens (copiados literalmente de `.claude/state/dialogue-M1.md` → `## Astra (rodada 4)`) cujo cenário tem de aparecer no teste de integração, não só no teste unitário da tarefa de origem:

- [ ] T1.2 — Preservar `ts` da fonte e `received_at` desde a normalização, incluindo timestamp da atualização WS para ordenar parciais de candle; demonstrar que atualizações atrasadas ou duplicadas não rejuvenescem dados em conexões sobrepostas.
- [ ] T1.3 — Persistir apenas candles finais no Postgres; ... REST usa `ON CONFLICT (market_id, timeframe, open_time) DO NOTHING`, sem sobrescrever final existente; validar resposta REST atrasada após avanço WS e conflitos sem abortar lotes.
- [ ] T1.3 — Manter escritor único e serializado para a lista de candles Redis ... Abertura maior avança a ponta; na mesma abertura, parcial mais novo atualiza parcial, final substitui parcial e parcial nunca substitui final; rejeitar parciais atrasados/duplicados.
- [ ] T1.3 — Detectar buracos internos a cada minuto comparando aberturas esperadas na janela de 24 h com finais persistidos ... resposta incompleta mantém pendência e incrementa tentativas, quinta falha produz `failed` visível como `degraded`.
- [ ] T1.3 — Deduplicar liquidações com `id = uuid5(...)` ... usar exatamente `INSERT ... ON CONFLICT (id, ts) DO NOTHING`. Validar linha única em sobreposição WS, retry após commit incerto, reentrega após 3600 s e perda do cache Redis.
- [ ] T1.3 — Publicar `market.liquidations` com `EventEnvelope.event_id` igual ao UUID determinístico e validar deduplicação no consumidor. ... O teste dessa morte verifica histórico único e admite publicação ausente sem exigir registro inexistente.
- [ ] T1.3 — Coalescer preserva timestamps do último evento aceito e só renova dados/TTL com evento novo aceito; ciclos sem eventos deixam o TTL cair.
- [ ] T1.4 — Calcular agregado sobre ticker, book e mark obrigatórios, nesta precedência: todos ausentes → `unavailable`; gap `open/failed` ou obrigatório ausente → `degraded`; senão qualquer obrigatório com idade > 10 s → `stale`; senão → `ok`.
- [ ] T1.4 — Validar book parado com outros canais ativos, mark parado, OI atualizado com mark parado, chave expirada, nenhum dado, gap `failed` com ticks atuais e passagem do tempo sem publicações.

## (b) Critérios da linha da tarefa em `docs/plans/M1.md`
- [ ] `tests/integration/test_market_pipeline.py`: caminho completo **fake adapter → worker → Redis → contrato da API → WS `rt:market`**. Sem rede externa: o `fake_adapter` de T1.2 é a fonte.
- [ ] Invariantes testadas: `open_time` alinhado ao timeframe; **nenhum** candle duplicado; `data_quality` muda com a passagem do tempo (ok → stale → degraded/unavailable).
- [ ] `tests/e2e/markets.spec.ts` (Playwright): a lista carrega; o detalhe carrega; o badge `stale` aparece com o WS desligado.
- [ ] Verificação: `uv run pytest tests/integration -q` verde e `pnpm e2e` verde local.

## (c) Regras do `CLAUDE.md` que mais pegam aqui
- [ ] **Teste não pode mentir:** nada de `assert True`, `skip` silencioso, `xfail` sem motivo escrito, ou espera fixa que passa por sorte. Falha tem de falhar.
- [ ] Sem dado falso: os fixtures vêm de payload real gravado (T1.2), não de JSON inventado.
- [ ] Integração usa **testcontainers** (Postgres + Redis reais), não SQLite nem fake de banco — regra "sem estado local".
- [ ] `Decimal` e UTC também nas asserções: comparar string/Decimal, nunca `float` aproximado em preço.
- [ ] Tempo controlado explicitamente (clock injetável / `freezegun`), não `sleep` longo — mas o que a decisão conjunta chama de "passagem do tempo sem publicações" tem de ser realmente exercitado.
- [ ] Marcadores corretos: `integration` para o pipeline, `live` só para o que toca a exchange real (fora do CI).
- [ ] Nenhum arquivo acima de 350 linhas; `structlog`, nunca `print`.
- [ ] Nenhum segredo em fixture, `.env` de teste ou snapshot do Playwright.

## (d) Comandos de verificação exatos
```bash
export PATH="/c/Program Files/nodejs:/c/Users/evert/AppData/Roaming/npm:/c/Users/evert/AppData/Local/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe:/c/Users/evert/.local/bin:/c/Users/evert/AppData/Local/Programs/DockerDesktop/resources/bin:$PATH"
cd /c/dev/project-hunter
uv run pytest tests/integration -q
uv run pytest -q                                # suíte inteira: nada regride
pnpm e2e
uv run pyright && uv run ruff check .
uv run python infra/scripts/check_file_size.py
```
Prova de que o teste pega o erro (anti-teste-verde-inútil): quebrar de propósito **uma** invariante (ex.: deixar um parcial sobrescrever um final) e mostrar o teste vermelho; desfazer e mostrar verde. Colar as duas saídas.

## (e) Revisores a despachar (em paralelo)
| Revisor | Escopo |
|---|---|
| `code-reviewer` | cobertura real dos cenários da lista (a), testes que de fato falham quando o contrato quebra, ausência de flakiness por `sleep`, tamanho de arquivo |
| `database-architect` | se o teste tocar migração/schema ou depender de partição/retenção — conferir que usa testcontainers e o role correto |
| `exchange-integration-specialist` | conferir que o `fake_adapter` representa fielmente o comportamento do adapter real (ordenação, reconexão, parciais) — senão o E2E passa contra uma ficção |
| `security-reviewer` | não obrigatório em T1.7; dispensado salvo se aparecer credencial em fixture ou config de teste |
| `risk-engine-guardian` | não se aplica no M1 |

## (f) Segunda opinião da Astra (obrigatória, depois do `code-reviewer`)
```bash
bash infra/scripts/astra.sh ask review-T1.7 "Review tests/integration/test_market_pipeline.py e tests/e2e/markets.spec.ts against docs/plans/M1.md (linha T1.7) e os itens de T1.2/T1.3/T1.4 da DECISÃO CONJUNTA em .claude/state/dialogue-M1.md que o pipeline integrado deve provar. Confira: o teste cobre fake adapter → worker → Redis → contrato da API → WS rt:market de ponta a ponta; invariantes open_time alinhado, nenhum candle duplicado e data_quality mudando com o tempo; precedência unavailable/degraded/stale/ok; parcial nunca substitui final; liquidação única sob sobreposição e retry; TTL caindo sem evento novo. Diga quais cenários da decisão conjunta NÃO estão cobertos e quais testes passariam mesmo com o contrato quebrado. Must-fix com cenário de falha, nice-to-have, concordâncias. Não modifique arquivos."
```

## (g) Commit esperado
```
test(m1): market pipeline integration and e2e

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```
`git -c commit.gpgsign=false commit` · só `tests/integration/**` e `tests/e2e/markets.spec.ts` · `git push origin main`.
