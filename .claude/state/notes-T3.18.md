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

---

## T3.18b — dois blocos por versão (replay, replication), curva por coorte (D14/D15)

Base: `main` em `96cb101`. **Nada commitado.** Caminhos tocados (só os meus, `apps/api/**` e
`packages/shared-types/src/generated/api.d.ts`):
`apps/api/hunter_api/{repositories,services,schemas,routers}/lab_scoreboard.py` (editados),
`apps/api/hunter_api/{repositories,services,schemas}/lab_replication.py` (novos),
`apps/api/hunter_api/services/lab_scoreboard_replay.py` (novo), `apps/api/pyproject.toml`
(dependência nova `hunter-indicators`), `uv.lock` (efeito colateral obrigatório de `uv sync` — só
duas linhas, a entrada da dependência nova), `apps/api/tests/unit/test_lab_replication.py`,
`apps/api/tests/unit/test_lab_scoreboard_replay.py` (novos),
`apps/api/tests/integration/test_lab_scoreboard_replay_api.py`,
`apps/api/tests/integration/test_lab_replication_scoreboard_api.py`,
`apps/api/tests/integration/test_lab_curve_cohort_api.py` (novos),
`apps/api/tests/integration/test_lab_scoreboard_api.py` (uma linha: o monkeypatch de `rows_for` no
teste do 503 precisou aceitar kwargs extras depois que o método ganhou o parâmetro `cohort`),
`packages/shared-types/src/generated/api.d.ts` (regenerado via `pnpm gen:types`; `openapi.json` não
commitado — já está no `.gitignore`).

### 1. ScoreboardRowOut.replay (item 1, D14/D15)

Bloco novo e nulo quando não há evidência (`runs == 0` e zero linhas na coorte replay). Campos:
`runs` (contagem de `run_id` distintos em `replay_runs`), `decisions_simulated` (soma de
`bars_evaluated` — a métrica de massa do D14), `operations_closed` (avaliáveis pela mesma porta
`is_evaluable()` do bloco prospectivo, sobre as coortes replay — a métrica de evidência),
`expectancy_r`/`net_profit_rate`/`profit_factor` (as mesmas funções puras de
`lab_summary_metrics.py`, nunca reimplementadas), `distinct_days`/`distinct_markets` (mesma
definição "todo sinal emitido", não só os avaliáveis), `window_from`/`window_to` (min/max sobre os
runs) e o rótulo fixo "replay — não conta para o veredito".

`LabScoreboardRepository.rows_for` ganhou um parâmetro `cohort` opcional (default `prospective`,
compatível com o comportamento antigo) com um terceiro valor além de um rótulo exato:
`REPLAY_COHORT_WILDCARD = replay`, que vira `LIKE 'replay:%'` — a mesma função serve ao bloco
replay do placar e à curva por coorte (item 3). `replay_runs_summary` é consulta nova (COUNT
DISTINCT, SUM, MIN, MAX sobre `replay_runs`).

Prova pedida no brief (versão com replay positivo e prospectivo negativo — o veredito nunca troca):
`test_lab_scoreboard_replay_api.py::test_replay_positive_and_prospective_negative_never_swap_the_verdict`.
Exemplo real da resposta no relatório final.

### 2. ScoreboardRowOut.replication (item 2, D15) — adaptador, não reimplementação

`apps/api/hunter_api/repositories/lab_replication.py` carrega as três populações que
`hunter_indicators.replication.protocol.replication_report()` (pura, importada — `hunter-indicators`
virou dependência declarada de `hunter-api`) precisa, e nada mais: nenhuma conta estatística foi
copiada. Duas decisões deliberadas, ambas exigidas pelo D15 e ambas registradas no docstring do
módulo:

1. A população do pai é filtrada a cohort=prospective — `replication_stats.py` (do strategy-worker,
   fora do meu caminho) não filtra coorte nenhuma, o que era inofensivo antes do motor de replay
   existir sob o mesmo strategy_version_id do pai e deixaria de ser assim que uma versão puder ser
   replayada (T3.19b). Sem esse filtro, o bloco 1, o parent.verdict e os blocos 3/4 vazariam replay
   para dentro da régua — exatamente o que o D15(b) proíbe.
2. As irmãs são reconhecidas só pelas colunas da 0012 (replication_parent_id/replication_index),
   nunca pelo changelog — o banco de teste (e o real, hoje) já está pós-migração; o fallback de
   regex do worker existe para irmãs anteriores à 0012, que este endpoint não precisa cobrir.

D15(a), irmãs por replay: `sibling_population()` lê a coorte viva (replication:pai:k) E qualquer
replay:uuid gravado sob o strategy_version_id da própria irmã, e rotula
evidence: prospective|replay|mixed|null (null = zero resultados ainda) — carimbado no JSON de cada
braço depois que `replication_report()` devolve o relatório, nunca dentro da conta estatística em si.

Seed do bootstrap: lido de volta do changelog da primeira irmã (padrão `seed=(\d+)`, a mesma
gramática de `sibling_changelog()`); sem irmãs (status none/promissora), uso uma semente
determinística derivada dos 4 primeiros bytes do version_id — decisão minha, não do brief,
documentada em `resolve_seed()` e aqui como CONCERN.

Bloco nulo quando status == none (a versão nunca foi validada) — um cartão sem irmãs mas já
promissora aparece (com siblings.reason == sem_irmas).

Prova: três testes de integração (`test_lab_replication_scoreboard_api.py`) — nulo antes de validar,
promissora sem irmãs, uma irmã real com evidence: prospective — mais 8 testes de unidade
(`test_lab_replication.py`) cobrindo os quatro valores de evidence e o `resolve_seed`. Exemplo real
da resposta no relatório final.

### 3. GET /lab/shadow/curve?cohort=

Aceita prospective (default), replay (coringa — todas as coortes replay: da versão numa linha só)
ou uma coorte exata (`ShadowCohort.is_valid`: replay:uuid ou replication:pai:k); qualquer outra coisa
é 422 invalid-cohort. Mesma `rows_for` do item 1, então a curva e o bloco replay do placar nunca
podem discordar de população.

### 4. pnpm gen:types

`packages/shared-types/openapi.json` gerado e descartado (já ignorado pelo git);
`packages/shared-types/src/generated/api.d.ts` regenerado — diff puramente aditivo (259 linhas, 0
remoções): ReplayBlockOut, ReplicationBlockOut, SiblingArmOut e os campos novos em ScoreboardRowOut.

### 5. Concerns

1. **uv.lock mudou** (2 linhas, a entrada de hunter-indicators em hunter-api) — consequência
   inevitável de declarar a dependência nova; fora de apps/api/** no sentido estrito do caminho, mas
   é o arquivo de lock de todo o workspace uv e não tem como declarar uma dependência sem tocá-lo.
2. **infra/docker/Dockerfile.api** (não toquei, é infra/**) pode precisar copiar packages/indicators
   para a imagem da API agora que hunter-api depende de hunter-indicators — sinalizando para o
   devops-engineer/database-architect revisarem o build de container antes do deploy.
3. **Uma irmã não ganha linha própria no placar.** `versions_with_signals` (T3.18, inalterado por
   mim) só inclui versões com sinal sob coorte prospective; uma irmã emite sob replication:pai:k,
   nunca prospective, então ela nunca aparece como cartão — só dentro do bloco replication do pai
   (siblings.arms). Documentado no teste (`test_one_sibling_cohort_shows_up_with_its_evidence_label`);
   mudar `versions_with_signals` para incluir irmãs como cartões próprios é decisão de escopo maior,
   fora deste brief.
4. **resolve_seed()'s fallback determinístico** (sem irmãs registradas) não veio do brief — é meu,
   documentado no código e aqui.
5. **Um round de replicação com menos de 10 irmãs pode refutar cedo** por maioria_impossivel mesmo
   com zero negativas (visto no exemplo real capturado com 1 irmã: total - mature_negative <
   required já é verdade com total=1). É o comportamento correto da função pura do quant sobre uma
   população de teste deliberadamente pequena — não é bug, é a aritmética do protocolo.
6. **Blocos 3/4 (metades de mercado, bootstrap) do replication sempre rodam sobre a população
   prospective do pai**, nunca sobre uma população de replay do pai — o D15 (item 5) permite a
   segunda leitura ("se a população do pai for replay, os dois blocos herdam a mesma etiqueta"), mas
   isso não foi implementado aqui: escopo deliberadamente reduzido (o brief não pediu explicitamente
   essa variante, e ela exigiria decidir uma segunda fonte de dados e um segundo par de blocos no
   payload). Fica para quem quiser essa leitura extra.
7. **Item (c) do D15** ("o mesmo replay rode para o pai na mesma janela, para a comparação ser
   justa") é regra operacional de quem roda um replay, não algo que o endpoint verifica
   automaticamente — o placar expõe os dois blocos (replay do pai e replication.siblings das irmãs)
   lado a lado para essa comparação ser feita visualmente; não inventei uma checagem cruzada de
   janelas que o brief não pediu.
8. **infra/scripts/check_file_size.py reporta 1 arquivo fora do orçamento**
   (services/market-worker/hunter_market_worker/recovery_queries.py, 413 linhas) — não é meu, é
   services/** (fora do meu escopo), provavelmente trabalho em voo de outro agente.
9. **pyright do repo inteiro não rodei** (só apps/api, que está limpo: 0 erros); o repo tem histórico
   de erros em services/execution-worker/** de outros agentes (visto em notas de tarefas anteriores)
   que não são meus e não verifiquei se ainda estão lá.

---

## T3.18c — um contrato só para "avaliável", maturidade e PF (quant-engineer, 2026-09-08)

Fecha os MUST-FIX da revisão da Astra (`astra-review-lab-pronto-2026-09-08.md` §1) e os 13 achados
de `review-T3.18b-quant.md`. **Nada commitado.**

### O que mudou, item a item

1. **A CLI não é enganável por replay.** `replication_stats` passou a filtrar coorte: o pai é lido
   **só** em `prospective` (D15 b). Teste: prospectivo maduro e negativo (200 resultados, 40 dias,
   −0,4 R) + replay grande e positivo → `replicate()` recusa sem `--force-research`, nenhuma irmã é
   criada e `promising_at` continua nulo.
2. **Uma definição de "avaliável", e é a do placar.** A API carrega as linhas e aplica a **mesma**
   `lab_summary_metrics.is_evaluable` (terminal, `exit_ts <= as_of`, horizonte transcorrido); o
   worker aplica a tradução literal disso em SQL. `PopulationStats.days` conta **dias de saída**
   (`Outcome.exit_at`, campo novo e obrigatório) e `PopulationStats.of` só devolve PF nulo por
   `sem_perdas` — só-perdas é `0` com motivo nulo. `scoreboard_verdict` passou a aceitar o nulo por
   `sem_perdas`, como o placar sempre fez. Provado contra Postgres: `row.evaluable ==
   parent.evaluable`, `row.maturity.days == parent.days`, `row.verdict == parent.verdict` nos três
   casos (misto, sem perdas, sem ganhos).
   - **Efeito colateral declarado no placar:** `maturity.days` passou a contar dias de saída da
     população **avaliável** (com R conhecido). Antes contava também linhas que passavam no portão
     mas tinham `r_multiple` nulo (funding não apurável), o que fazia `maturity.days` medir uma
     população maior que `maturity.evaluable`.
3. **Evidência de irmã contada uma vez.** `sibling_population` deduplica por
   `(mercado, decision_at)` com precedência da coorte viva (`dedupe_outcomes`, pura, compartilhada
   com o worker). 25 resultados replayados sob dois `run_id` são 25. Cada braço publica
   `window_from`/`window_to` (recibos com `finished_at <= as_of`) e `duplicates_dropped`; o bloco
   publica `label = "siblings: replay sobre <janela>"` quando qualquer braço é `replay`/`mixed`.
4. **Rodada incompleta é imatura, não refutada.** `pool = max(n, expected)`; refuta só quando
   `pool − negativas_maduras < required`; `passed=None` com `rodada incompleta: {n} de 10` enquanto
   as dez não existirem. Testado com n = 1, 6, 7 (todas positivas → aguardando) e 10 (passa).
5. **Ordem total.** Toda consulta de outcome ordena por `(emitted_at, id)`. Teste com empates
   deliberados: duas leituras seguidas devolvem o mesmo `bootstrap` e o mesmo `parent`.
6. **Proveniência da semente.** `seed_source: registrada | derivada_do_id`, lida do evento
   `strategy_version_replicated` (campo `data->>'seed'`), não de um `seed=` dentro do `changelog`.
7. **Ponto no tempo.** `replay_runs_summary(version_id, as_of=)` só lê recibos com
   `finished_at <= as_of`; idem as janelas das irmãs.
8. **Custo.** Sem `promising_at` o bloco `replication` é `null` **sem** carregar população, irmãs ou
   rodar o bootstrap. `?include=replay,replication` (padrão: os dois) — **escolhi manter os dois por
   padrão**, para não mudar o contrato de quem já consome o placar; `include` desconhecido é 422.
9. **Massa honesta.** `replay.bars_evaluated` (barras varridas) e `replay.decisions_simulated`
   (`triggered + not_triggered + rejected`) são campos distintos, com `evaluations_by_state`
   publicado inteiro. Recibo sem o mapa → `decisions_simulated: null` +
   `decisions_simulated_reason: "sem_estados_registrados"`.
10. **Curva.** `CurveOut.cohort` ecoado; `cohort=replay` com corridas de janelas sobrepostas é
    **422** (`janelas_sobrepostas`) em vez de somar o mesmo R duas vezes. Janelas semiabertas
    adjacentes não são sobreposição.
11. **Testes reforçados**, 12. **`ensure_utc`** em todo timestamp de outcome, 13. **irmã promovida
    a viva mantém a evidência prospectiva** (a coorte viva de uma irmã é o braço **e**
    `prospective`).

### Item 13 do brief — a regra exata que o cartão do Lab tem de mostrar (para a T3.24b)

**`replication.status` pode repousar em replay; `verdict` nunca.**

- `verdict` e `maturity` do cartão vêm **só** de `prospective`. Nunca rotule nem misture: se a tela
  mostrar um selo de veredito, ele é sobre a faixa viva, ponto.
- `replication.status` (`promissora`/`replicando`/`real`/`refutada`) **pode** ter sido alcançado com
  evidência histórica nas irmãs. Sempre que `replication.siblings.label` for não nulo, a tela **tem
  de** exibir esse texto junto do status (ele já vem pronto:
  `"siblings: replay sobre 2026-08-08 → 2026-09-08"`). Um `status` de replicação sem esse rótulo,
  quando o rótulo existe, é apresentar replay como se fosse prospectivo.
- Por braço: `evidence` (`prospective|replay|mixed|null`) e, quando houver, `window_from`/
  `window_to`. Um braço `replay`/`mixed` nunca deve aparecer com a mesma aparência de um `prospective`.
- `replay.decisions_simulated` é **decisão**, não barra; `replay.bars_evaluated` é barra. Se a tela
  mostrar "500 mil/dia", o número comparável é `decisions_simulated` (e ele pode ser `null` com
  motivo — mostre o motivo, nunca 0).
- `parent.verdict` e `verdict` são o **mesmo** veredito por contrato; se algum dia divergirem na
  tela, é bug de dados e vale dizer isso em vez de escolher um.

### Arquivos

- `packages/indicators/hunter_indicators/replication/{stats,protocol,__init__}.py`
- `apps/api/hunter_api/repositories/{lab_replication,lab_replication_rows,lab_scoreboard}.py`
- `apps/api/hunter_api/services/{lab_replication,lab_scoreboard,lab_scoreboard_replay,lab_curve}.py`
- `apps/api/hunter_api/schemas/{lab_replication,lab_scoreboard,lab_curve}.py`
- `apps/api/hunter_api/routers/lab_scoreboard.py`
- `services/strategy-worker/hunter_strategy_worker/{replication_stats,replication}.py`
- testes: `packages/indicators/tests/**`, `apps/api/tests/unit/test_lab_{replication,curve,scoreboard_replay}.py`,
  `apps/api/tests/integration/test_lab_replication_{contract,siblings}_api.py` (novos),
  `apps/api/tests/integration/{lab_fixtures,test_lab_curve_cohort_api,test_lab_scoreboard_replay_api,test_lab_replication_scoreboard_api}.py`,
  `services/strategy-worker/tests/test_replicate_strategy_version.py`
- docs: `docs/plans/REPLICATION.md` (§1.5 √2, §3.2 pool, §3.5 contagem única, §5 "não são quatro
  repetições independentes", §6 contrato, §9 D14), `docs/plans/SHADOW-LAB.md` (seção "Placar")
- `packages/shared-types/{openapi.json,src/generated/api.d.ts}` (regenerados por `pnpm gen:types`)

### Ressalvas

- O brief cita "SHADOW-LAB.md §19"; o documento não tem §19. Tratei como o **item 9** da decisão
  conjunta + a seção "Placar (T3.18)", que é onde a régua de PF nulo mora, e é lá que a referência
  cruzada foi escrita.
- `include` continua com os dois blocos por padrão (decisão minha, declarada acima).
- O bloco 2 por replay é rotulado, mas a checagem cruzada da D15 (c) — "o mesmo replay rodou para o
  pai na mesma janela" — continua **operacional**, não verificada pelo endpoint.

## T3.18d — um veredito, uma função (backend-specialist, 2026-09-08)

Fecha o achado da revisão de T3.18c: `compute_verdict` (placar) e `scoreboard_verdict`/
`profit_factor_passes` (`hunter_indicators.replication.stats`) implementavam a mesma regra em dois
pacotes, concordando por vigilância de teste, não por construção.

### O que mudou

1. **Núcleo único extraído.** `stats.py` ganhou `verdict_from_values(*, mature, expectancy_r,
   profit_factor, no_losses) -> str`, sobre valores soltos (sem exigir um `PopulationStats`
   inteiro) — e um `_pf_passes_values` privado que `profit_factor_passes` e `verdict_from_values`
   compartilham. `scoreboard_verdict` passou a só extrair os campos de `PopulationStats` e chamar
   `verdict_from_values`; nenhuma comparação de veredito sobrevive fora dela.
2. **`compute_verdict` delega.** `lab_scoreboard_metrics.compute_verdict` agora chama
   `hunter_indicators.replication.verdict_from_values` e faz `cast(Verdict, result)` — a única
   conta que ainda faz sozinha é traduzir o vocabulário do motivo de PF nulo: a API diz
   `pf_reason == "no_losses"` (inglês, de `lab_summary_metrics.profit_factor`), o pacote puro diz
   `PF_NO_LOSSES == "sem_perdas"` (português); a fronteira agora é um único `bool` (`no_losses=`) em
   vez de duas strings que precisavam concordar por acidente. Saída **byte-idêntica**: os literais
   `VERDICT_INCONCLUSIVE/VALIDATED/REJECTED` do pacote puro já eram
   `"inconclusivo"/"validada"/"reprovada"`, os mesmos do `Literal["inconclusivo", "validada",
   "reprovada"]` da API.
3. **Teste-matriz nas bordas.** `test_lab_scoreboard_metrics.py::TestComputeVerdict` ganhou
   `test_borderline_matrix` (8 casos parametrizados): imaturo com números ótimos, PF nulo por
   `no_losses` com expectancy positiva/zero, PF exatamente 1 (reprova — desigualdade estrita), PF
   logo acima de 1 (valida), só perdas, e o caso positivo comum. Rodado **antes** do refactor
   (caracterização sobre a implementação antiga — todos os 26 testes do arquivo passavam) e depois
   (mesmo resultado), provando que a delegação não mudou uma vírgula do comportamento.
4. **Teste-trava do placar com R nulo após o portão.** A revisão de T3.18c apontava a falta de um
   teste que semeasse explicitamente uma linha terminal, horizonte vencido, `r_multiple IS NULL`
   (funding não apurável) e provasse que ela não conta nem para `evaluable` nem para
   `maturity.days`. `test_scoreboard_excludes_a_terminal_matured_row_with_null_r_multiple`
   (integração) semeia exatamente isso — uma linha avaliável (dia 2026-09-05) e uma terminal
   madura com `r_multiple=None`/`r_net_reason="funding_schedule_unknown"` num dia de saída
   diferente (2026-09-06) — e afirma `evaluable == 1`, `maturity.evaluable == 1`,
   `maturity.days == 1`, `emitted == 2`. **O teste já passava sem nenhuma mudança em
   `lab_scoreboard.py`**: `_evaluable_rows` já filtrava `r.r_multiple is not None` separado do
   portão `is_evaluable` — o comportamento estava certo, só faltava a trava. Isso é honestamente
   reportado como achado, não como bug corrigido.

### Arquivos

- `packages/indicators/hunter_indicators/replication/stats.py` — `verdict_from_values` (nova),
  `_pf_passes_values` (novo, privado), `profit_factor_passes` e `scoreboard_verdict` reescritas
  para delegar.
- `packages/indicators/hunter_indicators/replication/__init__.py` — exporta `verdict_from_values`.
- `apps/api/hunter_api/services/lab_scoreboard_metrics.py` — `compute_verdict` delega ao pacote
  puro.
- `apps/api/tests/unit/test_lab_scoreboard_metrics.py` — `TestComputeVerdict.test_borderline_matrix`
  (novo).
- `apps/api/tests/integration/test_lab_scoreboard_api.py` —
  `test_scoreboard_excludes_a_terminal_matured_row_with_null_r_multiple` (novo).

### Testes (saída real)

- `uv run pytest apps/api/tests/unit/test_lab_scoreboard_metrics.py -q` → **antes** do refactor: `18
  passed` (baseline) e `26 passed` (com a matriz nova, ainda sobre a implementação antiga); **depois**
  do refactor: `26 passed`.
- `uv run pytest apps/api/tests/integration/test_lab_scoreboard_api.py -q` → `16 passed in ~59-64s`
  (arquivo único por invocação, testcontainers).
- `uv run pytest apps/api/tests/integration/test_lab_replication_scoreboard_api.py -q` → `3 passed`
  (arquivo separado, garante que `scoreboard_verdict`/`stats.py` não regrediram para a replicação).
- `uv run pytest packages/indicators/tests/unit -q -k "replication or protocol"` → `56 passed, 922
  deselected`.
- `uv run ruff check` + `uv run ruff format --check` (após `ruff format` nos dois arquivos que
  precisaram de reindentação) → limpos nos arquivos tocados.
- `uv run pyright` nos arquivos de produção e de teste tocados → `0 errors, 0 warnings, 0
  informations`.
- `uv run python infra/scripts/check_file_size.py` → os dois arquivos acima do limite
  (`trendline_breakout_v1.py`, `seed_reference.py`) são de outra frente de trabalho, fora do escopo
  deste brief; nenhum arquivo tocado aqui estourou.

### Ressalvas

- Nenhuma pendência de comportamento: a delegação é byte-idêntica e o teste-trava do item 2 já
  passava contra o código existente — a lacuna era só de cobertura, como a revisão de T3.18c
  apontou.
