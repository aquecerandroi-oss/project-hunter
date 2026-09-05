# Kit de revisão — T1.5 · Web: páginas de mercado, Live Market Status, tabela de workers

**Owner:** `frontend-specialist` (Claude, sonnet) · **Estado:** em voo em 2026-09-05
**Files (do plano):** `apps/web/app/(app)/[orgSlug]/markets/**`, `apps/web/components/markets/**`, `components/system/live-status.tsx`, `components/system/workers-table.tsx`, `lib/api/{markets,system}.ts`, `lib/nav-registry.ts`, `hooks/**`, `tests/**`, `packages/shared-types/**`
**Depends-on:** T1.4 (contrato)
**Commit esperado:** `feat(web): markets pages, live market status, workers table`

---

## (a) Itens da decisão conjunta que se aplicam a T1.5
A decisão conjunta não abriu uma seção `T1.5` — a UI é o consumidor do contrato de T1.4/T1.2. Estes itens valem aqui **pelo lado do consumo** e são o que a revisão cobra (copiados literalmente de `.claude/state/dialogue-M1.md` → `## Astra (rodada 4)`):

- [ ] T1.4 — Expor `components` para ticker, book e mark com `ts`, `age_ms` e `quality`, além de idade própria de OI, funding e liquidações e tipo de funding; distinguir estimativa de funding realizado. `age_ms` deriva do timestamp da exchange do último evento aceito, nunca do flush; OI, funding e liquidações ficam fora da regra de 10 s.
  → **na UI:** a tela mostra a qualidade que a API devolveu; não recalcula regra própria, não inventa "agora" a partir do horário do navegador para dado que a API já datou.
- [ ] T1.4 — Calcular agregado sobre ticker, book e mark obrigatórios, nesta precedência: todos ausentes → `unavailable`; gap `open/failed` ou obrigatório ausente → `degraded`; senão qualquer obrigatório com idade > 10 s → `stale`; senão → `ok`. Preservar qualidades individuais e motivos, inclusive quando `degraded` prevalece; heartbeat global não substitui frescor por mercado.
  → **na UI:** badge por mercado reflete o agregado da API; heartbeat global do worker não pode ser usado como "este mercado está ok".
- [ ] T1.4 — ... API recalcula qualidade e fornece metadados para a UI envelhecer os dados sem mensagem nova. Expor snapshot top 20 conforme T1.2; limiares refinados de 1 s/3 s e painel detalhado ficam para M2.
  → **na UI:** o contador de idade envelhece localmente a partir do `ts` da API (é o papel do `useAgeTicker`); ao cruzar o limiar o badge muda **sem** precisar de novo evento.
- [ ] T1.2 — ... projetar `book.kind="snapshot"`, `book.depth=20` na API.
  → **na UI:** o book é apresentado como snapshot top 20 que se substitui inteiro, sem acumular níveis antigos na tela.

## (b) Critérios da linha da tarefa em `docs/plans/M1.md`
- [ ] `/[orgSlug]/markets`: tabela **real** com busca, ordenação, badge `stale`/`degraded`, estado `UNAVAILABLE` quando a API falha.
- [ ] `/[orgSlug]/markets/[exchange]/[symbol]`: candles com `lightweight-charts`, book top 20, últimos trades, funding/OI/mark — tudo via API + `useRealtime` em `rt:market:*`.
- [ ] Widget **Live Market Status** no dashboard e no topbar, alimentado por `rt:system`: mercados monitorados, WS `CONNECTED`/`RECONNECTING`/`DOWN`, último tick há N ms, gaps.
- [ ] Página System com tabela de workers real (`/api/v1/system/workers`) — substituindo o texto de placeholder de M0 (`apps/web/app/(app)/[orgSlug]/system/page.tsx:34`).
- [ ] `nav-registry`: `markets` passa de planejado a `available` (o teste `apps/web/tests/nav-registry.test.ts` acompanha).
- [ ] Tipos gerados a partir do OpenAPI de T1.4 (`packages/shared-types`), sem tipos escritos à mão para o mesmo contrato.

## (c) Regras do `CLAUDE.md` que mais pegam aqui
- [ ] **Sem dado falso:** nenhum gráfico de exemplo, nenhuma série gerada no cliente, nenhum número "plausível" enquanto carrega. Skeleton ou `UNAVAILABLE`, nunca placeholder numérico.
- [ ] **Sem botão inerte:** todo controle da tela faz algo hoje; o que é de M2+ não aparece ou aparece desabilitado dizendo qual milestone traz.
- [ ] **Estado vazio honesto:** "nenhum mercado monitorado" tem de dizer o porquê (worker parado / universo vazio), não uma frase genérica.
- [ ] **Sem estado local:** nada de `localStorage`/JSON como fonte de verdade; a API é a fonte.
- [ ] Precisão numérica: `Decimal` chega como **string** — formatar sem passar por `Number` onde a precisão importa (preço, quantidade, notional).
- [ ] Datas em UTC vindas da API; exibição pode ser local, mas o cálculo de idade usa o `ts` da API.
- [ ] Nenhuma chave, token ou variável de ambiente sensível no bundle do cliente.
- [ ] Sem `console.log` esquecido; lint e typecheck limpos.

## (d) Comandos de verificação exatos
```bash
export PATH="/c/Program Files/nodejs:/c/Users/evert/AppData/Roaming/npm:$PATH"
cd /c/dev/project-hunter
pnpm --filter @hunter/web lint
pnpm --filter @hunter/web typecheck
pnpm --filter @hunter/web test
pnpm --filter @hunter/web build
pnpm gen:types && git diff --stat -- packages/shared-types   # tipos batem com o OpenAPI de T1.4
```
> Nota de ambiente: `pnpm build` no Windows pode falhar com `EPERM ... symlink` no trace do Next (KNOWN ISSUES #0 de `docs/reports/M0.md`) — se acontecer, registrar como problema de ambiente, não da tarefa, e validar o build no container.

Fluxo manual exigido pela linha do plano (com worker e API rodando):
1. abrir `/ever/markets` → preços mudando ao vivo;
2. derrubar a rede / parar o worker → badge `stale` em ≤ 15 s;
3. parar a API → tela mostra `UNAVAILABLE`, não tela em branco nem número velho;
4. `/ever/system` → tabela de workers com o heartbeat real do `market`.

## (e) Revisores a despachar (em paralelo)
| Revisor | Escopo |
|---|---|
| `code-reviewer` | conformidade com a linha T1.5, dado falso, botão inerte, estados vazios, testes Vitest cobrindo badge/tabela/live-status, tamanho de componente |
| `security-reviewer` | não obrigatório em T1.5; dispensado salvo se o diff tocar auth, `middleware.ts`, headers, CORS ou introduzir variável `NEXT_PUBLIC_*` nova — nesse caso vira obrigatório |
| `database-architect` | não se aplica |
| `exchange-integration-specialist` | não se aplica |
| `risk-engine-guardian` | não se aplica no M1 |

## (f) Segunda opinião da Astra (obrigatória, depois do `code-reviewer`)
```bash
bash infra/scripts/astra.sh ask review-T1.5 "Review apps/web/app/(app)/[orgSlug]/markets/**, apps/web/components/markets/**, components/system/live-status.tsx, components/system/workers-table.tsx, lib/api/{markets,system}.ts, hooks/** e apps/web/tests/** against docs/plans/M1.md (linha T1.5) e os itens T1.4 da DECISÃO CONJUNTA em .claude/state/dialogue-M1.md, pelo lado do consumo. Confira: nenhum dado falso, gráfico de exemplo ou número plausível durante o carregamento; estado UNAVAILABLE real quando a API falha; badge stale/degraded vindo do agregado da API e não recalculado no cliente; idade envelhecendo localmente a partir do ts da API e mudando o badge sem novo evento; Decimal recebido como string e formatado sem perder precisão; book top 20 substituído inteiro sem acumular níveis; nenhum botão inerte; nenhuma variável sensível no bundle. Must-fix com cenário de falha, nice-to-have, concordâncias. Não modifique arquivos."
```

## (g) Commit esperado
```
feat(web): markets pages, live market status, workers table

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```
`git -c commit.gpgsign=false commit` · só `apps/web/**` (+ `packages/shared-types/**` e `pnpm-lock.yaml` se dependência nova, ex. `lightweight-charts`) · `git push origin main`.
