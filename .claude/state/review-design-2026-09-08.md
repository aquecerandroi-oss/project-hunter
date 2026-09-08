# Auditoria de design nº 1 — Radar, Lab, Carteira, System, Markets (T3.23)

**Autor:** product-designer · **Data:** 2026-09-08 · **Base:** `main` em `79c52c3` · **Brief:** `.claude/state/brief-T3.23-design-audit-1.md` · **Notas/setup:** `.claude/state/notes-T3.23.md`

## STATUS

**Parcial, com um bloqueio de ambiente diagnosticado.** A parte "com dado real no navegador" não aconteceu: a imagem `hunter-web:dev` que serve `localhost:3000` foi construída com a chave **falsa** do Clerk (`clerk.example.com`), então qualquer navegador — o embutido, o Chromium do Playwright, Chrome e Edge reais — é redirecionado (307) para um domínio que não existe (`net::ERR_NAME_NOT_RESOLVED`). É a causa raiz das 5 horas travadas na sessão anterior; não era o navegador. `curl` sem cabeçalhos de navegador recebe 200, por isso o stack parecia pronto. `/_design` devolve 404 no contêiner (`NODE_ENV=production`). Evidência completa e os dois comandos que destravam (rebuild do `web` com `--env-file .env`) em `notes-T3.23.md` §1.2–1.3; não posso recriar contêineres do stack local por regra da tarefa.

O que **foi** feito, e é o que este relatório contém:

1. **Contraste medido** a partir dos valores exatos dos tokens de `apps/web/app/globals.css`, incluindo as composições com alfa que o navegador faz (`bg-x/15`, `text-fg/80`, `opacity-60`) — 29 pares × 2 temas, `.claude/state/design/2026-09-08/contrast-tokens.{md,json}`. **12 falhas AA reais**, sete delas em componentes que aparecem em toda tela (badges, botão destrutivo, item "Planejado" da sidebar, borda dos inputs).
2. **Auditoria do código de tela** (hierarquia, estados, copy, escala tipográfica, foco, responsividade) de Radar, Lab, Carteira, System, Markets, detalhe de mercado e do shell (topbar/sidebar/nav/badges/botões/formatadores/tempo). Cada achado está marcado **(código)** quando o código basta para afirmá-lo, ou **(confirmar no navegador)** quando depende do render real.
3. **A infra de captura pronta**: `tests/e2e/design-audit.audit.ts` + `design-audit.config.ts` (sign-up de teste → vínculo à `ever` no Postgres → 7 telas × 3 viewports × 2 temas + interações do Lab + `/_design` + `/sign-in`, com PNG, métricas de contraste computado, overflow e texto visível por tela). Um comando de ~4 min assim que o `web` for reconstruído.

Sem capturas de tela nesta rodada, portanto: a pasta `.claude/state/design/2026-09-08/` tem só a matriz de contraste. Os achados abaixo que precisam de imagem estão sinalizados; a segunda passada (T3.24d, ver PRÓXIMO PASSO) fecha isso.

Achado de dado: no banco local, `ever` **não tem carteira principal** (`portfolios` só nas orgs de prova). A Carteira local cai no estado vazio e a régua do Lab na "carteira de referência" — a auditoria com dado real da Carteira precisa de `open_paper_wallet.py` para `ever` no local, ou da VPS.

## O QUE FOI AUDITADO

| Tela | Rota | Fonte | Viewports/temas |
|---|---|---|---|
| Radar | `/ever/radar` | código (`radar/page.tsx`, `components/radar/*`) | — (spec pronta para 1440/768/375 × dark/light) |
| Lab | `/ever/lab` (Placar, Curva, tabela com guias, painel de sinal, toggle de pesquisa) | código (`lab/page.tsx`, `components/lab/*`, 44 arquivos) | — |
| Carteira | `/ever/portfolio` | código (`portfolio/page.tsx`, `components/portfolio/*`) | — |
| System | `/ever/system` | código (`system/page.tsx`, `components/system/*`) | — |
| Markets + detalhe | `/ever/markets`, `/ever/markets/binance/BTCUSDT` | código (`components/markets/*`) | — |
| Shell | topbar, sidebar, mobile nav, nav-links, `ui/button`, `ui/badge`, `lib/format.ts`, `lib/time.ts`, `hooks/useAgeTicker.ts` | código | — |
| Tokens | `globals.css` dark + light | valores exatos, composição calculada | ambos os temas |

## ACHADOS

Severidade: **bloqueante** (impede o uso ou a própria auditoria) · **alto** (regra do contrato quebrada em componente compartilhado, ou copy que mente/vaza) · **médio** (inconsistência entre telas, polimento com impacto de leitura) · **baixo** (detalhe).

### 0. Ambiente

| # | Sev. | Achado | Evidência | Regra |
|---|---|---|---|---|
| E1 | bloqueante | `hunter-web:dev` construída com `pk_test_...clerk.example.com`; todo navegador é redirecionado para `https://clerk.example.com/v1/client/handshake` e falha em DNS. Nenhuma tela é renderizável por navegador no stack local. | `notes-T3.23.md` §1.2 (curl com `Sec-Fetch-Dest: document` → 307; bundle contém `clerk.example.com` 2×; probe Playwright `requestfailed`) | `docs/DEPLOYMENT.md` §2 (chaves reais no build); memória "frontend always polished ... browser-checked with real data" |
| E2 | alto | `ever` sem carteira principal no Postgres local → Carteira e régua do Lab não auditáveis com dado real localmente. | `select organization_id, count(*) from portfolios group by 1` → só `ever-t35-proof*` | brief §"Why you can see the real screens now" (assume paper wallet) |

### 1. Contraste (medido, ambos os temas) — `contrast-tokens.md`

| # | Sev. | Par | Escuro | Claro | Onde aparece | Regra |
|---|---|---|---|---|---|---|
| C1 | alto | `text-white` sobre `bg-red` (botão destrutivo, `ui/button.tsx`) | **3.76:1 falha** | 6.47 passa | kill switch, ações destrutivas | DESIGN §1 "AA 4.5:1 para texto em todos os pares" |
| C2 | alto | badge `negative` (`text-red` sobre `bg-red/15` composto em `bg-elevated`) | **4.34:1 falha** | 4.81 passa | `gap`, `stop`, `prejuízo`, `dead`, `BLOQUEADO`, `Not Ready` — em todas as telas | idem |
| C3 | alto | badge `positive` (`text-green` sobre `bg-green/15`) | 6.55 passa | **3.93:1 falha** | `OK`, `alvo`, `lucro`, `alive`, `Ativa`, `Em posição` | idem |
| C4 | alto | badge `warning` (`text-warning` sobre `bg-warning/15`) | 6.84 passa | **3.93:1 falha** | `atrasado 12s`, `ANOMALY`, `censurado`, `late`, `AVISO`, proteções degradadas | idem |
| C5 | alto | badge `gold` (`text-gold` sobre `gold-soft`) e guia ativa do Lab (`border-gold bg-gold-soft text-gold`) | 7.34 passa | **4.49:1 falha** (por 0.01) | `HOT`, `N monitorados`, versão `ativa`, guia "Concluídas (n)" | idem; DESIGN-1 só checou `gold` sobre branco |
| C6 | alto | item "Planejado" da sidebar: `text-fg-subtle` + `opacity-60` (`nav-links.tsx`) | **2.42:1 falha** | **2.41:1 falha** | sidebar e menu mobile, 8 itens planejados | idem; DESIGN §3 diz `fg-subtle` (sem opacidade) |
| C7 | alto | borda dos campos de formulário (`border-border` sobre `bg-overlay`) e o próprio campo sobre o card (`bg-overlay` sobre `bg-elevated`) | 1.26:1 / **1.04:1** | 1.26:1 / **1.06:1** | Radar (7 campos), Lab (3), busca de Markets | WCAG 1.4.11 (contorno de componente ≥ 3:1) — regra ausente no contrato, adicionada em DESIGN-5 |
| C8 | baixo | `fg-subtle` sobre `gold-soft` continua 3.47:1 no escuro — proibido desde DESIGN-3, e **não há uso no código** (conferido) | — | — | — | ok, só registro |

Os pares base (`fg`, `fg-muted`, `fg-subtle` sobre os três fundos; `gold` sobre `bg`; `gold-fg` sobre `gold`; verde/vermelho/âmbar/info sobre `bg`; tudo sobre `red-soft` e `gold-soft`) **passam** nos dois temas — a fundação está certa; as falhas estão nas composições que o contrato §1 nem os testes (`theme-contrast.test.ts`) cobrem: badges com alfa, o botão destrutivo e a opacidade da sidebar.

### 2. Radar (`/ever/radar`)

| # | Sev. | Achado | Regra |
|---|---|---|---|
| R1 | alto (código) | **Copy vaza enum cru** em cinco lugares: chips de Status (`NORMAL`, `WATCHING`, `ENTRY_CANDIDATE`, `EXTENDED`, `EXPIRED`), Estágio (`EARLY`, `DEVELOPING`), Regime (`TRENDING_UP`…), `<option>` de Regime e Tipo de anomalia, e a célula de anomalias (`volume_spike, funding_extreme (30d, ativas)`). O leitor vê o nome interno do valor, em inglês e em caixa alta. | brief: "copy em português, sem jargão"; DESIGN §3 define as cores dos badges, não que o rótulo seja o enum |
| R2 | alto (confirmar no navegador) | **Chips demais por linha**: até 6 badges (status, estágio, regime, confiança, anomalias, + "Em posição"/"Bloqueado (risco)") em linha de 40px; no 375 ficam 6 colunas visíveis (só Anomalias/Idade escondem) — a tabela rola dentro do contêiner, mas cada linha vira uma fila de pílulas. | DESIGN §2 "Menos chips por célula"; §3 markets table "colunas essenciais no mobile" |
| R3 | médio (código) | Filtros: `Score mínimo`, `Exchange`, `Volatilidade min`/`max` sem unidade; campos que navegam no `onBlur` sem botão "Aplicar" nem estado "aplicando" — a página recarrega sem feedback. Checkboxes nativos sem estilo de foco/tema. | SaaS craft: "keyboard focus visible, no dead controls" |
| R4 | médio (código) | `Score` em inglês como cabeçalho e no filtro; a barra de score usa `bg-fg-muted` (neutro, correto) mas o valor `change` verde/vermelho sem sinal de unidade (é "pontos de score", não %). | copy; §2 "sinal explícito" |
| R5 | baixo (código) | Nota de rodapé "Paginação sobre um ranking que muda continuamente…" em 11px `fg-subtle`, parágrafo de duas linhas: texto explicativo em tamanho de metadado. | DESIGN-5 (11px só para metadados de uma linha) |
| R6 | baixo (código) | Placeholder de idade `—` (travessão) vs `--` no resto do app. | consistência |

### 3. Lab (`/ever/lab`) — a tela central

| # | Sev. | Achado | Regra |
|---|---|---|---|
| L1 | alto (código) | **O banner "SOMBRA — hipotético, sem capital" vem depois do Placar.** A ordem da página é: h1 → Placar (2 cards com "Resultado acumulado (simulado)" em USDT/BRL em 18px + curva de 280px) → guia "Sombra" → **só então** `LabHeader` (o banner que "deve sobreviver a scroll, filtros e estados vazios") → filtros → cards de versão → totais → tabela. O leitor vê dinheiro antes de ser avisado que é simulado; o "(simulado)" no rótulo 12px é a única defesa. | `lab-header.tsx` docstring ("always visible"); CLAUDE.md "no fake anything"; hierarquia |
| L2 | alto (código) | **Três resumos antes da tabela**: Placar (por versão) + `LabVersionCard` (por versão, com funil, 5 métricas, bloco `r_ex_funding`, cobertura — tudo aberto por padrão) + `LabTotalsCard` (12 tiles, desta página). Mesmo número (resultado acumulado) aparece em três formas, e o card de versão repete em pesquisa o que o Placar já mostra em dinheiro. Estimativa (código): ~2 000px de altura antes da primeira linha de sinal em 1440. | hierarquia "o que o olho lê primeiro"; DESIGN T1.5b "clareza sobre os dados, não mais elementos" |
| L3 | alto (código) | Copy com **id de tarefa e nota obsoleta**: `LAB_TOTALS_SCOPE_NOTE = "os totais do Lab inteiro chegam com o placar (T3.18)"` — o placar já existe na mesma página e "T3.18" é id interno. `LabVersionsEmpty` cita `strategy-worker`, o caminho `infra/scripts/activate_strategy_version.py` e "critérios S0-S2". | brief: "sem jargão, listar vazamentos"; DESIGN-5 regra nova (sem ids de tarefa/ADR/caminhos na UI) |
| L4 | alto (código) | **Léxico de pesquisa em inglês/código na visão padrão** (não só atrás do toggle): filtro `Cohort` com valor `prospective` num input livre; `momentum/v2` como nome de estratégia; badge de status cru (`active`/`deprecated`/`draft`) no `LabVersionCard`; `code_ref` (hash) em 11px; "PnL de carteira: não aplicável (`portfolio_pnl_reason` cru)"; "Expectancy", "Profit factor", "Tracking", "n=…, ordenada por exit_ts", "outcomes avaliáveis", "MFE/MAE", "Ver envelope" (JSON cru em `<pre>`), "(capado em 2.000 pontos)", chips de resultado terminal `target: 3`. | copy; SaaS craft "density for power users without noise for newcomers" |
| L5 | médio (código) | Escala tipográfica: valores em `text-lg` (18px) nos `MoneyStat`/`Stat`; título "Placar" em 18px; chip de propósito `text-[10px]`; 11px em 14 lugares. Nenhum dos três está na escala de 5 tamanhos. | DESIGN §2 (escala), corrigido por DESIGN-5 |
| L6 | médio (código) | Fatos-chave só em `title` (hover): `MONEY_TOOLTIP` em toda célula de dinheiro, `PERIOD_TOOLTIP` no rótulo "período: todo o disponível", `VERDICT_RULE_TEXT` no badge de veredito (também impresso em 11px no rodapé do card — ok). No toque (375/768) o tooltip não existe. | DESIGN T1.5b decisão #9 "acessíveis sem hover" |
| L7 | médio (código) | Guia única "Sombra" renderizada como tablist com um `div role=tab` — ocupa uma linha inteira para dizer uma palavra; o segmento ("Concluídas · Abertas · Pendentes/sem entrada · Todas") é a guia real e fica bem abaixo. | "no inert controls"; hierarquia |
| L8 | médio (confirmar no navegador) | Tabela: 9 colunas sempre visíveis com `min-w-max` (+5 com pesquisa); "Quando (Brasília)" e "Resultado" com `min-w-[150px]`; no 1440 com sidebar (240) + painel lateral (384) sobram ~700px para a tabela → rolagem horizontal já no desktop. Painel de sinal com `lg:w-96` fixo. | §2 densidade; §3 "colunas essenciais sempre visíveis" |
| L9 | médio (código) | Estado de erro do Placar é um `<p class="text-sm text-red">` solto (sem caixa, sem "Tentar novamente") — diferente do `LabError`/`RadarError`/`MarketsError`. | consistência de estados |
| L10 | baixo (código) | `LabScoreboardEmpty` sem `bg-bg-elevated` (os outros vazios têm); `LabMarketLink` é `<button>` com sublinhado só no hover (parece texto). | consistência |
| L11 | baixo (código) | Régua "0,25% de 10,000.00 USDT" mistura vírgula decimal (pt) e ponto/vírgula en-US na mesma frase (ver X4). | §2 |

### 4. Carteira (`/ever/portfolio`)

| # | Sev. | Achado | Regra |
|---|---|---|---|
| P1 | alto (código) | **Enums crus em toda a tela**: badges `summary.type`/`summary.status` (`paper`, `open`), `p.direction` (`long`), `p.status`, `o.side` (`buy`), `o.type`, `o.purpose`, `o.execution_mode`, `o.status`, `t.exit_reason`, escopos do kill switch (`ACTIVE` ×3), transição `from_state → to_state`, `actor_type`, `fx_observation.source` (`binance.spot.ticker`), evidência em JSON. Os rótulos das colunas estão em português, os valores não. | copy |
| P2 | alto (código) | Ids de tarefa/ADR e comando de terminal na UI: `PortfolioProposalsEmpty` ("chega em T3.12/T3.14"), `PortfolioEmpty` ("ADR 0005" + `uv run python infra/scripts/open_paper_wallet.py …` num `<pre>`), `PortfolioRiskCard` ("preset paper_v1 … docs/plans/M3.md T3.12/T3.14"). Para o operador-dono é útil; para o produto é o backstage aparecendo. | DESIGN §2 "não construído ainda: nomeia o milestone" — milestone (M3), não id de tarefa; DESIGN-5 |
| P3 | médio (código) | KPI: 9 cards em duas fileiras de 5, todos iguais (12px eyebrow + `text-2xl` 24px mono). "Patrimônio (USDT)" não se destaca de "Reservado (notional)". 24px não está na escala; "100,000.00 USDT" em mono 24px ≈ 200px em coluna de ~215px no `lg` — risco de quebra em 1024–1280. | DESIGN §3 "Cards KPI: valor 28px" (contrato) vs 24 (código); hierarquia |
| P4 | médio (código) | Rótulos de jargão sem explicação: "Reservado (caixa)/(risco)/(notional)", "Exposição", "Mark", "PnL não realizado", "Câmbio de abertura" (bom) vs "opening_rate" só no texto. | copy |
| P5 | baixo (código) | Três tabelas (`Posições`, `Ordens`, `Trades`) sem `thead` fixo nem densidade do `useRowHeight()` (linhas `py-1`), diferentes das tabelas virtualizadas. Aceitável enquanto vazias (docstring explica), mas nascerão inconsistentes quando o executor escrever. | §2 densidade 40/32px |
| P6 | baixo (código) | "Tipo" card com dois badges `outline` (`paper`, `open`) sem rótulo do segundo (status). | copy |

### 5. System (`/ever/system`)

| # | Sev. | Achado | Regra |
|---|---|---|---|
| S1 | médio (código) | Copy em inglês/cru: título "System", colunas `Role`/`Instância`/`Status`, valores `alive/late/dead`, `market/scanner/strategy/execution`, `CONNECTED`, badges `Ready`/`Not Ready`, "Feature flags", "Git SHA", "Ambiente: development". É a tela do operador — parte disso é vocabulário honesto (`CONNECTED` é o estado do socket), mas `alive`/`late`/`dead` e `Ready` têm tradução direta (vivo/atrasado/morto; Pronto/Não pronto). | copy |
| S2 | médio (código) | Estado de erro `UnavailableSection` e "Workers indisponível" sem botão "Tentar novamente" (Radar/Markets/Lab/Carteira têm). | consistência de estados |
| S3 | baixo (código) | Dois estilos de título de seção na mesma tela: eyebrow 12px maiúsculo (`API`, `Dependências`, `Workers`) e `h3 text-sm` ("Execução paper"). | X2 |
| S4 | baixo (código) | Card "Execução paper" no `lg:grid-cols-[2fr_1fr]` fica ao lado de duas tabelas empilhadas — alturas desiguais; abaixo de `lg` fica embaixo, correto. | (confirmar no navegador) |

### 6. Markets e detalhe de mercado

| # | Sev. | Achado | Regra |
|---|---|---|---|
| M1 | médio (código) | Cabeçalho "Status" é a coluna de **qualidade** (`QualityBadge`); o Radar chama a mesma coisa de "Qualidade". Mesma coisa, dois nomes. | consistência |
| M2 | médio (código) | Copy: título "Markets"; "Último", "24h %", "24h Vol" (aceitáveis como jargão de terminal); no detalhe "Book", "Bids/Asks" (trades usam "C/V" = Compra/Venda), "Mark price", "Open interest", "Funding (estimated)" com `fundingKind` cru, "Snapshot", "gap", "relógio local". | copy; §3 já fixa "Snapshot · há N s" e "gap" — manter esses dois |
| M3 | baixo (código) | Sumário de chips: 7 badges (`N shards, 200 mercados`, `N mercados`, `N monitorados`, `ok`, `atrasados`, `degradados`, `sem dado`) — a única linha do app com badge `gold` para um número neutro ("monitorados"). | §2 "dourado é raro" |
| M4 | baixo (código) | Detalhe: preço 28px inline com badge, bid/ask 12px e "atualizado há" 11px na mesma linha `flex-wrap` — no 375 a linha quebra em 3–4 alturas diferentes (confirmar). | hierarquia |

### 7. Transversal (shell, tokens, escala, tempo, foco)

| # | Sev. | Achado | Regra |
|---|---|---|---|
| X1 | alto (código) | **Sem `loading.tsx` nem `error.tsx` em nenhuma rota** (`find apps/web/app -name loading.tsx` → nada). Navegar entre páginas (todas Server Components com 3–7 fetches em série) não dá feedback até a resposta chegar; um erro de render cai na tela padrão do Next em inglês. | SaaS craft (estados loading/error nomeados); DESIGN §2 "Shimmer só no primeiro carregamento" pressupõe que exista |
| X2 | médio (código) | **Dois idiomas de título de seção**: eyebrow 12px maiúsculo (`System`, Dashboard, detalhe de mercado) vs `h2 text-lg` 18px semibold + `h3 text-sm` (Lab, Carteira). | §2 escala; consistência |
| X3 | médio (código) | **Vocabulário de tempo** não unificado: "Painel consultado <t>" (Radar), "Estado em <t>" (Lab), "Consultado em <t>" (Carteira, 4×), "consultado em" (minúsculo), "atualizado há Ns", "Snapshot · há", "há Xs (<t>)", "Decisão: <t> -- barra de referência: <t>". E quatro componentes idênticos (`LabAsOf`, `PortfolioAsOf`, `SystemAsOf`, `BrasiliaInstant`) por decisão de "duplicar em vez de compartilhar". | regra ausente → DESIGN-5 |
| X4 | médio (código) — **Everton decide** | **Convenção numérica dupla na mesma tela**: USDT em en-US (`19,333.01 USDT`), BRL em pt-BR (`R$ 100.000,00`), percentuais em en-US (`+1.23%`) — e o contrato §2 escreve `+1,23%` (vírgula). Doc e código se contradizem. | §2 |
| X5 | médio (código) | **Escala tipográfica**: `text-[11px]` ×36, `text-[10px]` ×8, `text-lg` ×16, `text-2xl` ×1 em telas de produto. O contrato lista 5 tamanhos + 3 exceções únicas; a interface usa 11px como sexto degrau de fato e 10px em chips de propósito, no glyph C/V e no hint "relógio local". | §2 → DESIGN-5 formaliza 11 e 24, proíbe 10 (exceto `kbd`) e 18 |
| X6 | médio (código) | **Foco visível**: botões e grids têm `focus-visible:ring-2 ring-gold`; `<input>`, `<select>`, `<input type=checkbox>` (Radar, Lab, busca de Markets) e os `<Link>` da navegação não têm — ficam com o outline do navegador (azul/branco), inconsistente com o anel dourado. | §2 "anel de foco dourado"; SaaS craft |
| X7 | médio (código) | **Nomes de página em dois idiomas**: `Dashboard`, `Radar`, `Markets`, `Opportunities`, `Carteira`, `Trades`, `Lab`, `System`, `Settings`… — a sidebar mistura inglês e português. | copy — **Everton decide** (D1) |
| X8 | baixo (código) | Marca duplicada: "HUNTER" (topbar, dourado) e "Hunter" (topo da sidebar) lado a lado no desktop; a topbar mostra o slug (`ever`) em vez do nome da organização. | §3 topbar "nome da organização em `fg`" |
| X9 | baixo (código) | Idades "12s / 3min / 2h" (`formatAge`) vs contrato "há 3 s, 2 min, 1 h" (com espaço). | §2 |
| X10 | baixo (código) | Placeholders de ausência: `--` (markets, lab), `—` (radar), `?` (workers, live status). | consistência |
| X11 | baixo (código) | Tabelas de dados em 13px em Radar, Lab, Carteira e System — o contrato só autoriza em `markets-table.tsx`. A interface já decidiu; o contrato precisa dizer. | §2 → DESIGN-5 generaliza |

## PROPOSTAS (specs)

### PR-1 · Tokens e componentes compartilhados (fecha C1–C7) — brief `T3.24-design-quick-wins`

**Problema:** 7 pares medidos abaixo de AA em componentes que aparecem em toda tela. **Mudança (antes → depois), tudo verificado por cálculo em `contrast-candidates.mjs`:**

| Onde | Antes | Depois | Escuro | Claro |
|---|---|---|---|---|
| `ui/button.tsx` `destructive` | `bg-red text-white` | `bg-red text-bg` (`--color-bg` é #0A0A0A no escuro e #FFFFFF no claro — um token, dois temas certos) | 5.26 | 6.47 |
| `ui/badge.tsx` `positive` | `bg-green/15 text-green` | `bg-green-soft text-green` (o token `green-soft` existe em §1 exatamente para "fundo de badge") | 6.75 | 4.57 |
| `ui/badge.tsx` `negative` | `bg-red/15 text-red` | `bg-red-soft text-red` | 4.78 | 5.30 |
| `ui/badge.tsx` `warning` | `bg-warning/15 text-warning` | `bg-warning-soft text-warning` — **novo token** `--color-warning-soft`: escuro `#2E1F06`, claro `#FEF3C7`; e `--color-warning` claro de `#B45309` → `#A34A05` (5.33 sobre `warning-soft`, 5.02→~6 sobre branco) | 7.44 | 5.33 |
| `ui/badge.tsx` `info` | `bg-info/15 text-info` | `bg-info-soft text-info` — **novo token** `--color-info-soft`: escuro `#0F1F33`, claro `#DBEAFE` | 6.53 | 5.49 |
| `ui/badge.tsx` `gold` + `lab-segment-tabs.tsx` | `text-gold` sobre `gold-soft` | mantém; `--color-gold` **claro** de `#8A6D00` → `#7F6400` (`gold-strong` claro → `#665000`) | 7.34 | 5.14 (e 5.64 sobre branco, 5.64 `gold-fg`) |
| `nav-links.tsx` item planejado | `text-fg-subtle opacity-60` | `text-fg-subtle` sem `opacity-60`; o "planejado" já é dito pelo ícone apagado + badge tracejado + `cursor-not-allowed` | 4.91 | 5.50 |
| campos (`<input>`, `<select>`) em Radar/Lab/Markets | `border-border bg-bg-overlay` | `border-border-input bg-bg` — **novo token** `--color-border-input`: escuro `#666666`, claro `#8A8A8A` (≥ 3.1:1 sobre `bg-overlay` e `bg`); campo com fundo `bg` (mais escuro que o card) para o contorno existir também por preenchimento | 3.15 | 3.11 |
| `theme-contrast.test.ts` | 8 pares | + os 8 pares acima (badge×5 compostos, destrutivo, planejado, `border-input`) nos dois temas | | |
| `/_design` `badges-showcase.tsx`, `buttons-showcase.tsx`, `inputs-showcase.tsx` | — | mostram o antes/depois medidos (o `contrast.ts` do showcase já calcula) | | |

**Acessibilidade:** todas as razões acima ≥ 4.5 (texto) / ≥ 3 (contorno). **Copy:** nenhuma. **Onde aplica:** todo o app (5 arquivos + `globals.css` + `docs/DESIGN.md` §1).

### PR-2 · Escala tipográfica honesta (fecha X5, L5, P3) — DESIGN-5 (feito) + quick wins

Escala passa a **7 degraus nomeados**: `11` micro (metadado de uma linha: idade, código de exchange, cobertura, `kbd`), `12` label/eyebrow, `13` corpo de tabela de dados, `14` texto, `16` destaque, `20` título de seção e valor de stat, `24` KPI em grade, `28` número-herói (um por tela). Proibidos: `10px` (exceto o `kbd` Ctrl K), `18px`. Migração: `text-[10px]` → `text-[11px]` (chips de propósito, hint "relógio local", glyph C/V); `text-lg` → `text-xl` (títulos "Placar", nome da carteira, valores de `MoneyStat`/`Stat`); `text-2xl` da Carteira fica (24 = KPI). Uma constante `TYPE_SCALE` no `/_design` `typography-scale.tsx` com os 7.

### PR-3 · Copy: dicionários de enum e regra "sem backstage" (fecha R1, L3, L4, P1, P2, S1, M1, M2) — quick wins (R/P/S/M) + Lab (L)

Um módulo por domínio, plain data, testado: `components/radar/labels.ts` (status, estágio, regime, tipo de anomalia), `components/portfolio/labels.ts` (direção, lado, tipo/propósito/modo/status de ordem, escopo/estado do kill switch, ator, fonte de câmbio), `components/system/labels.ts` (papel, status, ws), `components/lab/labels.ts` (status de versão, propósito, resultado terminal, tracking). Antes → depois (amostra):

| Cru | Rótulo |
|---|---|
| `NORMAL` / `WATCHING` / `ANOMALY` / `HOT` / `ENTRY_CANDIDATE` / `EXTENDED` / `EXPIRED` | Normal / Observando / Anomalia / Quente / Candidato a entrada / Esticado / Expirado |
| `EARLY` / `DEVELOPING` / `EXTENDED` / `NONE` | Início / Em desenvolvimento / Esticado / estágio indisponível (já) |
| `TRENDING_UP` / `TRENDING_DOWN` / `RANGING` / `VOLATILE` / `UNKNOWN` | Alta / Baixa / Lateral / Volátil / Sem classificação |
| `volume_spike` / `funding_extreme` / … (todos os `ANOMALY_TYPE_VALUES`) | Pico de volume / Funding extremo / … (tabela completa no brief) |
| `long` / `short` / `buy` / `sell` | Comprado / Vendido / Compra / Venda |
| `ACTIVE` / `WARNING` / `TRADING_DISABLED` / `EMERGENCY` | Ativo / Aviso / Bloqueado / Emergência (já existe em `killSwitchLabel`; usar nos 3 escopos e na transição) |
| `alive` / `late` / `dead` · `Ready` / `Not Ready` | vivo / atrasado / morto · Pronto / Não pronto |
| `active` / `deprecated` / `draft` (versão) | ativa / substituída / rascunho |
| `target` / `stop` / `expired` / `invalidated` (terminal, funil) | alvo / stop / expirou / invalidada (já existe em `EXIT_REASON_LABEL`; usar no funil) |

Regra nova (DESIGN-5): **nada de id de tarefa, número de ADR, caminho de arquivo ou comando de terminal na UI**. O "não construído ainda" nomeia o milestone ("chega no M3"), o operador encontra o comando no runbook (`docs/ACTIVATION.md`), e a tela pode linkar o runbook. Aplicação: `LAB_TOTALS_SCOPE_NOTE` → **remover** (o Placar está na mesma tela; o heading já diz o escopo); `LabVersionsEmpty` → "Nenhuma versão de estratégia ativa nesta janela e coorte. Zero versões é um resultado, não uma falha — versões são ativadas pelo operador, fora desta tela."; `PortfolioProposalsEmpty` → "Ainda sem propostas — o serviço de admissão, que registra os checks e o limitante vencedor de cada decisão, chega no M3."; `PortfolioEmpty` → texto sem "ADR 0005" e o comando atrás de `<details>` "Para o operador" (o dono da instância é hoje o único usuário — o comando fica, mas não como corpo do estado vazio); `PortfolioRiskCard` rodapé → "Os limites numéricos do preset paper (risco por operação, exposição, participação) ainda não são expostos pela API nesta tela." ("T3.25 part A" acabou de entregar `GET …/risk/limits`, então este rodapé some quando a T3.25 parte B ligar o endpoint).

### PR-4 · Estados de carregamento e erro por rota (fecha X1) — quick wins

`apps/web/app/(app)/[orgSlug]/loading.tsx` (esqueleto genérico: h1 em `bg-bg-overlay` 20×160, três caixas 96px com shimmer **só no primeiro carregamento**, respeitando `prefers-reduced-motion`) e `error.tsx` ('use client', mesma caixa tracejada `border-red/40` dos erros de página, "Algo falhou ao renderizar esta tela: {message}", botão "Tentar novamente" → `reset()`, link "Ver System"). Por rota, `loading.tsx` específico para Lab (esqueleto com Placar + tabela) e Radar (filtros + tabela). Sem texto em inglês.

### PR-5 · Vocabulário de tempo e um componente só (fecha X3, X9) — consistency

Três rótulos, e só três: **"Consultado em <dd/mm/aaaa hh:mm:ss>"** (quando o servidor leu — `as_of` de página/seção), **"Atualizado há <N s|min|h>"** (idade de um dado que envelhece — ticker, heartbeat, MTM), **"Snapshot · há <N s>"** (foto tirada no load — book/trades). `formatAge` passa a "3 s / 2 min / 1 h" (com espaço, como o contrato diz). `BrasiliaInstant`/`BrasiliaShort` viram o único componente (os três `*AsOf` são re-exports finos ou somem), com `title` = ISO UTC. Onde muda: Radar ("Painel consultado" → "Consultado em"; "anomalias verificadas" → "anomalias consultadas em"), Lab ("Estado em" → "Consultado em"), Carteira (maiúscula consistente), System (mantém "há Xs (<t>)" → "Atualizado há X s · <t>").

### PR-6 · Lab: uma hierarquia (fecha L1, L2, L6–L10) — brief `T3.24-design-lab`

Dentro da direção atual (Placar no topo, dinheiro através da régua), a ordem passa a ser:

1. **Faixa SOMBRA** compacta no topo (1 linha: "SOMBRA — simulação sobre dado real, nada foi comprado ou vendido · régua 0,25% de <equity> (<fonte>) = <risco> por operação · custos assumidos: …", `border-l-4 border-l-gold`), **antes** de qualquer número. A régua e os custos deixam de ser dois parágrafos.
2. **Placar**: cards por versão (mantém) — o veredito domina, dinheiro em 20px (não 18), "Detalhes de pesquisa" como hoje. A curva **colapsa para 200px** e ganha o toggle USDT/R já existente.
3. **Sinais** (o assunto da tela): segmento como guia principal ("Concluídas (n) · Abertas · Pendentes/sem entrada · Todas") **no lugar** da guia única "Sombra" (que vira o próprio nome da seção: "Sinais — Sombra"); filtros (janela/coorte/versão) na mesma linha; `LabTotalsCard` **colapsado em uma linha de 4 stats** (operações · com lucro/prejuízo · taxa de acerto · resultado acumulado USDT (BRL)) com "mais" para os 12; tabela; painel lateral.
4. **Versões (pesquisa)**: os `LabVersionCard` **colapsados** por padrão (cabeçalho = identidade + veredito/maturidade em uma linha; funil, 5 métricas, `r_ex_funding` e cobertura abrem por versão) — consistente com o toggle "Detalhes de pesquisa" que a tela já usa.
5. `MONEY_TOOLTIP` vira **uma nota visível** no rodapé da tabela ("Valores simulados: dado real, custos assumidos, sem dinheiro.") em vez de `title` em cada célula; `PERIOD_TOOLTIP` vira texto ("período: todo o disponível — o resumo acima usa a janela escolhida"); `Cohort` vira `<select>` com as coortes que a API devolve (ou "prospective (padrão)").
6. Tabela: no `lg` com painel aberto, esconder `Duração` e `Quantia simulada` (ambas no painel) para caber sem rolagem horizontal; no 375, colunas essenciais = Estratégia, Mercado, Resultado (badge + USDT), com Entrou/Saiu no painel.

Mockups: `apps/web/app/_design` ganha `lab-hierarchy-showcase.tsx` com as duas opções da seção "Só o Everton decide" (D3), renderizadas com o mesmo `LabScoreboardCard`/`LabSignalRow` e dados reais capturados (nunca inventados — usar o fixture do teste `lab-*.test.tsx`).

### PR-7 · Radar: linha legível (fecha R2, R3, R4) — quick wins (parte) + consistency

Linha: `Mercado` (símbolo + exchange 11px + **uma** linha de chips: status · estágio · regime, em ordem fixa; "Em posição"/"Bloqueado" como ícone + `title`), `Score` (valor + delta com "pts"), `Confiança` (badge + "atualizado há"), `Anomalias` (md+), `Idade` (md+). Abaixo de `md`: só Mercado (com os 3 chips) + Score + Confiança. Filtros: botão "Aplicar" explícito (ou `aria-busy` + spinner no `onBlur`), unidades nos rótulos ("Volatilidade mín. (%)", "Score mín. (0–100)"), checkboxes via `ui/checkbox` (shadcn) com anel de foco.

### PR-8 · Títulos de seção, erro e foco (fecha X2, X6, S2, L9, M1) — consistency

Um idioma: **eyebrow 12px maiúsculo `fg-muted`** para título de card/seção dentro da página; **20px semibold `fg`** para o título de página (h1) e para blocos que são "páginas dentro da página" (Placar). Lab e Carteira migram (`text-lg` → eyebrow). Erro de seção = `SectionUnavailable` compartilhado (caixa tracejada `border-red/40`, "X indisponível: {reason}", "Tentar novamente"). Foco: `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold focus-visible:ring-offset-2 focus-visible:ring-offset-bg` nos `ui/input`, `ui/select`, `ui/checkbox` (usar os shadcn em vez de nativos) e nos `<Link>` do `nav-links.tsx`. "Status" da tabela de Markets → "Qualidade".

## O QUE FOI IMPLEMENTADO / ENTREGUE AO FRONTEND

- Nada de código de tela (regra da tarefa). Entregues: este relatório; `docs/DESIGN.md` §2 + §5 DESIGN-5 (regras que faltavam ou se contradiziam: escala de 7 degraus, 13px em toda tabela de dados, badges com tokens `-soft`, contorno de campo ≥ 3:1, vocabulário de tempo, sem backstage na copy); três briefs `T3.24-design-{quick-wins,lab,consistency}`; a spec de captura; a matriz de contraste.
- Astra: não consultada nesta rodada (sem quota confirmada e sem imagem para revisar); a segunda passada pede a opinião dela sobre PR-6 antes de dispatch do brief Lab.

## TESTES (saída real)

```
$ node .claude/state/tmp/contrast-tokens.mjs
FALHA dark: fg-subtle @60% on bg-elevated = 2.42:1 (#525252 on #111111) -- item 'Planejado' da sidebar (opacity-60)
FALHA dark: white on red = 3.76:1 (#ffffff on #ef4444) -- botão destrutivo (button.tsx destructive)
FALHA dark: red on red/15 over bg-elevated = 4.34:1 (#ef4444 on #321919) -- badge negative (gap, stop, prejuízo, dead)
FALHA dark: fg-subtle on gold-soft = 3.47:1 (#828282 on #3a2e08) -- (proibido desde DESIGN-3, conferência)
FALHA dark: border on bg = 1.26:1 (#232323 on #0a0a0a) -- bordas 1px (não-texto, referência 3:1 para UI)
FALHA dark: border-strong on bg-elevated = 1.39:1 (#2e2e2e on #111111) -- separadores (não-texto)
FALHA light: fg-subtle @60% on bg-elevated = 2.41:1 (#a3a3a3 on #fafafa) -- item 'Planejado' da sidebar (opacity-60)
FALHA light: gold on gold-soft = 4.49:1 (#8a6d00 on #fff4d6) -- badge gold (HOT, versão ativa, monitorados), guia ativa do Lab
FALHA light: green on green/15 over bg-elevated = 3.93:1 (#15803d on #d8e8de) -- badge positive (OK, alvo, lucro, alive)
FALHA light: warning on warning/15 over bg-elevated = 3.93:1 (#b45309 on #f0e1d6) -- badge warning (atrasado, ANOMALY, censurado, late)
FALHA light: border on bg = 1.26:1 (#e5e5e5 on #ffffff) -- bordas 1px (não-texto, referência 3:1 para UI)
FALHA light: border-strong on bg-elevated = 1.42:1 (#d4d4d4 on #fafafa) -- separadores (não-texto)
ok: 29 pares x 2 temas

$ node .claude/state/tmp/contrast-candidates.mjs   (valores propostos em PR-1)
  5.26 dark destructive: bg(#0a0a0a) on red
  6.47 light destructive: bg(#ffffff) on red
  6.75 dark green on green-soft        4.57 light green on green-soft #dcfce7
  4.78 dark red on red-soft            5.30 light red on red-soft #fee2e2
  7.44 dark warning on #2e1f06         5.33 light warning #a34a05 on #fef3c7
  6.53 dark info on #0f1f33            5.49 light info on #dbeafe
  5.14 light gold #7f6400 on gold-soft · 5.64 sobre branco · 5.64 gold-fg branco sobre #7f6400
  3.15 dark input border #666666 on bg-overlay · 3.11 light #8a8a8a on bg-overlay
  4.91 dark fg-subtle on bg-elevated (planejado sem opacity)

$ cd tests/e2e && pnpm exec playwright test -c design-audit.config.ts -g signup --timeout 120000
  x  1 [chromium] › design-audit.audit.ts:200:3 › T3.23 design audit › signup: test user, onboarding, membership in ever (9.2s)
    Error: page.goto: net::ERR_NAME_NOT_RESOLVED at http://localhost:3000/sign-up
  (requestfailed https://clerk.example.com/v1/client/handshake?...  net::ERR_NAME_NOT_RESOLVED)
```

Bordas `border`/`border-strong` a ~1.3:1 são decorativas (linhas de tabela, separadores) e ficam como estão — a regra 3:1 vale para o contorno de **campo**, que é o C7.

## O QUE SÓ O EVERTON DECIDE

**D1 · Idioma dos nomes de página/navegação (X7).** Hoje: Dashboard · Radar · Markets · Opportunities · Carteira · Trades · Lab · System · Settings.
- (A) **Tudo em português**: Painel · Radar · Mercados · Oportunidades · Carteira · Operações · Laboratório (ou "Lab") · Sistema · Configurações. Coerente com a copy do resto do app e com o público (PT-BR).
- (B) **Nomes de produto em inglês como marca, resto em português**: Dashboard · Radar · Markets · Opportunities · Carteira · Trades · Lab · System — só se assumirmos que são "nomes próprios"; hoje só "Carteira" fugiu, por pedido explícito, então a regra atual é inconsistente por acidente, não por decisão.
- (C) Manter como está.
Recomendação: **A**, com "Lab" mantido (curto, já é a palavra que o Everton usa) e "Radar" (igual nas duas línguas). Aplica em `lib/nav-registry.ts` (labels) e nos `h1` — um arquivo + 7 títulos.

**D2 · Convenção numérica (X4).** (A) **pt-BR em tudo**: `19.333,01 USDT`, `R$ 100.000,00`, `+1,23%` — o contrato §2 já escreve assim; muda `formatUsdt`/`formatMoney`/`formatPct` para `pt-BR` (o preço cru da API continua a string decimal recebida, com ponto, como a exchange). (B) **Como a exchange**: manter en-US para USDT e % (Binance, TradingView), pt-BR só para BRL; corrigir o contrato para dizer isso. Recomendação: **A** para valores em dinheiro e percentuais (o leitor é brasileiro e "19,333" lê como dezenove vírgula), **preço de mercado cru fica como a API manda** (regra já existente). Risco de B: dois separadores decimais na mesma linha ("+15.00 USDT (+R$ 77,60)") — é o que o Lab imprime hoje.

**D3 · Direção do Lab (PR-6).** (A) **Placar-primeiro** (atual, reorganizado como em PR-6: faixa Sombra → Placar → Sinais → Versões colapsadas). (B) **Sinais-primeiro**: faixa Sombra → uma linha de totais do Placar (1 card por versão em linha, sem curva) → tabela de sinais → Placar completo com curva e versões abaixo — a tabela é onde o Everton olhou primeiro nas duas capturas dele (T3.17b). (C) Duas abas reais: "Placar" e "Sinais" (a estrutura de abas já existe em `lab-tabs.tsx`). Recomendação: **A** agora (menor mudança, respeita "top of /lab" da T3.18) e medir com ele qual das duas ele abre mais; mockups A/B no `/_design` fazem parte do brief Lab. Vai à Astra antes do dispatch.

**D4 · Backstage na UI (PR-3).** Confirmar a regra "sem id de tarefa/ADR/caminho/comando na copy" — hoje há 5 ocorrências; o operador é ele mesmo, então a regra pode soar exagerada; a proposta mantém o comando de abrir carteira atrás de um `<details>` "Para o operador".

## PRÓXIMO PASSO

1. **Everton (2 comandos)**: `docker compose --env-file .env -f infra/docker/docker-compose.yml build web` e `... up -d web`; conferir `curl -s http://localhost:3000/sign-in | grep -c clerk.example.com` → 0. Opcional: abrir a carteira principal de `ever` no banco local (`open_paper_wallet.py`) para a Carteira ter dado real.
2. **product-designer (T3.24d, ~1 h)**: rodar `cd tests/e2e && E2E_BASE_URL=http://localhost:3000 pnpm exec playwright test -c design-audit.config.ts --timeout 120000`, anexar os PNGs, confirmar/derrubar cada item "(confirmar no navegador)" (R2, L8, S4, M4), medir o contraste **renderizado** (deve bater com a matriz), e pedir a segunda opinião da Astra sobre PR-6 (`bash infra/scripts/astra.sh ask design-lab-hierarchy "..."`).
3. **Dispatch** (independe do passo 2): `brief-T3.24-design-quick-wins.md` (1 dia, sem mudança de direção; inclui D1/D2 só se o Everton decidir antes) → `brief-T3.24-design-consistency.md` → `brief-T3.24-design-lab.md` (depois da opinião da Astra e da decisão D3).
4. Depois do rebuild, este relatório ganha a seção "Capturas" com os caminhos `.claude/state/design/2026-09-08/*.png` e a tabela de contraste renderizado por tela; a linha do Obsidian é atualizada.
