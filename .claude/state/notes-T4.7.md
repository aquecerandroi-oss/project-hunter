# T4.7 — Mesa do operador meme (`/meme/mesa` + rotas de operador)

Execução de 12/09/2026, ~04:40–05:20 BRT (07:40–08:20 UTC), papel full-stack. Sem commit.
Contrato: `.claude/state/contrato-T4.6-T4.7-mesa-meme.md` (Emendas T4.7 acrescentadas no fim).

## O que foi construído

**API** (`apps/api/hunter_api`): `routers/meme_desk.py` (`GET /desk`, `POST /proposals/{id}/approve|reject|cancel`,
`POST /proposals/manual`, `POST /bets/{id}/sell-now`; VIEWER+ lê, TRADER+ opera; `Idempotency-Key` obrigatório
— o mesmo `IdempotencyKey` de `routers/orders.py`); `schemas/meme_desk.py`; `services/meme_desk.py` (decisões),
`services/meme_desk_commands.py` (sell-now/cancel), `services/meme_desk_common.py` (recusas nomeadas, auditoria,
teto, replay), `services/meme_desk_out.py` (linha → payload, cotação manual com `quote_buy` a 1,75 %),
`services/meme_desk_idempotency.py` (Redis, 24 h, replay relê a entidade no Postgres);
`repositories/meme_desk.py` + `meme_desk_rows.py` + `meme_desk_summary.py` + `meme_desk_tables.py`.
A API escreve só `meme_proposals.{status,decision,decided_by,decided_at}` (UPDATE guardado por
`WHERE status='proposed'`), INSERT em `meme_proposals` (manual) e em `meme_operator_commands` — exatamente os
grants que a `0022_meme_lab` dá ao `hunter_app`; nunca `meme_paper_bets` (há teste de fonte que proíbe).

**Web** (`apps/web`): `app/(app)/[orgSlug]/meme/mesa/page.tsx` (Server Component, `AutoRefresh` 5 s),
`components/meme-desk/*` (faixa, propostas com contagem regressiva, folha de aprovação pré-preenchida com
`suggested`, comprar manual, abertas com "Vender agora" em um toque + aviso "vende na próxima fotografia, não
neste preço", fechadas hoje, decididas recentemente, rótulo PAPEL permanente, `labels.ts`, `meme-desk-format.ts`),
`lib/api/meme-desk{,-types,-actions,-form-schema}.ts`, item "Mesa" sob o Meme Radar (`nav-registry.ts` ganhou
`parent?`, `nav-links.tsx` indenta), `packages/shared-types/src/generated/api.d.ts` regenerado.

**Docs**: `docs/plans/T4-MEME-RADAR.md` §T4.7; contrato §Emendas (5 linhas). `docs/API.md` não existe.

## Linha do tempo com a T4.6 (paralela)

Construí contra o contrato com DDL próprio no testcontainer. Na primeira rodada o teste `xfail` contra
`alembic upgrade head` já encontrou a `0022_meme_lab` e revelou três diferenças reais: `meme_rule_sets` só
aceita `SELECT` (o `operator/1` é semeado pela migração com `max_sol_per_bet = 0.05`), `code_ref NOT NULL`,
e a FK de retorno `meme_proposals.bet_id → meme_paper_bets`. Copiei as quatro `CREATE TABLE` da
`infra/migrations/ddl/meme_lab.py` literalmente para o DDL do teste; os CHECKs reais pegaram um bug
legítimo — SQLAlchemy grava `None` em `JSONB` como `'null'` JSON, e `(applied_at IS NULL) = (result IS NULL)`
falhava — corrigido com `JSONB(none_as_null=True)` nas tabelas. O probe HTTP contra a migração real passa
(XPASS, marcador `xfail(strict=False)` mantido por pedido do brief). `GET /meme/lab` da T4.6 expõe
`sources.lab_last_tick_at`, exatamente o que a tela lê.

## Comandos e saída real

`timeout 200 uv run ruff check <13 arquivos meme_desk*>` → `All checks passed!`
`timeout 200 uv run ruff format --check <13 arquivos>` → `13 files already formatted`
`timeout 290 uv run pyright <routers/services/repositories/schemas meme_desk* + 2 testes>` → `0 errors, 0 warnings, 0 informations`
`timeout 290 uv run pytest apps/api/tests/unit/test_meme_desk_service.py -q` → `32 passed in 0.34s`
`timeout 290 uv run pytest apps/api/tests/unit -q -m unit` → `635 passed, 18 deselected, 1 warning in 70.45s`
`timeout 590 uv run pytest apps/api/tests/integration/test_meme_desk_repository.py -q -ra` →
`15 passed, 1 xpassed in 31.58s` (XPASS: `test_http_approve_against_the_real_migration` — app real sobre
Alembic head com `0022`: approve 200, replay 200 com o mesmo id, `GET /desk` 200 com rótulo PAPEL, linha
`audit_logs` `meme_desk.proposal.approved`).
`timeout 290 pnpm gen:types` → `packages/shared-types/openapi.json → .../api.d.ts [320ms]`
`cd apps/web && timeout 290 npx vitest run tests/meme-desk-*.test.ts tests/approve-sheet.test.tsx tests/nav-registry.test.ts tests/nav-links.test.tsx tests/org-layout.test.tsx`
→ `8 passed (8) / 70 passed (70)`; suíte inteira `npx vitest run` → `1302 passed (1302)`.
`timeout 590 npx turbo run typecheck lint --filter=@hunter/web` → `Tasks: 2 successful, 2 total`; lint
`0 errors, 2 warnings` (pré-existentes: `tests/lab-page.test.tsx`, `tests/ws.test.ts`, tamanho).
`timeout 120 uv run python infra/scripts/check_file_size.py` → `scanned 710 files; 1 over budget`
(`packages/exchange-adapters/hunter_exchanges/pumpfun/solana_codec.py`, 356 — de outra tarefa; nenhum meu).

## Concerns

- Nenhuma tela verificada no navegador: não há stack rodando e subir dev server viola as regras da tarefa;
  fica para a sessão Playwright logada (memória "in-app browser não abre localhost/Clerk").
- `test_http_approve_against_the_real_migration` está em XPASS: quando a T4.6 commitar a `0022`, o
  orquestrador pode remover o `xfail` para virar um teste duro.
- Idempotência em Redis (não em coluna): se o commit da transação falhar depois do `remember`, o replay
  não encontra a entidade e refaz — desenho registrado nas Emendas; um `IdempotencyStore` em Postgres
  exigiria coluna nova na `0022`.
- `packages/shared-types/src/generated/api.d.ts` é gerado e inclui também os schemas da T4.6 já registrados
  em `app.py`; regenerar de novo antes do commit se a T4.6 ainda mudar schemas.
