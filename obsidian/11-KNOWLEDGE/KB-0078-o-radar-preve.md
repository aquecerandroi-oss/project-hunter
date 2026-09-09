---
tags: [knowledge, nota, radar, anomalias, oportunidades, previsibilidade, diagnostico, m3]
tema: o Radar (anomalias) e a página Opportunities (score ranqueado) preveem alguma coisa?
fonte: dado próprio da VPS — `anomalies`, `opportunities`, `opportunity_history`, `feature_baselines`, `signal_outcomes`, `candles`
fonte_url: —
lido_em: 2026-09-08
evidencia: seis consultas SQL somente leitura + dois bootstraps por blocos (reuso de `t342-blocos/blocos.py`)
hipotese_testavel: sim — a condição de reabertura está quantificada em §6
astra: pendente
status: arquivada
owner: sexta-feira
updated: 2026-09-08
confiança: "?"
---

# O Radar prevê alguma coisa? — o que 1,8 dia de anomalias e 176 desfechos cruzados dizem

> Arquivada pela Sexta-feira em 2026-09-08 (T3.46). Decisão: Radar rebaixado a painel até a condição de reabertura em §6; nenhuma estratégia lê o Radar. Ver [[KB-0076-por-que-perdemos-2026-09-08]].
>
> **Nota de vocabulário controlado (lint, 2026-09-08):** o campo `confiança` do frontmatter aceita
> só `anedótico | backtest do autor | estudo revisado | replicado | ?` (`obsidian_lint_rules.py`).
> Esta KB é diagnóstico de dado próprio, não literatura — mesma categoria de [[KB-0076-por-que-perdemos-2026-09-08]]
> e [[KB-0077-linhas-de-tendencia]], ambas `"?"`. A nuance real ("alta no diagnóstico de cobertura;
> baixa em qualquer afirmação de previsibilidade — amostra insuficiente, e isso é o achado") não cabe
> no vocabulário de uma palavra e fica registrada aqui, por extenso, em vez de forçada no frontmatter.

## O que provocou a pergunta

O Everton, em 2026-09-08 às 19:25: *"e o radar, o que ele tá fazendo, não tá ajudando?"*. A pergunta
tem duas metades e as duas são o mesmo pipeline: as **anomalias** (`PIPELINE.md` §3) e o **score de
oportunidade ranqueado** (`PIPELINE.md` §5) saem do mesmo `scanner-worker`, das mesmas baselines, no
mesmo corte. Esta nota responde para os dois de uma vez.

## 1. O fato que precisa vir antes de qualquer número

**Nenhuma estratégia consome o Radar hoje.** `StrategyContext`
(`packages/core/hunter_core/strategies/base.py:109`) tem `exchange`, `symbol`, `source_bar_close`,
`candles_1m`, `funding`, `open_interest` e `eligible`/`eligibility_reason` — e mais nada. Não há
campo de anomalia, de score ou de regime. O `strategy-worker` não tem uma linha sequer que mencione
`opportunit` ou `anomal`. O único parâmetro do sistema que serviria a isso —
`agent_configs.min_opportunity_score` — é do caminho de proposta do M4 e não é lido por serviço
nenhum.

Portanto: **o Radar não está ajudando nem atrapalhando o Lab, porque não está ligado nele.** A
pergunta "ele ajuda?" é, hoje, a pergunta "ele *ajudaria* se fosse ligado?" — e é essa que as
seções seguintes tentam responder.

## 2. O Radar é jovem, e isso domina tudo

| medida | valor |
|---|---|
| primeira anomalia gravada | 2026-09-07 02:24:01Z |
| primeira amostra de score | 2026-09-07 02:40:20Z |
| histórico total | **1,8 dia** |
| mercados monitorados | 217 |
| mercados com alguma anomalia | **25** |
| linhas de `feature_baselines` que passam o gate da `opportunity_weights` v2 | **4,28 %** (11 754 de 274 596) |
| tipos de anomalia do enum que já produziram uma linha | **4 de 12** |
| **maior score já gravado** | **38,33** |
| primeiro degrau da página (`WATCHING`) | **40** |

A última linha merece parágrafo próprio. O `PIPELINE.md` §5 desenha cinco degraus —
`NORMAL < 40 → WATCHING 40 → HOT 75 → ENTRY_CANDIDATE 80`. Em 20 392 amostras, **100 % ficaram em
`NORMAL`**. A página "Opportunities" nunca teve um candidato. Ela ranqueia — o decil de cima vai a
38, o de baixo fica em 0 —, mas ranqueia dentro da faixa que o próprio sistema chama de "nada
acontecendo".

**Por quê:** o heartbeat do scanner (`hb:scanner:*`, lido em 2026-09-08 22:36 UTC) mostra
`baselines_usable = 9 029` contra `baselines_under_construction = 102 597` (**8,1 %**) e
`baselines_state = "bootstrapping 1000FLOKIUSDT (4/200)"`. Um componente sem baseline é `None`, o
peso dele é redistribuído (a regra do §4b item 4, que é a regra certa), e a nota final nunca sobe.
A cobertura confirma a mesma história: dos 25 mercados cobertos, **17 estão entre os 30 primeiros em
ordem alfabética** e 7 entre os 30 últimos. A cobertura do Radar é a posição do ponteiro de um
bootstrap sequencial, não uma escolha de liquidez.

## 3. A anomalia carrega informação sozinha? (o teste que não depende de estratégia)

Para cada uma das 1 292 anomalias: o retorno do mercado em +1 h / +4 h / +24 h, contra **toda** barra
de 1 min do **mesmo mercado**, na **mesma janela**, sem anomalia nos 60 min anteriores.

| horizonte | eventos | barras de base | retorno após anomalia | retorno da base | movimento absoluto após | movimento absoluto da base |
|---|---|---|---|---|---|---|
| 1 h | 1 247 | 37 959 | −0,116 % | +0,021 % | 1,029 % | 0,992 % |
| 4 h | 1 090 | 36 569 | +0,003 % | +0,062 % | 1,794 % | 1,938 % |
| 24 h | 679 | 8 888 | +0,945 % | +1,531 % | 3,978 % | 3,730 % |

Com intervalo (bootstrap por blocos de hora, 44 blocos, estimador pareado por mercado):

| contraste | Δ | IC95 |
|---|---|---|
| retorno com sinal, 1 h | −0,1375 pp | [−0,3759; +0,1246] |
| movimento absoluto, 1 h | **+0,0374 pp** | [−0,1165; +0,1980] |
| retorno com sinal, 4 h | −0,0615 pp | [−0,6098; +0,4927] |
| movimento absoluto, 4 h | −0,1459 pp | [−0,4215; +0,1179] |

**Leitura:** uma anomalia não marca uma hora mais direcional **nem uma hora mais agitada** do que uma
hora qualquer do mesmo mercado. Todos os intervalos cruzam o zero, e em 4 h o sinal do movimento
absoluto **inverte**.

E o rótulo de direção que o detector publica:

| direção declarada | n (1 h) | acerto do sinal | retorno 1 h | retorno 4 h |
|---|---|---|---|---|
| `down` | 648 | 54,6 % | −0,082 % | +0,051 % |
| `up` | 598 | **45,3 %** | −0,153 % | −0,051 % |

Anomalia marcada como `up` é seguida de queda em 1 h e acerta o sinal em 45,3 % das vezes. Com
598 eventos isso é medida, não anedota — e o que ela mede é ausência.

## 4. O Radar separa os desfechos do Lab?

De **6 283** desfechos do Lab, **176** (5,5 % da população prospectiva dentro da janela, 0 % de
qualquer replay) têm o Radar comprovadamente olhando o mesmo mercado no instante da decisão.
"Comprovadamente" = existe amostra de `opportunity_history` daquele mercado nos 15 min anteriores à
decisão; sem essa prova, "sem anomalia" significa "ninguém estava olhando".

| janela | com anomalia | n | expectancy líquida | acerto | PF |
|---|---|---|---|---|---|
| 4 b (60 min) | não | 35 | −0,148 R | 37,1 % | 0,70 |
| 4 b (60 min) | sim | 141 | −0,172 R | 31,2 % | 0,71 |
| 16 b (240 min) | não | **23** (1 dia!) | +0,147 R | 52,2 % | 1,45 |
| 16 b (240 min) | sim | 153 | −0,215 R | 29,4 % | 0,65 |
| 96 b (1440 min) | sim | **176 (todos)** | −0,167 R | 32,4 % | 0,71 |

Na janela de 96 barras **não existe grupo de controle**. Na de 16 barras o controle tem 23 decisões
de **um** dia. E o score:

- **Spearman entre score na decisão e `r_net`: −0,0896** (n = 176).
- Decis sem ordem: decil 2 = +0,34 R, decil 4 = −0,52 R, decil 7 = −0,52 R, decil 10 = +0,12 R.
- Quartil de cima do score: +0,103 R contra −0,258 R do resto — **mas** o bootstrap por blocos de
  hora dá IC95 `[−0,2169; +0,6006]`, que cruza o zero.

**Nenhum dos seis gates testados sobrevive ao bootstrap.** Detalhe metodológico que vale registrar
como aprendizado: com blocos de **dia** (o padrão do [[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] e do T3.42) só existem **2 blocos**,
e o gate "sem anomalia" aparece com IC `[+0,3143; +0,4500]` — excluindo o zero. É artefato de ter 2
blocos com o subconjunto quase inteiro dentro de um deles. Com blocos de **hora** (38 blocos) o mesmo
gate dá `[−0,2669; +0,7754]`. **Um bootstrap por blocos com 2 blocos não é um bootstrap por blocos**;
é uma máquina de fabricar achados.

Outra armadilha, registrada para não circular: ignorando a exigência de cobertura, o contraste vira
−0,261 R (sem anomalia, n = 3 003) contra −0,205 R (com anomalia, n = 216) e *pareceria* que a
anomalia ajuda. Não ajuda — os 3 003 são majoritariamente mercados que o scanner nunca olhou. Esse
número mede **cobertura**, não previsão.

## 5. Veredito

**O Radar não prevê nada hoje — e a causa principal é que ele mal existe ainda.** Não há direção
depois da anomalia, não há sequer movimento extra, o rótulo `up` erra mais do que acerta, o score
não ordena resultado (ρ = −0,09) e nenhum corte sobrevive a um intervalo honesto. Ao mesmo tempo,
25 de 217 mercados, 8 % das baselines prontas, 4 de 12 detectores vivos e 1,8 dia de série **não são
um teste da ideia** — são um teste do aquecimento. As duas frases têm de andar juntas: *não há
evidência de que ajuda* e *não houve teste justo*.

## 6. Recomendação: rebaixar a painel, com condição de reabertura escrita

**Não construir a variante gateada pelo Radar agora.** Três motivos:

1. **Não existe parâmetro.** Exigiria um campo novo (`radar_gate`) em `StrategyContext`, o que muda
   a assinatura que todas as versões vivas usam e mexe no digest do catálogo — custo alto em cima de
   176 observações.
2. **O gate seria cego em 88 % da população.** Só 25 dos 217 mercados têm Radar; nos outros ele
   responderia "não sei".
3. **A pergunta é de dado, não de estratégia.** Gatear por um score cujos componentes estão ausentes
   é gatear pela ordem alfabética do bootstrap de baselines.

**Manter o Radar rodando como painel de observação** (é barato e é a única série que enxerga o
universo inteiro), **marcar na página que os degraus `WATCHING`/`HOT`/`ENTRY_CANDIDATE` nunca
acenderam** — mostrar degraus inalcançáveis ensina o operador a desconfiar do produto —, e **não
investir em detector novo, peso novo ou gate** até a condição abaixo.

**Condição de reabertura (repetir exatamente as seis consultas quando as três valerem):**

1. `feature_baselines` com **≥ 60 %** das linhas passando o gate da `opportunity_weights` v2;
2. `anomalies` cobrindo **≥ 150 mercados**;
3. **≥ 14 dias** de série contínua.

Com isso o contraste "com/sem anomalia" teria ordem de 3 000 desfechos cobertos e 14 blocos de dia —
aí o bootstrap do T3.42 responde de verdade, sem desvio de bloco.

**Um item que não espera pela condição:** `ORDERBOOK_IMBALANCE`, `OPEN_INTEREST_SPIKE` e
`TRADE_VELOCITY_SPIKE` não produziram **nenhuma** linha e **não** aparecem em `detectors_disarmed`
(que declara motivo para `CROSS_EXCHANGE_DIVERGENCE`, `FUNDING_ANOMALY` e `LIQUIDATION_CLUSTER`).
Silêncio com motivo é decisão; silêncio sem motivo é defeito.

## 7. Uma dívida de schema que este estudo esbarrou

`anomalies.severity` é **mutável**: o §3 atualiza a linha enquanto o episódio dura, então o valor
gravado é o do **fim**. Prova disso está no próprio inventário — a severidade mediana de
`VOLUME_SPIKE`, `MOMENTUM_SHIFT` e `PRICE_ACCELERATION` é **0,0**. Consequência: **"qual era a
severidade quando a decisão foi tomada" não é respondível pelo schema**, e o corte mais óbvio do
§5 ("anomalia com severidade ≥ 60", que é o gatilho do status `ANOMALY`) é irreproduzível
retroativamente. Este estudo usou só `detected_at` e `type`, que são imutáveis.

Pedido: uma série de amostras de severidade (o análogo de `opportunity_history` para anomalias), ou
`severity_at_detection` / `peak_severity` imutáveis na linha. Sem isso o Radar nunca será auditável
para trás — e um Radar não auditável não pode ser promovido a gate de estratégia nem quando as
baselines maturarem.

## Ligações

- [[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] — por que o bloco é o dia (e, aqui, por que 2 blocos não servem)
- `PIPELINE.md` §3 (anomalias), §4b (regime horário e a regra de redistribuir peso de componente
  ausente), §5 (score e degraus)
- `.claude/state/notes-T3.46.md` — tabelas cruas, comandos e `read_at`
- `infra/scripts/sql/research/2026-09-09-radar-0{1..6}-*.sql` — as consultas, executáveis sozinhas
