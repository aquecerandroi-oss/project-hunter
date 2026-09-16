---
tags: [trading, meme, pumpfun, estudo, risco, execucao, estagio-1, admissao, dinheiro-real]
titulo: O que a admissão real recusa além do primeiro motivo — as 16 ordens do estágio 1
status: vivo
owner: astra-quant
data: 2026-09-16
updated: 2026-09-16
tarefa: R5
---

# Estudo R5 — o que a admissão real recusa além do primeiro motivo (16/09/2026)

> Fonte: `meme_live_orders` na VPS (todas as 16 ordens do dia, 11:46–15:33 BRT), `meme_features_1m`,
> `meme_risk_snapshots`, `meme_tokens`, `meme_proposals`. Consultas em
> `infra/scripts/sql/research/2026-09-16-r5-q0{1..4}-*.sql`. Horas em BRT.
> Contrato: `docs/RISK_ENGINE_MEME.md` §4 (as 25 checagens) e §3.1 (os limites do perfil).
> Contexto do dia: `obsidian/09-OPERATIONS/Diario/2026-09-16.md`, `.claude/state/notes-T4.28e.md`.

**O fato que este estudo desmonta:** `meme_live_orders.reason` guarda **só a primeira** recusa. Hoje
ele diz `progress_above_window` (10), `progress_below_window` (5) e `creator_flow_unknown` (1) — e por
isso a leitura fácil do dia é "é só arrumar o progresso e a gente compra". **Não é.** As 25 checagens
são todas avaliadas e gravadas em `admission->'checks'` mesmo depois da primeira reprovada (§4), e
elas mostram que **nenhuma das 16 ordens** teria passado se o progresso fosse corrigido: em 15 das 16
havia pelo menos uma segunda recusa, e a mais frequente é um insumo que **ainda não existia**.

---

## 1. Ordem × checagem — todas as reprovações, não só a primeira

16 ordens, 7 mints, 25 checagens cada. Abaixo, toda checagem com `state <> passed`
(as omitidas passaram). `valor` e `limite` são os do próprio `admission->'checks'`.

| # | hora | mint | motivo gravado | checagem | estado | recusa | valor | limite |
|---|---|---|---|---|---|---|---|---|
| 1 | 11:46:36 | FHcHh1 | progress_below_window | curve_progress | failed | progress_below_window | −541 546,797 | 0,02 |
| | | | | bundled_share | unavailable | bundled_share_unmeasurable | — (nulo) | 0,20 |
| | | | | creator_behaviour | unavailable | creator_flow_unknown | — (nulo) | — |
| 2 | 11:46:55 | FHcHh1 | progress_below_window | curve_progress | failed | progress_below_window | −554 166,980 | 0,02 |
| | | | | bundled_share | unavailable | bundled_share_unmeasurable | — | 0,20 |
| | | | | creator_behaviour | unavailable | creator_flow_unknown | — | — |
| 3 | 11:47:18 | FHcHh1 | progress_below_window | curve_progress | failed | progress_below_window | −657 115,148 | 0,02 |
| | | | | bundled_share | unavailable | bundled_share_unmeasurable | — | 0,20 |
| | | | | creator_behaviour | unavailable | creator_flow_unknown | — | — |
| 4 | 11:47:55 | FHcHh1 | progress_below_window | curve_progress | failed | progress_below_window | −425 330,841 | 0,02 |
| | | | | bundled_share | unavailable | bundled_share_unmeasurable | — | 0,20 |
| | | | | creator_behaviour | unavailable | creator_flow_unknown | — | — |
| 5 | 12:07:27 | 3tAFaZ | progress_below_window | curve_progress | failed | progress_below_window | −505 184,782 | 0,02 |
| | | | | bundled_share | unavailable | bundled_share_unmeasurable | — | 0,20 |
| | | | | creator_behaviour | unavailable | creator_flow_unknown | — | — |
| 6 | 12:52:40 | Gn9U13 | progress_above_window | curve_progress | failed | progress_above_window | 0,829 | 0,50 |
| | | | | bundled_share | unavailable | bundled_share_unmeasurable | — | 0,20 |
| 7 | 12:52:41 | Gn9U13 | progress_above_window | curve_progress | failed | progress_above_window | 0,838 | 0,50 |
| | | | | bundled_share | unavailable | bundled_share_unmeasurable | — | 0,20 |
| 8 | 12:52:57 | Gn9U13 | progress_above_window | curve_progress | failed | progress_above_window | 0,813 | 0,50 |
| | | | | bundled_share | unavailable | bundled_share_unmeasurable | — | 0,20 |
| 9 | 12:53:21 | Gn9U13 | progress_above_window | curve_progress | failed | progress_above_window | 0,964 | 0,50 |
| | | | | **bundled_share** | **failed** | **bundled_share_above_cap** | **0,397 646** | **0,20** |
| 10 | 14:04:45 | 7uwn4T | progress_above_window | curve_progress | failed | progress_above_window | 0,652 | 0,50 |
| | | | | bundled_share | unavailable | bundled_share_unmeasurable | — | 0,20 |
| | | | | creator_behaviour | unavailable | creator_flow_unknown | — | — |
| | | | | participation | unavailable | volume_unavailable | — | 0,01 |
| | | | | sizing | unavailable | below_min_sol | — (não dimensionado) | — |
| | | | | price_impact | unavailable | price_impact_above_cap | — (não dimensionado) | — |
| | | | | sol_available | unavailable | insufficient_sol | — (não dimensionado) | — |
| | | | | exposure_after | unavailable | exposure_after_above_cap | — (não dimensionado) | — |
| 11 | 14:05:07 | 7uwn4T | progress_above_window | curve_progress | failed | progress_above_window | 0,640 | 0,50 |
| | | | | **top10_share** | **failed** | **top10_share_above_cap** | **0,499 862** | **0,25** |
| | | | | bundled_share | unavailable | bundled_share_unmeasurable | — | 0,20 |
| 12 | 14:05:27 | 7uwn4T | progress_above_window | curve_progress | failed | progress_above_window | 0,649 | 0,50 |
| | | | | **top10_share** | **failed** | **top10_share_above_cap** | **0,499 862** | **0,25** |
| | | | | bundled_share | unavailable | bundled_share_unmeasurable | — | 0,20 |
| 13 | 14:08:26 | FLHSaT | progress_above_window | curve_progress | failed | progress_above_window | 0,605 | 0,50 |
| | | | | **top10_share** | **failed** | **top10_share_above_cap** | **0,253 336** | **0,25** |
| | | | | bundled_share | unavailable | bundled_share_unmeasurable | — | 0,20 |
| 14 | 14:13:51 | 3T4Aue | progress_above_window | curve_progress | failed | progress_above_window | 0,813 | 0,50 |
| | | | | **participation** | **failed** | **participation_above_cap** | **0** | **0** |
| | | | | **sizing** | **failed** | **below_min_sol** | **0** (binding=participation) | **0,001** |
| 15 | 14:14:14 | 3T4Aue | progress_above_window | curve_progress | failed | progress_above_window | 0,783 | 0,50 |
| 16 | 15:33:15 | Cfsb4v | **creator_flow_unknown** | creator_behaviour | unavailable | creator_flow_unknown | — | — |
| | | | | bundled_share | unavailable | bundled_share_unmeasurable | — | 0,20 |
| | | | | **top10_share** | **failed** | **top10_share_above_cap** | **0,257 641** | **0,25** |
| | | | | **participation** | **failed** | **participation_above_cap** | **0** | **0** |
| | | | | **sizing** | **failed** | **below_min_sol** | **0** (binding=participation) | **0,001** |

Três leituras que a coluna `reason` esconde:

1. **A ordem 15 (14:14:14) é a única do dia com apenas uma reprovação.** Se o teto de progresso fosse
   85 % em vez de 50 %, essa compra teria saído — e teria sido a única.
2. **A ordem 16 (15:33:15) é a primeira em que o `curve_progress` passou** (a decisão A do Everton, o
   `operator/5.max_progress_pct` → 50, aplicada 15:08, funcionou). Ela bateu em **quatro** outras
   paredes ao mesmo tempo: fluxo do criador desconhecido, bundled desconhecido, top-10 em 25,76 %
   (teto 25 %) e volume orgânico do minuto **zero** → participação 0 → tamanho final 0 → `below_min_sol`.
   É o retrato exato do que vem depois de arrumar o progresso.
3. **`participation = 0` não é "volume baixo", é `volume_1m = 0`.** No `admission->'sizing'` das
   ordens 14 e 16: `binding_limit = {name: participation, sol: 0, detail: volume_1m=0E-10}`, com
   `size_without_participation = 0,05` — a participação é o limitante inteiro. Já na ordem 15 o
   volume era 11,10 SOL/min e o limitante virou `requested` (0,05 SOL, `price_impact` 0,069 %).

---

## 2. Custo escondido — em quantas ordens cada checagem recusaria se fosse a única

| checagem | recusa | estado | ordens (de 16) | mints (de 7) |
|---|---|---|---|---|
| `bundled_share` | `bundled_share_unmeasurable` | unavailable | **13** | 6 |
| `curve_progress` | `progress_above_window` | failed | 10 | 4 |
| `creator_behaviour` | `creator_flow_unknown` | unavailable | **7** | 4 |
| `curve_progress` | `progress_below_window` | failed | 5 | 2 |
| `top10_share` | `top10_share_above_cap` | failed | **4** | 3 |
| `participation` | `participation_above_cap` | failed | 2 | 2 |
| `sizing` | `below_min_sol` | failed | 2 | 2 |
| `bundled_share` | `bundled_share_above_cap` | failed | 1 | 1 |
| `participation` | `volume_unavailable` | unavailable | 1 | 1 |
| `sizing` / `price_impact` / `sol_available` / `exposure_after` | (não dimensionado) | unavailable | 1 cada | 1 |

**O custo escondido atrás do progresso:** o `progress_above_window` de hoje (10 ordens) e o
`progress_below_window` do bug de unidade (5, corrigido pela T4.28e) **não eram o gargalo**.
Se as 15 ordens tivessem passado no `curve_progress`:

- **14 das 15 seriam recusadas mesmo assim** — 12 por `bundled_share_unmeasurable`, 1 por
  `bundled_share_above_cap` (ordem 9: 39,76 % contra o teto de 20 %, bundle real, recusa correta) e 1
  por `participation_above_cap` + `below_min_sol` (ordem 14, volume do minuto zero);
- só a ordem 15 (14:14:14) sobraria. **1 compra em 16, não 15.**

`creator_flow_unknown` (a recusa gravada da última ordem) aparece em **7 das 16** — não é um caso
isolado do fim da tarde, é 44 % do dia; ele só não vira `reason` antes porque o `curve_progress`
chega primeiro na lista de checagens.

`top10_share_above_cap` é a recusa **de mercado** mais frequente depois do progresso: 4 ordens, 3
mints, e duas delas por margem mínima (25,33 % e 25,76 % contra 25,00 %) — é um teto que morde
exatamente na fronteira.

---

## 3. As checagens `unavailable` — quem preenche, com quanto atraso, e se reproposição resolve

| insumo | coluna | job que escreve | janela de frescor exigida pelo executor |
|---|---|---|---|
| `creator_net_sol` | `meme_features_1m.creator_sold` | fold do `services/meme-worker` (`fold.py` + `features_tape.py`), 1 linha por mint rastreado por minuto **fechado**, da fita de trades | sem janela (`repo.py::_FEATURES`, a linha mais nova do mint) |
| `top10_share_pct` | `meme_features_1m.top10_share` | mesmo fold (`holders_source`: board / `in-memory-coin`) | mesma linha `_FEATURES` |
| `organic_volume_1m_sol` | `meme_features_1m.curve_volume_1m_sol` | mesmo fold | **≤ 120 s** (`admission.py::context_from`, `volume_fresh`) |
| `bundled_share_pct` | `meme_risk_snapshots.bundled_share` | `services/meme-worker/risk.py::RiskReader` → `GET advanced-indexer.pump.fun/in-memory-coin/{mint}`, **≤ 1 leitura/mint/5 min** | **≤ 600 s** (`repo.py::RISK_SNAPSHOT_MAX_AGE_S`) |

> Correção de procedência: `bundled_share` **nunca** esteve em `meme_features_1m` — a query da T4.14
> nomeava a tabela errada e teria levantado `UndefinedColumn` na primeira candidata real (achado da
> T4.28). Hoje vem de `meme_risk_snapshots`, gravada pelo leitor de risco, não pela API.

### Latência medida (7 mints de hoje, segundos desde a criação do token)

| mint | criada | 1ª ordem | 1ª linha `meme_features_1m` | 1º `creator_sold` | 1º `bundled_share` | creator − ordem | bundled − ordem |
|---|---|---|---|---|---|---|---|
| 3T4Aue | 14:09:56 | +235 s | +3 s | +123 s | +114 s | **−111 s** | **−121 s** |
| Gn9U13 | 12:49:40 | +179 s | +19 s | +139 s | +202 s | **−40 s** | +23 s |
| FLHSaT | 14:04:44 | +223 s | +16 s | +196 s | +366 s | **−27 s** | +143 s |
| 7uwn4T | 14:01:33 | +192 s | +27 s | +207 s | +314 s | +15 s | +122 s |
| Cfsb4v | 15:29:46 | +209 s | +13 s | +313 s | +290 s | +104 s | +81 s |
| FHcHh1 | 11:43:56 | +160 s | +3 s | +243 s | +263 s | +83 s | +103 s |
| 3tAFaZ | 12:02:38 | +288 s | +21 s | +441 s | +419 s | +153 s | +131 s |

(negativo = o insumo **já existia** quando a admissão rodou.)

- **A primeira linha de `meme_features_1m` chega em 3–27 s** (mediana 16 s) depois da criação. Por
  isso `top10_share` nunca saiu `unknown` hoje: o fold é rápido. O que atrasa é o **conteúdo**, não a
  linha.
- **`creator_sold` só fica não-nulo em +123 a +441 s** (mediana 207 s), porque depende de o criador
  aparecer na fita. Contra a 1ª ordem: **mediana +15 s**; em 4 dos 7 mints já estava lá.
- **`bundled_share` chega em +114 a +419 s** (mediana 290 s) e, contra a 1ª ordem, **mediana +103 s**;
  em 6 dos 7 mints a ordem chegou **antes** da medição.
- **Mesa → executor: 3–10 s** (média 6 s). O atraso não é do executor; é do insumo.

### Por que o bundled chega sempre depois: a ordem causal está invertida

O `RiskReader` só lê `/in-memory-coin` para mints **com aposta paper aberta** ou no board
`graduating` (docstring de `risk.py`). Uma moeda de 3 minutos só entra nessa lista **quando o Lab
abre a aposta de papel** — que é o mesmo instante em que a mesa propõe. O executor decide 6 s depois;
o leitor de risco só passa no próximo tique, dentro do seu intervalo de 5 min. **O executor pergunta
antes de o coletor ter motivo para ter perguntado.**

### Reproposição 20–60 s depois resolveria?

| insumo | resolvido em ≤ 60 s | resolvido em ≤ 150 s |
|---|---|---|
| `creator_sold` | **5 de 7** (4 já tinham + 7uwn4T em +15 s) | 6 de 7 (falta 3tAFaZ, +153 s) |
| `bundled_share` | **2 de 7** (3T4Aue já tinha + Gn9U13 em +23 s) | **6 de 7** (falta FLHSaT, +143 s — no limite) |

**Resposta honesta:** uma reproposição de 20–60 s resolve o **fluxo do criador** (5/7), mas **não**
resolve o bundled (2/7). O bundled precisa de ~2 min — ou de o leitor de risco passar a cobrir
também os mints com **proposta live aberta**, que é a correção da causa em vez do sintoma. E esperar
2 min tem custo: nos 7 mints, o progresso da curva subiu de 60 % para 96 % em 41 s (Gn9U13,
12:52:40 → 12:53:21). **Esperar o dado é comprar mais tarde numa curva mais cara.**

---

## 4. Com a porta de encanamento: o que recusa em seguida, e quanto

Estimativa sobre os **48 mints distintos** que o conjunto `operator` propôs nas últimas 24 h
(`meme_rule_sets.name = 'operator'`), perguntando se o insumo existia **no instante da proposta**,
com as mesmas janelas de frescor do executor (Q04):

| insumo disponível na proposta | mints | % |
|---|---|---|
| `bundled_share` (não-nulo, ≤ 600 s) | 10 / 48 | **21 %** |
| `creator_sold` (não-nulo) | 16 / 48 | **33 %** |
| `top10_share` ≤ 0,25 e fresco (≤ 120 s) | 35 / 48 | 73 % |
| `curve_volume_1m_sol` > 0 e fresco | 42 / 48 | 88 % |
| **os quatro ao mesmo tempo** | **4 / 48** | **8 %** |
| os quatro **menos** o bundled | 9 / 48 | 19 % |
| só top-10 e volume | 32 / 48 | 67 % |

Ou seja: mesmo com a porta de encanamento (holders ≥ 10, compradores ≥ 5, sem "subindo") entregando
candidatas, e com `max_progress_pct = 50` já aplicado na mesa, **o executor admitiria ~8 % das
propostas** — 4 em 48, ~4 compras por dia no ritmo atual. O limitante não é o progresso nem o
mercado: é `bundled_share_unmeasurable` (79 % de perda sozinho), seguido de `creator_flow_unknown`
(67 %).

### Conclusão em 5 linhas

1. `progress_above_window` (10) e `progress_below_window` (5) eram **sintoma**: corrigindo os dois,
   14 das 15 ordens continuariam recusadas — 12 por `bundled_share_unmeasurable`, 1 por bundle real
   (39,76 %) e 1 por volume do minuto zero. Sobraria **uma** compra em 16.
2. A próxima parede é **`bundled_share_unmeasurable`**: 13 de 16 ordens hoje, e 79 % dos 48 mints
   propostos em 24 h; depois **`creator_flow_unknown`** (7 de 16; 67 % dos 48) e
   **`top10_share_above_cap`** (4 de 16; 27 % dos 48, duas delas na casa dos 25,3–25,8 % contra 25,0 %).
3. A causa não é o mercado: o leitor de risco só consulta `/in-memory-coin` para mint com aposta
   paper aberta ou `graduating`, então o bundled chega **103 s depois** (mediana) da ordem; o
   `creator_sold` depende da fita e chega **15 s depois** (mediana).
4. **Ajuste 1 (causa, recomendado):** incluir no `RiskReader` os mints com proposta `operator`
   ativa ou com ordem live pendente, ainda dentro de 1 leitura/mint/5 min — leva o bundled de 21 %
   para perto de 100 % na proposta e a admissão estimada de 8 % para ~19 % sem afrouxar check nenhum.
5. **Ajuste 2 (sintoma, barato):** a mesa só propor com `creator_net_seller` **conhecido**
   (`creator_sold IS NOT NULL`) — corta 67 % das propostas na origem, mas troca 7 recusas de executor
   por 0 e devolve as vagas do cap/hora. *Não recomendo* o executor "esperar a foto de 1 min": num
   caso medido a curva foi de 60 % a 96 % em 41 s, e esperar vira comprar caro.

**Assunção numérica declarada:** trato "`creator_sold IS NOT NULL` na proposta" como equivalente ao
`creator_net_sol` que a admissão monta (`admission.py::context_from` mapeia `True → −1`, `False → +1`);
e uso a 1ª ordem de cada mint como o instante de decisão, porque as reproposições do mesmo mint
(4× no mesmo mint em 80 s) não são eventos independentes.

## Ligações

[[09-OPERATIONS/Diario/2026-09-16]] · `docs/RISK_ENGINE_MEME.md` §4 · `.claude/state/notes-T4.28e.md` ·
`services/meme-executor/hunter_meme_executor/{admission,repo}.py` ·
`services/meme-worker/hunter_meme_worker/risk.py`
