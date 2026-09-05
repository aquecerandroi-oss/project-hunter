# Kit de revisão — T1.5b (polimento UX/UI, `apps/web/**` + `docs/DESIGN.md`)

Estado: **em revisão** (fix pass despachado 2026-09-05). Atualizado ao fechar.

Critério de aceite = `.claude/state/brief-T1.5b-ux.md`, seção "Decisão conjunta de design (Claude ⇄ Astra)", itens 1–10 — prevalece sobre o texto anterior do brief.

## Revisores rodados

| Revisor | Como | Veredito |
| --- | --- | --- |
| `code-reviewer` | working tree (`git diff -- apps/web docs/DESIGN.md` + 17 arquivos novos) | REQUEST_CHANGES — 3 HIGH, 3 MEDIUM, 1 LOW |
| `security-reviewer` | Server Action nova, topbar/layout, dialog, varredura de segredos | sem CRITICAL/HIGH — 2 MEDIUM, 2 LOW |
| Astra (GPT-6, `astra.sh ask review-T1.5b-final`) | must-fix anteriores + diff atual | "ainda não aprovaria" — 4 FECHADOS, 3 PARCIAIS, 3 cenários novos |
| Sexta-feira (leitura de design + QA de navegador) | `/_design` claro/escuro, desktop/mobile | ver "QA visual" abaixo |

## QA visual (Playwright + Chromium, 2026-09-05)

Screenshots em `.claude/state/screenshots/T1.5b/` (`design-{dark,light}-{desktop,mobile}.png`, ~150 KB cada, `command-palette-open.png` quando o servidor permitir interação).

Verificado no HTML renderizado: escala tipográfica 12/14/16/20/28; tabela densa nas duas densidades (40 px / 32 px lado a lado); paridade clara/escura; vocabulário de staleness completo e separado (`OK` / `atrasado 12s` / `gap` / `sem dado` e `operacional` / `degradado` / `indisponível` / `sem verificação`); painel de snapshot rotulado "Snapshot · há N min" com a frase que diz que não é fita ao vivo; botão visível "Buscar mercados" com dica `Ctrl K`, colapsado para ícone no mobile; candles verdes/vermelhos no código do gráfico.

**Limitação honesta:** o QA *interativo* (abrir a palette por Ctrl/⌘K, ver o anel de foco, disparar o flash) **não pôde ser executado**. O ambiente tinha dois dev servers concorrentes sobre o mesmo `apps/web/.next` (um órfão na porta 3001, deixado por um subagente, com código antigo; o da porta 3000 com o `.next` sobrescrito por um build de produção), então a página da 3000 renderiza o HTML certo mas **não carrega JavaScript nenhum** (`/_next/static/chunks/main-app.js` → 404) e a da 3001 nem tem o command palette. Encerrar processos é bloqueado pela política de permissão desta sessão. Prova de comportamento fica pelos testes de Vitest (`command-palette.test.tsx`, `topbar.test.tsx`, `use-price-flash.test.ts`, `use-density.test.ts`, `use-arrow-key-row-selection.test.ts`) e pelos screenshots estáticos.

## Achados aceitos (enviados ao `frontend-specialist`)

| # | Sev | Arquivo | Cenário de falha |
| --- | --- | --- | --- |
| H1 | HIGH | `hooks/useDensity.ts` | Usuário com densidade "Compacta": SSR calcula 28 linhas a 40 px, hidratação recalcula 31 a 32 px → mismatch estrutural, tabela inteira re-renderiza e as linhas saltam de altura em todo carregamento |
| H2 | HIGH | `lib/format.ts` (`formatUtcWithOffset`) | Usuário fora de UTC (Everton, UTC−3): servidor renderiza `(14:32:10 +00:00)`, cliente hidrata `(11:32:10 −03:00)` → erro de hidratação em cada linha de trade e no `aria-label` |
| H3 | HIGH | `components/system/readiness-panel.tsx` | Sem `API_URL`, a página System mostra vermelho "Indisponível (not_configured)" enquanto a topbar diz "sem verificação" — o alarme falso volta exatamente na página de diagnóstico, com token interno cru na copy |
| H4 | HIGH | `hooks/useArrowKeyRowSelection.ts` | Geometria ignora os 32 px do `thead` fixo: descendo com as setas, só 8 px da linha selecionada ficam visíveis (confortável); no compacto a 15ª linha fica inteiramente fora. O teste atual afirma `scrollTop === -32`, ou seja, codifica o bug |
| M1 | MED | `settings/appearance-form.tsx`, `design/motion-showcase.tsx` | `useState(isPriceFlashEnabled)` lê `localStorage` no initializer: quem desligou o flash hidrata com texto e `aria-checked` diferentes do SSR |
| M2 | MED | `markets/markets-table.tsx` | `role="grid"` numa `<div>` que embrulha uma `<table>` nativa → duas árvores de papel concorrentes, contagem de linhas/colunas inconsistente no NVDA/JAWS |
| M3 | MED | `markets/markets-table.tsx` | Selecionar uma linha, rolar com o mouse até ela sair da janela virtualizada e apertar Enter abre uma linha que não está na tela |
| M4 | MED | `markets/market-row.tsx` | `price_change_24h_pct === null` renderiza `--` em **verde** — cor afirmando "positivo" sobre dado ausente |
| M5 | MED | `globals.css`, `layout/sidebar.tsx` | `prefers-reduced-motion` só cobre `.flash-up`/`.flash-down`; a sidebar continua animando a largura |
| M6 | MED | `tests/theme-contrast.test.ts` | Rede de regressão só cobre `fg-subtle` sobre `bg`/`bg-elevated`; faltam `bg-overlay` e `gold-soft` (a linha selecionada da palette) |
| M7 | MED | `lib/api/markets-actions.ts` (segurança) | Server Action é um POST público e **falha aberta**: sem sessão ainda dispara a chamada à API sem `Authorization`, virando amplificador de requisição não autenticado |
| M8 | MED | `layout/command-palette.tsx` (segurança) | Debounce de 200 ms sem tamanho mínimo: alguns usuários digitando esgotam o balde de 120/min por IP que toda a renderização SSR compartilha → 429 nas páginas de todo mundo |
| M9 | MED | `command-palette.tsx`, `markets-table.tsx` | 2 warnings de lint (complexidade 13/12, 27 statements/20) — extrações baratas, `useMarketSearch` e `useVirtualizedRows` |
| L1–L3 | LOW | `command-palette.tsx`, `markets-table.tsx`, `topbar.tsx` | `encodeURIComponent` em `exchange`/`symbol`; anel de foco dourado no container da grade; "mercados indisponível" na topbar quando só o widget de status falhou |

## Achados rejeitados / adiados por decisão do orquestrador

| Item | Origem | Decisão |
| --- | --- | --- |
| Corpo da tabela em 13 px em vez de 14 px | Astra | **Fica.** Meio degrau abaixo da escala para caber as colunas numéricas sem truncar. Documentado como exceção explícita em `docs/DESIGN.md` §2 |
| Tooltip por componente no badge de qualidade ("qual componente está atrasado") | Astra | **M2.** Precisa de superfície de tooltip acessível por toque; fora do escopo do T1.5b |
| Reestruturar o modelo de scroll do `thead` fixo / adotar biblioteca de virtualização | Astra | **M2.** O sintoma concreto (H4) é aritmética e foi corrigido agora; a reestruturação é mudança de arquitetura |
| Frescor vs conexão no `live-status` ("CONNECTED" com eventos velhos) | Astra | **M2.** Depende de campo de idade por exchange que a API ainda não expõe |
| Explicação do ponto de status acessível por toque no mobile | Astra | **M2.** Mesmo requisito de tooltip acessível acima |
| Botão de tentar de novo no erro da palette | Astra | **M2.** Nice-to-have; o erro já é honesto e a nova busca reexecuta |
| Layout dos trades a 1024 px com sidebar aberta | Astra (inferência, não medida) | **M2.** Sem medição em navegador não há cenário provado |
| Tier de rate limit próprio para o servidor web na API | `security-reviewer` | **M2 / backend.** `apps/api/**` é de outra tarefa; o lado cliente (mínimo de 2 caracteres, debounce 250 ms, `q` limitado a 64) foi feito agora |
| Verificação geométrica de que conteúdo quebrado nunca aumenta a altura da `<tr>` | Astra | Registrado. `height` na `<tr>` é mínimo, não máximo; hoje o conteúdo mais alto é o badge (~22 px) < 32 px |

## Comandos de verificação

```
pnpm --filter @hunter/web lint        # alvo: zero warnings
pnpm --filter @hunter/web typecheck
pnpm --filter @hunter/web test
docker compose -f infra/docker/docker-compose.yml build web
```

---

## Segunda rodada de revisão (fix pass #1 → verificação, 2026-09-05)

Verificação minha, com saída real:

| Comando | Resultado |
| --- | --- |
| `pnpm --filter @hunter/web lint` | `$ eslint .` — exit 0, zero avisos |
| `pnpm --filter @hunter/web typecheck` | `$ tsc --noEmit` — exit 0 |
| `pnpm --filter @hunter/web test` | `Test Files 42 passed (42)` · `Tests 309 passed (309)` |
| `docker compose -f infra/docker/docker-compose.yml build web` | **falhou na primeira execução** (ver abaixo); verde depois do conserto: `Image hunter-web:dev Built`, exit 0 |

### O defeito que lint, typecheck e 309 testes verdes não pegaram

```
./lib/api/markets-actions.ts
Error: x Only async functions are allowed to be exported in a "use server" file.
  21 | export const MARKET_SEARCH_MAX_LENGTH = 64;
Import trace: ./lib/api/markets-actions.ts -> ./hooks/useMarketSearch.ts -> ./components/layout/command-palette.tsx
```

A constante introduzida pela correção do M8 quebrava o `next build`. Vitest não aplica as restrições do App Router, então os 309 testes passavam com o build quebrado. **Regra que fica: `docker compose build web` é obrigatório no aceite de qualquer tarefa de `apps/web`; lint + typecheck + Vitest não substituem o build de produção.**

Conserto: constante extraída para `apps/web/lib/api/markets-search.ts` (módulo sem diretiva), import repontado em `tests/markets-actions.test.ts`; removi o bloco de JSDoc órfão que sobrou em `markets-actions.ts`. Auditei todos os arquivos com `"use server"` em `apps/web` — os demais exportam só funções `async` e interfaces (tipos, apagados na compilação).

**Nota de procedência:** `lib/api/markets-actions.ts`, `lib/api/markets-search.ts` e `tests/markets-actions.test.ts` foram reescritos em disco às 13:39–13:40 por um processo fora desta sessão (provavelmente o `frontend-specialist` da instância anterior terminando). Conferi o conteúdo linha a linha antes de aceitar; a mudança é exatamente a extração acima e nada mais. `find apps/web -newermt` não achou nenhum outro arquivo tocado nessa janela.

### Revisores da segunda rodada

| Revisor | Veredito |
| --- | --- |
| `code-reviewer` (confirmação do fix pass) | APPROVE_WITH_NITS — H1–H4 e M1, M3–M9, L1–L3 FECHADOS com evidência; **M2 PARCIAL** |
| Astra (`astra.sh ask review-T1.5b-fixpass`) | "ainda não aprovaria" — H1–H4 fechados; **M2 ABERTO**, **M3 PARCIAL**, 1 achado novo |

Os dois revisores chegaram ao M2 de forma independente e pelo mesmo raciocínio — isso decidiu a questão sem precisar de desempate.

### Achados da segunda rodada (enviados ao `frontend-specialist`, fix pass #2)

| # | Sev | Arquivo | Cenário de falha |
| --- | --- | --- | --- |
| M2b | MED | `markets-table.tsx:263`, `markets-table-head.tsx`, `market-row.tsx` | `role="presentation"` na `<table>` cascateia para os descendentes estruturais (regra de conflito da WAI-ARIA): nenhum `<tr>`/`<th>`/`<td>` tem papel explícito, então o `role="grid"` externo expõe **zero linhas e zero colunas**. Usuário de NVDA/JAWS entra na tabela e ouve "grid" vazio; o `aria-activedescendant` aponta para uma `<tr>` sem semântica de linha. A navegação por setas construída no H4 não chega à tecnologia assistiva. Correção: árvore de papéis explícita (`row`/`columnheader`/`gridcell`) + `aria-rowcount`/`aria-rowindex`, porque a tabela é virtualizada |
| M3b | MED | `markets-table.tsx:180`, `useVirtualizedRows.ts:47` | O guard testa presença na janela de render, mas o overscan de 8 linhas põe no DOM linhas acima da dobra: selecionar a 1ª linha, rolar 160 px no confortável e apertar Enter navega para uma linha que está entre −128 px e −88 px do viewport. O teste atual só cobre um salto de 4000 px, quando a linha já saiu do DOM — não distingue *renderizada* de *visível* |
| S1 | MED | `usePriceFlash.ts:24,43`, `appearance-form.tsx:41` | `localStorage` **lança `SecurityError`** quando o armazenamento é negado (Safari com cookies bloqueados, política de navegador gerenciado). Cada linha da tabela chama `usePriceFlash`, então a exceção sobe do render e a página de mercados inteira fica em branco — perda total da tela por causa de uma preferência cosmética. Correção: helper único de storage tolerante a falha |
| S2 | LOW | `usePrefersReducedMotion.ts:19` | `matchMedia` no initializer do `useState`: servidor `false`, navegador com movimento reduzido `true` → mismatch de hidratação. Só alcançável pelo `/_design` (dev-only), mas é a mesma família do H1/M1 e são três linhas |
| D1 | LOW | `docs/DESIGN.md` | A escala documentada (12/14/16/20/28 + exceção de 13 px) omite 11 px de metadado, 10 px da dica de atalho e 18 px do showcase que a interface realmente usa — a próxima implementação seguiria uma regra que a tela não obedece |
| D2 | LOW | `docs/DESIGN.md`, `markets-empty.tsx`, `recent-trades.tsx`, `candles-chart.tsx` | A regra "todo empty state diz qual milestone traz o dado" não cabe em dado **já implementado e apenas ausente agora**. Decisão: não inventar milestone futuro; a regra passa a distinguir ausência operacional de funcionalidade não construída |

### Achados da segunda rodada rejeitados / adiados

| Item | Origem | Decisão |
| --- | --- | --- |
| Testes de hidratação real (SSR + hydrate) em vez de asserções pós-efeito | Astra | **M2 (milestone).** Astra tem razão que `appearance-form.test.tsx` e `motion-showcase.test.tsx` passariam com o bug antigo. Cobrir isso de verdade exige harness de SSR + hidratação no Vitest — infraestrutura de teste, não polimento de UI. O `use-density.test.tsx` já registra o primeiro render, que é o padrão a replicar |
| Medir visibilidade física / layout real (jsdom não faz layout) | Astra | **Fora de alcance do Vitest.** Fica para o E2E de Playwright do M2 |
| Tooltip por componente no badge de qualidade; frescor vs conexão no live-status; explicação do status por toque no mobile; retry na palette; layout dos trades a 1024 px | Astra (1ª rodada) | Mantidos em **M2**, sem mudança |
