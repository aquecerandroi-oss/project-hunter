# T3.46c — a página do Radar/Opportunities diz a verdade sobre o próprio estado

**Owner:** frontend-specialist · **Data:** 2026-09-08, 20:20 Brasília (23:20 UTC) · **Base:** `main` @ `2e39774`. **Nada foi commitado.**

---

## STATUS: `DONE_WITH_CONCERNS`

Entreguei o endpoint de cobertura (aditivo), a faixa "Estado do Radar" com tabela de
detectores e as três condições de reabertura, e os dois estados vazios honestos —
tudo com dados reais (heartbeat do scanner + contagens de banco), nada inventado.
Os concerns estão em três frentes: (1) o teste de integração do backend foi escrito
mas **não rodou** (sem slot de testcontainers, conforme a regra operacional do
brief); (2) `pnpm gen:types` regenerou `api.d.ts` e o diff inclui campos de OUTRA
tarefa em voo (T3.43b/T3.44, `RegimeComponentOut`, `RegimeOut.as_of/identity/components`,
`MarketStatusOut.exchanges_planned`) que já estavam na árvore Python mas ainda não
tinham sido regenerados; (3) toquei `components/opportunities/opportunities-empty.tsx`
e `components/opportunities/opportunities-table.tsx`, que estão fora do glob literal
do brief (`apps/web/components/radar/**`) mas são o único lugar onde o item 2 do
brief ("a empty Opportunities state para de implicar 'nada interessante agora'")
pode ser implementado.

---

## O QUE FOI ENTREGUE

### 1. Backend — `GET /api/v1/radar/coverage` (aditivo)

Novo endpoint no router existente `routers/radar.py` (não criei router novo — path
adicional `/coverage` sob o mesmo `APIRouter`, sem tocar `list_radar`). Lê:

- **Contagens reais via SQL** (`repositories/radar_coverage.py`, leitura global,
  sem RLS, mesma classe de tabela que `radar.py`/`anomalies.py` já leem):
  `markets_monitored` (`COUNT(*) FROM markets WHERE is_monitored`),
  `markets_with_anomaly` (`COUNT(DISTINCT market_id) FROM anomalies`),
  `max_score_ever` (`MAX(score) FROM opportunity_history` — a série completa, não
  `Opportunity.peak_score`, porque uma amostra de histórico mais alta que o pico do
  episódio ainda conta mesmo depois do episódio expirar), `first_anomaly_at`
  (`MIN(detected_at) FROM anomalies`), `anomaly_rows_by_type` (agrupado, janela de
  31 dias) e `baseline_gate_progress` (conta `feature_baselines` passando o gate
  `distinct_days`/`sample_size` da `opportunity_weights` **ativa** — `None` honesto
  quando não há versão ativa ou nenhuma baseline ainda, nunca um `0%` fabricado).
- **Heartbeat bruto do scanner** (`services/radar_coverage.py`, mesmo padrão que
  `routers/regime.py::_newest_regime_last_ts` já usa para campos que
  `WorkerHeartbeatOut` não carrega): escaneia `hb:scanner:*`, pega o hash **mais
  fresco** por `ts` (nunca mistura campos de duas instâncias), lê
  `baselines_usable`, `baselines_under_construction`, `baselines_state`
  (`bootstrap_pointer`) e `detectors_disarmed` (parseado de
  `"TIPO:motivo=contagem,..."` para `{AnomalyType: motivo}`, tipo desconhecido é
  descartado sem 500). Falha de Redis aqui é diagnóstico, não 503 — a página
  continua com os números do Postgres.
- `detectors`: **sempre os 12 tipos** de `AnomalyType`, nunca só os que produziram
  linha — um tipo com 0 linhas e sem motivo declarado tem que aparecer como
  "silencioso", não sumir por não ter nada a reportar.
- Nenhum cache: cada request lê Postgres+Redis direto, então "sem cache mais velho
  que 60 s" vale trivialmente (frescor = 0s). Decisão de simplicidade (CLAUDE.md
  §2) — a página só chama isto uma vez por carregamento de página, não no loop de
  reconciliação de 5 s.
- `pnpm gen:types` rodado; `RadarCoverageOut`/`RadarDetectorOut` aparecem em
  `packages/shared-types/src/generated/api.d.ts` e em
  `apps/web/lib/api/radar-coverage-types.ts`.

Arquivos novos: `apps/api/hunter_api/schemas/radar_coverage.py`,
`apps/api/hunter_api/repositories/radar_coverage.py`,
`apps/api/hunter_api/services/radar_coverage.py`.
Arquivo modificado (aditivo): `apps/api/hunter_api/routers/radar.py` (só o novo
`GET /coverage`; `list_radar` intocado).

### 2. Web — faixa "Estado do Radar"

`components/radar/radar-coverage-format.ts` (lógica pura, sem fetch/JSX — testável
sem DOM) constrói:

- **A frase de cabeçalho**, clausula por clausula, cada uma vinda de um campo real:
  `"Radar em construção — cobre {markets_with_anomaly} de {markets_monitored}
  mercados (bootstrap em ordem alfabética: {símbolo} {n}/{total}) · baselines
  prontas {pct} % · maior score já visto {score} (primeiro degrau 40) · nenhum
  mercado passou de NORMAL desde {data} Brasília"`. Cada clausula tem um fallback
  honesto quando o campo é `null` (`"sem heartbeat do scanner no momento"`,
  `"nenhum episódio pontuado ainda"`, `"nenhuma anomalia registrada ainda"`) — nunca
  um número inventado.
- **A tabela de 12 detectores**: `classifyDetector` decide `producing` (rows_31d>0,
  sempre vence) / `disarmed` (0 linhas + motivo declarado) / `silent` (0 linhas,
  **sem** motivo — o defeito que o T3.46 apontou em `ORDERBOOK_IMBALANCE`,
  `OPEN_INTEREST_SPIKE`, `TRADE_VELOCITY_SPIKE`). Motivo técnico traduzido para
  português via `disarmReasonLabel` (D19 — nunca `snake_case` cru na tela; um motivo
  desconhecido ainda aparece, com o código ao lado, nunca escondido).
- **As três condições de reabertura**, cada uma com valor real e barra de progresso:
  baselines passando o gate v2 (≥ 60 %), mercados com alguma anomalia (≥ 150),
  dias de histórico (≥ 14) — as três constantes vêm literalmente do veredito do
  T3.46 (`.claude/state/notes-T3.46.md`), citadas em comentário de código, nunca na
  copy visível ao usuário (D19).
- `WATCHING_THRESHOLD = 40` é citado de `docs/PIPELINE.md §5` (não existe endpoint
  para esse número; é uma constante de pipeline, não de organização).

`components/radar/radar-coverage-strip.tsx` renderiza isso (Server Component, sem
`"use client"` — sem interatividade) com `id="estado-do-radar"` como âncora. Usada
em `/radar` e `/opportunities` (ambas as páginas buscam a cobertura uma vez por
carregamento, em paralelo com a própria listagem, nunca bloqueando uma pela outra).

Números reais de referência usados nos testes/fixtures (T3.46, 2026-09-08):
25/217 mercados, baselines usable 9 029 / em construção 102 597 (~8 %), score
máximo já visto 38,33, 4 dos 12 detectores produzindo, 3 desarmados com motivo
declarado, 5 silenciosos sem motivo.

### 3. Estado vazio honesto (Radar e Opportunities)

`RadarEmpty`/`OpportunitiesEmpty` ganharam uma prop opcional `coverage` e um
`NeverLitNote` que — só quando `coverage` está presente e `max_score_ever` ainda
não bateu 40 — acrescenta: *"Isto não é 'nada acontecendo agora': desde que o Radar
existe, nenhum episódio passou de NORMAL (maior score já visto X, primeiro degrau
40)."* com link `#estado-do-radar` voltando para a faixa. A mensagem-base de cada
estado (com/sem filtro) foi mantida palavra por palavra — os testes existentes que
já afirmavam esse texto continuam passando sem alteração.

Isto se aplica sobretudo ao filtro rápido "Só HOT/ENTRY_CANDIDATE" de
`/opportunities` (`opportunities-filters.tsx`, que eu **não** toquei): hoje ele
sempre cai vazio, porque nenhum episódio jamais alcançou esses status — a nota
explica por quê, em vez de sugerir "ajuste os filtros".

### 4. Prova de tela (item 3 do brief)

**Não executei.** O brief pede `bash .claude/state/tmp/run-design-audit.sh -g
"screens 1440 dark"` **depois que o orquestrador reconstruir** os containers/app —
isso está fora do meu escopo desta tarefa (não paro/recrio containers locais, regra
operacional). Fica pendente para o orquestrador rodar após o rebuild e me devolver
(ou pedir ajuste) se algo ficar estranho visualmente.

---

## COMANDOS RODADOS (saída real)

### Web

```
pnpm --filter web lint
```
```
C:\dev\project-hunter\apps\web\tests\lab-page.test.tsx
  1:1  warning  File too large (377 lines | max 350).
C:\dev\project-hunter\apps\web\tests\ws.test.ts
  156:23  error  Forbidden non-null assertion  @typescript-eslint/no-non-null-assertion
  195:66  error  Forbidden non-null assertion  @typescript-eslint/no-non-null-assertion
✖ 3 problems (2 errors, 1 warning)
```
**Pré-existente, não é meu.** Não toquei `tests/ws.test.ts` nem `tests/lab-page.test.tsx`
(ambos pertencem a outra tarefa em voo — `ws.test.ts` está em `git status` como
modificado por outro agente). Rodei ESLint escopado só nos meus arquivos
(`pnpm exec eslint <lista exata>` dentro de `apps/web`) e voltou limpo, sem saída.

```
pnpm --filter @hunter/web run typecheck
```
```
$ tsc --noEmit
```
Limpo (0 erros). `pnpm typecheck` na raiz (via turbo) falha só em
`tests/e2e/design-audit.audit.ts`/`ws-disconnect-repro.audit.ts` — pré-existente,
não toquei `tests/e2e/**`.

```
pnpm --filter @hunter/web test
```
```
Test Files  109 passed (109)
     Tests  1020 passed (1020)
Duration  106.01s
```

Re-rodei os 4 arquivos que criei/editei isoladamente depois de um ajuste de tipos:
```
pnpm --filter @hunter/web exec vitest run tests/radar-coverage-format.test.ts tests/radar-coverage-strip.test.tsx tests/radar-table.test.tsx tests/opportunities-table.test.tsx
```
```
Test Files  4 passed (4)
     Tests  45 passed (45)
```

### API (Python)

```
uv run ruff check .
```
```
All checks passed!
```

```
uv run ruff format --check <meus arquivos>
```
Um arquivo (`services/radar_coverage.py`) precisou de reformatação (linha de
assinatura de função quebrada pelo formatter); rodei `uv run ruff format` nele e
o check voltou limpo.

```
uv run pyright apps/api
```
9 erros — todos em `apps/api/tests/integration/test_lab_signals_pagination_api.py`,
arquivo que não toquei (pré-existente). `uv run pyright <meus 4 arquivos novos +
router>` = `0 errors, 0 warnings, 0 informations`.

```
uv run python infra/scripts/check_file_size.py
```
```
error   380 > 350  apps/api/hunter_api/services/system_status.py
error   369 > 350  infra/scripts/seed_reference.py
error   360 > 350  infra/scripts/seed.py
scanned 577 files; 3 over budget, 0 grandfathered
```
Nenhum dos três é meu (não editei `system_status.py`, só importei uma função dele;
`seed.py`/`seed_reference.py` não toquei). Meus 4 arquivos: 57/105/162/104 linhas.

```
uv run pytest apps/api/tests/unit/test_radar_coverage_service.py -v
```
```
12 passed in 0.83s
```

```
uv run pytest -m unit apps/api
```
```
500 passed, 5 failed, 412 deselected
```
As 5 falhas são em `test_system_workers_status.py::test_build_market_status_*`
(`AttributeError: ... does not have the attribute 'MarketRepository'`) — em
`services/system_status.py`, que está em refatoração por outra tarefa em voo (já
aparecia modificado em `git status` antes de eu começar); não toquei nenhum dos
dois arquivos.

```
uv run pytest apps/api/tests/integration/test_radar_coverage_api.py --collect-only -q
```
```
5 tests collected in 1.72s
```
Confirma que os imports/assinaturas de modelo estão corretos; **não executei** os
5 testes de verdade (precisam de Postgres+Redis via testcontainers, e a regra
operacional deste brief proíbe abrir slot de testcontainers). Ficam marcados para
o orquestrador rodar no próximo slot livre.

```
pnpm gen:types
```
```
🚀 packages/shared-types/openapi.json → packages/shared-types/src/generated/api.d.ts [562ms]
```

---

## ARQUIVOS

**Criados:**
- `apps/api/hunter_api/schemas/radar_coverage.py`
- `apps/api/hunter_api/repositories/radar_coverage.py`
- `apps/api/hunter_api/services/radar_coverage.py`
- `apps/api/tests/unit/test_radar_coverage_service.py`
- `apps/api/tests/integration/test_radar_coverage_api.py` (escrito, não executado — ver concern 1)
- `apps/web/lib/api/radar-coverage-types.ts`
- `apps/web/lib/api/radar-coverage.ts`
- `apps/web/components/radar/radar-coverage-format.ts`
- `apps/web/components/radar/radar-coverage-strip.tsx`
- `apps/web/tests/fixtures/radar-coverage.ts`
- `apps/web/tests/radar-coverage-format.test.ts`
- `apps/web/tests/radar-coverage-strip.test.tsx`

**Modificados:**
- `apps/api/hunter_api/routers/radar.py` (aditivo: `GET /coverage`)
- `apps/web/app/(app)/[orgSlug]/radar/page.tsx` (busca `coverage`, renderiza a faixa)
- `apps/web/app/(app)/[orgSlug]/opportunities/page.tsx` (idem)
- `apps/web/components/radar/radar-empty.tsx` (prop `coverage` + nota honesta)
- `apps/web/components/radar/radar-table.tsx` (encaminha `coverage` para `RadarEmpty`)
- `apps/web/components/opportunities/opportunities-empty.tsx` (fora do glob literal — ver concern 3)
- `apps/web/components/opportunities/opportunities-table.tsx` (idem)
- `apps/web/tests/radar-table.test.tsx` (+1 teste)
- `apps/web/tests/opportunities-table.test.tsx` (+1 teste)
- `packages/shared-types/src/generated/api.d.ts` (regenerado — ver concern 2)

**Não toquei** (excluídos pelo brief, confirmado por leitura, não por suposição):
`hooks/useRealtime.ts`, `components/system/live-status.tsx`, topbar,
`components/dashboard/regime-tile.tsx`, `services/scanner-worker/**`.

---

## CONCERNS

1. **Teste de integração escrito, não executado.** `test_radar_coverage_api.py`
   cobre: 401 sem auth; leitura sem heartbeat (todo campo derivado de heartbeat
   honesto em `None`/`0`); leitura com heartbeat (baselines/bootstrap_pointer/
   detectors_disarmed corretos, `ORDERBOOK_IMBALANCE` sem linha e sem motivo
   continua `None`); `max_score_ever` vindo de `opportunity_history` (não de
   `Opportunity.peak_score`); `baseline_gate_v2_pct` com uma `OpportunityWeights`
   ativa + duas `FeatureBaseline` (uma passa o gate, uma não) = 50,00 %. Rodei
   `--collect-only` (importa e monta os 5 testes sem erro) mas não tenho slot de
   testcontainers nesta tarefa (regra operacional do brief). Um risco que não pude
   verificar: o teste do gate assume que nenhum outro teste do mesmo arquivo/sessão
   deixou linhas em `feature_baselines`/`opportunity_weights` (leitura **global**,
   sem RLS) — se o ambiente de testcontainers não isola por teste, esse teste
   específico pode precisar de um filtro adicional por `market_id`. Deixei isso
   fora do repositório de produção (a contagem real precisa ser global mesmo) e
   registro aqui para quem for rodar.

2. **`api.d.ts` regenerado inclui campos de outra tarefa em voo.** `pnpm gen:types`
   lê o estado *inteiro* da API no momento em que roda — o diff resultante tem
   `RadarCoverageOut`/`RadarDetectorOut` (meus) **e** `RegimeComponentOut`,
   `RegimeOut.as_of/identity/components`, `MarketStatusOut.exchanges_planned`
   (de T3.43b/T3.44, já presentes no Python da árvore compartilhada mas ainda não
   regenerados por aquela tarefa). Não há como comitar por pathspec só a minha
   metade de um único arquivo de texto gerado. Registrado para o orquestrador
   decidir: (a) comitar o arquivo inteiro sob qualquer uma das duas tarefas (ambas
   as adições são aditivas e corretas para o código-fonte atual), ou (b) pedir para
   a outra tarefa rodar `gen:types` de novo depois que a minha aterrissar, o que dá
   o mesmo resultado.

3. **Toquei `components/opportunities/opportunities-empty.tsx` e
   `-table.tsx`, fora do glob literal do brief** (`apps/web/components/radar/**`
   estava no escopo; `components/opportunities/**` não). Sem tocar esses dois
   arquivos, o item 2 do brief ("a empty Opportunities state para de implicar
   'nada interessante agora'") não tem onde ser implementado — o estado vazio de
   `/opportunities` vive lá, não em `components/radar/**`. Nenhum dos dois estava
   sendo tocado por outra tarefa em voo (confirmado por `git status` antes de eu
   começar). Mudança é estritamente aditiva: nova prop opcional `coverage`, texto-base
   existente intocado, testes antigos passam sem alteração.

4. **`baseline_gate_v2_pct` é uma leitura nova, sem precedente na página antes de
   hoje.** É a % de `feature_baselines` passando o gate versionado da
   `opportunity_weights` ativa — diferente da métrica de maturidade do heartbeat
   (`baselines_usable`/`baselines_under_construction`, ~8 %, que é sobre o cache do
   scanner, não sobre o gate v2). As duas aparecem juntas na tela (uma na frase de
   cabeçalho, outra na condição de reabertura) porque são fatos diferentes — achei
   importante não confundir as duas, mas é uma leitura a mais para o
   code-reviewer conferir contra `packages/indicators/hunter_indicators/baselines/
   revision.py::BaselineGate`.

5. **Prova de tela pendente** (item 3 do brief) — depende do orquestrador reconstruir
   o app; não posso parar/recriar containers locais nesta tarefa.

6. **Ambiente sem `preview_start`/navegador disponível para mim nesta sessão** —
   não pude fazer a checagem visual "browser-checked with real data" antes de
   reportar (memória "Frontend always polished"). Só typecheck/lint/testes
   automatizados; a checagem visual real fica com o design-audit do item 3.
