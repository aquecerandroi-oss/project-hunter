---
tags: [experimento, mean-reversion, timeframe, custo, 90-dias, pre-registro]
updated: 2026-09-11
status: pre-registrado
owner: quant-engineer
exp: EXP-0028
strategy: "mean_reversion_m5"
version: "v1 (módulo novo, code_ref próprio)"
result: nao-iniciado
evaluable: 0
days: 0
last_eval: ""
---

# EXP-0028 — a reversão à média decidida em 5 minutos

> **Pré-registro escrito em 2026-09-11, 05:20 BRT (08:20 UTC), ANTES de existir qualquer replay,
> qualquer `seed`, qualquer ativação e qualquer linha em `agent_signals`.** Origem: brief T3.84
> (`.claude/state/brief-T3.84-lote-diario-5min.md`); pedido do Everton em 09/09 — *"podemos fazer
> teste 5 min 10 min 1 h"* — com a condição que ele mesmo pôs: só depois do atraso de decisão cair
> abaixo de 5 s. A condição foi atendida na noite de 10/09 (`decision_lag` p50 **2,2 s**). Nada
> aqui é dinheiro real (`ENABLE_LIVE_TRADING=false`); nenhuma versão é ativada, promovida ou
> aposentada por esta página.
>
> **O prior desta equipe é que a resposta é `descartar`.** O experimento existe para fechar a
> pergunta com o **nosso** dado e porque o Everton pediu — não porque alguém aqui espere vantagem.
> As três razões estão escritas abaixo, com número, antes do resultado.

## Hipótese (congelada)

**Decidir a mesma reversão à média em barras de 5 min, em vez de 15 min, produz expectativa
líquida (ex-funding) positiva em 90 dias × 16 mercados.** É o eixo de timeframe da
[[EXP-0021-timeframe|EXP-0021]] percorrido para **baixo**: a T3.54 mediu que subir a grade
(15 min → 1 h) multiplica o ATR% por **2,208** e portanto divide o pedágio por R por 2,208. Descer
a grade faz o **oposto**, e a hipótese só pode ser verdadeira se o ganho bruto por operação a 5 min
crescer mais rápido do que o pedágio — que é exatamente o que os três priors abaixo dizem que não
acontece.

## Priors contrários, escritos antes (cada um com o número)

1. **[[KB-0076-por-que-perdemos-2026-09-08|KB-0076]] — a identidade de custo.** `custo_R ≈ 0,0020 /
   (stop_atr × ATR%)`. Com `stop_atr = 1` e o piso `atr_pct_min = 0,006` herdado da mãe byte a
   byte, o pedágio no piso é **0,333 R**. O que muda de grade para grade não é o piso, é a
   **distribuição realizada** acima dele — e a 5 min ela é muito mais apertada contra o piso (§
   "Previsões numéricas").
2. **[[KB-0086-ic-positivo-nao-paga-o-pedagio-btc-perp-5-min|KB-0086]] — o precedente publicado.**
   Zeng et al. (arXiv 2608.25348) buscaram fatores em BTCUSDT perpétuo **a 5 min**, 2 anos,
   209 951 decisões: IC de teste positivo (0,155–0,235) e **"all 460 executed cost cells were
   negative"** numa grade de taxa 4–10 bp × slippage 1–10 bp por lado. Limite declarado da fonte, e
   repetido aqui para não virar argumento de autoridade: são 23 execuções × 20 células
   **dependentes**, um instrumento, uma exchange, e busca de fatores — **não** é uma estratégia de
   reversão como a nossa. Vale como prior forte sobre o **regime de custo a 5 min**, não como prova
   sobre esta regra.
3. **[[EXP-0025-mean-reversion-90-dias|EXP-0025]] — a família já é negativa a 15 min.** Em 90 d ×
   16 mercados, eixo `r_ex_funding`: `v1` **−0,0910 R** / PF 0,851 (542 desfechos, 83 dias),
   `v2` −0,0343 / PF 0,940, `v10` −0,0293 / PF 0,910; **K3 dispara nas três**; as três `frágeis a
   custos`. Se a mãe já é negativa com o pedágio de 15 min, a filha precisa de um ganho bruto
   **maior** para pagar um pedágio **maior**.

**Braço de falseamento:** não é um braço novo, é a mãe **já medida** — `mean_reversion v1` na mesma
janela de 90 d e nos mesmos 16 mercados (coorte `replay:fa005985…` da T3.62b, EXP-0025). Ela não
será re-rodada: re-rodar produziria uma coorte nova e o contraste deixaria de ser contra um número
pré-existente. É o controle pré-declarado desta página.

## Portão de desenho (C1–C8) — congelado, escrito **antes** do primeiro replay

> O código do módulo foi escrito no mesmo dia, **antes** desta tabela, porque a T3.54 estabeleceu
> que um irmão de timeframe é um transporte byte a byte do contrato da mãe: não há desenho novo a
> aprovar, há uma grade nova. O portão abaixo julga essa transposição, e é aqui que ela pode falhar.

| # | Critério | Veredito | Justificativa (obrigatória) |
|---|---|---|---|
| C1 | Plausibilidade da vantagem | **PASS (fraco)** | Mecanismo idêntico ao da mãe ([[EXP-0009-mean-reversion-pullback-em-tendencia\|EXP-0009]]): quem vende o recuo dentro de uma alta é fluxo forçado (stop, liquidação, rebalance) que aceita perder por ter pressa. A grade de 5 min **não cria** mecanismo novo; ela aposta que o mesmo fluxo se resolve em minutos e não em horas. Fraco de propósito: é a mesma tese num relógio mais rápido, e o relógio mais rápido é onde o custo mora |
| C2 | Risco de sobreajuste | **PASS** | **Cinco** condições de entrada (tendência de 15 m, `z ≤ −1`, fechamento acima do meio da barra, piso e teto de ATR%), muito abaixo do limite de 8. **Zero limiares novos**: todos os 18 parâmetros são os da mãe, e os únicos três que mudam (`atr_timeframe`, `trend_timeframe`, `horizon_s`) mudam por **derivação da grade**, não por busca. `atr_bars = 97` é o único com 2 algarismos e vem herdado de `rolling_window_v1`. Nenhum número desta página foi garimpado nos dados de 5 min, porque nenhum dado de 5 min foi olhado |
| C3 | Adequação da amostra | **PASS (com risco declarado)** | A mãe fez 0,376 decisão/mercado/dia (542 em 90 d × 16 mkt) ⇒ **137/ano/mercado**. A 5 min há **3× mais barras**, mas o piso de ATR% corta **muito mais** (§ "Previsões"): estimativa pré-registrada **41 a 206/ano/mercado**, contra o piso de REVISE de 30. Passa até no extremo pessimista, mas o extremo pessimista é a previsão central se o piso de ATR% morder como esperado |
| C4 | Dependência de regime | **PASS** | Medida, não assumida: a coorte será cortada pelas mesmas três janelas de 30 d da EXP-0025 (J1 jun-12→jul-12, J2 jul-12→ago-11, J3 ago-11→set-10) e o regime horário do BTC está 100 % coberto desde o reparo da [[EXP-0026-regime-como-estrategia\|EXP-0026]] (2 161/2 161 h). Nenhum portão de regime é aplicado a esta versão — seria um segundo eixo |
| C5 | Calibração das saídas | **REVISE** | Stop **1,0 ATR**, alvo **1,5 ATR**, alvo 2 informativo 2,5 ATR ⇒ R/R 1,5 (o contrato da mãe, byte a byte). O problema é o **piso** do `paper_v1`: `min_stop_distance_pct = 0,3 %`. Com ATR%(5m) p50 estimado em **0,30 %** (§ "Previsões"), o stop mediano de 1 ATR cai **exatamente em cima do piso**. Quem salva o critério é o próprio `atr_pct_min = 0,006`: só barras com ATR% ≥ 0,6 % disparam, logo todo stop emitido tem ≥ 0,6 % e cabe na faixa \[0,3 %; 3 %\]. **REVISE e não PASS** porque isso não é folga de desenho, é uma coincidência de que o piso de custo herdado também serve de piso de risco — e é a mesma coincidência que torna a versão rara. Horizonte 4 800 s (16 barras, como as duas irmãs) |
| C6 | Concentração de risco | **PASS (com risco declarado)** | Nenhum parâmetro pede exceção ao `paper_v1` (0,25 % por operação, 1 % agregado, 10 % por ativo, 40 % total, 5 posições, β 0,5, alavancagem 1). O risco declarado é de **fila**, não de limite: a 5 min as decisões chegam 3× mais rápido e `max_concurrent_positions = 5` satura mais cedo — o que num Lab `research_only` não tem efeito (não há carteira), e que seria a primeira objeção a promover esta versão para `paper` |
| C7 | Realismo de execução | **PASS (com o número no limite)** | Mesmos 16 mercados, todos acima dos 50 M USDT/24 h; mesmos custos assumidos (2 bps spread total, 5 bps slippage/lado, 4 bps taxa/lado) e o **mesmo** `max_entry_delay_s = 120` — e é aqui que o timeframe morde: 120 s são **40 % de uma barra de 5 min** contra 13 % de uma de 15 min, então o mesmo atraso de sistema come proporcionalmente três vezes mais da barra de entrada. O `decision_lag` p50 de **2,2 s** medido em 10/09 é o que torna isso viável; o p95 é o número a vigiar na avaliação |
| C8 | Qualidade da invalidação | **PASS** | `invalidations = ()`, herdado com argumento explícito: braço **INV-B** da [[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo\|KB-0006]]. Uma entrada cuja tese é "o preço está *abaixo* do que deveria" não pode carregar uma regra que sai quando o preço cai mais — o argumento vale idêntico em qualquer grade, e vale **mais** a 5 min, onde o ruído por barra é proporcionalmente maior |

**Regras mecânicas:** 5 condições (< 8) ✔ · nenhum limiar novo com > 2 algarismos ✔ · frequência
estimada ≥ 30/ano/mercado ✔ · controle pré-declarado nomeado (`mean_reversion v1`, coorte
`replay:fa005985…`) ✔ · sem REJECT em C1/C2 ✔.

**Veredito do portão:** `REVISE` — 2026-09-11, quant-engineer. O que o REVISE significa, por
escrito: **C5 passa por dependência de um piso que existe por outro motivo**. Se a avaliação
mostrar que a versão dispara com ATR% realizado colado em 0,006 (a previsão central), o veredito
final desta página deve dizer isso em voz alta — a versão não terá "escolhido" volatilidade alta,
terá sido **definida** pelo piso, e o experimento terá medido o piso, não a grade.

## Protocolo (congelado na primeira ativação — nunca editar)

- **Strategy:** `strategies.key = mean_reversion_m5`, `strategy_versions.version = v1`
- **code_ref:** `hunter_core.strategies.mean_reversion_m5_v1@sha256:f733467fedc529c661f53cf84653e9c5a514d86767471757ee43679af763734b`
  (fecho transitivo: `aggregate`, `base`, `canonical`, `envelope`, `indicators`,
  `mean_reversion_m5_v1`, `numeric`, `schema` — a mãe **não** está no fecho, e este módulo não está
  no fecho de nenhuma das outras nove versões)
- **params_hash / params_format:** `5eaf76a7188078e773341b3e509d67509326107a80c5f0e2a1e781d5934fa6c7` / `1`
- **Parameters (JSON completo, nada implícito):**

```json
{"assumed_spread_bps":"2","atr_bars":"97","atr_pct_max":"0.05","atr_pct_min":"0.006",
 "atr_period":"14","atr_timeframe":"5m","base_confidence":"0.5","fee_bps":"4","horizon_s":"4800",
 "max_entry_delay_s":"120","slippage_bps":"5","stop_atr":"1","target2_atr":"2.5","target_atr":"1.5",
 "trend_sma_bars":"20","trend_timeframe":"15m","zscore_bars":"20","zscore_depth_min":"1"}
```

- **Os três parâmetros que diferem da mãe, e como foram derivados** (os **mesmos três nomes** que a
  irmã de 1 h moveu na T3.54 — o experimento tem um eixo só):

| parâmetro | mãe (15 m) | irmã 1 h | **esta (5 m)** | regra |
|---|---|---|---|---|
| `atr_timeframe` | `15m` | `1h` | **`5m`** | o ATR é medido **na própria grade de decisão**, nas três |
| `trend_timeframe` | `1h` | `4h` | **`15m`** | **o degrau seguinte da grade.** A mãe e a irmã de 1 h realizam 4×, mas `4 × 5 min = 20 min` **não existe** em `Timeframe` (1m, 5m, 15m, 1h, 4h, 1d). 15 m é 3× — declarado aqui porque é a **única liberdade** que esta derivação teve. A alternativa (1 h, 12×) poria a porta de tendência a doze vezes o horizonte do z-score |
| `horizon_s` | 14 400 | 57 600 | **4 800** | 16 barras da grade, nas três |

- **Timeframe de decisão / de outcome:** 5 min / 1 min, UTC
- **Agregação e ATR:** 1 m → 5 m só com barras UTC contíguas e finais; ATR = Wilder(14) sobre 97
  barras de 5 m (`rolling_window_v1`), seed e âncora persistidos no envelope
- **Janela de contexto:** requisito **490 min** (ATR 97 × 5 = 485, mais uma barra de folga; a
  tendência alcança 21 × 15 + 10 = 325; o z-score, 100). Abaixo do piso `SHADOW_CONTEXT_MINUTES`
  (1560), logo o worker carrega os **1560** de sempre e esta versão **não encarece nenhuma outra** —
  o oposto da irmã de 1 h, que precisou de 5880. Declarado em
  `hunter_strategy_worker.context_budget.WINDOWS`
- **Entrada:** open da primeira barra de 1 min estritamente posterior a `decision_at`, com
  `entry_bar_open − source_bar_close ≤ 120 s`
- **Saída:** gap na abertura primeiro, depois toques intrabar; stop e alvo na mesma barra → **stop**
  (convenção pessimista); horizonte 4 800 s contado da entrada
- **Custos assumidos (hipóteses, não tarifas verificadas):** spread total 2 bps, slippage 5 bps por
  lado, taxa 4 bps por lado; funding assinado
- **Eixo primário de medição:** `r_ex_funding` — o mesmo da EXP-0025 e da EXP-0026, pelo mesmo
  motivo (cobertura 100 %, enquanto `r_multiple` perde centenas de linhas por
  `funding_schedule_unknown`)
- **Política de reentrada:** um acompanhamento `pending_entry|active` por
  `(strategy_version_id, market_id, cohort)`; rearme só após barra elegível com a condição falsa
  **depois** do término anterior
- **Cohort:** `replay:<run_id>`, uma por fatia, todas nomeadas na avaliação
- **Controle predeclarado:** `mean_reversion v1`, coorte `replay:fa005985…` (EXP-0025/T3.62b) —
  **não será re-rodado**
- **Universo elegível:** os 16 mercados com ≥ 90 d de histórico contíguo (regra T3.82) — ARB BNB
  BTC DASH DOGE ETH LINK NEAR PROM SAHARA SOL SUI TAO UNI XRP ZEC, perpétuos da Binance
- **Janela:** 90 dias, fronteiras `06-12 / 07-12 / 08-11 / 09-10` (as mesmas três janelas de 30 d
  da EXP-0025), em fatias de ≤ 4 mercados × ≤ 31 dias
- **Bootstrap:** blocos de dia inteiro, `.claude/state/exp-drafts/t362b/blocos90.py`, 20 000
  reamostragens, semente `20260910` (a mesma das EXP-0025/0026 — trocar a semente entre páginas
  tornaria os IC incomparáveis)
- **Data de início da coleta:** 2026-09-11 (replay; não há coorte prospectiva nesta página)

## Regra de sucesso — congelada

**Aprova** quem cumprir **todas**:

1. **expectativa ex-funding em 90 d > 0** com o **IC 95 % por blocos de dia acima de zero**;
2. **PF > 1 em ao menos 2 das 3 janelas** de 30 dias;
3. **leave-one-market-out nunca negativo** (16 reajustes, um por mercado retirado);
4. **estresse não `frágil`** (`--stress`: custos ×2, entrada +1 barra, metades, sem-mercado).

**Qualquer coisa menos que isso é `descartar`**, e `descartar` aqui significa
`activate_strategy_version.py --deprecate` na mesma tarefa — não "guardar para depois".

**Régua editorial, independente do acima:** abaixo de **100 desfechos avaliáveis E 30 dias
distintos** o `Result` é obrigatoriamente `inconclusivo`, e nem aprova nem descarta.

## Previsões numéricas pré-registradas (o que faria esta página estar errada)

> Escritas antes de qualquer replay, com a aritmética à vista, para que o resultado possa
> **falsificá-las** em vez de só confirmá-las de véspera. As três primeiras são deriváveis de
> medições existentes; a quarta é a previsão de resultado.

**P1 — ATR% da grade de 5 min.** A T3.54 mediu (16 mkt × 31 d) ATR%(15m) p50 = **0,5585 %** e
ATR%(1h) p50 = **1,2331 %**, razão 2,208 sobre um fator 4 de tempo ⇒ expoente empírico
`H = ln(2,208)/ln(4) = 0,571`. Extrapolando **para baixo** com o mesmo expoente:
`ATR%(5m) ≈ 0,5585 % × 3^(−0,571) = 0,5585 % × 0,534 =` **0,298 %**, ou ≈ **0,30 %**.
*Assunção declarada: que o expoente medido entre 15 m e 1 h vale entre 5 m e 15 m. Não foi medido a
5 m — é a primeira coisa que a avaliação deve conferir, e se `ATR%(5m) p50 > 0,40 %` esta previsão
está errada e as duas seguintes caem com ela.*

**P2 — o piso de ATR% deixa de ser um piso e vira a definição da versão.** Para a mãe, o piso
`0,006` é **1,07×** a mediana de 0,5585 % — corta a metade calma da distribuição. Para esta versão,
`0,006` é **2,01×** a mediana de 0,298 % — corta quase tudo. Previsão: **ATR% realizado das
decisões de 5 min com p50 entre 0,60 % e 0,75 %**, colado no piso, contra os **0,922 %** que a mãe
realizou (implícitos no pedágio p50 de 0,2169 R da `v1`: `0,0020/0,2169`).

**P3 — o pedágio em R sobe.** `custo_R = 0,0020 / ATR%` com `stop_atr = 1` ⇒ pedágio p50 previsto
entre **0,267 R** (se ATR% realizado = 0,75 %) e **0,333 R** (se = 0,60 %), contra os **0,2169 R**
da mãe. Δ previsto: **+0,05 a +0,12 R de pedágio por operação**, na direção contrária à do ganho
que a irmã de 1 h obteve.

**P4 — o resultado.** Assumindo que o ganho **bruto** por operação a 5 min não supere os
**+0,1270 R** que a mãe mediu (um horizonte 3× menor dificilmente colhe mais movimento), e somando
P3: **ex-funding previsto entre −0,25 R e −0,09 R**, PF previsto **entre 0,65 e 0,90**, veredito
previsto **`descartar`**. *O que falsifica:* ex-funding > 0 com IC de blocos de dia acima de zero.
*O que também seria informativo e não está previsto:* uma expectativa bruta a 5 min **maior** que
+0,1270 R — significaria que o sinal de reversão é mais forte no relógio curto e que o problema é
só custo, o que apontaria para uma versão de custo (maker, alvo maior) em vez do descarte.

**P5 — frequência.** Entre **0,3× e 1,5×** as 542 decisões da mãe em 90 d × 16 mkt (3× mais barras,
gate 3–5× mais seletivo) ⇒ **160 a 810 decisões**. Abaixo de 100 avaliáveis, `inconclusivo` por
régua.

## Avaliações (acrescentadas, nunca reescritas)

### Avaliação de <AAAA-MM-DD> — `as_of = <timestamp UTC>`

*Nenhuma ainda. Esta seção existe vazia de propósito: a página foi criada no pré-registro, antes de
o primeiro replay rodar, e a primeira avaliação será **acrescentada** aqui sem tocar em nada acima.*

## Variantes tentadas

| Variante | Quando | Por quê | Onde ficou registrada |
|---|---|---|---|
| `mean_reversion_h1_v1` (1 h) | 2026-09-09 (T3.54/T3.52d) | o mesmo eixo **para cima**: ATR% 2,208× maior, pedágio 2,208× menor | [[EXP-0021-timeframe]] — 123 decisões, 22 dias, +0,0067 R / PF 1,0116, **`frágil a custos`**, não promovida |
| `mean_reversion_m5_v1` (5 min) | 2026-09-11 (T3.84) | o mesmo eixo **para baixo** — esta página | aqui |

## Relacionadas

[[Experiments Index]] · [[EXP-0021-timeframe]] · [[EXP-0025-mean-reversion-90-dias]] ·
[[EXP-0026-regime-como-estrategia]] · [[EXP-0009-mean-reversion-pullback-em-tendencia]] ·
[[KB-0076-por-que-perdemos-2026-09-08]] ·
[[KB-0086-ic-positivo-nao-paga-o-pedagio-btc-perp-5-min]] ·
[[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]] · [[Strategies]] · [[Dialogos/SHADOW]]

## Fontes

`packages/core/hunter_core/strategies/mean_reversion_m5_v1.py` ·
`packages/core/tests/unit/strategies/test_mean_reversion_m5_v1.py` ·
`services/strategy-worker/hunter_strategy_worker/context_budget.py` (entrada `mean_reversion_m5_v1`) ·
`infra/scripts/seed_reference.py` (linha `mean_reversion_m5`) ·
`.claude/state/brief-T3.84-lote-diario-5min.md` · `.claude/state/notes-T3.54.md` (ATR% por grade) ·
`.claude/state/notes-T3.62b.md` (números da mãe em 90 d) · `.claude/state/notes-T3.76.md` (o funil
de um dia) · `.claude/state/exp-drafts/t362b/blocos90.py` · `docs/plans/SHADOW-LAB.md` §6 ·
`docs/PIPELINE.md` §6b/§6c
