# T4.3 — Meme Radar API + web (pump.fun, só monitoramento)

Execução de 2026-09-12, papel frontend-specialist. Sem commit.

## Linha do tempo do contrato

O brief pedia para aguardar `.claude/state/notes-T4.2.md` §"contrato" (T4.2 escrevendo em
paralelo) por até ~30 min, com poll periódico, e construir contra `docs/plans/T4-MEME-RADAR.md`
§5 + os modelos do T4.1 caso não aparecesse.

1. Poll inicial (antes de codar): `notes-T4.2.md` não existia.
2. Construí schemas/repositório/serviço/router/testes contra uma reconstrução provisória
   (§5 do plano + `pumpfun/models.py`), documentando isso nos docstrings de cada arquivo.
3. Poll seguinte (já com testes passando): `notes-T4.2.md` **apareceu**, com a seção
   "contrato" completa (tabelas `meme_tokens`, `meme_curve_snapshots`, `meme_trades` sem
   produtor, `meme_features_1m`, `meme_ingest_gaps`, mais a view `meme_radar_features_v1`).
4. **Reescrevi schemas, tabelas Core, repositório, serviço e os dois arquivos de teste
   inteiros contra o contrato real** — nomes de coluna, nulidade e o vocabulário de motivo
   divergiam da reconstrução provisória em pontos importantes (ver abaixo). Nada do
   contrato provisório sobrou no código final; só a nota acima registra que ele existiu.

Divergências relevantes entre a reconstrução provisória e o contrato real (para quem ler o
histórico): `meme_tokens.complete` (boolean) não existe — só `completed_at`
(timestamptz nulo); `meme_features_1m` usa `end_time`/`features_version` (não
`minute`/`version`), `progress_reason` + `curve_reason` (dois motivos, não um só),
`unique_buyers`/`buy_sell_ratio`/`top10_share` (não `..._1m`/`..._holder_share_pct`),
`coverage` é fração numérica (não enum `full|partial|none`); `meme_ingest_gaps` usa
`stream` (não `source`), não tem `status`/`recovered_at`, tem `gap_end` obrigatório e
`generation`/`detail` (jsonb); o vocabulário de motivo é `no_trade_feed`,
`no_holders_reader`, `denominator_unknown`, `not_polled`, `rate_limited`,
`insufficient_coverage`, `unsupported_quote` (7 valores fixos, não os 4 que eu tinha
inventado). A leitura correta da lista é "filtrar a view pelo último `end_time` fechado",
não um `DISTINCT ON` por mint que eu tinha desenhado antes do contrato aparecer.

## Contrato congelado — shape JSON de cada endpoint (final, pós-contrato real)

Todo `Decimal` é string; toda ausência dependente de trade/holders é `null` + `*_reason`
(nunca `0`/`false`); `age_minutes` é `null` quando `created_at` é desconhecido (migração
chegou antes da criação, cenário do T4.1).

### `GET /api/v1/orgs/{org_id}/meme/overview`

Duas formas possíveis, nunca um número inventado — ver `schemas/meme.py`'s
`MemeOverviewOut`:

```json
{
  "label": "Meme Radar — só monitoramento, nunca execução (pump.fun)",
  "source": "meme_tokens",
  "observed_at": "2026-09-12T04:30:00Z",
  "coins_created_24h": 128,
  "coins_created_7d": 940,
  "coins_created_by_mode": null,
  "mayhem_active_coins": 12,
  "graduations_24h": { "count": 3, "tracked_tokens": 128, "reason": null }
}
```

Sem cobertura ainda (fallback ao `/mayhem/overview` gratuito, `pumpfun_rest_mayhem_overview`):
`coins_created_by_mode` vem preenchido com o corte `auto`/`manual` do próprio pump.fun
(mercado inteiro, não o radar), e `graduations_24h` é `{"count": null, "tracked_tokens": 0,
"reason": "insufficient_coverage"}` (não existe esse número na fonte externa).

### `GET /api/v1/orgs/{org_id}/meme/tokens?state=&sort=&limit=&cursor=`

Lista dirigida pelo "último minuto fechado" de `meme_features_1m` via
`meme_radar_features_v1` — um mint sem nenhuma linha de features não aparece na lista
(ausência honesta, não zero fabricado). `sort` ∈ `mcap|age|progress` (default `mcap`);
`state` ∈ `curve|completed|migrated` (default: todos).

```json
{
  "label": "Meme Radar — só monitoramento, nunca execução (pump.fun)",
  "items": [
    {
      "mint": "Fh42kAfy27CGoUA8CgFwpTGMubzndaAyTy2gghu5pump",
      "name": "bum bum",
      "symbol": "bam bum",
      "creator": "s9uu4shkYUQUmnWN2jkwgA2Nbg2Rmv7vUprtjy71xgP",
      "created_at": "2026-09-12T01:30:41Z",
      "age_minutes": 6,
      "state": "curve",
      "mcap_sol": "9.14",
      "curve_progress_pct": "0.00189",
      "mayhem_enabled": true,
      "mayhem_state": "active",
      "migrated_at": null,
      "snapshot_observed_at": "2026-09-12T01:35:41Z",
      "snapshot_source": "solana_rpc"
    }
  ],
  "next_cursor": "bWNhcHw5LjE0fEZoNDJr..."
}
```

### `GET /api/v1/orgs/{org_id}/meme/tokens/{mint}`

Token (identidade, cai de volta em `meme_tokens` puro se não houver linha de
features ainda) + série de `meme_curve_snapshots` (mais recente primeiro) + série de
`meme_features_1m` (mais recente primeiro), cada ponto com seu próprio motivo:

```json
{
  "label": "Meme Radar — só monitoramento, nunca execução (pump.fun)",
  "token": { "...": "mesmo shape da lista" },
  "snapshots": [
    {
      "observed_at": "2026-09-12T01:35:41Z",
      "source": "solana_rpc",
      "virtual_sol_reserves": "9.8",
      "virtual_token_reserves": "1071000000",
      "real_sol_reserves": "0.12",
      "real_token_reserves": "791100000",
      "complete": false,
      "mcap_sol": "9.14"
    }
  ],
  "features": [
    {
      "end_time": "2026-09-12T01:31:41Z",
      "age_minutes": 3,
      "curve_progress_pct": null,
      "progress_reason": "denominator_unknown",
      "mcap_sol": null,
      "curve_reason": "not_polled",
      "unique_buyers": null,
      "unique_buyers_reason": "no_trade_feed",
      "buy_sell_ratio": null,
      "buy_sell_ratio_reason": "no_trade_feed",
      "top10_share": null,
      "top10_share_reason": "no_holders_reader",
      "creator_sold": null,
      "creator_sold_reason": "no_holders_reader",
      "coverage": "0.5",
      "features_version": "meme_features_v1"
    }
  ]
}
```

### `GET /api/v1/orgs/{org_id}/meme/gaps?limit=&cursor=`

```json
{
  "label": "Meme Radar — só monitoramento, nunca execução (pump.fun)",
  "items": [
    {
      "id": "6f1c...-uuid",
      "stream": "pumpportal_ws",
      "mint": null,
      "gap_start": "2026-09-12T01:00:41Z",
      "gap_end": "2026-09-12T01:02:41Z",
      "detected_at": "2026-09-12T01:02:41Z",
      "reason": "reconnect_backoff",
      "generation": 3,
      "detail": { "attempts": 2 }
    }
  ],
  "next_cursor": null
}
```

## Comandos e saída real

### Backend

`timeout 290 uv run ruff check <arquivos meme>` → `All checks passed!`
`timeout 290 uv run ruff format <arquivos meme>` → sem diffs pendentes
`timeout 290 uv run pyright <arquivos meme>` → `0 errors, 0 warnings, 0 informations`

`timeout 290 uv run pytest apps/api/tests/unit/test_meme_cursor.py apps/api/tests/unit/test_meme_service.py apps/api/tests/integration/test_meme_repository.py -q`
→ `37 passed` (19 unitários + 18 de integração via testcontainer Postgres, schema real
aplicado por DDL literal neste próprio arquivo de teste — não via Alembic, para não
depender do timing da migração `0021` do T4.2; ver docstring do arquivo).

`timeout 290 uv run pytest apps/api/tests/unit -q -m unit` → `603 passed, 18 deselected`
(suíte inteira de `apps/api`, sem regressão pela alteração em `app.py`).

`timeout 290 uv run python infra/scripts/check_file_size.py` → `scanned 676 files; 1 over
budget` (só `packages/core/hunter_core/settings.py`, de outro agente; nenhum arquivo meu
no limite).

### Frontend

`timeout 290 pnpm gen:types` → regenerou `packages/shared-types/src/generated/api.d.ts`
com os schemas `Meme*`/`GraduationsOut`/`OverviewByModeOut`/`OverviewWindowCountOut`
(openapi.json é gitignored, intermediário).

`timeout 290 npx turbo run typecheck --filter=@hunter/web` → `tsc --noEmit` limpo.
`timeout 290 npx turbo run lint --filter=@hunter/web` → `0 errors` (2 warnings
pré-existentes, arquivos de outro trabalho: `tests/lab-page.test.tsx`, `tests/ws.test.ts`).
`timeout 290 npx turbo run test --filter=@hunter/web` → `135 passed (135) / 1254 tests
passed`.

## Arquivos — `git status --porcelain` (escopo desta tarefa)

```text
 M apps/api/hunter_api/app.py
 M apps/web/components/layout/nav-icons.ts
 M apps/web/lib/nav-registry.ts
 M apps/web/tests/nav-registry.test.ts
 M packages/shared-types/src/generated/api.d.ts
?? .claude/state/brief-T4.3-meme-radar-api-web.md
?? .claude/state/notes-T4.3.md
?? apps/api/hunter_api/repositories/meme.py
?? apps/api/hunter_api/repositories/meme_cursor.py
?? apps/api/hunter_api/repositories/meme_rows.py
?? apps/api/hunter_api/repositories/meme_tables.py
?? apps/api/hunter_api/routers/meme.py
?? apps/api/hunter_api/schemas/meme.py
?? apps/api/hunter_api/services/meme.py
?? apps/api/tests/integration/test_meme_repository.py
?? apps/api/tests/unit/test_meme_cursor.py
?? apps/api/tests/unit/test_meme_service.py
?? apps/web/app/(app)/[orgSlug]/meme/
?? apps/web/components/meme/
?? apps/web/lib/api/meme-actions.ts
?? apps/web/lib/api/meme-types.ts
?? apps/web/lib/api/meme.ts
?? apps/web/tests/meme-curve-chart.test.ts
?? apps/web/tests/meme-format.test.ts
?? apps/web/tests/meme-labels.test.ts
?? apps/web/tests/meme.test.ts
```

`apps/web/app/(app)/[orgSlug]/meme/` contém `page.tsx` e `[mint]/page.tsx`.
`apps/web/components/meme/` contém `labels.ts`, `meme-format.ts`, `meme-curve-chart.tsx`,
`meme-features-table.tsx`, `meme-token-row.tsx`, `meme-tokens-table.tsx`,
`meme-overview-strip.tsx`, `meme-filter-bar.tsx`.

`packages/shared-types/src/generated/api.d.ts` é gerado (`pnpm gen:types`, offline, sem
Postgres/Redis) — tecnicamente sob `packages/**`, mas é o artefato que toda tela nova
precisa para tipar `components["schemas"]`; não editado à mão, e é o mesmo arquivo que
qualquer outra tarefa de frontend já regenerou antes (rastreado no git, `openapi.json`
não). Sinalizado aqui para revisão explícita do orquestrador, já que o brief pede para não
tocar `packages/**`.

## Pendências / concerns

- **Playwright bloqueado localmente** — não há stack rodando (Postgres/Redis/API/web +
  Clerk real) e subir esse stack como processo de fundo violaria a regra "nunca shell em
  background" desta tarefa; checagem visual autenticada fica para quem tiver a sessão
  Playwright já logada (nota de memória "in-app browser não abre localhost/Clerk").
  Nenhuma tela foi verificada no navegador — reportando isso honestamente em vez de
  alegar uma checagem que não aconteceu.
- `meme_trades` não tem produtor nesta fatia (T4.2, T4.2b futuro) — nenhum endpoint da
  T4.3 lê essa tabela; as quatro colunas dependentes em `meme_features_1m`
  (`unique_buyers`, `buy_sell_ratio`, `top10_share`, `creator_sold`) chegam `null` com
  motivo em toda linha até então, e a tela mostra isso explicitamente (nunca 0/false).
- O teste de integração cria seu próprio schema via DDL literal (não via a migração real
  `0021` do T4.2, que eu não devo tocar) — se a migração final divergir do contrato
  publicado em `notes-T4.2.md`, alguém precisa reconciliar `repositories/meme_tables.py`
  e este teste contra ela.
- Nenhuma tabela `meme_features_1m`/`meme_curve_snapshots` real existe em produção ainda
  (o coletor do T4.2 não rodou) — em produção, `GET /meme/tokens` retorna lista vazia
  (`latest_end_time() is None`) e `GET /meme/overview` cai no passthrough do
  `frontend-api-v3.pump.fun`, ambos caminhos exercidos pelos testes unitários/integração.
