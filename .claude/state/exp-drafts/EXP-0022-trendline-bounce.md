---
tags: [experimento, trendline, repique, geometria, shadow-lab]
updated: 2026-09-09
status: em-andamento
owner: sexta-feira
exp: EXP-0022
strategy: trendline_bounce
version: v1
result: pendente
evaluable: 0
days: 0
last_eval: null
---

# EXP-0022 — repique em suporte ascendente com volume (`trendline_bounce_v1`)

> **RASCUNHO do quant-engineer (T3.57, 2026-09-09).** Para a Sexta-feira arquivar em
> `obsidian/05-EXPERIMENTS/EXP-0022-trendline-bounce.md` e ligar a partir de
> [[Strategy Backlog]], [[Experiments Index]], [[EXP-0016-trendline-breakout]],
> [[KB-0006-invalidacao-vs-stop-vs-tempo]] e [[KB-0077-linhas-de-tendencia]].
> Não editei `obsidian/**`.
>
> **Nada foi rodado. Nada foi ativado. Nada foi commitado.** "Hipótese", "Portão" e "Protocolo" são
> **congelados**; avaliações são **acrescentadas** abaixo, datadas. Brief: a tarefa T3.57.
> Recibos e ordem dos atos: `.claude/state/notes-T3.57.md`.

## Por que existe uma segunda versão (a procedência da hipótese)

O [[EXP-0016]] declarou uma hipótese sobre **rompimento** de linha de tendência e mediu outra coisa.
Números do dia um dele (`.claude/state/notes-T3.34c.md`, 2026-09-08, 47 decisões, 31 d × 4 mercados):

| achado da T3.34c | número | consequência aqui |
|---|---|---|
| **89,4 % das decisões foram repique**, não rompimento (K6 disparou) | 42 de 47 | a porta de repique vira **a versão**, não um modo |
| a porta de rompimento decidiu 5× e perdeu as 5 | 0 alvos, 4 invalidações, **−0,5075 R** cada | a porta de rompimento **não** existe aqui |
| remover a invalidação estrutural, pareado nos mesmos 47 episódios | **Δ +0,0922 R**, expectancy −0,038 → **+0,054** | **não há invalidação** nesta versão |
| C4 refutado: `line_slope_per_bar` é **colinear com o modo** | decil 1 de slope/ATR = exatamente os 5 rompimentos | **nenhum** limiar de inclinação é acrescentado |
| expectancy **bruta** positiva, líquida negativa só pelo pedágio | +0,1045 bruta, 0,1401 de custo | a margem é o pedágio; qualquer seleção que aumente o bruto vale mais que qualquer ajuste de saída |

**Isto é uma reenunciação, e ela é a que o próprio EXP-0016 exigiu** quando escreveu que ≥ 60 % de um
modo obriga a reenunciar a hipótese **antes** da avaliação seguinte
([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]). Reenunciar é honesto; o que não
seria honesto é fingir que a nova população é independente da que gerou a hipótese — não é, e o
rótulo de toda avaliação sobre a mesma janela continua sendo **REPLAY**.

## Hipótese (congelada)

Num perpétuo USDT de 15 min, o **repique confirmado numa suporte ascendente** — traçada por regra
com ao menos três toques, extremo da barra dentro de `tolerance_atr = 0,25` ATR da linha e
fechamento a `bounce_atr = 0,5` ATR dela — **numa barra que negociou ao menos o volume mediano das
últimas 96 barras** (`rvol_min = 1,0`) tem expectancy líquida hipotética positiva, **saindo apenas
por stop, alvo ou horizonte**.

Duas negações fazem parte da hipótese e são tão congeladas quanto ela:

1. **não há invalidação estrutural.** A linha continua desenhada, continua no envelope
   (`line_price_at_decision`) e **não** fecha operação nenhuma. Isso é a aplicação direta da
   [[KB-0006]] (*a invalidação adianta a perda, ela não a cria*), agora com a quinta população a
   confirmá-la;
2. **não há porta de rompimento.** Não como parâmetro desligado — como identidade: o contrato não
   tem `mode` nem `max_violations_breakout`, então nenhum `derive_variant.py --set` pode
   transformar esta versão de volta no outro experimento.

**A ressalva antes da tese, e ela é a mesma do EXP-0016:** "linha de tendência" é a figura mais
desenhada e menos medida da análise técnica
([[KB-0003-rompimento-de-canal-e-data-snooping]]). O que torna isto refutável é que a geometria é
determinística e o corte é uma barra — "a linha que existia às 14:15" é verificável.

## Procedência de `rvol_min = 1,0` (declarada, porque é o único número novo)

**Ordem dos atos, registrada em `.claude/state/notes-T3.57.md` antes da consulta:**

1. o limiar foi escolhido **por princípio**: 1,5 é um pedido de *expansão*, e a v1 dizia — com
   razão — que "repique é continuação, não expansão"; 1,0 é a leitura mínima de "com RVOL", isto é
   *não abaixo do normal*;
2. só **depois** o banco foi lido, para **uma** pergunta: a população sobrevivente ainda passa K1?

**Consulta** (`infra/scripts/sql/research/2026-09-09-t357-q00-rvol-dos-repiques.sql`, somente
leitura, `read_at = 2026-09-09 17:28:17+00`), sobre os 42 repiques da coorte
`replay:d78c14d1-b4c5-424a-8f31-a43100744bb4`:

| corte | n | RVOL médio | R líq. médio (com invalidação) | dias |
|---|---:|---:|---:|---:|
| todos os repiques | 42 | 1,7785 | +0,0177 | 13 |
| rvol ≥ 0,8 | 33 | 2,0993 | +0,1462 | 12 |
| rvol ≥ 0,9 | 29 | 2,2725 | +0,2203 | 12 |
| **rvol ≥ 1,0 (o congelado)** | **26** | 2,4264 | **+0,1676** | **11** |
| rvol ≥ 1,1 | 23 | 2,6049 | +0,2330 | 11 |
| rvol ≥ 1,25 | 22 | 2,6701 | +0,2662 | 11 |
| rvol ≥ 1,5 | 16 | 3,1542 | +0,1963 | 11 |

**A coluna de R vai publicada de propósito, e ela é a prova de que o limiar não foi escolhido por
ela:** 1,0 é um **mínimo local** entre os vizinhos (0,9 dá +0,2203, 1,1 dá +0,2330, 1,25 dá
+0,2662). Quem estivesse garimpando teria escolhido 1,25. O que a consulta autorizou foi só isto:
**26 ≥ 20, K1 não dispara**.

**O que a tabela não é:** evidência de que o portão de volume funciona. Ela é in-sample sobre os
mesmos 42 episódios que geraram a ideia, e a monotonicidade dela é fraca e não-monótona. A pergunta
"o volume seleciona?" é respondida pelo item 4 de "o que o dia um tem de publicar", não aqui.

## Portão de desenho (C1–C8) — congelado

**Declaração de processo, como no EXP-0016:** este portão foi escrito pelo mesmo quant que escreveu
o código, na mesma tarefa. É **autoavaliação**, não revisão viva. A revisão da Astra sobre as regras
de decisão continua **pendente**, e o C8 do EXP-0016 é o precedente exato de por que isso importa
(foi rebaixado de `PASS` para `REVISE` quando o número apareceu).

| # | Critério | Veredito | Justificativa |
|---|---|---|---|
| C1 | Plausibilidade da vantagem | **REVISE** | Mecanismo: um suporte ascendente com três toques é um nível onde compradores apareceram três vezes; um extremo que o toca e um fechamento que se afasta dele diz que apareceram de novo, e o volume acima da mediana diz que houve **transferência** e não apenas ausência de vendedor. Quem está do outro lado é quem vendeu no toque. **Mas:** o mecanismo é o mesmo do `sweep_reclaim_v1` (varredura de pivô e retomada, T3.45) e parente do pullback do `mean_reversion_v1`, e nenhum dos dois provou vantagem líquida. E a inclinação **não** acrescenta informação medida — a T3.34c mostrou que ela é o modo com outro nome. `REVISE` |
| C2 | Risco de sobreajuste | **REVISE** | 18 constantes de geometria continuam congeladas sem medição — mas **herdadas verbatim** da v1, não re-escolhidas aqui (`test_only_the_rvol_floor_differs_in_value_from_the_mother` prova que só `rvol_min` mudou de valor). O risco novo é outro e é real: esta versão é uma **seleção post-hoc feita sobre a janela que a gerou** (a porta escolhida depois de ver que 89,4 % das decisões vinham dela). É [[KB-0010]] em estado puro. O que segura: a seleção está **declarada**, a versão é nova (não um ajuste), e toda avaliação sobre 2026-08-08→09-08 sai rotulada **REPLAY** e serve para matar, nunca para promover |
| C3 | Adequação da amostra | **PASS com número pré-registrado** | Diferente do EXP-0016, aqui há estimativa: 26 decisões em 31 d × 4 mercados, 11 dias distintos, do corte de RVOL sobre os repiques da v1 (tabela acima). **Não é uma previsão exata** — a população da v2 não é subconjunto da da v1 (ver "o que o dia um tem de publicar", item 1) —, mas põe o piso de K1 a 30 % de folga. Continua **muito** abaixo dos 100 avaliáveis / 30 dias da régua de maturidade |
| C4 | Dependência de regime | **FAIL declarado, e é herdado** | `market_regimes` só tem `UNKNOWN` ([[KB-0076]] item 6) e o substituto que o EXP-0016 prometeu — inclinação da linha — **foi refutado** na T3.34c: colinear com o modo por construção. Esta versão **não tem** substituto de regime, e mente menos ao dizer isso do que ao repetir a promessa. Consequência aceita: se a janela de 31 d for um regime só, a expectancy medida não se transporta. Registrado como o principal limite deste experimento |
| C5 | Calibração das saídas | **PASS com ressalva herdada** | Stop estrutural (`min(pivô de baixa, C − 2·ATR)`), risco entre 2 e 3 ATR; a ~1 % de ATR% isso é 2 %–3 % do preço, **na borda** do `max_stop_distance_pct` de 3 % do `paper_v1` — irrelevante para `research_only`, **impeditivo** para promover a `paper`. Alvo `max(largura do canal, 2 R)`: equilíbrio bruto 33,3 %, ~37,8 % depois do pedágio. **Sem invalidação, o horizonte passa a fazer trabalho**: as saídas por expiração da v1 eram **positivas** (+0,6074 R em 9 casos), o que sugere que 8 h é curto — e mexer nisso é **versão nova**, declarado no docstring |
| C6 | Concentração de risco | **PASS** | `research_only`, sem carteira, sem ordens. Custo computacional idêntico ao da v1 (mesma varredura de 96 barras por corte); a suíte de 52 casos roda em 4,0 s |
| C7 | Realismo de execução | **PASS** | Custos idênticos aos das outras versões (2 + 5 + 4 bps, `max_entry_delay_s = 120`), entrada na abertura da barra seguinte pelo perfil congelado do SHADOW-LAB §3. **Teto de pedágio corrigido:** `0,002 / (risco_atr · ATR%)` R dá **0,20 R** no piso de ATR com risco de 2 ATR — e é este o teto declarado, não o 0,1333 R do EXP-0016, que era o melhor caso simultâneo e foi medido como falso (59,6 % das decisões pagaram mais, `notes-T3.34c.md` §6) |
| C8 | Qualidade da invalidação | **N/A por construção, e é a tese** | **Não há invalidação.** O critério não se aplica porque a versão declara, como hipótese, que a invalidação estrutural desta geometria não faz trabalho — é a [[KB-0006]] aplicada, com o Δ +0,0922 R da T3.34c como evidência prévia (fraca: IC 95 % [−0,0618; +0,2151], Holm não rejeita). **O que substitui C8 é uma medição obrigatória de mão dupla** (item 5 abaixo): se a v2 tiver cauda esquerda **pior** que a v1 pareada por barra, a tese está errada e isto tem de aparecer com a mesma clareza |

**Veredito do portão: `REVISE`** — 2026-09-09, quant-engineer, **autoavaliação**. Dois `REVISE`
(C1, C2), um `FAIL` declarado e aceito (C4), um `N/A` que é a própria tese (C8). As revisões, em
ordem:

1. **C2 é o risco dominante**, e não é resolvível por medição nesta janela: a porta foi escolhida
   depois de ver o resultado. A única leitura que vale como confirmação é **prospectiva**, em
   `prospective`, sobre barras que ainda não existem;
2. **C4:** publicar a decomposição por mercado e por dia; sem regime, é o que sobra para dizer se a
   vantagem é um mercado ou uma semana;
3. **C1:** a comparação que interessa é contra o `sweep_reclaim_v1` (mesmo mecanismo, nível
   horizontal e pivô único) na mesma janela e nos mesmos mercados.

## Protocolo (congelado na primeira ativação — nunca editar)

- **Strategy:** `strategies.key = trendline_bounce` (**família nova**, acrescentada a
  `infra/scripts/seed_reference.py`), versão `v1`, `purpose = research_only`.
  Módulo `packages/core/hunter_core/strategies/trendline_bounce_v1.py`.
- **`code_ref` previsto:**
  `hunter_core.strategies.trendline_bounce_v1@sha256:fb7263ce5f06956f6d57c86f2a0790c62644b3f453904d83546674de4dabdb75`
  (fecho de 13 módulos: `aggregate, base, canonical, envelope, indicators, numeric, schema,`
  `tl_events, tl_lines, tl_pivots, tl_scan, tl_setup, trendline_bounce_v1`). **Conferir no
  `--dry-run` antes de escrever; se divergir, PARAR.**
- **`params_hash` previsto:** `9b1e882f169c89ca` (34 parâmetros).
- **Os seis digests vivos não se moveram** e um teste os pina
  (`test_the_six_live_digests_did_not_move`): `momentum_v1 …ab2e0398…`,
  `volume_anomaly_v1 …9b8c14ab…`, `breakout_v1 …4c920b0c…`, `mean_reversion_v1 …a970c9d9…`,
  `session_orb_v1 …a4d514ad…`, `trendline_breakout_v1 …7b83a1ff…`.
- **A v1 não está no fecho desta versão.** `trendline_bounce_v1` importa os cinco `tl_*` e **não**
  importa `trendline_breakout_v1` — os dois experimentos são independentes, e um `import` os
  amarraria pelo digest. Provado por `test_the_closure_is_the_geometry_and_not_the_other_experiment`.
- **Janela de contexto:** **1470 min**, declarada em
  `hunter_strategy_worker.context_budget.WINDOWS` (T3.54b: uma versão que este build não sabe
  dimensionar é **recusada** na ativação, nunca emudecida). Cabe no piso de 1560 já implantado, então
  nenhuma população viva se move.
- **Timeframe de decisão / de outcome:** 15 min (fechamentos distintos, UTC) / 1 min.
- **Regra de entrada (exata), na ordem — idêntica à da v1 para que dois livros-razão pareiem barra a
  barra:** elegibilidade → janela de 97 barras de 15 min → janela de ATR (Wilder 14 × 15 m, 97
  barras, `rolling_window_v1`) → varredura da geometria nas **96** últimas barras → **evento de
  repique nesta barra, em suporte ascendente** (`find_trigger(scan, MODE_BOUNCE)`) → **volume
  relativo ≥ 1,0** → qualidade da linha (`touches ≥ 3`, `violations ≤ 2`) →
  `0,005 ≤ ATR% ≤ 0,05` → pivô de baixa confirmado.
- **Geometria:** `stop = min(mínima do último pivô de baixa confirmado, C − 2·ATR)`;
  `risk = C − stop`; `alvo1 = C + max(largura do canal, 2·risk)`; **`invalidations = ()`**;
  horizonte 8 h.
- **Duas recusas (`REJECTED`, o mercado não re-arma):** `geometry` e `risk_too_wide`. A terceira da
  v1, `geometry_invalidation`, **não existe** — provado por
  `test_there_is_no_invalidation_guard_left_to_refuse_anything`.
- **Parâmetros congelados:** **34** chaves = as 36 da v1 **menos** `mode` e
  `max_violations_breakout`; **um único valor movido**, `rvol_min` de 1,5 para 1,0.
- **Universo:** replay em ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT (os mesmos quatro da T3.34c, para que
  o pareamento seja possível); `prospective` no universo elegível.

### Premissas numéricas declaradas

Os 18 parâmetros de geometria e os quatro de custo são **herança verbatim** da v1 (T3.34, prática
clássica), nenhum medido. `target_r = 2,0` é convenção. `atr_pct_min = 0,005` é o piso do
`breakout_v1` ([[KB-0008]]). `rvol_min = 1,0` é o único número novo e tem procedência declarada na
seção acima. `horizon_s = 28800` é herdado **apesar** de a T3.34c sugerir que é curto — mudar é uma
quarta mudança e uma quarta versão.

## O que falsifica esta hipótese

- **K1** < 20 decisões · **K2** > 1 500 decisões · **K3** ≥ 100 avaliáveis **e** ≥ 30 dias **e**
  expectancy **bruta** < 0 · **K4** `unavailable` > 40 % · **K5** cobertura de `R_net` < 70 %
  (`.claude/state/notes-T3.33.md` §5.1).
- **K6 (a regra dos 60 %, reescrita para esta versão).** O eixo "modo" deixou de existir — só há
  uma porta —, então K6 aqui é **só por mercado**: se ≥ 60 % das decisões vierem de **um** mercado,
  a hipótese é sobre aquele ativo e tem de ser reenunciada **antes** da avaliação seguinte. (Na
  v1 o maior mercado foi 31,9 %; se subir para ≥ 60 % com a porta fechada, é sinal de que a porta
  fechada era o que segurava a diversidade.)
- **Falsificação própria desta versão, e é a mais importante:** se o Δ pareado contra a v1 (item 5)
  for **≤ 0**, então retirar a invalidação **não** ajudou nesta população, o achado da T3.34c não se
  reproduz nem sobre a sua própria janela e a tese central desta versão está errada.

## O que o dia um tem de publicar, além do recibo padrão

1. **A população, e por que ela não é um subconjunto da da v1.** Contagem por estado e por motivo, e
   **explicitamente** as três fontes de divergência: (a) barras em que a v1 achou um **rompimento**
   primeiro (`find_trigger` testa rompimento antes) e que aqui podem devolver um repique — a v2 pode
   ter decisões que a v1 **não** tem; (b) a barra que a v1 recusou por `geometry_invalidation`, que
   aqui não é recusada; (c) os repiques com RVOL < 1,0, que a v1 tinha e a v2 não.
   **Consequência operacional (T3.52d): o pareamento é por `(mercado, barra)`, nunca por "a v2 é um
   subconjunto".**
2. **Expectancy bruta, custo e líquida**, com a identidade do pedágio (`0,002 / (risco_atr · ATR%)`)
   conferida contra o custo medido, como na T3.34c §6.
3. **Decomposição por mercado e por dia** (bloco de dia, IC 95 % de t sobre as médias diárias) — o
   que sobra sem regime (C4).
4. **O portão de volume tem de se justificar.** Expectancy por **tercil de `relative_volume_15m`**
   dentro da população da v2, mais a contagem de `rvol_low`. Se o tercil baixo (o mais próximo de
   1,0) não for pior que os outros, o portão não selecionou nada e o `rvol_min` desta versão é
   decoração — o que é um resultado, e tem de ser escrito.
5. **O CONTRASTE PAREADO CONTRA A v1 — pré-registrado em 2026-09-09, antes de qualquer replay desta
   versão.** Rodar a v2 na **mesma janela** (2026-08-08 → 2026-09-08), nos **mesmos quatro
   mercados**, com `--explain-ledger`, e parear por `(mercado, barra de decisão)` contra a coorte
   `replay:d78c14d1-b4c5-424a-8f31-a43100744bb4`:

       Δ = média sobre as barras em que AS DUAS decidiram ( R_v2 − R_v1 )

   publicando **quatro** números, nunca só o primeiro:
   - **n pareado** (barras em que as duas decidiram), **n só-v2** e **n só-v1** — e o Δ **não** pode
     ser lido sem os dois últimos, porque uma versão que decide menos e melhor não é a mesma
     afirmação que uma que decide igual e melhor;
   - **Δ médio** com IC 95 % por **bloco de dia** e p de Holm, como no [[EXP-0007]];
   - **a cauda esquerda das duas** (pior decil de R, e o R médio das perdedoras): é o que substitui o
     portão C8;
   - **a leitura condicionada**: nos episódios em que a v1 saiu por `invalidated`, qual foi o R da
     v2 na mesma barra.
6. **Expectancy pré-registrada, para que a surpresa seja legível.** Partindo dos 26 repiques com
   RVOL ≥ 1,0 da v1 (soma **+4,3588 R**, média **+0,1676 R**, 10 saídas por invalidação) e do Δ por
   episódio invalidado medido na T3.34c (**+0,188462 R**), a projeção desta versão sobre a mesma
   janela é **+0,2401 R líquidos por decisão** em ~26 decisões e ~11 dias, com ~6 alvos.
   **Isto não é uma previsão: é o valor que a aritmética da v1 implica se nada mais mudar.** Um
   resultado materialmente abaixo dele significa que a diferença de população (item 1) trouxe
   decisões piores; materialmente acima, que trouxe melhores. Nos dois casos a explicação tem de ser
   o item 1, não uma narrativa nova.
7. **Linhas válidas por barra, `touches` das linhas que dispararam, e `pattern_retired_lines`** — os
   mesmos três da v1, para que a geometria seja comparável entre as duas.

## O que este experimento **não** prova

- **Não valida a figura "linha de tendência".** Valida **uma** regra determinística de traçado, com
  18 constantes, uma das seis possíveis ([[KB-0077]] §7).
- **Não prova que a porta de repique é melhor que a de rompimento.** Essa comparação já foi feita
  olhando o resultado; o que sobra é medir a porta escolhida, sabendo disso.
- **Não prova que a invalidação faz mal.** Prova, no máximo, que **esta** versão sem ela vai melhor
  que **aquela** com ela, nas barras em que as duas decidiram — e a evidência prévia (T3.34c) tem IC
  que contém zero.
- **O replay de abertura não confirma nada.** A janela avaliada é a que gerou a hipótese **duas
  vezes** (a v1 a gerou, e a v2 foi desenhada olhando o resultado da v1). Rótulo **REPLAY**, serve
  para matar. A leitura que vale é `prospective`.
- **Multiplicidade:** é a nona versão aberta nesta casa, e a **segunda** da mesma família sobre a
  mesma janela — o preço de multiplicidade da [[KB-0010]] é maior aqui do que numa família nova.
- **A elegibilidade replayada é a de hoje**, não a da janela (PIPELINE §6c).

## Avaliações (acrescentadas, nunca reescritas)

*(nenhuma: a versão ainda não foi semeada nem ativada em 2026-09-09)*

## Variantes tentadas

| Variante | Quando | Por quê | Onde ficou registrada |
|---|---|---|---|
| `derive_variant` da v1 com `mode = bounce` | 2026-09-09 | **recusada por impossibilidade, não por gosto:** `mode="bounce"` existe, mas **nenhum parâmetro desliga a invalidação estrutural** — ela é construída incondicionalmente em `trendline_breakout_v1._decide` e o guarda `geometry_invalidation` é igualmente incondicional. Uma derivação entregaria uma das duas mudanças e mentiria sobre a outra | `.claude/state/notes-T3.57.md` §1 |
| editar `trendline_breakout_v1.py` / `tl_setup.py` | 2026-09-09 | recusado: re-congelaria a v1 já ativada na VPS (`…7b83a1ff…`) e o Lab emudeceria atrás de um `/ready` verde | `tl_setup.py`, docstring ("um futuro `trendline_*_v2` … adicionaria o próprio módulo") |
| `import trendline_breakout_v1` para reusar `_decide` | 2026-09-09 | recusado: poria o código de outro experimento dentro deste fecho, e uma edição aqui re-congelaria a v1 | `test_the_closure_is_the_geometry_and_not_the_other_experiment` |
| limiar de inclinação mínima (só a faixa C da T3.34c) | 2026-09-09 | recusado: a faixa C tinha 37 casos contra 5 nas outras duas, e a inclinação é **colinear com o modo** — fechar a porta de rompimento já é o filtro. Acrescentar o limiar seria contar a mesma seleção duas vezes | C4 acima |
| `horizon_s` maior (as saídas por expiração da v1 eram positivas) | 2026-09-09 | adiado: é uma quarta mudança e tornaria o contraste pareado ilegível. Registrado como a próxima variante candidata | C5 acima |
| `rvol_min = 1,25` (o melhor da tabela in-sample) | 2026-09-09 | recusado: escolher o máximo de uma coluna de R medida nos mesmos episódios é exatamente a [[KB-0010]]. O congelado é o valor escolhido por princípio, que é um mínimo local | "Procedência de `rvol_min`" acima |

## Relacionadas

[[Experiments Index]] · [[Strategy Backlog]] · [[EXP-0016-trendline-breakout]] ·
[[EXP-0007-momentum-invalidacao-bracos-INV]] · [[EXP-0017-sweep-reclaim]] ·
[[KB-0003-rompimento-de-canal-e-data-snooping]] ·
[[KB-0006-invalidacao-vs-stop-vs-tempo]] ·
[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] ·
[[KB-0076]] · [[KB-0077-linhas-de-tendencia]] · [[Registro de Tentativas]]

**Por que [[KB-0006]] é a página-mãe deste experimento:** ela diz, em quatro populações do
[[EXP-0007]] mais a quinta da T3.34c, que *a invalidação adianta a perda, ela não a cria*. Esta
versão é a primeira desta casa a **nascer** dessa frase em vez de a redescobrir: ela não tem
invalidação nenhuma, e o item 5 do dia um é o teste que pode desmenti-la.

## Fontes

`.claude/state/notes-T3.57.md` · `.claude/state/notes-T3.34c.md` ·
`.claude/state/exp-drafts/EXP-0016-trendline-breakout.md` ·
`infra/scripts/sql/research/2026-09-09-t357-q00-rvol-dos-repiques.sql` ·
`packages/core/hunter_core/strategies/trendline_bounce_v1.py` ·
`packages/core/tests/unit/strategies/test_trendline_bounce_v1.py` ·
`infra/scripts/seed_reference.py` · `infra/scripts/activate_strategy_version.py` ·
`services/strategy-worker/hunter_strategy_worker/context_budget.py` ·
`services/strategy-worker/hunter_strategy_worker/replay/run.py`
