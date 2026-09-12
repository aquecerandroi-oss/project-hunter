# T4.13 — o registro completo de cada teste na mesa (`GET /meme/tests`, CSV, aba "Testes", ficha da aposta)

Execução de 12/09/2026, a partir de ~12:0x BRT (15:0x UTC), papel full-stack. Sem commit.
Brief: `.claude/state/brief-T4.13-registro-de-testes-na-mesa.md`. Base: `e096c0c` (T4.10a: `leg`/`parent_bet_id`,
`meme_features_v3`, `ExitReason` com `max_loss`/`line_broken`).

## Decisões de desenho (registradas antes de codar)

- **Dia da aposta = dia Brasília de `entry_at`** (a mesma régua de `meme_lab_scoreboard_v1`, que agrupa por
  `date(entry_at AT TIME ZONE 'America/Sao_Paulo')`). A "Fechadas hoje" da mesa usa `exit_at`; o registro de
  testes é o diário do dia em que o teste **começou** — a primeira coluna fixa é a hora de entrada. Aposta aberta
  entra no dia em que abriu, com a marca (`mark_sol`/`mark_at`) como saída provisória.
- **PnL US$ (fechada) = `pnl_sol × sol_usd_at_exit`** — exatamente a fórmula da vista `meme_lab_scoreboard_v1`
  (`ddl/meme_lab_views.py`), para o registro e o placar dizerem o mesmo número. Sem cotação de saída → `null` com
  `pnl_usd_reason = no_exit_quote`. Aberta → provisório `pnl_sol × sol_usd_at_entry` com
  `pnl_usd_basis = entry_quote_provisional`. Nunca uma cotação "ao vivo" que a API não tem.
- **Motivo em vocabulário fechado, traduzido no servidor**: `EXIT_REASON_PT` em `schemas/meme_tests.py` cobre
  os nove `ExitReason` (teste `typing.get_args` garante), e o CSV escreve o rótulo em português; o JSON leva o
  enum **e** o rótulo (`exit.reason` + `exit.reason_label`) — a tela usa o dicionário próprio
  (`components/meme-desk/labels.ts`, agora com `max_loss`/`line_broken`), com as mesmas palavras.
- **`lab_context`** lido de `meme_features_1m` em `(mint, meme_proposals.features_end_time)`, preferindo
  `meme_features_v3` (as colunas de linha/hype só existem nela); proposta manual não tem minuto →
  `reason = manual_no_minute`; minuto sem linha em `meme_features_1m` → `reason = no_features_row`.
  Uma consulta por página (`mint IN (...) AND end_time IN (...)`, filtrada ao par exato em Python), nunca N+1.
- **REAL (T4.12, paralela)**: `meme_wallet_positions` é lida por `to_regclass` + `SELECT *` sob SAVEPOINT; tabela
  ausente → `sources.wallets = "não observada"` e `real_items = []`; erro de leitura (colunas diferentes do
  esperado) → `"leitura indisponível"` sem derrubar a página. As linhas reais vêm em `real_items` (campo próprio,
  não misturado ao keyset das apostas de papel) e a tela/CSV as intercalam por hora de entrada.
- **CSV**: UTF-8 com BOM, `;`, CRLF, decimais com **vírgula** (Excel pt-BR reconhece número só assim quando o
  separador é `;`), datas `dd/mm/aaaa HH:MM:SS` Brasília, booleanos `sim`/`não`, vazio = ausência honesta.
  Teto de 5 000 linhas por dia (`CSV_MAX_ROWS`).
- **Download no navegador**: a API interna exige o bearer do Clerk; o botão "Exportar CSV" aponta para um route
  handler `app/(app)/[orgSlug]/meme/testes/export/route.ts` (passa pelo `clerkMiddleware`, pede o token com
  `getServerSession`, repassa o CSV com os mesmos cabeçalhos). O caminho **não** termina em `.csv` de propósito: o
  matcher do middleware ignora URLs com extensão `.csv` e `auth()` falharia sem o middleware.
- **Aba "Testes" em `/meme/mesa`** = `?tab=testes` renderiza a mesma seção da rota própria `/meme/testes`;
  as guias são `<Link>` (o padrão T3.51 do Lab: nunca um botão com `router.push`).
- **Tabela ≤ 200 linhas por página** (limite da API `MAX_PAGE_SIZE`), paginação por `?cursor=` (link), aviso
  "exporte o CSV para o dia inteiro" — cumpre "virtualiza a partir de 200" sem virtualizar uma tabela
  expansível com colunas fixas.

## Linha do tempo

- 12:0x BRT — leitura do brief, contrato T4.6/T4.7 + emendas, notas T4.7, `lab_bets.py`/`paper_fill.py`/
  `paper_engine.py`/`lab_values.py` (chaves reais de `entry`/`exit`: `snapshot{observed_at,source,mcap_sol,…}`,
  `decided_at`, `decision_to_fill_s`, `fill_delay_snapshots`, `marginal_price_before_sol`,
  `marginal_price_after_sol`, `average_price_sol`, `fee_sol`, `fee_pct`, `sol_spent`, `tokens`, `sol_usd*`,
  `leg`, `parent_bet_id`; saída: `reason`, `snapshot`, `sol_received`, `fee_sol`, `marginal_price_after_sol`,
  `trigger`, `pending_reason`), brief T4.12, DESIGN.md, ARCHITECTURE §7–8, PRODUCT.md.
- Árvore na partida: `git status --porcelain` já mostrava ` M .claude/launch.json`, ` M docs/DESIGN.md` e
  centenas de `??` em `.claude/state/**` (artefatos de sessões anteriores) — nada meu; não toquei.
- 12:1x–12:3x BRT — API: `schemas/meme_tests.py`, `repositories/meme_tests.py` (+ `meme_tests_rows.py` depois, pelo
  orçamento de 350 linhas: 366 → 278 + 118), `services/meme_tests.py` / `meme_tests_real.py` / `meme_tests_csv.py`,
  `routers/meme_tests.py`, registro em `app.py`. `TestBetRow` renomeado `BetRecord` (o pytest tentava coletar a
  classe `Test*`). Unit 18 → integração 13 no testcontainer contra o Alembic head (seed como `hunter_worker`;
  descobri que uma linha válida de `meme_features_1m` exige motivo em cada métrica nula das guardas 0021/0023 e o
  grupo da linha completo quando `line_points` não é nulo).
- 12:3x–12:5x BRT — web: `lib/server/api.ts` ganhou `apiFetchResponse(path, accept)` (o CSV precisa do bearer);
  `MEME_EXIT_REASONS` + rótulos `max_loss`/`line_broken`; `MemeCurveChart` aceita `Pick<…, "observed_at" | "mcap_sol">`;
  `components/meme-tests/*` (9 arquivos), rotas `/meme/testes`, `/meme/testes/export` (route handler), `/meme/mesa`
  com `?tab=testes`, `/meme/mesa/aposta/[betId]`; Vitest 44. `exactOptionalPropertyTypes` exigiu `| undefined` nas
  props opcionais; a checagem de tipos do Next recusa `export const` fora dos nomes reservados numa `page.tsx`
  (o primeiro `next build` falhou nisso; corrigido). Cinco advertências `complexity` (máx. 12) zeradas dividindo os
  componentes em subcomponentes.

## Comandos e saída real (12/09/2026, 12:2x–12:5x BRT)

- `timeout 290 uv run ruff check <7 arquivos API + app.py>` → `All checks passed!`
- `timeout 290 uv run ruff format --check <10 arquivos API>` → `10 files already formatted`
- `timeout 290 uv run pyright <9 arquivos API + 2 testes>` → `0 errors, 0 warnings, 0 informations`
- `timeout 290 uv run pytest apps/api/tests/unit/test_meme_tests_service.py -q` → `18 passed in 0.37s`
- `timeout 590 uv run pytest apps/api/tests/unit -q -m unit` → `680 passed, 18 deselected, 1 warning in 73.68s`
- `timeout 590 uv run pytest apps/api/tests/integration/test_meme_tests_api.py -q -ra` → `13 passed in 100.10s`
  (primeira rodada) e `13 passed in 98.50s` (após a divisão do repositório)
- `timeout 290 pnpm gen:types` → `packages/shared-types/openapi.json → .../api.d.ts [625.6ms]`
- `cd apps/web && timeout 290 npx vitest run tests/meme-tests-*.test.ts(x) tests/meme-desk-labels.test.ts
  tests/meme-curve-chart.test.ts` → `6 passed (6) / 44 passed (44)`; suíte inteira `npx vitest run` →
  `Tests 1451 passed (1451)` em 72 s
- `timeout 590 npx turbo run typecheck lint --filter=@hunter/web` → `Tasks: 2 successful, 2 total`; lint
  `✖ 2 problems (0 errors, 2 warnings)` — as duas pré-existentes (`tests/lab-page.test.tsx` 377 linhas,
  `tests/ws.test.ts` 557 linhas)
- `cd apps/web && timeout 590 npx next build` → `✓ Compiled successfully in 12.3s`, `Linting and checking validity
  of types` ok, `✓ Generating static pages (6/6)`; depois `EPERM: operation not permitted, symlink` ao copiar os
  traces do `standalone` — o problema conhecido do Windows (CLAUDE.md KNOWN ISSUES #0; Linux/CI não afetado)
- `timeout 290 uv run python infra/scripts/check_file_size.py` → `scanned 788 files; 0 over budget, 0 grandfathered`
  (na rodada anterior acusara `repositories/meme_tests.py` 366 — dividido — e dois arquivos de outras tarefas,
  `pumpfun/rpc.py` 363 e `services/meme-worker/.../wallets.py` 357 da T4.12, que já não aparecem)
- `git status --porcelain` (só os meus caminhos): 9 ` M` (`app.py`, `mesa/page.tsx`, `meme-desk/labels.ts`,
  `meme-curve-chart.tsx`, `meme-desk-types.ts`, `lib/server/api.ts`, `meme-desk-labels.test.ts`,
  `docs/plans/T4-MEME-RADAR.md`, `packages/shared-types/src/generated/api.d.ts`) e 21 `??` (os módulos novos,
  `components/meme-tests/`, rotas, testes, estas notas).

## Concerns

- **Nenhuma tela vista no navegador**: sem dev server (regra da tarefa) e o navegador embutido não abre
  localhost/Clerk; a prova visual fica para a sessão Playwright logada. A tabela densa com colunas fixas
  (`sticky left-0/left-8/left-28`) e os cartões 375 px foram verificados só por Vitest (estrutura e textos).
- **Prettier não aplicado**: `.prettierrc` existe na raiz, mas os arquivos de HEAD que toquei (`lib/server/api.ts`,
  `meme-curve-chart.tsx`, `meme-desk/labels.ts`, `closed-today-section.tsx`) já não eram conformes — o lint não o
  impõe; para não reformatar código alheio, deixei os arquivos novos no estilo dos vizinhos.
- **REAL depende da T4.12**: a leitura de `meme_wallet_positions` é por nome e tolerante (`services/meme_tests_real.py`
  procura `wallet`/`mint`/`state`/`first_buy_at`/`last_trade_at`/`sol_spent`/`sol_received`/`realized_pnl_sol`/
  `r_multiple`/`mark_sol`/`mark_source`/`lab_context` com sinônimos); se a T4.12 batizar colunas de outro jeito, as
  linhas reais aparecem com campos "não registrado" — nunca inventados — e o teste de integração só afirma o
  vocabulário de `sources.wallets`. Ajuste de nomes = uma linha por campo em `_real_row_out`.
- `real_items` só vêm na primeira página sem filtro de conjunto (fora do keyset das apostas de papel); nas demais
  páginas a API ainda responde `sources.wallets` (sonda `LIMIT 1`).
- CSV com decimais em vírgula e `;` (Excel pt-BR); quem quiser ponto usa o JSON.
- `/meme/mesa` passou a ler `searchParams` (`tab`, `day`, `set`, `cursor`) — sem teste de página existente para a
  mesa; o comportamento novo está coberto pelos testes dos componentes e pelo `next build`.
