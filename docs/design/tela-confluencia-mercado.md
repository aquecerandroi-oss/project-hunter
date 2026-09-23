# Tela "Confluência de mercado" — gráfico + Lab + notícias + a nossa mesa numa linha do tempo

**Pedido:** Everton, 23/09/2026 12:0x BRT — "na moeda sem ser meme precisamos analisar via gráfico colocando linha do
tempo, notícias e tudo — lembra, junção de coisas".
**Escopo:** mercados **não-meme** (Binance), onde a mesa real `spot/1` opera (`docs/design/spot1-lab-solana.md`).
**Status:** desenho. Nenhuma linha de componente, endpoint ou migração foi escrita aqui.
**Insumos lidos:** `docs/DESIGN.md`; `market-detail-view.tsx`, `candles-chart.tsx`, `lab-trendline-overlay.tsx` +
`lib/charts/lab-trendline-series.ts`, `spot1-panel.tsx`, `anomaly-timeline.tsx`; modelos `spot_desk.py`,
`meme_events.py`, `agents.py`, `analysis.py`, `markets.py`; roteadores `markets`/`lab`/`anomalies`/`regime`/
`opportunities`. **Segunda opinião:** Astra, `.claude/state/astra-review-confluencia.md` (§9).

## 1. A pergunta e a ordem de leitura

**A pergunta:** *"o que estava acontecendo às 11:45 neste mercado — e o que nós fizemos a respeito?"*

A tela é um **cursor de tempo** com um painel **"Neste instante"**. O olho lê, nesta ordem:

1. **O cabeçalho do instante** — o horário selecionado (Brasília, ISO UTC no `title`), o preço daquele candle e a
   distância até agora ("há 2 h 13 min"). É o que responde "onde eu estou olhando".
2. **O gráfico** — candles de 15 m com as marcas do que aconteceu ali, e uma linha vertical dourada no cursor.
3. **As faixas sob o gráfico** — quatro pistas no mesmo eixo de tempo (Lab, Notícias, Nossa mesa, Regime e
   anomalias), que dão a densidade de uma só olhada: "às 11:45 tinha três coisas empilhadas".
4. **O painel "Neste instante"** — a leitura por extenso daquele ponto, onde mora a linha mais valiosa da tela (§4).

Tudo o mais (book, trades, derivativos) **fica na aba de detalhe que já existe** e não vem para cá.

## 2. Layout

A tela é uma **aba do detalhe do mercado** (`…/markets/[exchange]/[symbol]/confluencia`), não um item novo de
navegação — o contexto é sempre um par exchange+símbolo que já foi escolhido.

**1440 (desktop).** Duas colunas, `grid-cols-[minmax(0,1fr)_380px] gap-4`.
Coluna esquerda: cabeçalho do instante (48 px) → gráfico (360 px) → as quatro faixas (28 px cada, coladas ao eixo do
gráfico, sem espaço entre elas) → eixo de tempo compartilhado → controles da janela (§4).
Coluna direita: painel "Neste instante", `sticky top-4`, altura máxima `calc(100vh - 6rem)` com rolagem interna.
Abaixo das duas colunas, largura inteira: **a lista do período** — a mesma informação das faixas em tabela (13 px,
40/32 px de altura conforme `useDensity`), ordenada por instante decrescente, que é o que sobrevive à impressão e à
busca com Ctrl+F.

**768 (tablet).** Uma coluna. Gráfico (320 px) → faixas → **painel "Neste instante" logo abaixo das faixas**, não
`sticky` (um painel fixo num viewport curto come o gráfico) → lista do período. A coluna direita desaparece; nada
some.

**375 (mobile).** O gráfico encolhe para 220 px e **as quatro faixas colapsam numa só**, com o ícone de cada pista
lado a lado no mesmo instante. O painel "Neste instante" passa a ser o **conteúdo principal**, logo abaixo do
gráfico; a lista do período fica sob um `<details>` "Todos os acontecimentos do período (N)", fechado por padrão. O
cursor no mobile é **toque no gráfico ou nas faixas**; não há hover.

## 3. Os cinco overlays

Regra-mãe, herdada de `lab-trendline-overlay.tsx`: **um elemento sem dado nunca é desenhado — é nomeado numa nota
sob o gráfico.** Nunca desenhar "aproximadamente ali".

Regra de cobertura (corrige o que existe hoje): o índice da barra é a **barra que contém o instante** (piso do
`open_time`), nunca `nearestCandleIndex` com a tolerância de 1,5 × timeframe (22,5 min em 15 m) de
`lib/charts/lab-trendline-series.ts`. Instante fora dos candles carregados ⇒ **não desenha**, e a nota diz
"registrado às 12:15 · fora dos candles carregados" com a ação "carregar até aqui".

| # | Overlay | Linguagem visual | Nunca desenhar quando |
|---|---|---|---|
| 1 | **Sinal do Lab** | Preço de referência: linha `--color-info`, 1 px, sólida, do `emitted_at` ao `exit_ts` (ou ao fim da janela). Stop: faixa `--color-red` 1 px + preenchimento do mesmo token a 8 % entre referência e stop. Alvo: idem em `--color-green`. Direção: seta `arrowUp`/`arrowDown` no `emitted_at`, cor do token da direção. | O sinal não é do mercado da tela; `stop`/`target1` ausentes (desenha só a referência, e a nota diz qual faltou); o sinal está **selecionado = não** — só o sinal selecionado desenha geometria sobre o preço (§6). |
| 2 | **Desfecho do sinal** | Marcador circular no `exit_ts`, cor pelo resultado, o mapa que já existe: alvo `--color-green`, stop `--color-red`, invalidado `--color-warning`, expirado `--color-info`, em curso `--color-fg-muted`. Rótulo com o `r_multiple`. | `result = open` (nada terminou: não há ponto de saída); `exit_ts` fora da cobertura; **e nunca colorir o desfecho dentro da faixa "o que se sabia às 11:45"** — desfecho é conhecimento posterior (§4). |
| 3 | **Nossa entrada/saída real** | Marcador `--color-gold` (losango) no `entry_at` e no `exit_at`, com o R e o PnL no rótulo. **Sem nível de preço no eixo.** | **Sempre que se tentar pôr a execução no eixo de preço.** A `spot/1` compra e avalia stop sobre a **cotação Jupiter do nosso lote em SOL** (`spot_exit_rules.py`), não sobre o preço Binance do gráfico: um stop disparado por valorização do SOL, desenhado no preço da Binance, faria a execução parecer errada. A geometria Binance do §1 é do **sinal**; a execução é uma **marca no tempo**. Também não desenhar ordem `refused`/`failed` como se fosse execução — recusa vive na faixa e no painel, nunca no gráfico. |
| 4 | **Notícia / evento** | Linha vertical `--color-fg-subtle`, 1 px, tracejada, no `published_at` — atrás dos candles, nunca por cima. O pino de verdade mora na faixa "Notícias": confiança pela **forma** (preenchido = confirmado, contorno = reportado, pontilhado = rumor), nunca por cor — cor continua sendo só semântica. | Mais de 3 eventos na mesma barra: a linha vertical some e a faixa mostra "3 notícias" agrupadas (expansível). Evento sem `published_at` (só `observed_at`): não vai ao gráfico, vai à lista com "horário de publicação desconhecido". |
| 5 | **Regime e anomalia** | Anomalia (é por mercado): barra `--color-warning` na faixa, do `start` ao `end`, mais um filete de 2 px logo **acima** dos candles no mesmo intervalo — nunca uma lavagem de fundo sobre os candles. Regime: barra na faixa, rotulada **"Regime (global)"**, cor neutra `--color-border-strong` com o nome do regime escrito dentro. | **Nunca sombrear os candles deste mercado com o regime.** `market_regimes.scope` só existe como `global`/`btc` — sombrear este símbolo diria "o regime deste mercado", que não é um dado que temos. Anomalia com `status = unknown` na avaliação não vira "resolvida": usa `EvaluationStateChip`, que já sabe separar os dois. |

**Amendment ao contrato (DESIGN-7, a registrar em `docs/DESIGN.md` §5 quando a tela subir):** §2 diz "dourado nunca
nos candles". A regra nasceu contra o dourado como **cor de série** (dominaria a tela). Passa a admitir uma exceção
nomeada: **dourado marca, como marcador discreto num instante, o momento em que o produto agiu com dinheiro real.**
Nunca como cor de série, nunca como preenchimento. Motivo: verde/vermelho já estão tomados por alta/baixa e por
alvo/stop no mesmo gráfico; o vermelho de `RealBadge` colidiria com stop; o dourado é o único token que lê como "nós".

## 4. O painel "Neste instante"

Seleção: clique (desktop e mobile) fixa o cursor; hover pré-visualiza sem fixar. Teclado: `←`/`→` andam uma barra,
`Shift+←/→` andam dez, `Home`/`End` vão às pontas, `Esc` solta o cursor. O foco fica visível (anel `gold`). O painel
tem **três blocos, nesta ordem e nunca fundidos** — a separação é o que impede a tela de mentir:

**A. O que estava vigente às 11:45** (não é janela; é interseção de intervalo)
- **Preço e volume** da barra que contém o instante (`open/high/low/close`, volume com o ativo de cotação explícito).
- **Sinal ativo:** sinais com `emitted_at ≤ cursor < expires_at` e `tracking_state` ainda em curso. Mostra direção,
  referência, stop, alvo, versão da estratégia e quanto falta expirar. Sem sinal: *"Nenhum sinal do Lab vigente às
  11:45."*
- **A nossa posição:** `spot_positions` com `entry_at ≤ cursor` e (`exit_at IS NULL` ou `exit_at ≥ cursor`). Mostra
  entrada, ficha em SOL, R corrente na marca mais próxima anterior ao cursor, horizonte restante.
- **A linha mais valiosa da tela — olhamos e recusamos:** para cada sinal vigente, procura `spot_orders` por
  `signal_id`. Três respostas, **três textos diferentes**:
  - existe linha `refused` → *"Recusada: paridade acima do teto (3 %)"* — o **motivo nomeado**, do dicionário, com
    o JSON de `admission` atrás de um "detalhes" (checks, valores, teto, `sizing.binding_constraint`);
  - existe linha `admitted`/`confirmed` → a execução, com a assinatura truncada;
  - **não existe linha nenhuma** → *"Sem registro de admissão ou recusa para este sinal."* Nunca "não olhamos": há
    caminhos reais que não geram linha (pista refutada ou em cooldown, o sinal excluído na seleção por idade/versão/
    mercado desabilitado, uma falha transitória de cotação que deixa o sinal envelhecer). Inferir o motivo pela
    configuração de hoje seria inventar.
- **Regime (global)** e **anomalias vigentes** deste mercado.

**B. O que acabara de acontecer — ±N em torno do cursor.** **N = 15 minutos** por padrão. Motivo: a unidade de
leitura da tela é o candle de 15 m, então ±15 min é "esta barra e uma de cada lado" — o menor recorte que ainda
contém causa e efeito sem virar lista. Não é uma janela validada estatisticamente, é uma escolha de produto: os
180 s de `SPOT1_MAX_SIGNAL_AGE_S` governam a **elegibilidade da entrada** e as 4 h de horizonte governam a **duração
da posição**; nenhum dos dois é a janela de leitura humana. **±60 min** é o segundo passo, visível como um par de
botões ao lado do cabeçalho do instante. Selecionar um sinal ou uma operação oferece **"ver o ciclo inteiro"**, que
estica a busca até o desfecho daquele item — nunca estica a janela padrão.
Entram aqui: emissão de sinal, notícia, recusa, entrada, saída, início/fim de anomalia, troca de regime.

**C. Depois deste instante** — bloco separado, rotulado, recolhido por padrão. O desfecho do sinal, a saída da
posição e a notícia **publicada antes mas ingerida depois** do cursor vivem aqui. Motivo: "às 11:45" não pode
absorver conhecimento posterior em silêncio. Por isso `market_events` guarda **`published_at` e `ingested_at` separados** (§7a), e a tela mostra os dois quando divergem mais de um minuto.

## 5. Estados vazios e honestos

Cada um é um texto diferente; nenhum inventa um zero onde a resposta é "não medimos".

| Situação | Texto | Natureza |
|---|---|---|
| Sem candles no período | "Sem candles neste período para este mercado." + botão "ampliar para 24 h" | ausência operacional |
| Candles chegaram, gráfico falhou | "Gráfico indisponível. Os dados chegaram, mas o gráfico não pôde ser desenhado. Recarregue a página." | falha (já existe em `candles-chart.tsx`) |
| Nenhum sinal no período | "Nenhum sinal do Lab neste período." | ausência operacional |
| Leitura de sinais falhou | "Sinais indisponíveis: {motivo}." + "tentar de novo" | falha — **texto distinto do anterior** |
| Nenhuma notícia | "Nenhuma notícia registrada para este mercado neste período." + linha de cobertura: "fontes ligadas: plantão manual" | ausência operacional |
| Fonte de notícia ainda não ligada | "Cobertura de notícias deste mercado: só o registro manual do plantão." | cobertura, não vazio |
| Mercado não monitorado | "Este mercado não está no universo monitorado — não há candles nem sinais sendo gravados." + link para System → Workers | ausência operacional |
| Mercado fora do mapa da mesa | "A mesa spot/1 não opera este mercado (fora do mapa, ou desligado)." + o motivo do `spot_desk_markets.note` quando existe | ausência operacional |
| A mesa nunca olhou | "Sem registro de admissão ou recusa para este sinal." | **nunca** "não olhamos" (§4A) |
| Estado do instante não reconstruível | "Estado da mesa naquele instante não reconstruível — não há registro anterior ao cursor." | nunca copiar o estado de agora para o passado |

Regime nunca diz "desconhecido" como se fosse um regime: sem leitura válida antes do cursor, diz "sem leitura de
regime anterior a este instante".

## 6. O que esta tela **não** pode virar

- **Não é um TradingView.** Sem indicadores configuráveis, sem estudos, sem múltiplos painéis, sem comparar
  símbolos. Um timeframe padrão (15 m) e dois alternativos (1 m, 1 h), e só.
- **Não é um caderno de desenho.** Nenhuma ferramenta de traçar linhas à mão. Toda geometria na tela **veio de uma
  decisão gravada** e aponta para a linha que a gravou.
- **Não é um placar de confluência.** Nada de somar "3 sinais + 1 notícia = score 7". A confluência é lida pelo
  Everton; a tela alinha os fatos e não os pontua.
- **Só o item selecionado desenha sobre o preço.** Com tudo desenhado ao mesmo tempo o gráfico vira sopa.
- **Sem POST.** Nenhum botão move dinheiro, liga mesa ou pede venda. É leitura.

## 7. Briefs de implementação

### (a) API — `backend-specialist` + `database-architect` (migração) + `security-reviewer` (item 3 e 4)

1. **Candles por janela.** `GET /api/v1/markets/{exchange}/{symbol}/candles` hoje só tem `timeframe`, `limit`
   (≤ 1500) e o cursor `before`. Acrescentar `since` e `until` (`UtcDatetime`, opcionais, compatíveis para trás),
   validando `since < until` e mantendo o teto de `limit`. Arquivos: `apps/api/hunter_api/routers/markets.py:118`,
   `repositories/` correspondente. Continua devolvendo só `is_final = true`.
2. **Sinais por janela.** `GET /api/v1/lab/signals` já filtra `market` por símbolo exato
   (`repositories/lab_signals.py:154`), mas **não tem recorte de tempo**. Acrescentar `emitted_from`/`emitted_to`.
   Sem isso a tela pagina o histórico inteiro do mercado para achar 15 minutos.
3. **NOVO `GET /api/v1/markets/{exchange}/{symbol}/desk`** — a trilha da mesa `spot/1` neste símbolo. **Hoje
   `spot_orders`/`spot_positions`/`spot_desk_markets` não têm nenhum endpoint** (só o worker
   `services/meme-executor` os lê e escreve). Payload: `{ as_of, desk_market: {enabled, tier, kind, mint,
   round_trip_cost_pct_at_seed, note} | null, orders: [{id, signal_id, side, status, reason, admission, quote,
   tx_signature, received_at, admitted_at, settled_at}], positions: [{id, signal_id, entry_at, entry, params,
   sol_spent_lamports, initial_risk_sol, mark_sol, mark_at, high_water_sol, exit_at, exit, pnl_sol, r_multiple,
   status}] }`. Consultas: ordens por `market_symbol` + `received_at` dentro da janela; posições por **interseção de
   intervalo** (`entry_at <= until AND (exit_at IS NULL OR exit_at >= since)`) — é o que sustenta o bloco A do §4;
   uma consulta pontual esconderia a posição aberta desde as 10:00. **Atenção de segurança:** estas três tabelas são
   **globais, sem `organization_id` e sem RLS** (como as `meme_live_*`); o endpoint precisa da mesma porta que o
   roteador `meme_live` já usa, e o `security-reviewer` revisa antes do merge.
4. **NOVA tabela `market_events` + `GET /api/v1/markets/{exchange}/{symbol}/events`.**
   **Recomendação: tabela nova, não reusar `meme_events`.** Justificativa com cenário concreto: `meme_events.mint` é
   **FK para `meme_tokens.mint`**, e o job de casamento (`services/meme-worker/hunter_meme_worker/events_repo.py`,
   1×/min) varre por `observed_at` — **não filtra `mint IS NULL`** — e casa o evento com um `meme_token` pelo
   `symbol_hint`, depois ligando propostas (`link_proposals`). Uma notícia sobre Zcash gravada com
   `symbol_hint = 'ZEC'` encontraria uma meme homônima criada na janela e passaria a contextualizar a proposta dessa
   meme. Um `kind` novo + índice parcial **não resolve**: índice não muda o `SELECT` do matcher, e seria preciso
   alterar os predicados de todos os consumidores. Colunas: `id`, `market_id` (FK `markets.id`, NULL enquanto o par
   não existir), `exchange`, `symbol` (NOT NULL), `source` (`baha|manual|plantao|exchange_notice`), `kind`
   (`listing|delisting|upgrade|incident|macro|company|narrative`), `title` (NOT NULL), `url`, `published_at`,
   `observed_at` (NOT NULL), `ingested_at` (default `now()`), `confidence` (`confirmed|reported|rumor`), `notes`
   JSONB, `recorded_by` (NOT NULL). Global, sem `organization_id`, como `meme_events`. Índices: `(symbol,
   published_at DESC)`; único parcial `(source, url) WHERE url IS NOT NULL` para o registro ser idempotente na
   reexecução. Check constraints no espelho de `meme_events.py` (rótulos conhecidos, título não vazio).
   **Não fazer a notícia depender do mapa executável da `spot/1`** — notícia existe para qualquer mercado.
5. **Regime e anomalias:** nenhum endpoint novo. `GET /api/v1/regime/history?scope=global` já existe e é
   **global/BTC, nunca por mercado** — a tela rotula "Regime (global)" e pronto;
   `GET /api/v1/anomalies?market_id=&window_hours=` já filtra por mercado.
7. **Fora do v1, declarado:** `opportunities` não tem filtro por `market_id` nem por tempo
   (`routers/opportunities.py`), e o sinal do Lab já é o artefato honesto a jusante. Fica fora, nomeado na spec, e
   não vira um card vazio na tela.

### (b) Web — `frontend-specialist`

**Rota nova:** `apps/web/app/(app)/[orgSlug]/markets/[exchange]/[symbol]/confluencia/page.tsx` (Server Component:
busca candles, sinais, desk, eventos, anomalias e regime em `Promise.all` com **um `try`/`catch` por fonte**, do
jeito que `page.tsx` do detalhe já isola candles — uma fonte que cai degrada só a sua faixa).
**Criar** em `apps/web/components/confluence/`:
`confluence-view.tsx` (cliente, dono do cursor e da janela) · `confluence-chart.tsx` (candles + os 5 overlays) ·
`confluence-lanes.tsx` (as 4 faixas, amarradas ao eixo do gráfico por `timeScale().timeToCoordinate()` +
`subscribeVisibleTimeRangeChange`) · `confluence-instant-panel.tsx` (os três blocos do §4) ·
`confluence-event-list.tsx` (a lista do período) · `confluence-window.ts` (puro: janela ±N e a interseção de
intervalo do bloco A) · `labels.ts` (dicionário de `status` de ordem, motivo de recusa, `kind` e `confidence` de
evento — regra "sem enum cru na tela").
**Criar** `apps/web/lib/charts/confluence-series.ts` com `barIndexContaining(times, iso)` — **piso na barra que
contém o instante, nunca o `nearestCandleIndex` com tolerância de 1,5 × timeframe** de `lab-trendline-series.ts`.
**Reusar sem alterar:** `lib/charts/css-var.ts`, `lib/charts/series-data.ts`, `lib/time.ts`
(`formatBrasiliaTick`/`formatBrasiliaWithUtcTooltip`), `components/time/brasilia-instant.tsx`,
`lab-result-badge.tsx`, `lab-format.ts`'s `EXIT_REASON_LABEL`, `meme-live/refusal-labels.ts`'s
`executorRefusalLabel`, `anomalies/anomaly-status-chip.tsx` e `evaluation-state-chip.tsx`, `ui/badge.tsx`.
**Modificar:** só `market-detail-view.tsx`, para ganhar o link da aba. `candles-chart.tsx` **não** é alterado — a
tela nova tem o seu próprio gráfico e a regra é não mexer no que já funciona.

**Casos de Vitest que importam:**
1. `confluence-window`: posição aberta às 10:00 e ainda aberta às 11:45 **aparece** no bloco A com janela ±15 min;
   a mesma posição depois do `exit_at` **não** aparece.
2. `barIndexContaining`: instante 20 min depois do último candle carregado devolve `null` (não a última barra) e
   produz a nota "fora dos candles carregados".
3. Sinal com `spot_orders.status = 'refused'` renderiza o motivo nomeado; sinal **sem nenhuma linha** renderiza
   "Sem registro de admissão ou recusa para este sinal" — e nunca "não olhamos".
4. Zero eventos com resposta 200 ⇒ "Nenhuma notícia registrada…"; erro 5xx ⇒ "Notícias indisponíveis: …". Duas
   mensagens distintas, nunca a mesma.
5. Teste de completude de `labels.ts`: falha quando um membro novo de `SPOT_ORDER_STATUSES`, de `kind` ou de
   `confidence` não tem rótulo em português.
6. A saída real **não** gera nenhum elemento no eixo de preço (asserção: nenhuma série de preço criada a partir de
   `exit`/`pnl_sol`), só um marcador no tempo.
7. O rótulo do regime contém "global" — um teste que quebra se alguém escrever "regime deste mercado".
8. Notícia com `published_at` anterior e `ingested_at` posterior ao cursor cai no bloco C ("depois deste instante"),
   não no bloco A.
9. Contraste: os pares novos (marcador dourado sobre `bg-elevated`, pino de notícia sobre a faixa) entram em
   `apps/web/tests/theme-contrast.test.ts`, nos dois temas.

## 8. Como o Everton alimenta as notícias

Hoje o plantão lê o baha.com no Chrome dele e escreve no vault — nada disso chega ao banco, e portanto à tela.
O caminho mais barato e auditado **não é um raspador nem um POST na web**: é um script de operador espelhando o que
já existe para memes (`infra/scripts/meme_event.py`) — `infra/scripts/market_event.py --symbol ZECUSDT --source baha
--kind listing --title "..." --url "..." --published-at 2026-09-23T14:32Z --confidence reported --by everton`,
**dry-run por padrão**, `--apply` para gravar, uma linha em `system_events` (componente `market_events`) a cada
gravação e idempotência pelo único parcial `(source, url)`. Três motivos: nenhuma superfície de escrita nova na web
(a tela continua sendo leitura pura), `recorded_by` e `published_at`/`ingested_at` ficam explícitos desde a primeira
linha — o que sustenta o bloco C do §4 —, e o custo é uma tarde, não um serviço. Quando a mão cansar, o mesmo
`market_events` recebe um coletor de verdade sem que a tela mude uma linha; até lá a tela diz honestamente "fontes
ligadas: registro manual do plantão" em vez de fingir cobertura.

## 9. Segunda opinião (Astra)

Concordou com: tabela separada das notícias, ±15/±60 min, prioridade da recusa explicada, e não fabricar elemento visual sem dado. **Corrigiu dois pontos do meu diagnóstico inicial**, e ambos entraram acima: (a) o matcher de memes
**não** filtra `mint IS NULL` — varre por `observed_at` —, o que torna o reuso de `meme_events` pior do que eu
supunha, não melhor; (b) as recusas `parity_above_cap`/`below_ticket:*`/`spot_max_open_reached` **são** gravadas
como `spot_orders` com `status = 'refused'`, então a tela tem o que mostrar — o buraco real é o conjunto menor de
caminhos que não geram linha nenhuma (§4A). Levantou ainda a separação "o que se sabia × o que descobrimos depois"
(virou o bloco C do §4), a armadilha da tolerância de 22,5 min do `nearestCandleIndex` (§3, regra de cobertura) e a
incompatibilidade de unidade entre o stop real em SOL e o preço Binance (§3, overlay 3) — os três são achados dela
com cenário de falha, e os três mudaram a spec. **Divergência:** ela pediu que a tela vincule a notícia por
`market_id`; mantenho `symbol` NOT NULL + `market_id` nulo-até-existir, porque uma notícia pode ser registrada antes
de o par entrar no universo monitorado, e perder a notícia por não haver ainda uma linha em `markets` seria pior do
que carregar um `market_id` nulo por alguns dias.
