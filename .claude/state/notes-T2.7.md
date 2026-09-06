# Notes — T2.7 (Web: `/radar`, `/opportunities`, `/opportunities/[id]`, timeline de anomalias, tiles do dashboard)

Owner: frontend-specialist. Companion to `docs/reports/M2.md` (T2.8). Registra
decisões tomadas durante a implementação, divergências entre o brief e o
contrato real da API/indicadores, e pendências explícitas para T2.5/T2.8.

## Segunda opinião da Astra (antes de implementar)

Íntegra em `.claude/state/astra-review-T2.7-radar-web.md`
(`bash infra/scripts/astra.sh ask T2.7-radar-web "..."`). Veredito: concordou
com a hierarquia proposta (`/radar` = descoberta com filtros ricos,
`/opportunities` = índice compacto, o "porquê" só no detalhe), com
invalidação opaca de `rt:radar` e com a integração dos tiles no dashboard.
Quatro must-fix, todos reconciliados nesta implementação:

1. **Cobertura do Radar.** O contrato é uma linha por **episódio de
   oportunidade** (`opportunity_id`), não por mercado — um mercado
   monitorado sem episódio não aparece. `radar-empty.tsx` e o texto acima da
   tabela em `radar-table.tsx` dizem isso explicitamente ("uma linha por
   episódio de oportunidade, não por mercado"), em vez de prometer "todos os
   mercados".
2. **Agregação de anomalias não é "total de anomalias ativas".** O join que
   alimenta a coluna "Anomalias" do Radar (`radar/page.tsx::loadAnomaliesAggregate`)
   é um único `GET /api/v1/anomalies?status=active&window_hours=720` (30
   dias, o teto do endpoint) agrupado por `market_id` — uma anomalia
   `active + unknown` genuinamente mais antiga que isso não aparece.
   `anomaly-count-cell.tsx` documenta o limite no próprio componente e mostra
   "lista de anomalias truncada" quando a página de anomalias tem
   `next_cursor` não nulo. Não fiz uma leitura por linha (não escalaria para
   200 linhas).
3. **Conexão do WS não é prova de scanner vivo; `as_of` é hora da consulta.**
   `radar-table.tsx` mostra "Painel consultado \<as_of\>" (o `RadarPage.as_of`
   da última leitura) separado da coluna "Atualizado" de cada linha
   (`last_updated_at`, absoluto, `formatUtc`) — nunca um funde no outro. A
   reconciliação roda a cada 5s **independente do estado do WebSocket**
   (`RECONCILE_INTERVAL_MS`), porque nenhum publisher real de `rt:radar`
   existe ainda (ver seção própria abaixo).
4. **Barras de componente nunca desenham "indisponível" como zero
   observado.** `why-components.tsx`'s `ComponentBar` mostra uma barra
   tracejada + o motivo real (`component.reason`) quando `available=false`,
   nunca uma barra de 0%. O Early-Movement (`early_movement`, fora do
   orçamento de pesos, pode ser negativo) é mostrado à parte da lista
   ponderada de componentes, nunca somado a ela.

## Decomposição/explicação: adaptador defensivo, não um formato inventado

A Astra apontou que já existe uma implementação real da T2.4 no working tree
(`packages/indicators/hunter_indicators/opportunity/{model,explanation,envelope}.py`),
ainda não commitada quando a opinião foi pedida — então em vez de tratar
`decomposition`/`explanation`/`feature_snapshot` como JSON opaco eu li o
código-fonte real e construí `components/opportunities/decomposition-parse.ts`
contra o formato exato que `ScoreResult.decomposition()`/`explain()`/
`opportunity_envelope()` produzem hoje, com fallback honesto
(`{recognized: false, raw}` → "formato não reconhecido, ver JSON bruto") se o
scanner-worker (T2.5) acabar escrevendo algo diferente. Testado em
`tests/decomposition-parse.test.ts` contra fixtures que espelham
`opportunity/model.py:268`/`explanation.py:217`/`envelope.py:37` byte a byte
(mesmas chaves, mesma forma).

**Divergência real encontrada entre T2.4 e T2.6, registrada aqui para quem
fechar a T2.5/reconciliar os dois:** `opportunity_envelope()` (T2.4, o que
efetivamente vira `opportunities.feature_snapshot`) grava o vetor de features
em `feature_snapshot.vector.values["<key>"]` (`FeatureVector.as_wire()`), mas
`.claude/state/notes-T2.6.md` (backend, T2.6) documenta a suposição
`feature_snapshot.features.values["<key>"]["value"]` para o filtro de
volatilidade do Radar (`repositories/radar_common.py::feature_value_expr`).
São dois caminhos diferentes para a mesma informação. `decomposition-parse.ts::parseFeatureSnapshot`
tenta `vector.values` primeiro (o formato real do T2.4), depois
`features.values` (a suposição do T2.6) como fallback — funciona com
qualquer um dos dois, mas **o filtro de volatilidade do Radar (backend) e
este parser (frontend) podem estar lendo caminhos diferentes do mesmo dado**
até alguém do backend confirmar/unificar. Não é algo que este brief autoriza
a corrigir (fora de `apps/api`).

## `rt:radar`: nenhum publisher real existe ainda

`scanner-worker` (T2.5) é só um pacote esqueleto
(`services/scanner-worker/hunter_scanner_worker/__init__.py` vazio) — o canal
`rt:radar` já existe no gateway (`realtime/channels.py:28`), mas nada publica
nele. Decisão (endossada pela Astra): tratar qualquer mensagem em `rt:radar`
como **invalidação opaca** (recarrega a página 1 com os filtros atuais via
`loadRadarAction`), nunca como um merge de campos parciais de um formato
assumido — inventar um payload agora só para desmontar depois seria pior que
não usar o campo nenhum. Além disso, `radar-table.tsx` reconcilia a cada 5s
**mesmo com o WebSocket "conectado"**, porque conexão saudável não prova
scanner vivo (must-fix 3 acima). Pendência explícita: quando o T2.5 definir o
payload real de `rt:radar`, `useRadarPage.ts::reconcile` pode ganhar um merge
otimista por `opportunity_id` em vez de sempre substituir a página inteira.

## Coluna "Qualidade" do Radar — não é o `QualityBadge` de `/markets`

`RadarItemOut` não carrega idades por componente nem um `stale_after_ms` para
comparar — inventar um limiar teria sido exatamente o dado fabricado que
CLAUDE.md proíbe. `components/radar/quality-cell.tsx` mostra em vez disso o
que o contrato realmente tem: `confidence` (a métrica de qualidade de dado do
próprio score, PIPELINE.md §5) como badge colorido, e a idade de
`last_updated_at` (`useAgeTicker`, o mesmo padrão de `/markets`) sem afirmar
um veredito fresco/atrasado que a API não declarou.

## `/opportunities` vs `/radar` — hierarquia (Astra)

`/opportunities` é o índice compacto (`opportunities-table.tsx`), sem
assinatura em `rt:radar` (uma tabela viva já basta) e sem os filtros ricos
(anomaly_type/regime/volatilidade não existem em
`GET /api/v1/opportunities`, `.claude/state/notes-T2.6.md`). Tem um filtro
rápido, removível, "Só HOT / ENTRY_CANDIDATE" em vez de restringir a lista
permanentemente a esses status. `/radar` é a descoberta completa. Chips de
status/estágio/regime (`components/radar/status-chip.tsx`) são
compartilhados entre as duas telas.

## Painel "Por que estamos olhando isso?" — ordem das seções

`why-panel.tsx`: resumo (score/direção/confiança/explanation.resumo) →
componentes (barras de contribuição + Early-Movement à parte) →
anomalias+regime (contexto de mercado agora) → feature_snapshot (dado bruto
que alimentou o score) → histórico (trajetória) → rodapé técnico colapsado
(baseline_ids/versions). A ordem segue a pergunta que um trader faria: o que
o score diz, o que o compôs, o que está acontecendo agora, com que dado bruto,
como chegou aqui, e só se for preciso, a prova técnica exata.

O regime do painel (`is_stale`) não vem de `OpportunityDetailOut` (que só tem
`regime`/`regime_id`) — `why-context.tsx` casa `detail.regime_id` contra
`GET /api/v1/regime` (buscado uma vez por `opportunities/[id]/page.tsx`) para
achar a linha real com `is_stale`/`start_time`. Sem correspondência (regime
fechado/substituído desde então, ou `regime_id` nulo), mostra um estado
honesto em vez de tratar como fresco.

## Exceção divulgada à lista de arquivos: `dashboard/page.tsx`

O brief pede "Tiles do dashboard" (linha 12) mas a lista de arquivos
permitidos só cita `apps/web/components/dashboard/**` (tiles novos), não
`app/(app)/[orgSlug]/dashboard/page.tsx`. A Astra apontou a mesma
contradição e recomendou "edição cirúrgica... integração necessária da
entrega já pedida, não uma nova funcionalidade" — segui essa recomendação:
editei `dashboard/page.tsx` apenas para importar e renderizar os três tiles
novos (`AnomaliesTile`, `HotOpportunitiesTile`, `RegimeTile`) logo após a
seção "Mercados", com cada tile isolado no mesmo `Promise.all` que já isolava
`loadWorkspace`/`loadMembers`. Nenhuma outra linha do arquivo mudou. Registro
aqui para o orquestrador corrigir a lista de arquivos do brief e/ou aceitar a
exceção formalmente.

## Tiles do dashboard: padrão loader + apresentação

Os três tiles (`components/dashboard/{anomalies,hot-opportunities,regime}-tile.tsx`)
exportam uma função de carga assíncrona (`loadAnomaliesTile`, etc.) chamada e
`await`ada em `dashboard/page.tsx` (mesmo padrão de `loadWorkspace`/
`loadMembers` já existente), e um componente de apresentação **síncrono**
que recebe o resultado já resolvido. Comecei com componentes de servidor
assíncronos renderizados direto como `<AnomaliesTile />` (mais perto do
"Server Component" idiomático do App Router), mas isso quebrou
`dashboard-page.test.tsx` (React: "AnomaliesTile is an async Client
Component. Only Server Components can be async" — o harness de teste deste
repo renderiza a página já resolvida com `render()` puro, sem o runtime RSC
do Next, então um componente-filho assíncrono nunca resolve). O padrão
loader+apresentação é o que `dashboard/page.tsx` já usava antes deste brief
e o único testável neste harness.

## "sem verificação" vs "0 com as_of" — os dois zeros

Cada um dos três tiles e a coluna de anomalias do Radar distinguem
explicitamente "a checagem em si falhou" (`sem verificação`, texto
`text-fg-muted`, nunca um número) de "a checagem rodou e achou zero"
(`0` real, `tabular-nums`, com o `as_of`/verificado ao lado) — nunca a mesma
string para os dois casos. Testado em `tests/dashboard-radar-tiles.test.tsx`.

## Timeline de anomalias no detalhe do mercado

`components/anomalies/anomaly-timeline.tsx` busca via Server Action
(`lib/api/anomalies-actions.ts::loadAnomalyTimelineAction`, já que
`components/markets/**` não pode importar `@/lib/server/**`), 24h por padrão
(`DEFAULT_ANOMALY_WINDOW_HOURS`), mostrando tipo, severidade,
`AnomalyStatus` (`AnomalyStatusChip`) e `AnomalyEvaluationState`
(`EvaluationStateChip`) lado a lado, nunca fundidos — uma anomalia
`active + unknown` nunca lê como resolvida. Integrada em
`components/markets/market-detail-view.tsx` (arquivo permitido pelo brief),
não na página do mercado.

## Escopo aceito, não implementado

- **Merge otimista de `rt:radar` por campo** — pendente até T2.5 definir o
  payload real (ver seção própria acima).
- **Reconciliação do formato de `feature_snapshot`** entre T2.4 (`vector`) e
  a suposição do T2.6 (`features`) — fora de `apps/api`, registrado acima
  para o backend.
- **`/opportunities` não replica os filtros ricos do Radar** (regime,
  anomaly_type, volatilidade) porque o endpoint real não os aceita
  (`.claude/state/notes-T2.6.md`) — decisão de produto, não lacuna de
  implementação.
- **Verificação com dado real no navegador**: as tabelas `opportunities`/
  `anomalies`/`market_regimes` estão vazias localmente (T2.5 não existe
  ainda) — verificação feita via os 472 testes Vitest (fixtures espelhando o
  contrato real da T2.6/T2.4) e via `pnpm --filter @hunter/web build`
  (compilação + páginas estáticas geradas, o EPERM de trace no Windows é o
  conhecido). O check com dado real fica registrado como pendência para
  quando o T2.5 produzir linhas, por instrução explícita do próprio brief
  (linha 18: "o orquestrador faz o check final").

## Pós-review (code-reviewer): `ScoreCell` — `change === 0` tinha dois significados

O code-reviewer apontou que `change === 0` rotulado sempre como "novo
episódio" estava errado: a API computa
`change = score − COALESCE(último histórico, score)`
(`schemas/radar.py::RadarItemOut.change`), então um episódio maduro e
genuinamente estável (score idêntico à última amostra de histórico) também
produz `0` — indistinguível, na UI antiga, de um episódio sem nenhum
histórico ainda. `components/radar/score-cell.tsx` agora desambigua usando
`first_seen_at`/`last_updated_at` (ambos já presentes em `RadarItemOut`,
antes ignorados por este componente): sem histórico, os dois carimbos vêm do
mesmo insert e ficam a poucos segundos um do outro
(`isNewEpisode`, `NEW_EPISODE_THRESHOLD_MS = 5s`) → "novo episódio"; caso
contrário → "sem mudança desde a última leitura". `change` positivo continua
com sinal `+` explícito e cor semântica positiva; negativo, cor negativa;
`null`, "mudança indisponível" (nunca um zero fabricado).

Isso exigiu que `ScoreCell` passasse a exigir `firstSeenAt`/`lastUpdatedAt`
como props obrigatórias — o único call site de produção
(`components/radar/radar-row.tsx:65`) precisou de uma linha a mais
(`firstSeenAt={row.first_seen_at} lastUpdatedAt={row.last_updated_at}`) para
continuar compilando com dado real, embora o brief desta correção liste
apenas `score-cell.tsx`/`tests/**`/este arquivo de notas como escopo.
Registro a exceção aqui pelo mesmo motivo já documentado acima para
`dashboard/page.tsx`: sem essa linha, `pnpm --filter @hunter/web typecheck`
falha (`TS2739`, props obrigatórias faltando) e a produção nunca recebe os
carimbos reais — nenhuma outra linha de `radar-row.tsx` mudou.

Testes novos em `tests/score-cell.test.tsx` (5 casos, TDD: escritos e vistos
falhar antes da implementação, depois passando): `change` positivo (sinal
`+` explícito, `text-green`), negativo (sinal bruto preservado, `text-red`),
zero-novo-episódio (carimbos a 2s um do outro), zero-estável (carimbos a
2h30 um do outro) e `null` (motivo explícito, nunca um `"0"` inventado).
Mutação manual confirmada: trocar `changeValue > 0` por `>= 0` e remover o
`+` explícito derruba o primeiro teste com a mensagem exata esperada
("Unable to find an element with the text: +3.25") antes de reverter.

## Segunda opinião da Astra sobre o diff (antes de reportar)

Íntegra em `.claude/state/astra-review-T2.7-radar-web-diff.md`. Veredito
inicial: REQUEST_CHANGES, 9 must-fix (ela rodou `tsc --noEmit`/`eslint .`
sozinha e reproduziu os bugs em memória com React real). Reconciliação:

**Corrigidos nesta rodada:**

1. **HIGH — reconciliação quebrava a paginação do Radar.** `useRadarPage.ts`
   ganhou um `requestIdRef` monotônico: `reconcile`/`loadMore` tiram um
   "ticket" ao disparar, e só aplicam o resultado se seu ticket ainda for o
   mais recente quando resolvem — "o último disparo vence, o resto é
   descartado", nunca um merge. `reconcile` também re-cobre a profundidade já
   carregada (`Math.max(items.length, limit)`) em vez de sempre truncar para
   a página 1. Teste de regressão em `tests/radar-table.test.tsx`
   ("drops a load-more response superseded by a newer reconciliation").
2. **HIGH — filtros de `/opportunities` não atualizavam linhas montadas.**
   `opportunities-table.tsx` ganhou o mesmo `useEffect` de resincronização
   que `useRadarPage.ts` já tinha (`setItems(initialItems)` quando os props
   do servidor mudam) mais o mesmo `requestIdRef` para descartar um
   "carregar mais" cuja resposta chegue depois de um filtro novo.
3. **HIGH — coluna de anomalias sem `truncated` no "nenhuma", sem `as_of`
   próprio, fora da reconciliação.** `anomaly-count-cell.tsx` agora mostra o
   aviso de truncamento mesmo quando não há nenhuma anomalia para aquele
   mercado (o mercado pode simplesmente não estar coberto pela página
   truncada). `lib/api/anomalies-types.ts::buildAnomaliesAggregate`/
   `unavailableAnomaliesAggregate` centralizam a montagem do agregado
   (compartilhado entre `radar/page.tsx` e a nova Server Action
   `lib/api/anomalies-actions.ts::loadRadarAnomaliesAggregateAction`), e
   `useRadarPage.ts::reconcile` busca radar + agregado de anomalias em
   paralelo a cada 5s, com o `as_of` próprio do agregado mostrado separado do
   `as_of` do radar na legenda da tabela.
4. **MEDIUM — falha de reconciliação silenciosa.** `useRadarPage.ts` ganhou
   `reconcileError` (distinto de `loadError`, nunca apaga as linhas já
   carregadas), mostrado em `radar-table.tsx` como um aviso `warning`
   separado.
5. **MEDIUM — parser não fechava para formato incompatível e trocava `null`
   legítimo por `"0"`.** `decomposition-parse.ts`: `agreement` agora
   preserva `null` (`ScoreResult.agreement: Decimal | None`,
   `opportunity/model.py:256` — distinto de um empate real em `"0"`);
   `parseComponent` exige `weight`/`contribution`/`confidence` como string e
   retorna `null` se qualquer um faltar; `parseDecomposition` falha a
   decomposição INTEIRA (`recognized:false`) se qualquer componente falhar a
   parsear, em vez de silenciosamente omitir só aquele componente;
   `parseValuesMap` falha o vetor INTEIRO se qualquer entrada não for um
   objeto, em vez de pular a entrada e devolver uma tabela "reconhecida"
   vazia. Quatro testes de regressão em `tests/decomposition-parse.test.ts`.
6. **MEDIUM — fallback de JSON bruto prometido mas não entregue; frases da
   explicação além do resumo eram descartadas.** `why-footer.tsx` agora
   recebe `explanation`/`featureSnapshot` também e renderiza o JSON bruto de
   qualquer um dos três (`decomposition`/`explanation`/`feature_snapshot`)
   que não tenha sido reconhecido. `why-summary.tsx` lista todas as
   `explanation.frases` além do resumo (`frases[0]` duplica `resumo` por
   construção do `explain()` — `explanation.py:246`), então um aviso como
   `estagio_divergente` não desaparece mais.
7. **MEDIUM — cabeçalho "Atualizado" ordenava por outro timestamp.**
   `sort=age` usa `first_seen_at` (`repositories/radar.py::_sort_raw_expr`),
   não `last_updated_at`. Coluna renomeada para "Idade" e a célula agora
   mostra a idade de `first_seen_at` (`useAgeTicker`), alinhando
   rótulo/valor/chave de ordenação. `last_updated_at` continua visível na
   coluna "Qualidade" (`quality-cell.tsx`), que já o usava.
8. **MEDIUM — timeline de anomalias perdia truncamento e nunca se
   renovava.** `anomaly-timeline.tsx` agora guarda `next_cursor`/`as_of` da
   página e mostra o aviso de truncamento; um `setInterval` de 15s (pausado
   com a aba oculta, mesmo padrão de `AutoRefresh`) recarrega enquanto o
   mercado permanece aberto, então uma anomalia resolvida depois da
   abertura deixa de aparecer como ativa.

**Registrado, não corrigido (fora do escopo de `apps/web`):**

9. **HIGH — o backend lê o caminho errado do envelope real.**
   `opportunity_envelope()` (T2.4) grava `feature_snapshot.vector.values`,
   mas `repositories/radar_common.py::feature_value_expr` (T2.6) lê
   `feature_snapshot.features.values` para os filtros `volatility_min`/
   `volatility_max`/`sort=volume` do Radar. Assim que o scanner-worker (T2.5)
   persistir o envelope real, esses filtros excluem linhas com ATR válido e
   a ordenação por volume perde seus valores — Astra confirmou o cenário
   lendo `envelope.py:45` × `radar_common.py:117` × `radar.py:118,194`. Já
   estava registrado acima ("Divergência real encontrada entre T2.4 e T2.6")
   como pendência de reconciliação; a revisão do diff eleva a severidade
   para bloqueante da aceitação funcional — quem fechar a T2.5 precisa
   corrigir a expressão SQL (ou o produtor) antes que os filtros de
   volatilidade/volume do `/radar` funcionem com dado real. O adaptador
   defensivo do frontend (`parseFeatureSnapshot`) não corrige uma consulta
   SQL do backend.

**Nice-to-have aceitos:**

- Detalhe interno sobre o publisher `rt:radar` movido da legenda principal
  da tabela para um `title` (tooltip), mantendo a legenda visível curta.

**Nice-to-have não implementado, registrado:**

- Mostrar a data (não só a hora) no histórico de score quando amostras cruzam
  a meia-noite UTC (`why-history.tsx`, `formatUtc` só imprime hora) — a
  lista já está ordenada por `ts` decrescente, então a ambiguidade é rara em
  janelas curtas; registrado para quando o histórico cobrir dias completos.
