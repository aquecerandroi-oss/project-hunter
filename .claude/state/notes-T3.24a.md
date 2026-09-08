# Notas T3.24a — design quick wins (frontend-specialist)

**Base:** `main` em `d91fac8`. **Brief:** `.claude/state/brief-T3.24-design-quick-wins.md`. **Escopo tocado:** `apps/web/**` (mais `pnpm-lock.yaml`/`apps/web/package.json` por uma dependência nova). Nada em `apps/api/**`, `.env*`, `docs/DESIGN.md`, `obsidian/**` — ver CONCERNS sobre `docs/DESIGN.md`.

## Comandos e saída real

```
$ export PATH="$HOME/.local/bin:/c/Program Files/nodejs:/c/Users/evert/AppData/Roaming/npm:$PATH"

$ pnpm --filter web add @radix-ui/react-checkbox
...
.                                        |   +1 +
Done in 11.8s using pnpm v11.25.0

$ pnpm --filter web lint
$ eslint .
(sem saída — 0 problemas)

$ pnpm --filter web typecheck
$ tsc --noEmit
(sem saída — 0 erros)

$ pnpm --filter web test
$ vitest run
 RUN  v5.0.0 C:/dev/project-hunter/apps/web
Not implemented: navigation to another Document
 Test Files  83 passed (83)
      Tests  804 passed (804)
   Duration  41.80s
```

`Not implemented: navigation to another Document` é um aviso pré-existente do jsdom (algum teste navega via `<a href>` real) — não é uma falha, o exit code é 0 e todos os 804 testes passam.

### Greps de aceite

```
$ grep -rn "text-\[10px\]" apps/web/components apps/web/app
apps/web/components/lab/lab-scoreboard-card.tsx:64   (fora do escopo — T3.24b)
apps/web/components/lab/lab-strategy-cell.tsx:27     (fora do escopo — T3.24b)
apps/web/components/lab/lab-version-card.tsx:52      (fora do escopo — T3.24b)
apps/web/components/layout/command-palette.tsx:69    (exceção viva, prevista pelo brief)

$ grep -rn "text-lg" apps/web/components apps/web/app --include=*.tsx | grep -v lab/
apps/web/app/(app)/[orgSlug]/lab/page.tsx:167 (h2 "Placar" -- rota do Lab, não é components/lab/**,
                                                mas é a mesma tela adiada para T3.24b; não toquei)
(nenhuma outra ocorrência -- as duas de /_design, que a doc pede migrar também
 [DESIGN §2: "o /_design dev-only migra também"], foram corrigidas: design-preview.tsx e
 motion-showcase.tsx)

$ grep -rn -E "T3\.[0-9]+|ADR 000" apps/web/components apps/web/app --include=*.tsx | grep -v _design
(dezenas de ocorrências -- todas dentro de comentários JSDoc/docstring, nenhuma em texto
 renderizado. A regra do DESIGN-5 é sobre COPY visível na tela ("nenhum id de tarefa... aparece
 na interface"), não sobre comentários de código -- ver CONCERNS #2.)
```

### Contraste (`tests/theme-contrast.test.ts`, 45 asserções, todas verdes)

Pares novos, valores exatamente os que o designer deixou em `contrast-tokens.md`/`review-design-2026-09-08.md`:

| Par | Escuro | Claro |
|---|---|---|
| `green` on `green-soft` | 6.75:1 | 4.57:1 |
| `red` on `red-soft` | 4.78:1 | 5.30:1 |
| `warning` on `warning-soft` | 7.44:1 | 5.33:1 |
| `info` on `info-soft` | 6.53:1 | 5.49:1 |
| `gold` on `gold-soft` | 7.34:1 | 5.14:1 |
| `bg` on `red` (botão destrutivo) | 5.26:1 | 6.47:1 |
| `fg-subtle` on `bg-elevated` (planejado, sem opacity) | 4.91:1 | 5.50:1 |
| `border-input` on `bg-overlay` (≥ 3:1) | 3.15:1 | 3.11:1 |
| `border-input` on `bg` (≥ 3:1) | 3.15:1 | 3.11:1 |

## O que mudou, por tela

- **Todo o app (tokens/componentes compartilhados):** `badge.tsx` (positive/negative/warning/info usam `-soft` sólido, não mais `bg-x/15`), `button.tsx` (`destructive` usa `text-bg`), `nav-links.tsx` (item "Planejado" sem `opacity-60`, foco dourado explícito nos dois estados), três tokens novos (`warning-soft`, `info-soft`, `border-input`) e três valores ajustados no tema claro (`gold`, `gold-strong`, `warning`) em `globals.css`.
- **Radar:** chips de Status/Estágio/Regime em português (`components/radar/labels.ts`), filtros com `ui/input`/`ui/select`/`ui/checkbox` (foco dourado, contorno ≥ 3:1) e unidades explícitas ("Score mínimo (0–100)", "Volatilidade mín./máx. (%)"), delta de score com sufixo " pts", idade `--` (era `—`), coluna de anomalias em português.
- **Carteira:** todo enum cru virou rótulo (`components/portfolio/labels.ts`): direção, lado, tipo/propósito/modo/status de ordem, status de posição/carteira, ator do kill switch, fonte de câmbio; card "Tipo" virou "Tipo · Status"; `PortfolioEmpty` sem "ADR 0005" (comando atrás de `<details><summary>Para o operador</summary>`); `PortfolioProposalsEmpty` sem id de tarefa, nomeia o M3; rodapé do `PortfolioRiskCard` reescrito sem caminho/id de tarefa.
- **System:** "Role" → "Papel", `alive/late/dead` → vivo/atrasado/morto, "Ready"/"Not Ready" → Pronto/Não pronto (`components/system/labels.ts`); `UnavailableSection` local virou `ui/section-unavailable.tsx` compartilhado, agora também usado por "Workers indisponível" (antes um `<p>` solto sem botão).
- **Markets:** cabeçalho "Status" → "Qualidade" (alinhado com o Radar); "Bids"/"Asks" → "Compras"/"Vendas"; `fundingKind` "estimated"/"realized" → "estimado"/"realizado"; busca da tabela usa `ui/input`.
- **Toda rota `(app)/[orgSlug]/**`:** `loading.tsx` (esqueleto decorativo, sem texto) e `error.tsx` (client, "Tentar novamente" + "Ver System", sem stack trace) — antes inexistentes.
- **Tipografia:** `text-[10px]` → `11px` em 4 arquivos nomeados; `text-lg` → `text-xl` em 11 arquivos nomeados + 2 do `/_design` (`design-preview.tsx`, `motion-showcase.tsx`, que a doc pede migrar também); `typography-scale.tsx` mostra os 8 degraus (11/12/13/14/16/20/24/28).
- **`/_design`:** pasta renomeada de `%5Fdesign` para `_design` (bug de path pré-existente, ver CONCERNS #1); `badges-showcase.tsx`/`buttons-showcase.tsx`/`inputs-showcase.tsx` mostram a razão de contraste calculada por `contrast.ts` ao lado de cada variante, nos dois temas.
- **Lab (uma linha só, autorizada pelo brief):** `LAB_TOTALS_SCOPE_NOTE` removida de `lab-money.ts`/`lab-totals-card.tsx`; `lab-result-badge.tsx` trocou `/15` por `-soft` (as duas linhas explicitamente liberadas).

## CONCERNS

1. **Bug pré-existente corrigido: `apps/web/app/_design` estava literalmente commitado como `apps/web/app/%5Fdesign`** (underscore percent-encoded no próprio nome do diretório, `git ls-files` confirma). Isso significa que `/_design` provavelmente NUNCA funcionou em dev — não só em produção (`NODE_ENV`) como o relatório T3.23 supôs. Corrigi com `git mv` porque bloqueava literalmente o requisito de aceite "`/_design` mostra a razão de contraste calculada" (a rota não existia). Path afetado: só `apps/web/app/_design/page.tsx` (era `%5Fdesign/page.tsx`). Também rodei `next typegen` para regenerar `.next/types` (cache stale apontando pro path antigo, causava erro de typecheck).
2. **`docs/DESIGN.md` não foi tocado**, apesar da seção 1 do brief pedir explicitamente a atualização da tabela §1. A regra operacional do despacho é explícita e teve prioridade: "não toque em... `docs/DESIGN.md` (só o designer edita)". Os três tokens novos e os três valores ajustados do tema claro estão implementados em `globals.css` e documentados nos comentários do próprio CSS (com a mesma justificativa/números que o designer calculou), mas a tabela §1 e a linha de histórico DESIGN-5→código continuam pendentes de o designer aplicar.
3. **Dois greps de aceite não fecham 100% zerados, por desenho, não por descuido:**
   - `text-[10px]`/`text-lg` continuam em `components/lab/**` e em `app/.../lab/page.tsx` — o brief proíbe explicitamente tocar `components/lab/**` ("é o brief T3.24b") e marca a tipografia do Lab como "(Lab em T3.24b)"; deixei a rota do Lab (`app/.../lab/page.tsx`) também intacta por ser a mesma tela, mesmo não estando no path literalmente restrito.
   - `grep -E "T3\.[0-9]+|ADR 000"` ainda acha dezenas de ocorrências: são comentários JSDoc de código (documentação de por que uma decisão foi tomada), nunca texto renderizado na tela. A regra do DESIGN-5 ("sem backstage na copy") é sobre a interface, não sobre comentários — os únicos lugares onde um id de tarefa aparecia na COPY visível (`PortfolioEmpty`, `PortfolioProposalsEmpty`, `PortfolioRiskCard`, `LAB_TOTALS_SCOPE_NOTE`) foram corrigidos. Scrubar todo comentário de código do repo estaria fora do escopo "mudanças cirúrgicas" e tocaria dezenas de arquivos não listados no brief.
4. **`ui/select.tsx` não usa Radix.** O brief pede "shadcn base" para input/select mas só nomeia Radix explicitamente para o checkbox. Os dois `<select>` do Radar (Regime, Tipo de anomalia) são dropdowns simples de valor único sem necessidade de portal/listbox customizado, então implementei como wrapper nativo com as mesmas classes de foco/contorno — mais simples, sem dependência nova, mesmo contrato visual. Se o designer quiser o Radix Select completo (trigger/content customizado), é um brief à parte.
5. **Enums reais divergem do que o relatório de auditoria assumia.** `MarketRegimeValue` real é `BTC_BULL/BTC_BEAR/SIDEWAYS/HIGH_VOLATILITY/LOW_VOLATILITY/RISK_ON/RISK_OFF/ALT_EXPANSION/PANIC/LIQUIDITY_CONTRACTION(+UNKNOWN)`, não o hipotético `TRENDING_UP/TRENDING_DOWN/RANGING/VOLATILE/UNKNOWN` do brief/relatório. Traduzi a partir do enum real e do `docs/PIPELINE.md` §4 (não inventei rótulos): "Alta de BTC", "Baixa de BTC", "Lateral", "Alta/Baixa volatilidade", "Apetite/Aversão a risco", "Expansão de altcoins", "Pânico", "Contração de liquidez", "Sem classificação". `AnomalyTypeValue` também tem `SOCIAL_SPIKE`/`WHALE_ACTIVITY` (Fase 2/3, já no contrato gerado, ainda sem detector) que o brief não listou — rotulei também, para o `Record` compilar exaustivamente.
6. **`lib/api/portfolio-types.ts` ganhou 7 aliases de tipo novos** (`OrderSide`, `OrderType`, `OrderPurpose`, `OrderStatus`, `ExecutionMode`, `PositionStatus`, `ExitReason`) — não existiam como exports nomeados, só usados inline via `components["schemas"][...]`. Precisei deles para tipar `components/portfolio/labels.ts` com `Record<Enum, string>` exaustivo. Esse arquivo não está nas restrições do brief (só `lab/**` e `lib/{format,time}.ts` são citados), mas registro a mudança por transparência.
7. **`@radix-ui/react-checkbox` é uma dependência nova** (`apps/web/package.json` + `pnpm-lock.yaml`). Precisei baixar do registry (rede disponível, ~12s). Nenhuma outra dependência nova.
8. **11 testes existentes precisaram de atualização** porque afirmavam o texto/comportamento antigo que este brief pediu para mudar (enum cru, "Ready"/"Not Ready", "Role", "alive", delta sem "pts", `LAB_TOTALS_SCOPE_NOTE`, footer do `PortfolioRiskCard`, fonte de câmbio crua). Lista completa na seção FILES da resposta final.
9. **Não usei o navegador/preview** (regra explícita da tarefa — "não use o navegador embutido"). A verificação visual real (spec `tests/e2e/design-audit.config.ts`) é do product-designer, conforme o brief já define.
10. **Diffs em `apps/api/**` visíveis no `git status` não são meus** — a árvore é compartilhada com outro agente (backend, aparentemente T3.7c/lab replication) trabalhando em paralelo; não toquei nenhum arquivo sob `apps/api/`.
11. **`apps/web/package.json` reordenou as listas de dependências inteiras** (ordem alfabética) como efeito colateral do próprio `pnpm add` — comportamento padrão do pnpm ao reescrever o arquivo, não uma reformatação manual minha. O diff funcional real é uma linha (`@radix-ui/react-checkbox`); as outras ~40 linhas do diff são só reordenação, sem mudança de versão.
