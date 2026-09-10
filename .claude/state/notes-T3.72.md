# Notas T3.72 — Nova ordem paper (Carteira)

Contrato do POST usado: `/api/v1/orgs/{org_id}/portfolios/{portfolio_id}/orders` (não o path do brief, que
omite `/orgs/{org_id}` — todo outro endpoint de carteira já usa esse prefixo). `notes-T3.68.md` ainda não
existe (agente de backend não terminou); construí contra `hunter_risk/decision.py`/`sizing.py` e
`docs/RISK_ENGINE.md` §2-4 diretamente. Schemas zod em `manual-orders-types.ts` (não uso
`@hunter/shared-types/api` pois o endpoint ainda não está gerado).

Comandos (todos em `C:/dev/project-hunter`, timeouts explícitos):
- `npx turbo run typecheck --filter=@hunter/web` → OK.
- `npx turbo run lint --filter=@hunter/web` → 0 erros (2 warnings pré-existentes em `tests/lab-page.test.tsx` e
  `tests/ws.test.ts`, não tocados).
- `npx turbo run test --filter=@hunter/web` → 119 arquivos, 1124 testes, todos verdes.
- `npx turbo run build --filter=@hunter/web` → compila e tipa OK; falha no EPERM symlink do standalone
  (KNOWN ISSUE #0 do CLAUDE.md, Windows, pré-existente, não relacionado a este diff).
- `pnpm exec playwright test` não executado: Chromium não alcança localhost nesta máquina desde 08/09
  (memória) e, além disso, o onboarding do M0 não abre carteira paper automaticamente — spec escrita
  como skip honesto (`E2E_MANUAL_ORDER_ORG_SLUG` ausente).

Arquivos tocados/criados — ver lista completa na resposta final (git status --porcelain conferido).
`docs/DESIGN.md` e `tests/e2e/design-audit.*` aparecem modificados/novos na árvore mas NÃO são deste
diff (outro agente).

## T3.72b — correções do code review (2026-09-10)

Achados tratados:
1. HIGH `manual-order-form.tsx`: `resetForRetry` ("Enviar outra ordem") agora gera uma nova
   `Idempotency-Key` (`crypto.randomUUID()`) e limpa mercado/stop/notional — é uma submissão NOVA, não
   um retry. A chave só é reaproveitada quando o próprio `handleSubmit` roda de novo sobre os MESMOS
   campos após uma falha (rede/API) sem nunca ter chegado a `filedOrder` (nada muda ali, comportamento
   preexistente preservado). Testes novos: `tests/manual-order-form.test.tsx` (2 casos: chave nova numa
   ordem realmente diferente após "Enviar outra ordem"; mesma chave num retry de rede da MESMA
   submissão).
2. MEDIUM `manual-order-section.tsx`: `blockReason` já tinha a prioridade correta (VIEWER > carteira
   não aberta > kill switch); faltavam os testes. Criado `tests/manual-order-section.test.tsx` (4 casos
   cobrindo os 3 motivos isolados/em conflito e o caminho "nada bloqueia").
3. LOW `manual-order-form-schema.ts`: `validateStopAgainstMarket` comparava `stop`/`last_price` via
   `Number()`. Não existe `decimal.js`/`big.js`/`compareDecimal` no projeto (`decimal.js` no
   `pnpm-lock.yaml` é transitivo do `jsdom`, não uma dependência real do app) — em vez de adicionar uma
   dependência, extraí `compareDecimalStrings` (novo, exportado) em `lib/format.ts` reaproveitando o
   `parseDecimal`/`BigInt` que `formatMoney`/`formatBrl` já usam (sem passar por `float`). Trocada só a
   comparação do lado do preço (`stopValue >= lastPriceValue` → `compareDecimalStrings(stop, lastPrice)
   >= 0`); a distância percentual (hint informativo, já documentado como não-bloqueante) continua com
   `Number()`. Testes novos em `tests/format.test.ts` (inclui caso que reproduz o bug real de `Number()`
   colidindo acima de 2**53).
4. Reconciliação com T3.68: `.claude/state/notes-T3.68.md` CONTINUA sem existir (só o brief). Os
   arquivos do router (`apps/api/hunter_api/routers/orders.py`, `schemas/orders.py`,
   `services/orders*.py`) já aparecem untracked na árvore, mas sem as notas com o contrato final não dá
   para conferir com segurança `manual-orders-types.ts`/`manual-order-labels.ts` — não mexi neles.
   Sinalizando para quem for reconciliar depois.

Comandos (todos em `C:/dev/project-hunter`, timeouts explícitos, foreground):
- `pnpm --filter @hunter/web exec vitest run tests/format.test.ts tests/manual-order-form-schema.test.ts
  tests/manual-order-form.test.tsx tests/manual-order-section.test.tsx` → 4 arquivos, 52 testes, verde.
- `npx turbo run typecheck --filter=@hunter/web` → OK (1 erro `noUncheckedIndexedAccess` em
  `manual-order-form.test.tsx` corrigido com `?.[2]`, depois verde).
- `npx turbo run lint --filter=@hunter/web` → 0 erros; só os 2 warnings pré-existentes de
  `tests/lab-page.test.tsx`/`tests/ws.test.ts` (não tocados).
- `npx turbo run test --filter=@hunter/web` → 121 arquivos, 1134 testes, todos verdes.

Arquivos tocados/criados nesta rodada (T3.72b):
- `apps/web/components/portfolio/manual-order-form.tsx` (modificado)
- `apps/web/lib/api/manual-order-form-schema.ts` (modificado)
- `apps/web/lib/format.ts` (modificado — `compareDecimalStrings`)
- `apps/web/tests/format.test.ts` (modificado)
- `apps/web/tests/manual-order-form.test.tsx` (novo)
- `apps/web/tests/manual-order-section.test.tsx` (novo)
- `.claude/state/notes-T3.72.md` (este arquivo)

## T3.72c — reconciliação com o contrato final da API (T3.68, 2026-09-10)

Lidos: `.claude/state/notes-T3.68.md`, `apps/api/hunter_api/routers/orders.py`,
`schemas/orders.py`, `services/orders.py`, `services/orders_derive.py`,
`services/admission.py` (as três `HunterError` — `OrderRefusedError` 422,
`OrderReplayConflictError`/`WalletNotOpenError` 409), `auth/rbac.py`
(`InsufficientRoleError` 403), `errors.py` (formato `problem+json`),
`packages/risk-core/hunter_risk/{decision,sizing,inputs}.py` (o
`RiskDecision`/`Sizing` já batiam exatamente com o que T3.72/b tinham
escrito de leitura direta do motor — nenhuma mudança ali) e
`packages/core/hunter_core/domain/enums.py` (`OrderSide`/`OrderType`/
`OrderPurpose`/`ExecutionMode`/`OrderStatus`, para tipar `outcome`).
**Nenhum arquivo de `apps/api/**` foi editado** (só lidos).

### Desvios encontrados entre o cliente (chute pré-contrato) e a API final

| Campo/aspecto | Cliente (T3.72/b, antes) | API final (T3.68) | Ação |
|---|---|---|---|
| Caminho | `.../portfolios/{id}/orders` | `.../portfolios/{id}/order-requests` | `manualOrdersPath` corrigido |
| `ManualOrderOut.market_id` | ausente no item base (só opcional na lista) | sempre presente | campo obrigatório adicionado ao schema base |
| `ManualOrderOut.direction` | ausente no item base (só opcional na lista) | sempre presente | campo obrigatório adicionado ao schema base |
| Item de lista (`GET` sem id) | `.extend()` chutando `market` (identidade completa), `stop`, `requested_notional` | é exatamente `ManualOrderOut` — sem esses três campos | `manualOrderListItemSchema` virou `manualOrderOutSchema.passthrough()`; tabela perdeu as colunas Stop/Notional pedido (inexistentes) e mostra `market_id` (truncado) em vez de uma identidade `exchange · symbol` que este endpoint nunca envia |
| `ManualOrderDetailOut.outcome` | `z.record(...).nullable().optional()` (passthrough cru) | `OrderOut \| None` tipado (id/market_id/side/type/purpose/execution_mode/status/qty/price/stop_price/filled_qty/avg_fill_price/created_at/completed_at) | novo `manualOrderOutcomeSchema` com os enums reais de `hunter_core.domain.enums`; campo passa a ser obrigatório (`nullable()`, não `optional()`) |
| Header `Idempotency-Key` | `"Idempotency-Key"`, min 8/max 128 | idêntico (`Header(alias="Idempotency-Key", min_length=8, max_length=128)`) | **sem mudança** — já estava certo |
| `problem.type` 409 (replay) | chute `order_replay_conflict` | `idempotency-key-conflict` (`OrderReplayConflictError`) | `manual-order-labels.ts` e os 3 testes que citavam o slug antigo corrigidos |
| `problem.type` 409 (carteira) | chute `wallet_not_open` | `wallet-not-open` (já batia depois do kebab-case) | mantido, só a doc/teste passaram a citar o slug real com hífen |
| `problem.type` 422 | chutes `non-spot-market`/`market-not-spot`/`bad-stop`/`invalid-stop` (nenhum existe) | um único slug `order-refused`, motivo dentro de `detail` como `"... (reason: <slug>)"` (`market_unknown`, `market_not_executable_spot`, `short_not_supported_spot`, `spot_price_unavailable`, `spot_spread_unavailable`) | `manualOrderProblemMessage` reescrito: extrai o motivo de `detail` com regex e mapeia cada um em `ORDER_REFUSED_REASON_LABEL`; os 4 chutes antigos removidos |
| `problem.type` 403 | sem mapeamento nomeado (só fallback por status) | `insufficient-role` (`auth/rbac.py::InsufficientRoleError`) | adicionado ao mapa `KNOWN`, mesma frase que o fallback já usava |
| `problem.type` 404 | inexistente no cliente | `portfolio-not-found`, `order-request-not-found` | adicionados ao mapa `KNOWN` |
| `ManualOrderCreate`/`RiskDecision`/`Sizing`/`MarketIdentity` | escritos direto de `packages/risk-core` (T3.72 nota 0) | idênticos — `decision` é o `risk_decision` bruto repassado, sem re-modelagem, pelo próprio design do router | **sem mudança** |

### Arquivos modificados nesta rodada (T3.72c)

- `apps/web/lib/api/manual-orders-types.ts` — caminho `order-requests`,
  `market_id`/`direction` obrigatórios em `ManualOrderOut`, `outcome` tipado
  (`manualOrderOutcomeSchema`), lista simplificada para `ManualOrderOut`
  + `.passthrough()`, docstrings atualizadas.
- `apps/web/lib/api/manual-orders.ts` — docstring (caminho/contrato final).
- `apps/web/lib/api/manual-orders-actions.ts` — docstrings (caminho/slugs
  finais); nenhuma mudança de lógica (o header já estava certo).
- `apps/web/components/portfolio/manual-order-labels.ts` —
  `manualOrderProblemMessage` reescrito com os slugs reais e o mapeamento de
  motivo de `order-refused` a partir de `detail`.
- `apps/web/components/portfolio/manual-orders-table.tsx` — colunas
  Stop/Notional pedido removidas (não existem no contrato final), coluna
  Mercado agora mostra `market_id` truncado (com `title` no `<td>` para o id
  completo), nova coluna "Tamanho aprovado" derivada de
  `decision.sizing.notional` quando aprovada (nunca inventada).
- `apps/web/tests/manual-orders-types.test.ts`,
  `apps/web/tests/manual-orders-actions.test.ts`,
  `apps/web/tests/manual-order-labels.test.ts`,
  `apps/web/tests/use-manual-order-poll.test.ts`,
  `apps/web/tests/manual-order-form.test.tsx` — fixtures/asserções
  atualizadas para o caminho `order-requests`, `market_id`/`direction`
  obrigatórios e os slugs reais de `problem.type`.
- `.claude/state/notes-T3.72.md` — esta seção.

Arquivos do T3.72/b lidos e **não alterados** por não precisarem de mudança
(já batiam com o contrato final ou não referenciam caminho/campo nenhum):
`manual-order-form-schema.ts`, `manual-order-form.tsx`,
`manual-order-section.tsx`, `manual-order-decision-card.tsx`,
`manual-order-filed-status.tsx`, `manual-order-market-chip.tsx`,
`manual-order-market-field.tsx`, `manual-order-stop-field.tsx`,
`useManualOrderPoll.ts`, `manual-order-decision-card.test.tsx`,
`manual-order-section.test.tsx`, `manual-order-form-schema.test.ts`,
`tests/e2e/portfolio-manual-order.spec.ts`.

### `git status --porcelain` — todos os arquivos T3.72/T3.72b/T3.72c

```
 M apps/web/lib/format.ts
 M apps/web/tests/format.test.ts
?? .claude/state/notes-T3.72.md
?? apps/web/components/portfolio/manual-order-decision-card.tsx
?? apps/web/components/portfolio/manual-order-filed-status.tsx
?? apps/web/components/portfolio/manual-order-form.tsx
?? apps/web/components/portfolio/manual-order-labels.ts
?? apps/web/components/portfolio/manual-order-market-chip.tsx
?? apps/web/components/portfolio/manual-order-market-field.tsx
?? apps/web/components/portfolio/manual-order-section.tsx
?? apps/web/components/portfolio/manual-order-stop-field.tsx
?? apps/web/components/portfolio/manual-orders-table.tsx
?? apps/web/hooks/useManualOrderPoll.ts
?? apps/web/lib/api/manual-order-form-schema.ts
?? apps/web/lib/api/manual-orders-actions.ts
?? apps/web/lib/api/manual-orders-types.ts
?? apps/web/lib/api/manual-orders.ts
?? apps/web/tests/manual-order-decision-card.test.tsx
?? apps/web/tests/manual-order-form-schema.test.ts
?? apps/web/tests/manual-order-form.test.tsx
?? apps/web/tests/manual-order-labels.test.ts
?? apps/web/tests/manual-order-section.test.tsx
?? apps/web/tests/manual-orders-actions.test.ts
?? apps/web/tests/manual-orders-types.test.ts
?? apps/web/tests/use-manual-order-poll.test.ts
?? tests/e2e/portfolio-manual-order.spec.ts
```

Fora deste recorte (T3.72/b/c), a árvore também mostra `apps/web/app/(app)/
[orgSlug]/portfolio/page.tsx`, `portfolio-activity-tables.tsx`,
`portfolio-proposals-empty.tsx`, `lib/api/markets{-actions,}.ts`,
`lib/api/portfolio{-types,}.ts`, `hooks/useSpotMarketSearch.ts` modificados —
são do T3.72/b original (consumo/infra do formulário), não tocados nesta
rodada por não referenciarem caminho ou campo algum do contrato de
`order-requests`. `apps/api/**`, `docs/**`, `.claude/state/design/**`,
`.claude/state/tmp/**`, `test_isolation.py`/`test_rbac_matrix.py`/`app.py` e
tudo mais na árvore pertencem a outras tarefas (T3.68 e trabalho concorrente
de outros agentes) e não foram tocados aqui.

### Comandos e saídas reais (T3.72c, todos em `C:/dev/project-hunter`, foreground, `timeout 290`)

```
pnpm --filter @hunter/web exec vitest run tests/manual-orders-types.test.ts \
  tests/manual-orders-actions.test.ts tests/manual-order-labels.test.ts \
  tests/manual-order-form.test.tsx tests/manual-order-section.test.tsx \
  tests/manual-order-decision-card.test.tsx tests/use-manual-order-poll.test.ts \
  tests/manual-order-form-schema.test.ts
  → Test Files 8 passed (8) · Tests 57 passed (57)

npx turbo run typecheck --filter=@hunter/web
  → 1ª rodada: 1 erro (`manual-order-labels.ts(111,60)`: `orderRefusedMessage`
    recebia `string | undefined`, mas `Problem.detail` é `string | null | undefined`
    sob `exactOptionalPropertyTypes`) — corrigido a assinatura.
  → 2ª rodada: tsc --noEmit OK, 0 erros.

npx turbo run lint --filter=@hunter/web
  → 0 erros; só os 2 warnings pré-existentes (`tests/lab-page.test.tsx`,
    `tests/ws.test.ts`, arquivos > 350 linhas, não tocados nesta tarefa).

npx turbo run test --filter=@hunter/web
  → 121 arquivos, 1138 testes, todos verdes (87.9s).
```

### Resumo em português (≤ 10 linhas)

Reconciliado com o contrato final do T3.68: caminho virou `.../order-requests`
(`.../orders` já é outra coisa); `market_id`/`direction` passaram a
obrigatórios em `ManualOrderOut`; a lista deixou de chutar `market`/`stop`/
`requested_notional` (não existem) — a tabela agora mostra `market_id` e um
"Tamanho aprovado" derivado da decisão, nunca inventado; `outcome` ganhou o
schema real de `OrderOut` (com os enums de `hunter_core.domain.enums`); os
slugs de erro (`order-refused` 422 com motivo em `detail`,
`idempotency-key-conflict`/`wallet-not-open` 409, `insufficient-role` 403)
substituíram os quatro chutes que não existiam. Header `Idempotency-Key` e o
shape de `RiskDecision`/`Sizing` já estavam certos, sem mudança. `apps/api/**`
só foi lido. Typecheck/lint/testes do `@hunter/web` verdes (121 arquivos,
1138 testes); nenhum commit feito.
