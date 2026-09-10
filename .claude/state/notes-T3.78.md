# notes-T3.78 — "Meta diária" no Placar: `GET /api/v1/orgs/{org_id}/lab/daily-goal`

**Data:** 2026-09-10. **Owner:** backend-specialist. **Base:** árvore compartilhada, nada
commitado, nada tocado em `apps/web/**`, `services/**`, `packages/risk-core/**`. Nenhum `.env*`
tocado. Nenhuma migração criada. Todo comando em primeiro plano, `timeout 290`. Testcontainer: um
arquivo por vez (`test_lab_daily_goal_api.py`).

---

## STATUS: DONE_WITH_CONCERNS

| # | Entrega do brief | Resultado |
|---|---|---|
| 1 | `GET /api/v1/orgs/{org_id}/lab/daily-goal` com o schema descrito | **OK**, com simplificações declaradas (§4 CONCERNS) |
| 2 | Repositório RLS, leitura só, caminho indexado; um testcontainer (dedupe/participação/FX ausente); testes unitários da aritmética | **OK** — §3 |
| 3 | Docs (`PRODUCT.md`, `RISK_ENGINE.md`), `notes-T3.78.md` com schema congelado | **OK** |

---

## 1. Schema congelado (freeze para o frontend-specialist)

```
GET /api/v1/orgs/{org_id}/lab/daily-goal?day=YYYY-MM-DD   (VIEWER+)
```

`day` default: hoje em America/Sao_Paulo. Exemplo de resposta real (cenário
"participação morde" do testcontainer, valores exatos — ver §3.2):

```json
{
  "day": "2026-09-06",
  "as_of": "2026-09-10T18:40:00.123456Z",
  "axis": { "used": "r_net", "pooled_funding_null": 0, "unique_funding_null": 0 },
  "dedupe_order": "activated_at asc, strategy_version_id asc, signal_id asc",
  "unique_bets": 1,
  "pooled_bets": 1,
  "unique_r": "1",
  "pooled_r": "1",
  "hit_rate": { "value": "1", "reason": null, "numerator": 1, "denominator": 1 },
  "r_per_unique_bet": "1",
  "value_of_1r": {
    "label_brl": "250.00",
    "real_brl_p10": "140",
    "real_brl_p50": "140",
    "real_brl_p90": "140",
    "sample_size": 1,
    "reason": null
  },
  "goal_brl": "9000",
  "progress": {
    "real_brl": "140",
    "label_brl": "250.00",
    "distance_to_goal_real_brl": "8860",
    "distance_to_goal_label_brl": "8750.00",
    "required_1r_brl": "9000",
    "required_unique_r": "64.28571428571428571428571429"
  },
  "portfolio": { "equity_usdt": "20000.0000000000", "source": "equity_snapshot" },
  "fx_reason": null,
  "series_30d": [ { "day": "2026-08-08", "unique_r": "0", "pooled_r": "0" }, "... 30 pontos" ]
}
```

**Campos e regras, por nome:**

- `axis.used` é sempre `"r_net"` (o `signal_outcomes.r_multiple` persistido, líquido de custo).
  Nunca cai para um `r_ex_funding` recomputado — ver CONCERN 1.
- `unique_bets`/`pooled_bets`: apostas deduplicadas (`(market_id, source_bar_close)`) e linhas
  brutas (toda versão), respectivamente, entre os desfechos **fechados** (`exit_ts` no dia) da
  coorte `prospective` (replay/replicação nunca entram — D15).
- `dedupe_order`: **vence a versão com `activated_at` mais antigo**; desempate por
  `strategy_version_id`, depois `signal_id`. Publicado como string fixa no payload, não só em doc.
- `value_of_1r.label_brl` = `PAPER_V1.risk_per_trade_pct × R$100.000` (0,25 % × 100.000 = R$250),
  constante, não depende do dia.
- `value_of_1r.real_brl_p10/p50/p90`: percentil "nearest-rank" (não interpolado) sobre o valor de
  1R em BRL de cada aposta única precificável naquele dia. Precificação de uma aposta:
  `notional = min(equity_usdt × risk_per_trade_pct / d_efetiva, max_participation_pct × volume_1m)`,
  `valor_1R_usdt = notional × d_efetiva`, convertido pela `fx_observations` mais recente disponível
  até o fim do dia. `sample_size = 0` e `reason` preenchido (`"no_bets"`, `"no_priceable_bets"`,
  `"no_fx_observation"`) quando nada foi precificável — nunca um número.
- `progress.required_1r_brl` = `goal_brl / unique_r` (null se `unique_r <= 0`).
  `progress.required_unique_r` = `goal_brl / real_brl_p50` (null se `real_brl_p50` nulo/≤0).
- `portfolio.source`: `"equity_snapshot"` (achou um ponto em `portfolio_equity_snapshots`),
  `"opening_anchor"` (carteira aberta, sem snapshot ainda — usa `credited_amount`) ou
  `"no_portfolio"`.
- `fx_reason`: `null` ou `"no_fx_observation"` — nunca uma taxa adivinhada.
- `series_30d`: 30 pontos, do dia `−29` ao dia consultado, `unique_r`/`pooled_r` por dia (mesmo
  eixo, mesmas regras de exclusão do funding-nulo).

## 2. Arquivos

**Backend:**
- `apps/api/hunter_api/repositories/lab_daily_goal.py` — leituras (globais de pesquisa + a única
  tenant: equity da carteira principal)
- `apps/api/hunter_api/services/lab_daily_goal_bets.py` — dedupe e as duas somas de R (puro)
- `apps/api/hunter_api/services/lab_daily_goal_sizing.py` — valor de 1R e percentil (puro)
- `apps/api/hunter_api/services/lab_daily_goal.py` — orquestração (IO + monta a resposta)
- `apps/api/hunter_api/schemas/lab_daily_goal.py` — Pydantic
- `apps/api/hunter_api/routers/lab_daily_goal.py` — rota
- `apps/api/hunter_api/app.py` — registra o router
- `apps/api/hunter_api/settings.py` — `ApiSettings.daily_goal_brl` (Decimal, default 9000)

**Testes:**
- `apps/api/tests/unit/test_lab_daily_goal_bets.py` — 9 casos (dedupe, somas, funding-nulo)
- `apps/api/tests/unit/test_lab_daily_goal_sizing.py` — 12 casos (precificação, rótulo, percentil)
- `apps/api/tests/integration/test_lab_daily_goal_api.py` — testcontainer, 6 casos (auth, 404,
  dedupe 3×1, EXPLAIN, participação morde, FX ausente)

**Docs:** `docs/PRODUCT.md` §4.2, `docs/RISK_ENGINE.md` §4 (uma frase), este arquivo.

## 3. Comandos e saídas reais

### 3.1 Unitários

```
$ timeout 120 uv run pytest apps/api/tests/unit/test_lab_daily_goal_bets.py apps/api/tests/unit/test_lab_daily_goal_sizing.py -q
.....................                                                    [100%]
21 passed in 0.47s

$ timeout 290 uv run pytest apps/api/tests/unit -q -m unit
... 556 passed, 18 deselected, 1 warning in 71.03s
```

### 3.2 Testcontainer (um arquivo, Postgres real)

```
$ timeout 290 uv run pytest apps/api/tests/integration/test_lab_daily_goal_api.py -q -p no:randomly --tb=short
......                                                                   [100%]
6 passed in 43.06s
```

O caso "participação morde": mercado com `quote_volume` de 1 minuto = 200.000 USDT, carteira aberta
com R$100.000 a 5,00 BRL/USDT (equity = 20.000 USDT), aposta com distância de stop 1 % + custo de
ida-e-volta 0,4 % (`d_efetiva = 1,4 %`). Teto de participação = 1 % × 200.000 = 2.000 USDT; orçamento
de risco = 20.000 × 0,25 % / 1,4 % = 3.571,43 USDT — a participação vence. `valor_1R_usdt` = 2.000 ×
1,4 % = 28; em BRL, 28 × 5,00 = **R$140** — a asserção exata do teste.

O EXPLAIN do caminho de leitura (por versão, filtrando `agent_signals.emitted_at`) usa
**`ix_agent_signals_version_cohort_emitted`** (migração `0014_lab_signals_indexes`,
`(strategy_version_id, cohort, emitted_at, id)`) — melhor que o índice que eu tinha citado no
primeiro rascunho do docstring (`ix_agent_signals_version_emitted`, sem a coluna de cohort);
corrigido no código e neste arquivo.

### 3.3 Portões

```
$ timeout 120 uv run ruff check <10 arquivos meus>            -> All checks passed!
$ timeout 60  uv run ruff format --check <10 arquivos meus>   -> already formatted
$ timeout 290 uv run pyright <10 arquivos meus>                -> 0 errors, 0 warnings
$ timeout 120 uv run python infra/scripts/check_file_size.py  -> scanned 612 files; 0 over budget
```

## 4. CONCERNS

1. **`axis` nunca cai para `r_ex_funding`.** Um desfecho terminal com `r_multiple` nulo
   (funding-schedule-unknown, T3.75) é excluído das somas e contado em
   `axis.pooled_funding_null`/`unique_funding_null` — nunca recomputado. Recomputar exigiria chamar
   `resolve_funding`/`settle()` de dentro de uma rota de leitura, fora do escopo deste brief
   (`infra/scripts/recompute_funding.py` é o caminho de escrita correto, e é uma decisão do
   Everton, não deste endpoint).
2. **`value_of_1r` usa só duas travas (participação e risco por operação), não o motor inteiro.**
   O brief pede especificamente "sob `max_participation_pct`"; o resto dos tetos
   (book, exposição por moeda/total, beta, agregado) precisa do histórico de posições concorrentes
   do dia inteiro — é o que `t360/carteira.py` faz, não uma leitura por requisição. Isso só pode
   fazer `real_brl` ficar **maior** do que uma simulação de carteira completa encontraria (T3.60 §9
   já registra o mesmo viés nas próprias travas neutralizadas do simulador).
3. **`entry_minute_quote_volume` lê uma barra, não a mediana de 30 que o T3.60 usava** para
   amortecer ruído de um minuto isolado. Ambos leem a mesma tabela `candles` e o mesmo
   `max_participation_pct`; a diferença é só o amortecimento.
4. **Sem índice em `signal_outcomes.exit_ts`.** A consulta filtra por
   `agent_signals.emitted_at` (indexado, por versão) com uma folga de `_MAX_HOLDING_DAYS = 2` e
   recorta o `exit_ts` exato em Python. Um sinal com mais de 48h entre decisão e saída seria
   perdido — nenhuma estratégia hoje segura posição por tanto tempo (`docs/PIPELINE.md` §2), mas é
   uma suposição, não uma garantia do schema.
5. **A combinação "equity presente, FX ausente" é estruturalmente inalcançável pelo caminho real de
   abertura de carteira** (abrir uma carteira exige uma observação de FX, que automaticamente passa
   a satisfazer "FX disponível até este instante"), então o testcontainer prova "FX ausente" com
   `portfolio.source = "no_portfolio"` simultaneamente — não isolei os dois motivos com dado real.
   Não escrevi um teste de unidade com repositório falso para cobrir esse ramo isoladamente
   (`_price_bets`/`build_daily_goal` quando `fx is None and priced_usdt` não é vazio); é código
   coberto por leitura, não por teste automatizado.
6. **Rota tenant, dado majoritariamente global.** Como o resto do Shadow Lab
   (`/api/v1/lab/shadow/*`), a pesquisa (`agent_signals`/`signal_outcomes`/`strategy_versions`) não
   tem `organization_id` e é lida sem filtro de RLS de propósito (DATABASE.md §16). A única leitura
   realmente tenant é o equity da carteira principal. Documentado no docstring do router; se isso
   não for a leitura pretendida pelo Everton, é uma pergunta de produto, não um bug.
7. **`goal_brl` é uma config de processo (`ApiSettings.daily_goal_brl`, default 9000), não uma
   tabela.** Trocar o valor por organização exigiria uma coluna nova; não há uma hoje e o brief não
   pediu.

## 5. `git status --porcelain` (só os meus arquivos)

```
 M apps/api/hunter_api/app.py
 M apps/api/hunter_api/settings.py
 M docs/PRODUCT.md
 M docs/RISK_ENGINE.md
?? .claude/state/brief-T3.78-meta-diaria.md
?? .claude/state/notes-T3.78.md
?? apps/api/hunter_api/repositories/lab_daily_goal.py
?? apps/api/hunter_api/routers/lab_daily_goal.py
?? apps/api/hunter_api/schemas/lab_daily_goal.py
?? apps/api/hunter_api/services/lab_daily_goal.py
?? apps/api/hunter_api/services/lab_daily_goal_bets.py
?? apps/api/hunter_api/services/lab_daily_goal_sizing.py
?? apps/api/tests/integration/test_lab_daily_goal_api.py
?? apps/api/tests/unit/test_lab_daily_goal_bets.py
?? apps/api/tests/unit/test_lab_daily_goal_sizing.py
```

`packages/core/hunter_core/settings.py` foi editado e revertido na mesma sessão (o campo mudou de
lugar para `ApiSettings`, que já herda de `Settings`) — diff líquido zero, por isso não aparece
acima. Não toquei `apps/web/**`, `services/**`, `packages/risk-core/**`, nem qualquer `.env*`. Não
criei migração.

## 6. Em dez linhas (português)

1. A API existe: `GET /api/v1/orgs/{org_id}/lab/daily-goal`, VIEWER+, schema congelado acima.
2. `unique_r`/`pooled_r` reusam a dedupe da T3.60 `(mercado, barra)`, vencendo a versão mais antiga.
3. `label_brl` = R$250 fixo; `real_brl_p10/p50/p90` vem do volume real de 1 minuto sob o teto de
   participação do `hunter_risk.limits.PAPER_V1` — nunca reimplementei um limiar.
4. `progress.required_1r_brl`/`required_unique_r` respondem "quanto falta" nas duas réguas.
5. `axis` nomeia o eixo (`r_net`) e conta quem ficou de fora por funding nulo — nunca mistura.
6. FX ou carteira ausentes viram `null` com motivo nomeado, nunca um número adivinhado.
7. Testcontainer prova dedupe 3-para-1, participação mordendo (R$140/R) e FX ausente, em um arquivo.
8. 21 testes unitários de aritmética pura, sem IO.
9. `real_brl` é teto superior: só participação e risco por operação, não a carteira inteira do dia
   (T3.60 mede o motor completo; aqui é uma leitura por requisição, mais barata e mais otimista).
10. Nada em `apps/web`, `services`, `packages/risk-core`; nenhuma migração; nada commitado.

---

## 7. Web — painel "Meta diária" (T3.78, frontend-specialist, 2026-09-10)

### STATUS: DONE_WITH_CONCERNS

Consome o schema congelado em §1 exatamente como publicado, sem editar `apps/api/**`.

### 7.1 Arquivos

- `apps/web/lib/api/lab-daily-goal-types.ts` — `zod` mirror do `DailyGoalOut` (não passou por
  `pnpm gen:types` ainda, mesma convenção de `manual-orders-types.ts`).
- `apps/web/lib/api/lab-daily-goal.ts` — `getLabDailyGoal(orgId, {day?})`, `"server-only"`,
  `.parse()` antes de confiar na resposta.
- `apps/web/components/lab/lab-daily-goal-format.ts` — formatação/mapeamento puro (dedupe, eixo,
  taxa de acerto, `null` → frase com motivo, cor semântica da meta, "sobrou"/"faltam" com sinal
  correto).
- `apps/web/components/lab/lab-daily-goal-sparkline.tsx` — SVG sem biblioteca, `sparklineGeometry`
  pura exportada para teste; `stroke="currentColor"` (compatível com os dois temas sem branch).
- `apps/web/components/lab/lab-daily-goal-date-picker.tsx` — `<input type="date">` client,
  reescreve `?day=` (mesma convenção de `lab-filters.tsx`).
- `apps/web/components/lab/lab-daily-goal-panel.tsx` — o painel em si (Server Component).
- `apps/web/app/(app)/[orgSlug]/lab/page.tsx` — `loadDailyGoal` isolado (falha própria vira
  `SectionUnavailable`, nunca derruba o resto de `/lab`), painel inserido logo após `LabHeader` e
  antes do Placar (topo do scoreboard, por brief); `DailyGoalSection` extraído para manter a
  complexidade de `LabPage` dentro do orçamento do lint.

### 7.2 Testes (novos)

- `apps/web/tests/lab-daily-goal-types.test.ts` — parse do exemplo real do §1 verbatim, ramos
  `null`+motivo (FX ausente, sem apostas), rejeita drift de tipo (`goal_brl` número).
- `apps/web/tests/lab-daily-goal.test.ts` — path/query, `.parse()` na resposta.
- `apps/web/tests/lab-daily-goal-format.test.ts` — dedupe/eixo/taxa de acerto/meta/sinal de
  distância/"o que 1R precisaria valer"/"quantos R únicos faltariam", todos os ramos `null`.
- `apps/web/tests/lab-daily-goal-sparkline.test.ts` — geometria pura (flat series, flip de Y,
  espaçamento, linha de zero só quando cruza zero).

### 7.3 Comandos e saídas reais

```
$ cd apps/web && npx vitest run tests/lab-page.test.tsx tests/lab-daily-goal-format.test.ts \
    tests/lab-daily-goal.test.ts tests/lab-daily-goal-types.test.ts tests/lab-daily-goal-sparkline.test.ts
 Test Files  5 passed (5)
      Tests  57 passed (57)

$ npx turbo run typecheck lint test --filter=@hunter/web
@hunter/web:typecheck: $ tsc --noEmit   -> sem erros
@hunter/web:lint: $ eslint .            -> 0 errors, 2 warnings (pré-existentes: tests/lab-page.test.tsx
                                            e tests/ws.test.ts, ambos > 350 linhas antes desta tarefa,
                                            não tocados aqui)
@hunter/web:test:                       -> Test Files 126 passed (126); Tests 1183 passed (1183)
 Tasks:    3 successful, 3 total
```

Playwright não foi executado: sem servidor dev rodando e o Chromium deste ambiente não alcança
`localhost`/Clerk (nota de memória "in-app-browser-limits" já registrada) — checagem visual
logada só é possível fora deste sandbox.

### 7.4 CONCERNS (frontend)

1. **Lucro real em USDT não é exibido como número.** O schema congelado (§1) publica só
   `real_brl_p10/50/90` e `progress.real_brl` — nunca o valor em USDT nem a taxa FX usada para
   chegar até ele. Converter o BRL de volta para USDT por uma razão diferente (ex.: a proporção
   atual `equity_brl/equity_usdt` da carteira, já calculada por `lab-money.ts` para outra parte da
   tela) seria misturar duas fontes/dois instantes de câmbio e produzir um número projetado
   vestido de real — na contramão explícita da regra de Everton. O painel mostra uma frase fixa e
   honesta (`USDT_PROFIT_UNAVAILABLE_REASON`) em vez de um valor. Se Everton quiser o USDT na tela,
   é o backend quem precisa publicar `real_usdt_p50` (ou o `fx_rate` observado) no schema — mudança
   de contrato, fora do escopo "frontend consome o schema congelado" deste brief.
2. **`goalStatus`/cor semântica dependem só de `progress.real_brl`.** Segue a regra literal de
   Everton (verde só com valor real >= meta); um dia com `real_brl` nulo (FX ausente, sem apostas)
   sempre renderiza neutro, nunca "quase lá" por extrapolação do rótulo fictício.
3. Não toquei `apps/api/**`, nenhum `.env*`, nenhum commit.

### 7.5 `git status --porcelain` (só os meus arquivos)

```
 M apps/web/app/(app)/[orgSlug]/lab/page.tsx
?? apps/web/components/lab/lab-daily-goal-date-picker.tsx
?? apps/web/components/lab/lab-daily-goal-format.ts
?? apps/web/components/lab/lab-daily-goal-panel.tsx
?? apps/web/components/lab/lab-daily-goal-sparkline.tsx
?? apps/web/lib/api/lab-daily-goal-types.ts
?? apps/web/lib/api/lab-daily-goal.ts
?? apps/web/tests/lab-daily-goal-format.test.ts
?? apps/web/tests/lab-daily-goal-sparkline.test.ts
?? apps/web/tests/lab-daily-goal-types.test.ts
?? apps/web/tests/lab-daily-goal.test.ts
```
