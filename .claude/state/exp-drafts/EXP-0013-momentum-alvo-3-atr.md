---
tags: [experimento, momentum, saida]
updated: 2026-09-08
status: em-andamento
owner: quant-engineer
exp: EXP-0013
strategy: "momentum"
version: "v6"
result: inconclusivo
evaluable: 195
days: 24
last_eval: "2026-09-08"
---

# EXP-0013 — momentum com alvo de 3 ATR (`target_atr` 1,5 → 3,0)

> Rascunho para a Sexta-feira arquivar em `obsidian/05-EXPERIMENTS/`. O número **EXP-0013** é a
> próxima vaga livre lida em 2026-09-08T19:25Z; se outra tarefa tomar o número antes, renumerar.

## Hipótese (congelada)

O alvo fixo de 1,5 ATR (≈ 1,0 R bruto, porque `stop_atr = 1,5`) **corta os ganhadores cedo**: o
braço `TGT-3` do EXP-0007 foi o maior Δ positivo pareado da população de replay (+0,104 R) e a
[[KB-0076]] item 7 mostrou que tirar o alvo levaria a expectancy de −0,17 R para −0,005 R **naquela
janela**. Mover o alvo para 3,0 ATR (2,0 R brutos) mantém stop, entrada e invalidação e testa
**apenas** o teto do ganhador.

**O que a hipótese não promete:** o item 4 da [[KB-0076]] mediu que o p90 do MFE dos ganhadores da
`momentum` é 1,20–1,23 R — **não há cauda direita grossa nesta janela**, e o mesmo braço deu **pior**
(−0,23 R e −0,10 R) nas duas populações prospectivas. Duas medições, sinais opostos.

## Portão de desenho (C1–C8) — congelado

Nenhum código novo: `momentum_v1` congelada (`sha256:ab2e0398…`) com a escada de alvos deslocada.

| # | Critério | Veredito | Justificativa |
|---|---|---|---|
| C1 | Plausibilidade da vantagem | **PASS com ressalva** | Mecanismo: em continuação de momentum, a distribuição de excursão favorável tem cauda; um alvo em 1 R trunca a cauda e mantém a perda inteira em 1 R, o que é assimetria ao contrário. Quem está do outro lado é quem vende a continuação cedo. **Ressalva grande:** a própria [[KB-0076]] mediu que a cauda **não** é grossa nesta janela (p90 do MFE dos ganhadores = 1,20–1,23 R), então o mecanismo pode simplesmente não existir neste universo |
| C2 | Risco de sobreajuste | **PASS** | Um limiar movido, dois algarismos significativos (`3,0`), origem declarada: é o **braço TGT-3 já pré-registrado** no EXP-0007, e `3,0 ATR` é exatamente o `target2_atr` que a versão-mãe já publicava como alvo informativo desde a `v1` — não é um valor garimpado. Nenhuma condição de entrada nova |
| C3 | Adequação da amostra | **PASS** | Mesma frequência de entrada do pai por construção (o alvo é lido depois das quatro portas): 460 barras `triggered` em 11 904, idênticas às do pai. A frequência de *decisão* cai (224 → 196) só porque o acompanhamento dura mais e o slot fica ocupado — efeito declarado, não seleção |
| C4 | Dependência de regime | **PASS por herança** | Igual à mãe; `market_regimes` só tem `UNKNOWN` e a perda da `momentum` é uniforme por hora, dia e direção do BTC ([[KB-0076]] item 6) |
| C5 | Calibração das saídas | **PASS** | Stop 1,5 ATR (inalterado, portanto a distância continua dentro de `min/max_stop_distance_pct` do `paper_v1`, 0,3 %–3 %); alvo 3,0 ATR ⇒ **R/R = 2,0**; escada informativa deslocada para 6,0 e 9,0 ATR mantendo a proporção 1:2:3 do pai; horizonte 4 h inalterado |
| C6 | Concentração de risco | **PASS** | `research_only`, sem carteira. O único efeito de carga é **acompanhamento mais longo** (duração mediana maior), que ocupa o slot por mais tempo e **reduz** o número de operações simultâneas por mercado |
| C7 | Realismo de execução | **PASS** | Custos e atraso de entrada idênticos aos do pai; o alvo mais distante **não** muda a barra de entrada nem o custo em R (medido: custo 0,2554 R na variante contra 0,2526 R no pai) |
| C8 | Qualidade da invalidação | **PASS por herança declarada** | Herda `close_below prior_max` de propósito — é o **contraste** que este EXP precisa manter fixo. E a herança tem consequência medida: a invalidação passa a matar operações que já andaram para o lado certo mas ainda não chegaram a 3 ATR (82 invalidações, 41,8 % dos desfechos) |

**Veredito do portão:** `PASS` — 2026-09-08, quant-engineer.

**Desvio de desenho a declarar (não é opcional):** a mudança literal do brief
(`--set target_atr=3.0`, um parâmetro só) foi **recusada pelo script auditado**:
`RECUSADO: a variante sai da faixa declarada: target_atr=3 não é menor que target2_atr=3`
(`constraints_table.py`, par ordenado `target_atr < target2_atr < target3_atr`, T3.26c/A2). A escada
do pai é `1,5 / 3 / 4,5` = `target_atr × {1, 2, 3}`, e a variante preserva **a mesma regra**:
`3 / 6 / 9`. `target2_atr` e `target3_atr` são **informativos** — o `walker` só usa `target1`
(`walker.py:73,157`) — então nenhum número desta avaliação depende deles; o que depende é o
`params_hash`, e por isso a escolha está congelada aqui.

## Protocolo (congelado na ativação)

- **Strategy:** `momentum` / `v6`
- **code_ref:** `hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c` (idêntico ao do pai `v2`)
- **params_hash / params_format:** `8cb1aa497956…` / `1`
- **Parameters:** `{"fee_bps":"4","atr_bars":"97","rvol_min":"1.5","stop_atr":"1.5","horizon_s":"14400","atr_period":"14","return_min":"0","target_atr":"3","atr_pct_max":"0.05","atr_pct_min":"0.003","rvol_window":"96","target2_atr":"6","target3_atr":"9","slippage_bps":"5","atr_timeframe":"15m","base_confidence":"0.5","lookback_closes":"20","max_entry_delay_s":"120","assumed_spread_bps":"2"}`
- **Linhagem:** `variante de v2 | derived_from=v2 | overrides=target2_atr=6,target3_atr=9,target_atr=3 | params_hash=8cb1aa497956 | T3.40 V2: alvo 3 ATR (KB-0076 MFE)`
- **Timeframe de decisão / de outcome:** 15 min / 1 min, UTC
- **Agregação e ATR:** 1 m → 15 m só com barras UTC contíguas e finais; ATR = Wilder(14) de 15 min, seed e âncora persistidos
- **Entrada:** open da primeira barra de 1 min estritamente posterior a `decision_at`, com `entry_bar_open − source_bar_close ≤ 120 s`
- **Saída:** gap na abertura primeiro, depois toques intrabar; stop e alvo na mesma barra → **stop**; horizonte 4 h contado da entrada
- **Custos assumidos:** spread total 2 bps, slippage 5 bps por lado, taxa 4 bps por lado; funding assinado
- **Política de reentrada:** um acompanhamento por `(strategy_version_id, market_id, cohort)`; rearme só depois do término anterior
- **Cohort:** `replay:9a08835a-ae13-4c23-b521-734b2f60a3a2` (retrospectiva) e `prospective` (aberta em 2026-09-08T19:04:56,213531Z)
- **Controle predeclarado:** o **pai** `momentum v2` na coorte `replay:f8d8279c-1fba-42ae-95ef-202042f96c60`, pareado por `(mercado, barra de decisão)` — o método da T3.26
- **Universo elegível:** `markets.is_monitored` **de hoje** (`docs/PIPELINE.md` §6c)
- **Markets:** binance ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT (replay); universo monitorado inteiro (prospectiva)
- **Data de início da coleta:** 2026-09-08 (prospectiva); janela de replay 2026-08-08 → 2026-09-08

## Avaliações (acrescentadas, nunca reescritas)

### Avaliação de 2026-09-08 — **REPLAY** (retrospectiva) — `read_at = 2026-09-08T19:11:21Z` / `19:14:21Z` / `19:15:07Z`

> **Rótulo obrigatório: REPLAY.** É a **mesma janela** que gerou a hipótese ([[KB-0010]]) e a mesma
> em que o braço `TGT-3` foi medido. Não é evidência prospectiva.

**SQL usado:** `q10-pop.sql`, `q11-pareado.sql`, `q12-motivos-mfe.sql`, `q13-blocos.sql`,
`q19-cobertura.sql`, transcritos verbatim em `.claude/state/notes-T3.40.md` §SQL.

**Cobertura (contagens completas):**

| coorte | Emitidos | Pendentes | Entradas | Não entradas | Ativos | Target | Stop | Expired | Invalidated | Censurados | Funding indisponível |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| variante `9a08835a` | 196 | 0 | 196 | 0 | 0 | 53 | 45 | 16 | 82 | 0 | 1 |
| pai `f8d8279c` | 224 | 0 | 224 | 0 | 0 | 91 | 45 | 6 | 82 | 0 | 2 |

**Métricas (denominador explícito):**

| Métrica | Variante `v6` | Pai `v2` | Denominador | Observação |
|---|---:|---:|---|---|
| Taxa de alvo entre toques resolvidos | 54,1 % | 66,9 % | `target + stop` | não é taxa de lucro |
| Taxa de lucro líquido | 32,8 % | 41,4 % | encerrados avaliáveis | `R_net > 0` |
| Expectancy líquida por entrada avaliável | **−0,0513 R** | −0,1717 R | 195 / 222 | média de `R_net` |
| Expectancy bruta (sem custo) | +0,2028 R | +0,0820 R | idem | `(exit_base − open)/risco` |
| Custo em R | 0,2554 | 0,2526 | idem | `bruto − r_ex_funding` |
| Profit Factor líquido | **0,9064** | 0,6454 | Σ+ / \|Σ−\| | |
| Profit Factor bruto | 1,5431 | 1,2455 | idem | |
| Soma de R | −10,01 | −38,13 | ordenação por barra | não é equity |
| MFE médio (R) | 0,4511 | 0,2343 | 196 / 224 | **limite inferior**: 98 e 136 leituras `ambiguous` |
| Fração do MFE capturada | 0,4496 | 0,3500 | médias | bruto médio ÷ MFE médio |
| **PnL de carteira** | **não aplicável** | — | — | não há carteira no Shadow Lab |
| **Max Drawdown de carteira** | **não aplicável** | — | — | idem |

- **Dias distintos com outcome avaliável:** 24 (variante e pai)

**Os quatro grupos pareados por `(mercado, barra)` — método T3.26:**

| Grupo | n | avaliáveis | bruta (R) | custo (R) | líquida (R) | soma R | acerto | PF líq. | dias |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pai **pareado** com a variante | 193 | 191 | +0,0567 | 0,2556 | −0,2005 | −38,29 | 38,9 % | 0,5971 | 24 |
| pai **sem par** na variante | 31 | 31 | +0,2396 | 0,2335 | +0,0052 | +0,16 | 51,6 % | 1,0129 | 13 |
| variante **pareada** com o pai | 193 | 192 | +0,1939 | 0,2558 | −0,0606 | −11,63 | 26,9 % | 0,8905 | 24 |
| variante **sem par** no pai | 3 | 3 | +0,7797 | 0,2326 | +0,5417 | +1,63 | 33,3 % | 3,1489 | 2 |

**O estimando (Δ pareado, 191 pares com os dois lados avaliáveis):**

| pares | Δ líquido médio | Δ líquido soma | Δ bruto médio | mesmo risco inicial | mesmo motivo de saída | dias |
|---:|---:|---:|---:|---:|---:|---:|
| 191 | **+0,1341 R** | +25,61 R | +0,1346 R | **191 / 191** | 168 / 191 | 24 |

`risco inicial idêntico em 191 de 191` é a prova de que entrada, stop e custo não se moveram: **só o
alvo mudou**.

**De onde vêm os +25,61 R (decomposição por motivo de saída dentro dos pares):**

| motivo no pai | motivo na variante | n | Δ líquido médio | Δ soma |
|---|---|---:|---:|---:|
| `target` | `target` | 52 | **+0,9549** | **+48,70** |
| `invalidated` | `invalidated` | 73 | 0,0000 | 0,00 |
| `stop` | `stop` | 40 | 0,0000 | 0,00 |
| `expired` | `expired` | 5 | 0,0000 | 0,00 |
| `target` | `expired` | 10 | −0,6006 | −6,01 |
| `target` | `invalidated` | 8 | −1,1385 | −9,11 |
| `target` | `stop` | 5 | −1,5953 | −7,98 |

Lê-se assim: **52 ganhadores dobraram** (+48,70 R) e **23 ganhadores foram devolvidos** (−23,10 R);
o resto do livro não se moveu **nem uma casa decimal** — é o mesmo trade até o alvo antigo.

**O teste de blocos (dia como bloco, o mesmo desenho da T3.32):**

| blocos (dias) | média das médias diárias | desvio | erro-padrão | IC 95 % (t, 23 gl) | dias positivos | dias negativos |
|---:|---:|---:|---:|---|---:|---:|
| 24 | **+0,0463 R** | 0,3320 | 0,0678 | **[−0,0939; +0,1866]** | 10 | 8 |

**O intervalo contém zero.** Os +0,134 R por decisão vêm de três dias (08-19 +0,70, 08-21 +0,47,
08-27 +0,63); seis dias têm Δ exatamente zero e oito são negativos.

**Distribuição do MFE (em R do risco inicial congelado):**

| coorte | n | MFE médio | p50 | p90 | % com MFE ≥ 1 R | % com MFE ≥ 2 R |
|---|---:|---:|---:|---:|---:|---:|
| variante `9a08835a` | 196 | 0,4511 | 0,1934 | 1,2988 | 10,7 % | **1,0 %** |
| pai `f8d8279c` | 224 | 0,2343 | 0,1264 | 0,6014 | 1,8 % | 0,0 % |

O alvo novo pede **2,0 R brutos**; apenas **1,0 %** das operações da variante registram MFE ≥ 2 R
(leitura por barras completas, `method = ohlc_complete_bars_v1`, **limite inferior** — 98 das 196
linhas têm `ambiguous = true`). A leitura honesta é que o alvo de 3 ATR quase nunca é alcançado por
excursão medida; ele é alcançado **na barra de saída**, e os 53 `target` da variante são
majoritariamente toques que a leitura conservadora de MFE não enxerga.

- **Versão da métrica / proveniência:** `agent_signals` + `signal_outcomes` + `replay_runs`, coorte `replay:9a08835a-ae13-4c23-b521-734b2f60a3a2`
- **Result:** **inconclusivo** — 195 avaliáveis e 24 dias distintos passam de 100, mas **não** dos 30
  dias exigidos, e acima disso a regra é prospectiva: esta é a janela que gerou a hipótese
- **Conclusion:** os dois critérios de descarte do brief **não** disparam (`PF_net = 0,906 > 0,80`;
  `expectancy_net = −0,0513 R > −0,1717 R` do pai). O Δ pareado é **positivo e grande por decisão**
  (+0,134 R) e **indistinguível de zero por dia** (IC 95 % [−0,094; +0,187]). A variante continua
  **perdendo dinheiro** em termos absolutos (−0,051 R por operação, PF < 1): ela reduz a perda em
  70 %, não a inverte. E o mecanismo medido é caro: paga 23 ganhadores devolvidos para receber 52
  ganhadores dobrados
- **Next Action:** manter em `research_only` e **deixar a coorte `prospective` correr 30 dias**
  (aberta em 2026-09-08T19:04:56Z). Reavaliar então contra a `momentum v3` (`paper`) e a `v2` na
  **mesma** janela prospectiva. **Não** promover a `paper`, **não** desligar o pai. Se o Δ
  prospectivo repetir o sinal negativo que o braço `TGT-3` deu em P3/P4 (−0,23 R e −0,10 R), a
  recomendação vira **descartar** com duas evidências independentes

## Variantes tentadas

| Variante | Quando | Por quê | Onde ficou registrada |
|---|---|---|---|
| braço de saída `TGT-3` sobre entradas congeladas | 2026-09-08 15:1xZ | contraste barato, sem versão nova | [[EXP-0007]] / [[KB-0076]] |
| braço `EXIT-NOTGT` (sem alvo) | 2026-09-08 15:1xZ | maior Δ do replay, **trocou de sinal** na prospectiva | [[EXP-0007]] |
| `target_atr = 3,0` como versão (`momentum v6`) | 2026-09-08 19:04:56Z | transformar o braço em versão com coorte própria e janela futura reservada | **este EXP** |
| `--set target_atr=3.0` sozinho | 2026-09-08 18:54:29Z | **recusado** pelo `derive_variant.py` (`target_atr` tem de ser < `target2_atr`); resolvido deslocando a escada para 3/6/9 | `system_events` `strategy_version_variant_refused` |

## Relacionadas

[[EXP-0007-momentum-invalidacao-bracos-INV]] · [[KB-0076-por-que-perdemos-2026-09-08]] · [[KB-0006]] · [[KB-0010]] · [[EXP-0012-momentum-teto-de-pedagio]] · [[Experiments Index]]

## Fontes

`.claude/state/notes-T3.40.md` (comandos, recibos e SQL verbatim) · `replay_runs` coortes
`replay:9a08835a-ae13-4c23-b521-734b2f60a3a2` e `replay:f8d8279c-1fba-42ae-95ef-202042f96c60` ·
`system_events` (`strategy_version_variant_refused`, `strategy_version_variant_derived`,
`strategy_version_activated`, `replay_run_finished`) · livro-razão `--explain-ledger` gravado nas
duas fatias (recibo `replay_explain_ledger bars=5760 lines=5760` e `bars=6144 lines=6144`); os
**arquivos** da variante foram perdidos quando outra tarefa recriou o container às 19:12Z — ver
CONCERN 4 em `.claude/state/notes-T3.40.md`.
