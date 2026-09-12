# Notas T4.17 — "Aprovar (REAL)" na mesa, com dupla confirmação, e o painel do executor real

Execução: 2026-09-12, ~17:2x–19:2x BRT. Papel: frontend specialist. Brief:
`.claude/state/brief-T4.17-aprovar-real-na-mesa.md`. Sem commit. Só `apps/web/**`
tocado (mais este arquivo). Nada real: nenhuma flag ligada, nenhuma chamada à API de
produção — tudo testado com mocks (Vitest/Testing Library).

## 1. Leitura

`.claude/state/notes-T4.14.md` §6/§7 (o que a mesa precisa renderizar),
`docs/ACTIVATION.md` §9b, `docs/RISK_ENGINE_MEME.md` §1/§3/§4/§9/§12 (as 25
verificações nomeadas, os dois portões + o teste pequeno), `apps/api/hunter_api/
routers/meme_live.py`, `schemas/meme_live.py`, `schemas/meme_desk.py`
(`ProposalMode`), `packages/shared-types/src/generated/api.d.ts` (não regenerado —
já tinha `MemeLiveOut`/`LiveExecutorOut`/`LiveOrderOut`/`LivePositionOut`/`SellNowOut`
e `ApproveProposalIn.mode`), `apps/web/components/meme-desk/*`, `apps/web/lib/api/
meme-desk*.ts`, `docs/DESIGN.md` (cores semânticas, vocabulário de tempo, "sem
backstage na copy"), `infra/migrations/ddl/meme_live.py` (os enums exatos de
status), `services/meme-executor/hunter_meme_executor/{heartbeat,kill_switch,
exits}.py` (os campos reais do heartbeat e do bloqueio de saída).

## 2. Arquivos novos

- `apps/web/lib/api/meme-live-types.ts` — aliases do OpenAPI (`MemeLive`,
  `LiveExecutor`, `LiveOrder`, `LivePosition`, `SellNowResult`), os guards de enum
  (`ExecutorStatus`/`LiveOrderStatus`/`LivePositionStatus`), `executorPanelState`
  (as três estados do brief: `ausente`/`desligado`/`ligado`) e `realActionsAvailable`
  (exige o flag do executor **e** o `api_live_enabled` da API).
- `apps/web/lib/api/meme-live.ts` — `"server-only"`, `getMemeLive(orgId)`.
- `apps/web/lib/api/meme-live-actions.ts` — `"use server"`, `sellNowLiveAction`
  (mesmo padrão de `Idempotency-Key`/schema de sanidade de `meme-desk-actions.ts`).
- `apps/web/components/meme-live/labels.ts` — rótulos exaustivos (status do
  executor, estado do kill switch + variante de badge, status de ordem/posição real,
  fonte da marca) e `realActionProblemMessage` (o vocabulário exato do brief:
  `meme_live_disabled`, `exceeds_max_sol_per_bet`, `rule_set_inactive`, `expired`,
  fallback `"recusa não prevista: <código>"`).
- `apps/web/components/meme-live/refusal-labels.ts` — as ~65 recusas nomeadas do
  motor (`RISK_ENGINE_MEME.md` §1/§4/§8/§9/§12), com fallback `"recusa: <código>"` e
  tratamento dos prefixos dinâmicos (`rpc_unreachable:`, `fill_decode_failed:`,
  `simulation_failed:`).
- `apps/web/components/meme-live/live-format.ts` — funções puras: `truncateAddress`,
  `policyLines` (os cinco tetos), `gatesLines` (vermelho / teste pequeno / verde,
  nunca inventa data), `killSwitchSourceLines` (as quatro fontes, `""` = "não
  configurada", nunca um estado inventado).
- `apps/web/components/meme-live/live-index.ts` — `buildLiveOutcomeIndex`: indexa
  `orders`/`positions` de `GET /meme/live` por `proposal_id`, para o deliverable 4.
- `apps/web/components/meme-live/real-confirm.tsx` — as peças compartilhadas da
  dupla confirmação REAL (`RealBadge`, `RealSummary`, `SizeMatchField`+`sizeMatches`,
  `WordMatchField`+`wordMatches`), usadas tanto pelo fluxo de aprovação quanto pelo
  "Vender agora (REAL)".
- `apps/web/components/meme-live/live-executor-panel.tsx` — o painel "Executor
  real" (deliverable 1), Server Component, os três estados.
- `apps/web/components/meme-live/live-positions-section.tsx` — "Posições reais
  abertas" + "Vender agora (REAL)" com o segundo passo digitando `VENDER`
  (deliverable 3).
- `apps/web/components/meme-live/real-shadow.tsx` — `RealShadowPanel` (deliverable
  4): quando `bet.mode === "live"`, mostra o desfecho real ao lado do de papel.
- `apps/web/components/meme-desk/approve-real-sheet.tsx` — "Aprovar (REAL)" na
  proposta: passo (a) os quatro parâmetros editáveis, passo (b) resumo + tetos +
  aviso de mainnet + campo de tamanho exato.
- Testes: `tests/meme-live-labels.test.ts`, `tests/meme-live.test.ts`,
  `tests/meme-live-actions.test.ts`, `tests/approve-real-sheet.test.tsx`,
  `tests/proposal-card.test.tsx`, `tests/live-positions-section.test.tsx`,
  `tests/live-executor-panel.test.tsx`, `tests/manual-buy-dialog.test.tsx`.

## 3. Arquivos modificados

- `apps/web/lib/api/meme-desk-form-schema.ts` — `toApproveBody`/`toManualBody`
  ganham um segundo parâmetro `mode` (default `"paper"`, preservando todo chamador
  existente); o fluxo REAL passa `"live"` explicitamente só depois da confirmação.
- `apps/web/components/meme-desk/proposal-card.tsx` — botão "Aprovar (REAL)"
  (vermelho, `variant="destructive"`), com seu próprio motivo de bloqueio
  (`realBlocked`): papel, prazo, e — só dele — "o executor real não está ligado".
- `apps/web/components/meme-desk/proposals-section.tsx` — estado do
  `ApproveRealSheet`, recebe `realAvailable`/`liveExecutor` do pai.
- `apps/web/components/meme-desk/manual-buy-dialog.tsx` — segundo botão
  "Registrar (REAL)" com o mesmo passo (a)/(b), gated por `liveAvailable`.
- `apps/web/components/meme-desk/open-bets-section.tsx` /
  `closed-today-section.tsx` — `RealShadowPanel` inserido em cada card cuja
  aposta é sombra de uma ordem real.
- `apps/web/app/(app)/[orgSlug]/meme/mesa/page.tsx` — carrega `GET /meme/live` em
  paralelo com a mesa (`Promise.all`, nunca bloqueia um pelo outro), monta o painel
  e as posições reais acima das propostas, calcula `realAvailable`/`liveOutcomes` e
  os repassa. Sem `Date.now()` em render (regra de pureza do React): a idade usa o
  `server_now` da própria resposta.

## 4. Decisões de desenho

1. **"Aprovar (REAL)" reabre os quatro parâmetros, editáveis**, em vez de só
   confirmar o que já estava sugerido — o brief pede "os quatro parâmetros" no
   passo (a); reusar o mesmo `deskParamsFormSchema`/`ParamsFields` do fluxo de
   papel evita duas fontes de validação.
2. **`meme-live` nunca importa de `meme-desk`** (unidirecional): `RealBadge`,
   `RealSummary`, os campos de confirmação e os rótulos vivem em `meme-live/` e
   `meme-desk/*` os importa de lá. Não há regra de ESLint que force isso (só
   `components/hooks` não podem importar `lib/server`), mas evita um ciclo de
   dependência entre os dois domínios.
3. **`blocked_exits`/`first_refusal`/`last_refusal` usam o vocabulário do motor**
   (`refusal-labels.ts`, ~65 nomes de `RISK_ENGINE_MEME.md`), separado do
   vocabulário do laço de papel (`meme-desk/labels.ts`) — são recusas de processos
   diferentes e nunca deveriam ser confundidas.
4. **`policyLines`/`gatesLines` nunca inventam um campo ausente**: um `dict[str,
   Any]` do heartbeat que não trouxer uma chave conhecida simplesmente não gera
   linha nenhuma para ela (nunca um "0" ou uma data fabricada).
5. **`sizeMatches` compara numericamente** (`compareDecimalStrings`, nunca
   `Number()`), então "0.020" confirma para um pedido de "0.02" — mas ainda exige
   dígitos de verdade (uma string vazia ou não numérica nunca casa).

## 5. Comandos e saídas

```
pnpm vitest run tests/meme                          -> 21 files, 264 passed
pnpm turbo typecheck lint --filter=@hunter/web       -> 2 tasks successful (0 errors,
                                                         2 warnings pré-existentes em
                                                         tests/lab-page.test.tsx e
                                                         tests/ws.test.ts — não meus)
pnpm --filter web build                              -> "Compiled successfully",
                                                         6/6 páginas estáticas geradas;
                                                         falha no passo de trace do
                                                         standalone com EPERM symlink
                                                         (limitação conhecida do
                                                         Windows, CLAUDE.md linha 46)
pnpm vitest run (suíte inteira)                      -> 158 files, 1529 passed
```

## 6. Concerns

1. **`bundled_share`/participação continuam `unavailable`** (achado antigo,
   `RISK_ENGINE_MEME.md` §4): mesmo com o painel pronto, o motor real recusa toda
   compra hoje por falta de dado do radar — o painel mostra isso honestamente via
   `last_refusal`/`first_refusal`, não é um defeito da tela.
2. **`GET /meme/live` falha independente da mesa de papel**: se cair, o painel
   mostra `SectionUnavailable` e "Aprovar (REAL)"/"Registrar (REAL)" ficam
   desabilitados (mensagem nomeada) — a mesa de papel continua funcionando.
3. **`policyLines`/`gatesLines` dependem do heartbeat estar no shape documentado
   em `hunter_meme_executor/heartbeat.py`** (2026-09-12); se os nomes dos campos
   mudarem lá, as linhas somem silenciosamente em vez de quebrar — coerente com a
   doutrina de "nunca inventar", mas vale um teste de contrato futuro se o heartbeat
   mudar.
4. **`RealShadowPanel` casa pelo `proposal_id` mais recente por ordem**; se um dia
   houver mais de uma tentativa de compra por proposta (retentativa após blockhash
   expirado, §9.4), o painel mostra só a mais nova — correto para o operador, mas
   não é um histórico completo de tentativas.
