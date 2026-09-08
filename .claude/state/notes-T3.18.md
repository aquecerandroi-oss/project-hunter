# Notes — T3.18 (Lab scoreboard)

## API (backend-specialist, 2026-09-08)

**Entregue:** itens 1, 2, 6 (parte `apps/api`) e 7 do brief.

**Endpoints novos**, ambos globais/no-RLS como o resto do Shadow Lab (DATABASE.md §16 —
`agent_signals`/`signal_outcomes`/`strategy_versions` não têm `organization_id`; não há schema
change no escopo desta entrega para acrescentar um):

- `GET /api/v1/lab/shadow/scoreboard?as_of=` — uma linha por `strategy_version` que **já emitiu**
  pelo menos um sinal até `as_of` (não "toda versão ativada" — uma versão sem sinal na população
  congelada não aparece). Campos: `version` (id/key/version/purpose/status/activated_at/code_ref),
  `emitted`, `evaluable`, `pending`, `no_entry`, `censored`, `distinct_days`, `distinct_markets`,
  `hit_rate`/`net_profit_rate` (com `numerator`/`denominator`), `expectancy_r`, `profit_factor`,
  `sum_r`, `worst_streak`, `max_drawdown_r`, `maturity` (`{evaluable, days, threshold, mature}`),
  `verdict` (`inconclusivo|validada|reprovada`).
- `GET /api/v1/lab/shadow/curve?version_id=&as_of=` — série `[{ts, r, cum_r}]` de todo outcome
  **resolvido** (terminal, `r_multiple` não nulo), ordenada por `exit_ts`, capada em 2000 pontos
  (`truncated`). Deliberadamente **não** aplica o portão de maturação do horizonte
  (`is_evaluable()`): esse portão existe para não enviesar estatística agregada, não para recortar
  uma trajetória.

**Decisão registrada (path fora do padrão `/orgs/{org}/...` do brief):** o brief pedia
`/orgs/{org}/lab/{scoreboard,curve}`. Implementei em `/api/v1/lab/shadow/{scoreboard,curve}` —
mesmo prefixo dos outros três endpoints do Lab (`/versions`, `/summary`, `/signals`), porque
Shadow Lab é global por desenho documentado (DATABASE.md §16: "Nenhuma tabela nova é de tenant...
sem `organization_id` e sem RLS"). Colocar estes dois sob `/orgs/{org_id}/...` exigiria uma
migração fora do escopo desta entrega e contradiria a arquitetura vigente. Ver CONCERNS no relatório
final para o pedido de confirmação ao quant-engineer/database-architect/Everton.

**Reuso, não reinvenção:** toda a matemática de `hit_rate`, `net_profit_rate`, `expectancy_r`,
`profit_factor`, `sum_r` e o portão de maturação (`is_evaluable`) vêm de
`lab_summary_metrics.py`/`lab_summary.py` (S3), literalmente as mesmas funções que já reproduzem o
SQL do plantão (EXP-0001/EXP-0002). Só `worst_streak`, `max_drawdown_r` e o veredito mecânico são
novos (`lab_scoreboard_metrics.py`).

**Arquivos:**
- `apps/api/hunter_api/repositories/lab_scoreboard.py` (novo)
- `apps/api/hunter_api/services/lab_scoreboard_metrics.py` (novo — pure math)
- `apps/api/hunter_api/services/lab_scoreboard.py` (novo — assembly)
- `apps/api/hunter_api/services/lab_curve.py` (novo — assembly)
- `apps/api/hunter_api/schemas/lab_scoreboard.py` (novo)
- `apps/api/hunter_api/schemas/lab_curve.py` (novo)
- `apps/api/hunter_api/routers/lab_scoreboard.py` (novo — router próprio para não estourar o
  budget de 350 linhas de `routers/lab.py`)
- `apps/api/hunter_api/routers/lab.py` (modificado — `_resolve_as_of` virou `resolve_as_of`,
  público, para ser reusado pelo router novo; comportamento idêntico)
- `apps/api/hunter_api/app.py` (modificado — registra o router novo)
- `apps/api/tests/unit/test_lab_scoreboard_metrics.py` (novo — 18 casos)
- `apps/api/tests/integration/test_lab_scoreboard_api.py` (novo — 15 casos, testcontainers)
- `docs/plans/SHADOW-LAB.md` (modificado — seção "Placar (T3.18)")
- `packages/shared-types/src/generated/api.d.ts` (regenerado via `pnpm gen:types`;
  `packages/shared-types/openapi.json` não é rastreado — não foi commitado)

**Testes:** `uv run pytest apps/api/tests/unit -q -p no:randomly` → 406 passed. Novo arquivo unit
(18 casos) e integração (15 casos, um arquivo por invocação) verdes isoladamente. `ruff
check`/`ruff format --check` limpos em `apps/api`. `pyright` limpo nos arquivos tocados (rodar
`uv run pyright` sem escopo no repo inteiro aponta ~2348 erros pré-existentes em
`services/execution-worker/tests/**`, alheios a esta entrega — T3.15c está em voo nesses arquivos).
`check_file_size.py`: nenhum arquivo novo/tocado acima de 350 linhas (maior é
`repositories/lab_scoreboard.py` com 132).

**Achado, não corrigido (fora do escopo desta entrega):** `test_lab_api.py::
test_summary_counts_and_metrics_over_a_mixed_population` já falha em `main` antes desta entrega —
`decimal_plain()` (`schemas/lab_common.py`) remove zeros à direita ("0.5000" vira "0.5"), mas o
teste espera a string com zeros. Não toquei em `lab_common.py` nem em `test_lab_api.py`; meus testes
novos já usam a forma correta (sem zeros à direita).

## Web (frontend-specialist, 2026-09-08)

**Entregue:** itens 3, 4, 5 e 6 (parte `apps/web`) do brief. Base `main` em `2e0dc08`, consumindo os
dois endpoints e os tipos já entregues pelo backend-specialist (seção acima) sem tocar
`apps/api/**`, `packages/**` nem `components/lab/lab-version-card.tsx` (T3.15e em voo).

**Onde entrou:** o Placar ficou no **topo de `/lab`** (não uma aba nova) — o brief autoriza as duas
opções; uma aba nova exigiria uma segunda rota real (CLAUDE.md: sem aba inerte), enquanto o topo
mantém o Placar sempre visível, independente da aba "Sombra" existente (`LabTabs`, hoje com uma
única entrada) e dos filtros `window`/`cohort` abaixo, que não se aplicam a ele (o endpoint só aceita
`as_of`). Um único `as_of = new Date().toISOString()` é congelado por carregamento de página e
compartilhado entre a chamada do placar e **todas** as chamadas de curva (uma por versão, em
paralelo com `Promise.allSettled`) — garante que os cartões e as linhas do gráfico descrevem
exatamente a mesma população, nunca dois instantâneos a milissegundos de distância. Uma falha no
placar (`getLabScoreboard` rejeita) degrada para uma mensagem inline ("Placar indisponível: falha ao
carregar (motivo)"), sem derrubar a aba "Sombra" existente abaixo — mesma filosofia de
`loadMoneyRuler` (T3.17). Uma falha em **uma** curva individual (`Promise.allSettled`) não derruba as
demais: essa versão simplesmente não desenha linha (`failed: true`), nunca uma linha reta fabricada.

**Arquivos novos:**
- `apps/web/components/lab/lab-scoreboard.ts` — lógica pura: ordenação (ativa primeiro, depois
  `sum_r` desc, com `sum_r` nulo sempre por último no seu grupo de status), vocabulário do veredito
  (`inconclusiva`/`validada`/`reprovada` — feminino, concordando com "a versão"; o campo da API é
  `inconclusivo`, masculino, espelhando o literal Python), cor da linha da curva por veredito (mesma
  regra "mesma cor dos cartões" do item 4), texto/percentuais da barra de maturação, `formatSince`,
  o motivo honesto de "ainda sem resultado avaliável" (nomeia pendentes/sem entrada/censuradas **e**
  um resto não nomeado pela API — sinais `active` ou terminais ainda não maturados pelo portão de
  horizonte — em vez de deixá-lo desaparecer da soma), `buildScoreboardCardDisplay` (monta todas as
  strings/cores do cartão fora do JSX, lição do T3.17b sobre o teto de complexidade ciclomática do
  ESLint) e `buildCurveSeries` (uma série por linha do placar, na mesma ordem).
- `apps/web/components/lab/lab-verdict-badge.tsx` — o chip dominante, com a régua como `title`
  nativo (item 5: "sempre ao lado da régua").
- `apps/web/components/lab/lab-maturity-bar.tsx` — duas barrinhas independentes (resultados, dias) em
  `--color-info` ("informação neutra", DESIGN.md §1) — nunca dourado (§2: "dourado é raro").
- `apps/web/components/lab/lab-scoreboard-card.tsx` — um cartão: identidade/status/desde -> veredito +
  barra de maturação -> dinheiro pela régua do T3.17 (sempre visível, exceto quando `evaluable === 0`,
  caso em que vira o motivo honesto) -> unidades de pesquisa atrás do toggle "Detalhes de pesquisa"
  (mesmo padrão `aria-pressed` de `lab-signals-table.tsx`) -> a régua por extenso no rodapé.
- `apps/web/components/lab/lab-scoreboard-section.tsx` / `lab-scoreboard-empty.tsx` — grade de
  cartões (Server Component; só o toggle interno de cada cartão é client) e o estado vazio do placar
  inteiro ("nenhuma versão emitiu sinal ainda" — a API só retorna linha para versão que já emitiu, então
  um placar vazio é ausência operacional real, não um caso não implementado).
- `apps/web/components/lab/lab-curve-chart.tsx` — mesma abordagem de `components/portfolio/
  portfolio-equity-chart.tsx` (`lightweight-charts`, sem lib nova): uma `LineSeries` por versão com
  pontos resolvidos, cor pelo veredito, toggle USDT (pela régua)/R, legenda com o chip do veredito e
  os avisos honestos (`capado em 2.000 pontos`, `curva indisponível: falha ao carregar`, `sem
  resultado resolvido ainda`). "Hover mostra data e valor" (item 4) usa o crosshair/eixos nativos da
  biblioteca — o mesmo mecanismo (sem tooltip customizado) que `portfolio-equity-chart.tsx` já usa,
  não uma peça nova.
- `apps/web/components/lab/lab-curve-section.tsx` — wrapper server-side (estado vazio do placar
  inteiro + monta as séries na mesma ordem dos cartões).
- `apps/web/tests/lab-scoreboard.test.ts` (26 casos), `lab-scoreboard-card.test.tsx` (9),
  `lab-curve-chart.test.tsx` (6) — novos.

**Arquivos modificados:**
- `apps/web/lib/api/lab.ts` — `getLabScoreboard`/`getLabCurve` (mesmo padrão de query string dos
  demais).
- `apps/web/lib/api/lab-types.ts` — `ScoreboardOut`/`ScoreboardRowOut`/`CurveOut`/`CurvePointOut`
  etc. aliados de `@hunter/shared-types/api` (tipos já regenerados pelo backend), ao contrário do
  resto do arquivo (hand-written desde antes da regeneração) — migrar o resto é fora do escopo
  cirúrgico deste brief, anotado no comentário do arquivo.
- `apps/web/components/lab/lab-money.ts` — `scoreboardMoney`/`rToUsdt`: mesma regra `R * risco` de
  `moneyForRow`, aplicada ao `sum_r`/`expectancy_r` inteiros da versão (a API nunca calcula dinheiro,
  item 1 do brief — só R e contagens cruzam a rede).
- `apps/web/app/(app)/[orgSlug]/lab/page.tsx` — `loadScoreboard`/`loadCurves` + a seção "Placar" no
  topo; nada do corpo existente (`LabPageBody`, filtros, tabela de sinais) mudou de comportamento.
- `apps/web/tests/fixtures/lab.ts` — `exampleScoreboardRow`/`makeScoreboardRow`/`exampleCurve`.
- `apps/web/tests/lab-page.test.tsx` — mocka `lightweight-charts` (mesmo padrão de
  `portfolio-equity-chart.test.tsx`) e cobre: placar vazio, um cartão + uma chamada de curva por
  linha com `as_of` compartilhado, falha do placar isolada da aba "Sombra", falha de uma curva sem
  linha fabricada.

**Testes:** `pnpm --filter @hunter/web test` → 673 passed (78 arquivos, nenhuma regressão nos
existentes). `pnpm --filter web lint` → 0 erros/0 avisos. `pnpm --filter web typecheck` → limpo.

**Docs (item 7):** não dupliquei -- a seção "Placar (T3.18)" que o backend-specialist já escreveu em
`docs/plans/SHADOW-LAB.md` cobre as definições e a regra do veredito para os dois lados (API e web:
"o placar é a leitura corrente da mesma régua"); a tela usa exatamente essa régua e essas definições,
sem inventar nada novo.

**Verificação em navegador:** sem sessão Clerk real disponível nesta execução (mesma limitação
registrada em `notes-T3.17b.md` item 8) -- não consegui abrir `/ever/lab` de fato. Verificação feita:
673 testes de componente/página com fixtures no formato real do contrato (`ScoreboardRowOut`/
`CurveOut`), incluindo um DOM renderizado real capturado via Testing Library (colado no relatório
final para o `product-designer`/Everton revisar antes de qualquer merge).
