# Brief T3.24b — Lab: uma hierarquia (a tela central)

**Owner:** frontend-specialist. **Revisor:** product-designer (diff + tela renderizada com dado real antes do commit), Sexta-feira (copy). **Pré-requisitos:** T3.24a aplicado (tokens, `ui/input|select`, escala); decisão D3 do Everton (`review-design-2026-09-08.md` §"Só o Everton decide") — este brief implementa a **opção A** (Placar-primeiro, reorganizado); se ele escolher B ou C, o product-designer reescreve a §2 antes do dispatch; segunda opinião da Astra registrada em `.claude/state/astra-review-design-lab.md`. **Base:** `main` ≥ T3.24a. **Regras:** não commitar; foreground ≤ 5 min; sem testcontainers; nunca `.env*`; árvore compartilhada. Escopo: `apps/web/components/lab/**`, `apps/web/app/(app)/[orgSlug]/lab/**`, `apps/web/app/_design/**` (mockup), testes em `apps/web/tests/lab-*.test.tsx`. Não tocar a API nem `lib/format.ts`.

## 1. Problema (relatório L1–L11)

O banner "SOMBRA — hipotético" vem **depois** do Placar com dinheiro; três resumos (Placar, cards de versão abertos, totais com 12 tiles) antes da primeira linha de sinal; guia única "Sombra" inerte; fatos-chave só em `title`; léxico cru (`Cohort`/`prospective`, `active`, `code_ref`, `target: 3`, `n=, ordenada por exit_ts`); 18px/10px fora da escala; tabela com rolagem horizontal já no desktop quando o painel está aberto.

## 2. Ordem da página (opção A)

```
h1 Lab
[1] Faixa SOMBRA (1–2 linhas, border-l-4 gold, bg-elevated)            <- LabHeader movido para cima e compactado
[2] PLACAR (eyebrow)  cards por versão (grid 2 col lg) + curva 200px    <- LabScoreboardSection + LabCurveSection
[3] SINAIS — SOMBRA (eyebrow) | guias: Concluídas (n) · Abertas (n) · Pendentes/sem entrada (n) · Todas (n)
     filtros: Janela do resumo | Coorte (select) | Versão (select)      <- LabFilters, mesma linha das guias no lg
     totais em UMA linha (4 stats) [mais ▾ -> os 12]                    <- LabTotalsCard colapsado
     tabela + painel lateral                                             <- LabSignalsTable
     nota visível: "Valores simulados: dado real, custos assumidos, sem dinheiro."
[4] VERSÕES (PESQUISA) (eyebrow)  1 linha por versão, colapsada          <- LabVersionCard com <details>
```

### [1] `lab-header.tsx`
- Uma frase forte 14px `fg`: "SOMBRA — simulação sobre dado real. Nada foi comprado ou vendido." Segunda linha 12px `fg-muted`: "Régua: 0,25% de {equity} ({fonte}) = {risco} por operação · custos assumidos: {custos} · consultado em {BrasiliaInstant}". Sem o terceiro parágrafo (redundante). Manter `data-testid`s (`lab-header`, `lab-money-banner`, `lab-money-ruler`) — os testes existentes dependem deles.
- Renderizar em `lab/page.tsx` **antes** da `<section>` do Placar; quando `loadLab` falha, a faixa continua (com "régua: carteira de referência").

### [2] Placar
- `lab-scoreboard-card.tsx`: `MoneyStat` valor `text-lg` → `text-xl`; chip de propósito `text-[10px]` → `text-[11px]`; `sinceText` em 11px `fg-subtle` fica. Status cru → `components/lab/labels.ts` (`ativa`/`substituída`/`rascunho`; `paper`→"paper", `research_only`→"pesquisa" já existe em `purposeLabel` — mover para `labels.ts`).
- `lab-curve-chart.tsx`: `CHART_HEIGHT` 280 → 200; legenda mantém; "(capado em 2.000 pontos)" → "(primeiros 2.000 pontos)"; "(curva indisponível: falha ao carregar)" fica.
- Erro do Placar em `lab/page.tsx`: usar `SectionUnavailable` (T3.24a) em vez do `<p class="text-red">`.
- Título "Placar": eyebrow 12px maiúsculo `fg-muted` (padrão X2) + subtítulo 12px existente.

### [3] Sinais
- `lab-tabs.tsx`: **remover** a guia única; o título da seção passa a "Sinais — Sombra" (eyebrow). `LAB_TABS` some (sem item inerte — CLAUDE.md).
- `lab-segment-tabs.tsx`: vira a guia principal da seção (mesma aparência, `aria-label` "Sinais por estado"); guia ativa com `border-gold bg-gold-soft text-gold` (contraste ok após T3.24a).
- `lab-filters.tsx`: `Cohort` → rótulo "Coorte", `<select>` (`ui/select`) com as coortes distintas presentes em `signals.items` + "prospective (padrão)" — sem input livre; "Janela do resumo" e "Versão (lista de sinais)" mantêm; usar `ui/select` (anel de foco).
- `lab-totals-card.tsx`: modo compacto por padrão — 4 `Stat` em uma linha (`grid-cols-2 sm:grid-cols-4`): "Operações", "Com lucro / prejuízo" (`{n} / {m}` com cores), "Taxa de acerto", "Resultado acumulado" (USDT + BRL em 11px abaixo); botão `ghost sm` "Mais detalhes" (`aria-expanded`) abre as demais 8 (médias, melhor/pior, pendentes/censuradas). Heading `totalsHeading` fica; `LAB_TOTALS_SCOPE_NOTE` já removida (T3.24a). Valores `text-lg` → `text-xl`.
- `lab-signals-table.tsx`: `PERIOD_TOOLTIP` vira texto visível 11px `fg-subtle` abaixo das guias: "período: todo o disponível — a janela acima só filtra o resumo"; `MONEY_TOOLTIP` sai dos `title` de célula e vira **uma** nota 11px no rodapé da tabela ("Valores simulados: dado real, custos assumidos, sem dinheiro."). Colunas: no `lg` com `selectedSignal !== null`, esconder `Duração` e `Quantia simulada` (`hidden xl:table-cell` quando painel aberto — ambas estão no painel); abaixo de `md`, colunas essenciais = Estratégia, Mercado, Resultado (badge + USDT); Quando/Entrou/Saiu/Variação viram `hidden md:table-cell`. `min-w-[150px]` do "Resultado" fica.
- `lab-signal-panel.tsx`: "Detalhe de pesquisa" eyebrow ok; `Referência`, `Stop`, `Alvo`, `Entrada virtual`, `Saída` ok; "R líquido"/"R ex-funding" ficam (termo do domínio, atrás do rótulo "Detalhe de pesquisa"); "Ver envelope" → "Ver dados brutos (JSON)". Panel `lg:w-96` → `lg:w-80 xl:w-96`.
- `lab-signal-chips.tsx`/`lab-funnel.tsx`: resultados terminais `target: 3` → usar `EXIT_REASON_LABEL` ("alvo: 3"); "Funding não apurável" ok; "Avaliações (decisões)" ok.
- `lab-market-link.tsx`: sublinhado permanente `underline decoration-dotted underline-offset-2` (é um link, deve parecer um).

### [4] Versões (pesquisa)
- `lab-version-card.tsx`: envolver o corpo em `<details>` com `<summary>` = linha única: badge status (rótulo pt) · `strategy_key / version` · chip propósito · `LabMaturityBadge` compacto (só "Inconclusivo · 37/100 · 2/30 dias") · "substituída por …". Aberto por padrão **só** quando `?version=` na URL aponta para ela. `code_ref` → dentro do corpo, rótulo "Código: {hash curto 7}" com `title` = hash completo. "PnL de carteira: não aplicável ({reason})" → `reasonLabel(reason)`. `r_ex_funding (mesma população, sem funding)` → "Sem funding (mesma população)" com o nome técnico em `title`. "n=…, ordenada por exit_ts" → "{n} resultados, em ordem de saída".
- `lab-versions-empty.tsx`: "Nenhuma versão de estratégia ativa nesta janela e coorte. Zero versões é um resultado, não uma falha — versões são ativadas pelo operador, fora desta tela."
- `lab-maturity-badge.tsx`: "outcomes avaliáveis" → "resultados avaliáveis"; "-- não é erro, é a regra editorial" → "— ainda pesquisa, nunca promessa" (uma frase para os dois estados).

## 3. Mockup no `/_design` (antes de mexer no Lab)

`components/design/lab-hierarchy-showcase.tsx` com as opções **A** e **B** do relatório lado a lado, usando os componentes reais (`LabScoreboardCard`, `LabSignalRow`, `LabSegmentTabs`) e os fixtures dos testes `lab-*.test.tsx` (dados reais gravados, rotulados "fixture de teste, dado de {data}"). O product-designer valida o mockup renderizado (dark/light, 1440/375) antes da implementação; o Everton escolhe.

## Aceite

- `pnpm --filter web lint|typecheck|test` verdes; testes existentes do Lab atualizados (não removidos): `lab-header`, `lab-scoreboard`, `lab-signals-table`, `lab-totals`, `lab-version-card`.
- Novos testes: ordem do DOM (`lab-header` antes de `lab-scoreboard-section`; `lab-scoreboard-section` antes de `Sinais do Shadow Lab`); totais compactos mostram 4 stats e "Mais detalhes" abre 8; `<details>` da versão fechado por padrão e aberto com `?version=`; coorte é `<select>` sem input livre; nenhuma célula da tabela tem `title` com o texto de `MONEY_TOOLTIP` e a nota aparece 1×; `grep -rn "text-\[10px\]\|text-lg" apps/web/components/lab` vazio; labels: todo membro de status/purpose/result/tracking tem rótulo em pt sem `_`.
- Tela real (product-designer, spec `design-audit`; **pré-condição:** sign-up de teste destravado na instância Clerk — relatório E3, `notes-T3.24d.md` §3; a `ever` local já tem carteira principal, então a régua do Lab renderiza com a carteira real, não a "de referência"): em 1440 com painel aberto a tabela **não** rola horizontalmente (`metrics-lab-detail-1440-*.json` `overflowers` vazio dentro do grid); em 375 as 3 colunas essenciais cabem; primeira linha de sinal visível acima de 1 200px de rolagem em 1440 (medir `getBoundingClientRect().top` da primeira `tr[role=row]` no spec).
- `docs/DESIGN.md` §3 ganha o âncora "Lab (Sombra)": ordem faixa → placar → sinais → versões, e a regra "nota de simulação visível uma vez por tabela, nunca só em tooltip".
