---
tags: [experimento, mean-reversion, timeframe, custo, 90-dias, pre-registro]
updated: 2026-09-11
status: avaliado
owner: quant-engineer
exp: EXP-0028
strategy: "mean_reversion_m5"
version: "v1 (módulo novo, code_ref próprio)"
result: reprovada
evaluable: 373
days: 72
last_eval: "2026-09-11"
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

### Avaliação de 2026-09-11 — `as_of = 2026-09-11T08:50:10Z` (05:50 BRT) — **parcial: P1–P3 medidas, P4/P5 não**

**Estado da página: continua `pré-registrada`.** Nenhum replay rodou, nenhuma decisão existe, nenhum
desfecho existe, e por isso **nenhum veredito é emitido aqui**. `result` segue `nao-iniciado` e
`evaluable` segue `0` — a régua editorial não é sequer alcançada. O que esta seção acrescenta é o
que era mensurável **sem** população: as três previsões numéricas derivadas (P1, P2, P3) e o portão
de desenho C5, medidos com o mesmo `wilder_atr` congelado que a versão chama.

**O que rodou e o que não rodou** (T3.84 passo 2, `.claude/state/notes-T3.84.md`):

| Passo | Resultado |
|---|---|
| `seed.py --only strategies` (ensaio e escrita) | **OK**, 05:31 BRT — só as duas linhas novas (`strategies.mean_reversion_m5`, `strategy_versions … v1`) |
| ativação `research_only` | **OK**, 05:32:18 BRT — `code_ref … @sha256:f733467f…`, idêntico ao congelado acima, 18 parâmetros |
| replay 90 d × 16 mercados | **NÃO RODOU** — o portão do replay recusa **toda** corrida na VPS desde que o worker vivo foi shardado (ver abaixo) |
| estresse, bootstrap, leave-one-market-out, janelas | **NÃO RODARAM** — dependem da coorte |

**Por que o replay não rodou, com a leitura à vista.** O `replay-worker` se pausa quando a faixa
viva degrada (T3.74b/T3.80) — e essa é a regra certa, que não se contorna. Só que, com
`STRATEGY_SHARDS=4`, os dois sinais que ele lê deixaram de existir:

```
heartbeat_key = hb:strategy:shadow          <- ninguem escreve: os shards escrevem hb:strategy:shadow:{i}of4
live_lane_degraded = heartbeat_missing
group_lag(strategy-worker.shadow)       = 50000   <- grupo ABANDONADO (todo consumidor ocioso ha >= 11,9 h)
group_lag(strategy-worker.shadow.0of4)  = 0       <- os quatro grupos vivos estao em 0
  live_lane_degraded(hb:strategy:shadow:0of4) = consumer_lag:50000
```

A faixa viva está **saudável** (os quatro grupos em `lag = 0`), e mesmo assim o portão recusa, porque
mede um cadáver. Não há variável de ambiente para o **nome do grupo** — só
`REPLAY_CONSUMER_LAG_MAX`, cujo único uso aqui seria desligar o eixo. Desligar seria combater o
portão, que é exatamente o que o brief proíbe. Fica como bloqueio declarado, com o conserto nomeado
nas notas (`replay/budget.py` e `replay/consumer_lag.py` precisam ser cientes de shard).

#### P1 — **confirmada**, e com precisão desconfortável

Fonte: `infra/scripts/sql/research/2026-09-11-t384-q01-barras-5m-15m.sql` (mesma janela de 31 d da
T3.54: 2026-08-08 → 2026-09-08) e `…-q02-…-90d.sql` (a janela própria do experimento, 90 d,
2026-06-12 → 2026-09-10), as duas com a mesma dobra no servidor e exigência de completude; ATR de
Wilder(14) sobre 97 barras rolantes **fora** do SQL, por
`.claude/state/exp-drafts/t384/medir_atr_5m.py`.

**Controle de método primeiro:** na janela da T3.54 esta conta devolve ATR%(15m) p50 =
**0,5582 %** contra os **0,5585 %** publicados — 0,05 % de diferença, explicada pelo backfill que
fechou os buracos daquela janela desde então. A conta é a mesma.

| medida | previsto (P1) | medido 31 d | medido 90 d |
|---|---:|---:|---:|
| ATR%(5m) p50 (mediana das medianas, 16 mkt) | **0,298 %** | **0,2984 %** | **0,2714 %** |
| razão 5m/15m | 0,534 | **0,5345** | **0,5449** |
| pedágio incondicional p50 (`0,0020/ATR%`) | 0,67 R | 0,6702 R | 0,7370 R |

A previsão dizia: *se `ATR%(5m) p50 > 0,40 %` esta previsão está errada*. Mediu-se 0,2984 % e
0,2714 %. **P1 não foi falsificada**; o expoente `H = 0,571` medido entre 15 m e 1 h vale também
entre 5 m e 15 m (implícito no dado de 90 d: `H = ln(1/0,5449)/ln 3 = 0,552`).

#### P2 — **mecanismo confirmado, número falsificado**

| medida | previsto (P2) | medido 31 d | medido 90 d |
|---|---:|---:|---:|
| fração de barras de 5 m no portão `[0,6 %; 5 %]` | corta quase tudo | **15,73 %** | **8,85 %** |
| a mesma fração a 15 m (a mãe) | — | 42,14 % | 33,04 % |
| ATR% p50 **condicional ao portão**, 5 m | **0,60–0,75 %** | **0,8211 %** | **0,7875 %** |
| ATR% p50 condicional, 15 m (a mãe) | 0,922 % (derivado do pedágio) | **0,9223 %** | 0,8149 % |

A última linha merece ser dita: a página derivou o ATR% realizado da mãe **de trás para frente**, do
pedágio p50 de 0,2169 R (`0,0020/0,2169 = 0,922 %`). A medição direta, na mesma janela, devolve
**0,9223 %**. Os dois caminhos se encontram na quarta casa — é a melhor prova disponível de que nem
a identidade de custo nem esta medição estão erradas.

O **mecanismo** de P2 está confirmado e é mais forte do que o previsto: o piso derruba de 33,04 %
para **8,85 %** das barras na janela do experimento. O **número** está errado: o ATR% condicional é
**0,79 %**, acima da banda 0,60–0,75 % que a página congelou.

#### P3 — **falsificada**, e é a descoberta desta seção

| medida | previsto (P3) | medido 31 d | medido 90 d |
|---|---:|---:|---:|
| pedágio p50 das decisões de 5 m | **0,267–0,333 R** | **0,2436 R** | **0,2540 R** |
| pedágio p50 da mãe, mesma janela | 0,2169 R | **0,2169 R** | 0,2454 R |
| Δ de pedágio (5 m − 15 m) | **+0,05 a +0,12 R** | +0,0267 R | **+0,0086 R** |

Na janela em que a versão seria avaliada, a filha de 5 min paga **oito milésimos de R a mais** por
operação do que a mãe — **uma ordem de grandeza abaixo** do que esta página previu. A razão está em
P2: o piso de 0,6 % não filtra a distribuição de 5 min, ele **seleciona a cauda volátil dela**, e a
cauda que sobrevive tem quase o mesmo ATR% que a mãe realiza. O prior de custo — KB-0076 aplicado à
mediana **incondicional** — estava certo sobre a grade e errado sobre as **decisões**.

**Consequência declarada, contra o interesse do prior desta página:** o argumento de custo
pré-registrado para `descartar` **não sobrevive à medição**. O veredito passa a depender inteiramente
da expectativa **bruta** a 5 min (P4), que é precisamente o que o replay mediria. A página fica mais
cara de fechar, não mais barata.

#### C5 — o `REVISE` estava certo, e pelo motivo que ele mesmo deu

| medida (90 d, leituras agregadas dos 16 mercados) | 5 m | 15 m |
|---|---:|---:|
| barras com ATR% ≤ 0,3 % (o piso de risco do `paper_v1`) | **60,29 %** | 21,51 % |
| barras com ATR% > 3 % (o teto) | 0,11 % | 0,63 % |
| **condicional ao portão `atr_pct_min`**: ≤ 0,3 % | **0,00 %** | 0,00 % |
| **condicional ao portão**: > 3 % | **1,11 %** | 1,69 % |
| mercados cuja **mediana** de 5 m cai sob o piso de 0,3 % | **11 de 16** | 0 de 16 |

As duas metades do `REVISE` estão medidas. (i) A coincidência **funciona**: nenhum stop emissível
cai fora da faixa `[0,3 %; 3 %]`, e a versão de 5 min está **menos** exposta ao teto (1,11 %) do que
a mãe (1,69 %). (ii) E o preço dela é o que o portão temia, em voz alta: **91,15 % das barras de
5 min ficam de fora**, e em **11 dos 16 mercados** a mediana da grade está abaixo até do piso de
risco. Esta versão não *escolhe* volatilidade alta — ela é **definida** pelo piso. Um experimento
que rodasse assim mediria o piso, e a frase que a página escreveu antes de qualquer dado continua
sendo a leitura correta do que ele significaria.

#### P5 — reestimada (não medida)

Com 3× mais barras e um portão 3,73× mais seletivo (33,04 % → 8,85 %), a expectativa de população é
`542 × 3 × 0,0885/0,3304 =` **≈ 436 decisões** em 90 d × 16 mercados, dentro da banda pré-registrada
de 160 a 810. *Assunção declarada:* que as outras três condições (tendência de 15 m, `z ≤ −1`,
fechamento acima do meio) são independentes do ATR% — não verificado, e só o replay verifica.

#### Limites desta seção, ditos

1. Nada aqui mede **retorno**. P4 — o eixo primário, `r_ex_funding` — continua sem uma única
   observação, e é ele que decide a página.
2. O ATR% condicional ao portão é condicional **só ao portão de ATR**, não às outras três condições
   de entrada; a distribuição real das decisões pode diferir.
3. A cobertura de velas foi de **100 %** nas duas janelas (414 720 barras de 5 m e 138 240 de 15 m
   em 90 d × 16 mercados, sem um balde incompleto), o que confirma a regra de elegibilidade da T3.82
   e remove "falta de dado" da lista de explicações possíveis.
4. A versão **não foi aposentada**. A regra do Everton — versão ruim morre no mesmo dia — vale para
   versão **medida** ruim; esta não foi medida. `--deprecate` aqui congelaria a linha sem resposta e
   jogaria fora a única coisa que o replay ainda pode dar. Ela segue `active`/`research_only`, e o
   custo disso está dito nas notas.

### Avaliação de 2026-09-11 — `as_of = 2026-09-11T10:42:26Z` (07:42 BRT) — **final: `descartar`, e o motivo não é o custo**

**Veredito: `descartar`.** A coorte existe, a régua editorial é alcançada com folga (**373 desfechos
avaliáveis** em **72 dias distintos**, contra o piso de 100 e 30) e **as quatro condições da regra de
sucesso congelada falham**. A versão foi aposentada na mesma tarefa, como a própria regra manda —
`deprecated` em **2026-09-11T10:54:08Z (07:54:08 BRT)**.

O que mudou desde a avaliação parcial de 05:50 BRT: o portão do `replay-worker` foi consertado pela
**T3.87** (`shard.py` expõe `heartbeat_keys`/`consumer_groups` pela topologia, `budget.py` toma o pior
dos N shards, o grupo órfão `strategy-worker.shadow` é detectado e ignorado com um log). Com ele de pé,
o replay rodou **sem uma única recusa e sem um único erro**.

#### A corrida

| item | valor |
|---|---|
| coorte | `replay:92c8d080-6009-4a59-9868-31282b1bd493` (uma só para as 23 fatias) |
| fatias | **23** — 1 de 4 mercados × 30 d e 22 de 4 mercados × 15 d, uma por vez, primeiro plano |
| barras avaliadas | **414 720** = 16 mercados × 90 d × 288 · conferido mercado a mercado: **25 920 cada, sem exceção** |
| janela | 2026-06-12 → 2026-09-10 (as três janelas de 30 d da EXP-0025) |
| `unavailable` | **736 barras (0,1775 %)** — K4 longe de disparar, e mensurável de verdade (esta versão não tem `eligibility_policy`, logo não há o falso verde da T3.52d) |
| erros | **0** · `decision_lag_s` assumido: 2 s · `context_minutes`: 1 560 (o piso, como previsto) |
| decisões | **597 `triggered`** → **373 desfechos terminais** com `r_ex_funding` (os 224 restantes são rearmes que não viraram entrada elegível) |
| tempo | 06:28 → 07:41 BRT, ~158 s por fatia de 15 d (≈ 110 barras/s com 4 processos) |

#### As quatro condições, uma a uma

| # | Condição congelada | Medido | Veredito |
|---|---|---|---|
| 1 | expectativa ex-funding em 90 d **> 0** com **IC 95 % de blocos de dia acima de zero** | **−0,1940 R**, IC95 **[−0,2889; −0,0943]** — o intervalo **inteiro** abaixo de zero; PF 0,6971 | **FALHA** |
| 2 | **PF > 1 em ao menos 2 das 3 janelas** de 30 d | J1 **0,5278** (n=75) · J2 **1,1657** (n=42) · J3 **0,6821** (n=256) → **1 de 3** | **FALHA** |
| 3 | **leave-one-market-out nunca negativo** (16 reajustes) | **negativo nos 16**, do melhor (`sem NEARUSDT` −0,1551) ao pior (`sem PROMUSDT` −0,2676); os IC95 dos 16 ficam **inteiramente abaixo de zero** | **FALHA** |
| 4 | estresse **não `frágil`** | `--stress` responde **`sem_vantagem_na_base`**: não há vantagem para estressar. Custos ×2 pioram para −0,3899 (Δ −0,1962 [−0,2116; −0,1818]); as **duas metades** da janela são negativas (1ª −0,2387, 2ª −0,1788) | **FALHA** (não avaliável por ausência de base) |

Bootstrap: blocos de **dia inteiro**, 20 000 reamostragens, semente **20260910** — as mesmas das
EXP-0025 e EXP-0026, de propósito, para que os IC sejam comparáveis entre as três páginas
(`.claude/state/exp-drafts/t362b/blocos90.py`, `.claude/state/exp-drafts/t384/analise.py`).

#### Funil K1–K6 — e o que ele **não** diz

| critério | medido | dispara? |
|---|---|---|
| K1 (< 20 decisões) | 373 | não |
| K2 (> 1 500) | 373 | não |
| **K3** (≥ 100 desfechos **e** ≥ 30 dias **e** bruta < 0) | 373 · 72 d · bruta **+0,0346 R** | **não, pela letra** |
| K4 (`unavailable` > 40 %) | 0,1775 % | não |
| K5 (cobertura de `R_net` < 70 %) | **99,20 %** (a mãe: 46,68 %) | não |
| K6 (≥ 60 % num mercado) | 28,15 % (PROMUSDT, 105/373) | não |

**Nenhum critério de morte dispara, e a versão morre de qualquer forma** — pela regra de sucesso, que
é mais exigente do que a régua de morte, e que foi escrita antes. Dito o que K3 esconde: a expectativa
bruta é positiva no ponto (+0,0346 R) mas o IC de blocos de dia é **[−0,0625; +0,1387]**, isto é,
**indistinguível de zero**. A cláusula "perde antes dos custos" não se aplica pela letra; a frase
honesta é "**não há vantagem bruta que um trabalho de custo possa resgatar**".

O K5 merece nota própria: a cobertura de `R_net` salta de 46,68 % na mãe para **99,20 %** aqui. Não é
melhoria de dado — é geometria: o horizonte de 4 800 s (1 h 20) atravessa uma liquidação de funding
muito mais raramente que as 4 h da mãe. Um efeito colateral do eixo, medido e não procurado.

#### De onde vem a piora — a decomposição que inverte o argumento desta página

O custo médio por decisão em R é uma **identidade**, não um modelo:
`custo = média(r_bruto) − média(r_ex_funding)`.

| | vantagem **bruta** | líquida (ex-funding) | **custo** medido | `0,0020/ATR%` (KB-0076) | ATR% p50 realizado |
|---|---:|---:|---:|---:|---:|
| mãe `mean_reversion v1` (15 m) | **+0,1270 R** | −0,0910 R | **0,2180 R** | 0,2354 R | 0,8495 % |
| filha `mean_reversion_m5 v1` (5 m) | **+0,0346 R** | −0,1940 R | **0,2285 R** | 0,2518 R | 0,7943 % |

`Δ líquida = −0,1030 R = Δ bruta (−0,0925 R) − Δ custo (+0,0105 R)`. Ou seja: **89,8 % da piora é a
vantagem bruta encolhendo e 10,2 % é o custo subindo.**

Isto é a terceira e última vez que esta página erra contra a própria versão pelo mesmo motivo. O
pré-registro apostou `descartar` **por custo** (KB-0076, KB-0086); a medição de 05:50 BRT já havia
falsificado P3 sobre a distribuição de barras; agora a medição **sobre as decisões que existiram**
confirma aquela falsificação com o número exato: o pedágio subiu **+0,0105 R**, não os +0,05 a +0,12 R
previstos. **O custo a 5 min é quase o mesmo da mãe. O que não existe a 5 min é o sinal.**

E o pré-registro nomeou este caminho antes: *"o que também seria informativo e não está previsto: uma
expectativa bruta a 5 min **maior** que +0,1270 R significaria que o sinal de reversão é mais forte no
relógio curto e que o problema é só custo"*. Aconteceu o **oposto exato**: a vantagem bruta a 5 min é
**3,7× menor** que a da mãe. Não há versão de custo (maker, alvo maior) a escrever — não há de onde
tirar o ganho. É este achado, e não o veredito, o que esta página entrega.

#### As cinco previsões, fechadas

| Previsão | Resultado | Número |
|---|---|---|
| **P1** ATR%(5m) p50 ≈ 0,30 % | **confirmada** (05:50 BRT) | 0,2984 % / 0,2714 % |
| **P2** o piso define a versão; condicional 0,60–0,75 % | **mecanismo sim, número não** | portão passa 8,85 %; ATR% realizado **nas decisões** p50 **0,7943 %** (p25 0,6791 · p75 1,1118) — o piso 0,006 é o p≈15 da própria população de decisões |
| **P3** pedágio 0,267–0,333 R, Δ +0,05…+0,12 R | **falsificada duas vezes** | 0,2518 R por KB-0076, **0,2285 R** pela identidade; Δ **+0,0105 R** |
| **P4** ex-funding −0,25 a −0,09 R, PF 0,65–0,90, veredito `descartar` | **confirmada, e no centro da faixa** | **−0,1940 R**, **PF 0,6971**, `descartar` |
| **P5** 160–810 decisões | **confirmada** | **373** (a reestimativa de 05:50 BRT era ≈ 436) |

**P4 acertou o resultado pelo motivo errado.** A faixa prevista foi construída somando um pedágio
maior a uma vantagem bruta intacta; o mundo entregou o mesmo número com pedágio intacto e vantagem
bruta destruída. Registrar isso importa mais do que o acerto: um pré-registro que acerta o número e
erra o mecanismo não valida o mecanismo.

#### C5 (`REVISE`) — as duas metades, agora sobre decisões e não sobre barras

Banda de risco do `paper_v1` `[0,3 %; 3 %]` sobre `initial_risk / entry`, 373 decisões:
**p50 0,8892 %**, **1 decisão (0,27 %)** abaixo do piso de 0,3 % e **7 (1,88 %)** acima do teto de 3 %
(a mãe, mesma leitura: p50 0,9242 %, 0,37 % e 2,21 %). Por janela: J1 0/0, J2 0/3 (7,14 % acima do
teto), J3 1/4.

A previsão de 05:50 BRT era **0,00 %** abaixo do piso; o medido é **uma** decisão. A explicação é
mecânica e vale registrar: o portão exige `ATR% ≥ 0,6 %` na **barra de decisão**, mas `risco_pct` é
medido contra o **preço de entrada** da barra seguinte — quando o preço sobe entre as duas, a mesma
distância de stop vale uma fração menor. C5 fica onde estava: **a versão cabe na banda por
dependência de um piso que existe por outro motivo**, e a exceção de 0,27 % é a prova de que a
dependência não é uma garantia.

#### Filha contra mãe, Δ pareado por dia — a honestidade que o número exige

As duas dividem o calendário de 90 d, então o contraste é **pareado por dia**: filha −0,1940 (n=373),
mãe −0,0910 (n=542), **Δ −0,1030 R, IC95 [−0,2670; +0,0686]** — **o intervalo cruza zero**. Dito sem
enfeite: a filha é pior no ponto, e **não é estatisticamente distinguível da mãe** com blocos de dia.
As duas são negativas; o que a coorte prova com IC é que **a filha é negativa** (condição 1), não que
ela seja *pior* que a mãe. O braço de falseamento pré-declarado cumpriu o papel: ele não salvou a
versão nem foi derrubado por ela.

#### Decomposição obrigatória por mercado (K6 não dispara, mas a régua exige a tabela)

| mercado | n | ex-funding | PF | ATR% médio |
|---|---:|---:|---:|---:|
| PROMUSDT | 105 | −0,0060 | 0,9893 | 1,4124 |
| UNIUSDT | 46 | −0,1971 | 0,6832 | 0,8282 |
| ZECUSDT | 43 | **+0,0688** | 1,1352 | 0,8155 |
| DASHUSDT | 36 | −0,1924 | 0,6847 | 1,0513 |
| ARBUSDT | 28 | −0,3418 | 0,5412 | 0,9699 |
| NEARUSDT | 27 | −0,6915 | 0,1928 | 0,7367 |
| TAOUSDT | 25 | −0,5503 | 0,3618 | 0,7666 |
| SAHARAUSDT | 21 | −0,1391 | 0,7720 | 0,8076 |
| DOGEUSDT | 13 | −0,5763 | 0,3219 | 0,7367 |
| XRPUSDT | 9 | −0,0850 | 0,8324 | 1,3196 |
| LINKUSDT | 9 | −0,3805 | 0,4599 | 0,6867 |
| SUIUSDT | 8 | −0,6744 | 0,2430 | 0,6995 |
| SOLUSDT | 2 | +1,2131 | — | 0,6842 |
| ETHUSDT | 1 | +0,8879 | — | 0,7516 |
| **BNBUSDT** | **0** | — | — | — |
| **BTCUSDT** | **0** | — | — | — |

**Dois dos 16 mercados elegíveis não produziram uma única decisão em 90 dias** (BNB e BTC, cujo ATR%
de 5 min tem mediana 0,1245 % e 0,1250 % e passa o piso em 0,15 % das barras). O universo **efetivo**
desta versão é de **14 mercados**, e os dois ausentes são justamente os dois de maior liquidez. Isso
é o C3 ("adequação da amostra") cobrando o preço previsto: a versão não escolhe onde operar, o piso
escolhe por ela — e ele escolhe as pontas.

Concentração de calendário, declarada: **J3 tem 256 das 373 decisões (68,6 %)** em 29 dias. O eixo de
volatilidade que abre a porta desta versão é o mesmo que concentra a amostra na janela mais agitada —
exatamente o efeito que a EXP-0025 mediu na mãe (C5 por regime) e que C4 pediu para medir em vez de
assumir.

#### Funil de saída

`stop` 197 (52,82 %, ex-funding médio −1,1696) · `target` 142 (38,07 %, +1,1106) · `expired` 34
(9,12 %, +0,0106). A mãe: 51,85 % / 39,85 % / 8,30 %. **A forma do funil é praticamente idêntica** —
a filha não perde por sair diferente, perde porque a taxa de acerto de 38,07 % não paga um R/R de 1,5
depois do pedágio (o ponto de equilíbrio bruto é ~40 %).

#### Aposentadoria — a regra do Everton aplicada ao caso que ela descreve

```
activate_strategy_version.py mean_reversion_m5 v1 --deprecate --changelog "T3.84/EXP-0028: ..."
deprecated mean_reversion_m5 v1 (purpose research_only) at 2026-09-11T10:54:08.545106+00:00, successor=none
```

A avaliação parcial de 05:50 BRT havia recusado aposentar com um argumento explícito: *"a regra vale
para versão **medida** ruim; esta não foi medida"*. Agora foi. O `changelog` gravado na auditoria
carrega os números, não a conclusão: coorte, 373 desfechos, IC, PF por janela, LOMO, veredito do
estresse e a decomposição bruta/custo.

#### Limites desta seção, ditos

1. **As fatias de 15 d não são as fatias de 30 d do protocolo.** Uma fatia de 4 mercados × 30 d levou
   **495 s** e estourou o `timeout` de 265 s do cliente (o container terminou sozinho e gravou o
   recibo; nada ficou pela metade). As 22 fatias seguintes foram de **15 d** com `--workers 4` — a
   saída que o brief autorizou. Consequência numérica, declarada: em cada fronteira nova
   (06-27, 07-27, 08-26) um acompanhamento aberto é liquidado pelo `drain_cohort` no fim da fatia, com
   velas reais até o seu próprio horizonte, e a fatia seguinte encontra o slot já rearmado. O
   horizonte é de 80 min, então o efeito vive em **3 × 80 min por mercado = 4 h de 2 160 h (0,19 %)** e
   só pode **adicionar** entradas perto da fronteira. Não há como o efeito produzir uma expectativa
   negativa; ele é a única diferença de método contra a EXP-0025, e é esta.
2. **`--workers 4` num container de 3 CPUs** é 1 acima do que o orçamento (`workers_for`) escolheria.
   É sobreinscrição contida pelo *cgroup* do `replay-worker`, nunca disputa com a faixa viva (outro
   container, outro limite). Não altera nenhum número: o paralelismo do replay é por mercado e cada
   mercado é uma máquina de estados independente.
3. **A elegibilidade é lida hoje**, não por barra (PIPELINE §6c). Os 16 são o universo de 2026-09-11.
4. **Dois mercados com zero decisões** não são um leave-one-market-out de verdade: o recorte
   "sem BNB" e "sem BTC" **é** a população inteira, e está na tabela dizendo isso.
5. **O explain-ledger não sobreviveu.** 23 JSONL (414 720 linhas) foram escritos em `/tmp` dentro de
   containers `docker compose run --rm` e morreram com eles — `replay-worker` não tem volume. O funil
   por estado que eu precisava deles está **durável** no recibo de cada corrida
   (`system_events.component = 'replay_engine'`, `evaluations_by_state`), e é dele que a linha
   `unavailable` desta seção sai.
6. **O que esta página não mediu:** nenhuma variante. `atr_pct_min` mais alto, alvo maior, `stop_atr`
   maior ou entrada maker seriam **versões novas**, com pré-registro novo. A leitura da decomposição
   acima recomenda **não** escrevê-las: sem vantagem bruta, mexer em custo não tem de onde tirar
   ganho.

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
