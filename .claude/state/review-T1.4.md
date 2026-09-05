# Kit de revisão — T1.4 · API de mercado e `system/workers`

**Owner:** `backend-specialist` (Claude, sonnet) · **Estado:** em voo em 2026-09-05
**Files (do plano):** `apps/api/hunter_api/routers/{markets,system}.py`, `schemas/{markets,system}.py`, `services/markets.py`, `repositories/markets.py`, `app.py` (só include), `apps/api/tests/**/test_markets*.py`, `test_system_workers*.py`
**Depends-on:** T1.1
**Commit esperado:** `feat(api): markets and system/workers endpoints`

---

## (a) Checklist da decisão conjunta Claude ⇄ Astra que se aplica a T1.4
Copiada literalmente de `.claude/state/dialogue-M1.md` → `## Astra (rodada 4)`.

- [ ] T1.4 — Expor `components` para ticker, book e mark com `ts`, `age_ms` e `quality`, além de idade própria de OI, funding e liquidações e tipo de funding; distinguir estimativa de funding realizado. `age_ms` deriva do timestamp da exchange do último evento aceito, nunca do flush; OI, funding e liquidações ficam fora da regra de 10 s.
- [ ] T1.4 — Calcular agregado sobre ticker, book e mark obrigatórios, nesta precedência: todos ausentes → `unavailable`; gap `open/failed` ou obrigatório ausente → `degraded`; senão qualquer obrigatório com idade > 10 s → `stale`; senão → `ok`. Preservar qualidades individuais e motivos, inclusive quando `degraded` prevalece; heartbeat global não substitui frescor por mercado.
- [ ] T1.4 — Validar book parado com outros canais ativos, mark parado, OI atualizado com mark parado, chave expirada, nenhum dado, gap `failed` com ticks atuais e passagem do tempo sem publicações; API recalcula qualidade e fornece metadados para a UI envelhecer os dados sem mensagem nova. Expor snapshot top 20 conforme T1.2; limiares refinados de 1 s/3 s e painel detalhado ficam para M2.

Item de T1.2 com efeito direto no contrato exposto pela API:

- [ ] T1.2 — ... reconciliar profundidade REST e projetar `book.kind="snapshot"`, `book.depth=20` na API. (discriminador interno `kind="book"` permanece intacto)

## (b) Critérios da linha da tarefa em `docs/plans/M1.md`
- [ ] `GET /api/v1/markets?exchange=&q=&monitored=` — lista do Postgres + hot state com `last_update` e `data_quality`.
- [ ] `GET /api/v1/markets/{exchange}/{symbol}` · `/candles?timeframe=1m&limit=` · `/book` · `/trades`.
- [ ] `GET /api/v1/system/workers` a partir de `hb:*`.
- [ ] `GET /api/v1/system/market-status`: mercados monitorados, conexões WS por exchange, idade do último tick, gaps abertos.
- [ ] Schemas Pydantic com `Decimal` **serializado como string** (o JSON não pode perder precisão).
- [ ] Repositórios globais lendo com o role `hunter_app` (SELECT).
- [ ] `app.py` recebe **só o include** dos routers — nenhuma outra mudança.
- [ ] OpenAPI regenerado: `pnpm gen:types` sem diff funcional pendente.

## (c) Regras do `CLAUDE.md` que mais pegam aqui
- [ ] **Isolamento de tenant:** estes endpoints leem dados **globais** de mercado. Verificar que (1) exigem autenticação e membership como os demais, (2) não vazam nada por organização, (3) não permitem que um parâmetro (`exchange`, `symbol`, `q`) vire acesso a tabela de tenant, (4) as consultas continuam sob `SET LOCAL ROLE hunter_app` — nunca `hunter_worker` no processo da API.
- [ ] Sem dado falso: exchange fora do ar → `UNAVAILABLE`/`degraded` explícito no payload, nunca último preço apresentado como atual.
- [ ] `Decimal` (string no JSON) e UTC (ISO-8601 com `Z`).
- [ ] Nenhum arquivo acima de 350 linhas; `structlog`, nunca `print`.
- [ ] Erros no formato RFC 9457 já usado pelo middleware, sem eco do input.
- [ ] Rate limit e headers de segurança continuam valendo para as rotas novas (nada fora do middleware existente).
- [ ] Nenhum segredo, chave de exchange ou variável de ambiente aparece em resposta ou log.

## (d) Comandos de verificação exatos
```bash
export PATH="/c/Program Files/nodejs:/c/Users/evert/AppData/Roaming/npm:/c/Users/evert/AppData/Local/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe:/c/Users/evert/.local/bin:/c/Users/evert/AppData/Local/Programs/DockerDesktop/resources/bin:$PATH"
cd /c/dev/project-hunter
uv run pytest apps/api -q -k "markets or system_workers"
uv run pytest apps/api -q                      # a suíte inteira não pode regredir
uv run pyright apps/api
uv run ruff check apps/api && uv run ruff format --check apps/api
uv run python infra/scripts/check_file_size.py
pnpm gen:types && git diff --stat -- packages/shared-types
```
Prova com dado real (worker de T1.3 rodando):
```bash
curl -s localhost:8000/api/v1/markets | head -c 800
curl -s localhost:8000/api/v1/system/workers
curl -s localhost:8000/api/v1/system/market-status
```
Cenários de staleness que precisam de saída colada: book parado com resto ativo; mark parado; OI novo com mark parado; chave Redis expirada; nenhum dado; gap `failed` com ticks atuais.

## (e) Revisores a despachar (em paralelo)
| Revisor | Escopo |
|---|---|
| `code-reviewer` | conformidade com a linha T1.4, contrato dos schemas, testes de cada cenário de staleness, tamanho de arquivo |
| `security-reviewer` | **obrigatório** — endpoints globais lidos por qualquer tenant: auth/RBAC, ausência de vazamento entre organizações, role de banco correto, injeção via `q`/`symbol`, ausência de segredo em resposta e log, rate limit e CORS |
| `database-architect` | só se o diff tocar modelo/migração (não deveria: T1.4 é leitura). Se `git diff --stat` mostrar `packages/core/hunter_core/db/**` ou `infra/migrations/**`, torna-se obrigatório |
| `exchange-integration-specialist` | não se aplica |
| `risk-engine-guardian` | não se aplica no M1 |

## (f) Segunda opinião da Astra (obrigatória, depois do `code-reviewer`)
```bash
bash infra/scripts/astra.sh ask review-T1.4 "Review apps/api/hunter_api/routers/{markets,system}.py, schemas/{markets,system}.py, services/markets.py, services/system_status.py, repositories/markets.py e os testes em apps/api/tests against docs/plans/M1.md (linha T1.4) e os 3 itens T1.4 da DECISÃO CONJUNTA em .claude/state/dialogue-M1.md. Confira: components (ticker, book, mark) com ts, age_ms e quality; age_ms derivado do timestamp da exchange do último evento aceito e nunca do flush; OI, funding e liquidações com idade própria fora da regra de 10s e funding_kind estimated/realized; precedência do agregado unavailable > degraded > stale > ok preservando motivos individuais; Decimal serializado como string; UTC; isolamento de tenant e role hunter_app; projeção book.kind=snapshot e book.depth=20; nenhum dado congelado apresentado como atual. Must-fix com cenário de falha, nice-to-have, concordâncias. Não modifique arquivos."
```

## (g) Commit esperado
```
feat(api): markets and system/workers endpoints

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```
`git -c commit.gpgsign=false commit` · só os arquivos de `apps/api/**` (+ `packages/shared-types` se `pnpm gen:types` mudar o contrato) · `git push origin main`.
