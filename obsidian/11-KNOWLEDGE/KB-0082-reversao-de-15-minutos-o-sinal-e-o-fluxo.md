---
tags: [knowledge, nota, mean-reversion, microestrutura, fluxo, custos, plantao, m3]
tema: reversão direcional de curto horizonte (15 min) em cripto — o sinal está no sinal do candle e no fluxo taker, e o edge bruto não paga custo
fonte: Kitron & Wengrowicz (2026), "Short-horizon mean reversion in cryptocurrency markets — a matched cross-market measurement", arXiv 2608.21888v1 (q-fin.TR, q-fin.ST), submetido em 2026-08-22
fonte_url: https://arxiv.org/html/2608.21888v1 (HTML completo, aberto) · https://arxiv.org/abs/2608.21888 (resumo)
lido_em: 2026-09-09
evidencia: preprint com protocolo congelado e holdout de 6 meses fora da amostra; dado de uma exchange (Binance spot), 14 meses; nenhuma medição própria nesta nota
hipotese_testavel: sim — H-P1a (ganho incremental sobre controle lag-1) e H-P1b (líquido > 0 a 20 bps), ver §Hipótese
astra: concorda
status: curada
owner: sexta-feira
updated: 2026-09-09
confiança: "?"
---

# KB-0082 — reversão de 15 minutos: o sinal está no sinal, e o fluxo taker é quem o carrega

> **Escrita pelo plantão de mercado em 2026-09-09 (T3.64, run 1, faixa 1)**, a partir do rascunho
> `.claude/state/plantao/2026-09-09-1700-lane1.md`. O HTML do artigo foi aberto duas vezes
> (19:24 e 19:41 de Brasília) — a segunda para conferir três números que a Astra questionou. Nenhum
> número aqui é de memória. Nada foi medido no nosso dado: a medição é a hipótese da §Hipótese, que
> entrou em [[Hipoteses-do-plantao]] como `nova`. Nada é dinheiro real.
> **Por que esta nota existe:** a `mean_reversion` é a única família com expectancy líquida positiva
> no Lab ([[EXP-0009-mean-reversion-pullback-em-tendencia]]), e este é o primeiro texto que li com
> holdout congelado sobre exatamente o horizonte em que ela opera. Se o que ela captura for só o que
> o artigo mede, ela não paga o pedágio de [[KB-0076-por-que-perdemos-2026-09-08]].

## O que afirma

A 15 minutos, a **reversão direcional** (a próxima barra fecha contra a anterior mais vezes do que o
acaso) é muito mais forte e difundida em cripto do que em ações: sob um protocolo pareado e
estritamente fora da amostra, **90 % de 183 pares spot USDT da Binance** carregam reversão
significativa (controle de FDR) contra **2,7 % de 187 ações e ETFs dos EUA**, "em todo coin-year
focal desde 2021". Três achados organizam o resto:

1. **O sinal vive no sinal, não na magnitude.** A autocorrelação lag-1 dos retornos é ~0 nas majors —
   e mesmo assim "apostar contra o candle anterior" captura a maior parte do efeito. Dependência de
   sinais sem correlação linear.
2. **É fluxo, não profundidade.** Na fita de origem, a reversão concentra-se depois de barras movidas
   por fluxo taker agressivo (o `taker-buy volume` das klines assina a barra) e **cresce com a
   intensidade do fluxo**; as medidas de profundidade do livro (snapshots de ~30 s de notional
   bid/ask a 1–5 % do mid nos perpétuos USDⓈ-M) não explicam o efeito. Os autores dizem que nos
   perpétuos "a reversão replica por inteiro" — mas isso entra só como evidência de mecanismo (§5.1);
   o dado principal é spot.
3. **O edge bruto não paga custo.** O ganho bruto por trade "nunca sai dos dígitos baixos de um ponto
   base", com pico perto de **1,3 bp** (BTC/ETH, 15 min, limiar de confiança do modelo) contra
   **5 bp** de ida e volta na faixa mais barata (maker) e 10–20 bp como taker. O efeito **decai
   monotonicamente** com o intervalo de amostragem e **some em 4 h**.

## Onde foi mostrado

- **Dado:** Binance spot, os 183 pares USDT de maior volume, candles de 15 min (também 5 min a 4 h);
  validação cruzada em Coinbase, OKX e Bybit; Alpaca para 187 ações/ETFs; Dukascopy para FX/metais.
- **Janela primária:** 2025-01-01 → 2026-02-11. **Holdout congelado:** toda escolha de modelagem foi
  fixada contra o dado até 2026-02-11 e o mesmo universo foi rebuscado em 2026-02-12 → 2026-08-08.
- **Modelo:** logit restrito sobre 12 retornos passados "soft-clipped", com pesos de defasagem
  amarrados a um kernel decrescente (poucos graus de liberdade); prevê o sinal da próxima barra;
  métrica é AUC contra o acaso.
- **Números do holdout:** gap de AUC médio por classe **+0,020 [+0,010; +0,028]** contra **+0,031
  [+0,027; +0,035]** na amostra; **60 % dos pares scorados continuam significativos** (contra 90 %).
  Persistência com atenuação — e é assim que o artigo a descreve.
- **Custos:** só custo bruto de referência; "ignora profundidade, latência e seleção adversa".
- **Limitações declaradas pelos autores:** uma exchange, 14 meses, sobreviventes; o painel de
  "wrappers" repousa em oito famílias numa janela só; o fluxo é **condicionamento, não
  identificação** ("o fluxo agressor escolhe negociar, então o que o faz empurrar o preço pode
  também prever para onde ele vai"); livro só em snapshots de ~30 s. Eles apontam ordens de
  liquidação forçada como teste mais afiado — que nós já coletamos
  ([[KB-0017-liquidacoes-o-fluxo-forcado-que-observamos-por-amostragem]]).

## Como mediríamos aqui

Tudo o que o artigo usa, nós temos ou quase:

| Ingrediente do artigo | O que temos | Onde falta |
|---|---|---|
| sinal do candle anterior de 15 min | velas de 1 min agregadas a 15 min (`aggregate.py`) | definir "anterior" como a **última barra fechada antes da entrada**, alinhada ao instante da decisão (Astra) |
| `taker-buy volume` por barra | 100 % de cobertura em `candles` ([[KB-0014-taker-buy-volume-o-que-temos-medido]]) | é **descartado no `_fold`** da agregação (`aggregate.py:40,77`): falta um campo no `Bar` e uma soma |
| intensidade do fluxo | `i = 2·taker_buy/volume − 1` por barra | cruzar sinal × tercis de **\|i\|**, separando fluxo concordante e discordante do candle — tercil assinado confunde direção com intensidade (Astra) |
| custo | 20 bps de ida e volta assumidos pelo Lab; identidade `custo_R = 0,0020/(stop_atr × ATR%)` | nenhum — é a nossa régua |
| controle | **não temos** | um contrarian lag-1 pareado por mercado/período, com a **mesma execução e saída** da decisão |

A nossa `mean_reversion_v1` não é "aposta contra o candle anterior": exige tendência de 1 h, desvio
e estabilização (`packages/core/hunter_core/strategies/mean_reversion_v1.py:186–212`, conferido pela
Astra). É justamente isso que o teste precisa isolar.

## Hipótese testável no Lab

**H-P1 — "o edge da `mean_reversion` é só a reversão lag-1 de sinal e, portanto, não paga 20 bps".**
Duas afirmações separadas, dois testes pré-registrados, sobre as **decisões congeladas** do
EXP-0009 (replay; nunca a coorte prospectiva):

- **H-P1a (incremental).** O retorno bruto até a saída original das decisões da `mean_reversion`
  **menos** o do controle contrarian lag-1 pareado (mesmo mercado, mesmo período, mesma execução
  sintética, mesma política de saída) é > 0. Se for, "é só lag-1" está refutada.
- **H-P1b (líquido).** A expectancy líquida em R a 20 bps das mesmas decisões é > 0. Se for, "não paga
  20 bps" está refutada.
- **Cortes:** sinal da última barra fechada de 15 min antes da entrada (`sign(close − open)`, dojis à
  parte) × tercis de |i| com cortes fixados numa janela **anterior** à das decisões; ausências de
  `taker_buy_volume` explícitas, sem imputar zero.
- **Régua:** IC por blocos de dia **conjuntos entre mercados** (a dependência é transversal —
  [[KB-0051-tres-barreiras-mais-uma-e-a-amostra-que-nao-e-independente]]), correção de Holm sobre as
  células, confirmação fora da amostra na janela seguinte. **Falta de significância não confirma
  nenhuma das duas.**
- **Refutação da nota inteira:** se o nosso dado não mostrar reversão de sinal a 15 min nem no
  controle (o artigo prevê que mostre, em ~60–90 % dos mercados), a extrapolação spot → perpétuo
  falhou aqui e a nota vira registro de leitura.

## Por que pode falhar

- **Spot ≠ perpétuo.** O dado principal é spot; a frase sobre os perpétuos é evidência de mecanismo,
  não o teste principal. Funding e liquidações forçadas mudam quem é o agressor.
- **Sobrevivência e uma exchange só**, declaradas pelos autores; o nosso universo gira 26 % em 20 h
  ([[KB-0062-o-primeiro-dia-que-nao-conseguimos-ver]]).
- **Condicionamento não é causa.** O fluxo taker "escolhe" negociar; a reversão pode ser provisão de
  liquidez compensada ou informação — o artigo não separa, e o nosso teste também não separará.
- **1,3 bp não é teto para nós** (Astra): é o que **aquele modelo** captura em BTC/ETH spot; a nossa
  regra pode capturar mais — ou menos — e só o replay diz.
- **Poder.** O EXP-0009 tem 37 avaliáveis em 11 dias (frontmatter de 2026-09-08); cruzar 2 × 3 células
  com isso é olhar, não concluir. A hipótese está registrada para rodar quando houver ≥ 100 E 30.
- **Look-ahead na barra "anterior".** Se a barra de referência for a que contém a decisão, o teste
  está viciado — por isso a definição da Astra é obrigatória.

## Segunda opinião (Astra)

Transcrição: `.claude/state/astra-review-plantao-20260909-1700.md` (2026-09-09, 19:36 BRT).
**Concorda:** testar isto primeiro, como diagnóstico da família positiva; priorizar custos e decisões
congeladas; "positiva" e "`HIGH_VOLATILITY` ganha" continuam descrições amostrais, não validação.
**Discorda / corrige:** (1) sinal × tercil **não basta** — exige controle pareado e os dois testes
separados (incorporado acima); (2) tercis assinados confundem direção e intensidade — usar |i| e
separar concordante/discordante (incorporado); (3) **1,3 bp não é teto universal** (incorporado em
"Por que pode falhar"); (4) o artigo sustenta previsibilidade direcional, **não** lucro nem
causalidade; (5) **no holdout os pares significativos caem de 90 % para 60 %** — eu tinha escrito só
o gap de AUC; conferi no HTML (19:41) e o número está na §Onde foi mostrado. Nenhum ponto dela ficou
sem resposta.

## Fontes

| URL | Aberta? | O que veio |
|---|---|---|
| https://arxiv.org/abs/2608.21888 | sim (19:24 BRT) | data, autores, resumo, categorias |
| https://arxiv.org/html/2608.21888v1 | sim (19:24 e 19:41 BRT) | dado, método, números da amostra e do holdout, limitações, frase sobre os perpétuos |

## Relacionados

[[Hipoteses-do-plantao]] · [[Plantao/2026-09-09|plantão de 2026-09-09]] ·
[[EXP-0009-mean-reversion-pullback-em-tendencia]] · [[KB-0076-por-que-perdemos-2026-09-08]] ·
[[KB-0014-taker-buy-volume-o-que-temos-medido]] · [[KB-0009-o-efeito-do-quarto-de-hora]] ·
[[KB-0002-momentum-e-reversao-em-cripto]] · [[KB-0048-o-teste-antes-da-regra-e-o-filtro-que-ja-estava-dentro]] ·
[[Strategy Backlog]] · [[11-KNOWLEDGE/Index|Conhecimento]]

## Adendo 2026-09-11 (plantão, run 11) — o dado de 5 min e o decaimento por horizonte

Lido de novo em https://arxiv.org/html/2608.21888v1 (09:36 e 09:41 BRT), dois números que a nota
acima não tinha e que a [[EXP-0028-mean-reversion-5-min|EXP-0028]] tornou relevantes no mesmo dia:

- **Grade 15 min → 5 min:** "the median pair earns 0.46 bp per trade at τ=0.02 where it trades at
  all against zero for the median stock, and moving to 5-minute bars makes matters worse rather than
  better (0.15 bp)". Razão **3,1×** a favor da grade de 15 min — no nosso dado, a vantagem bruta da
  filha de 5 min foi **3,7×** menor que a da mãe (+0,0346 R contra +0,1270 R), com o custo quase
  igual (+0,0105 R). Mesma direção; **não é replicação** (Astra): mediana entre pares em bp, spot,
  sinal do candle × média por entrada em R, perp, recuo em tendência — e o contraste líquido
  filha − mãe da EXP-0028 tem IC95 [−0,2670; +0,0686], cruzando zero.
- **Horizonte — o que a frase diz e o que não diz:** "the signal decays monotonically and is gone
  by four hours: the profile of a microstructure effect with finite memory rather than of
  slow-moving mispricing" (1 h: 58 % dos pares cripto ainda significativos; 4 h: nenhum). Kitron
  compara **previsibilidade entre intervalos de amostragem** (barras de 15 min, 1 h, 4 h). Isso
  **não** é a trajetória acumulada de uma posição aberta pelo sinal de 15 min, e não sustenta
  "some em 4 h ⇒ precisa de 4 h para pagar" — usar a ausência de previsibilidade em barras de 4 h
  para alongar posições é o cenário de falha nomeado. O que a EXP-0028 deixa em aberto é outra
  coisa: a transposição mudou três parâmetros de uma vez (tendência 1 h → 15 min, ATR 15 → 5 min,
  horizonte 14 400 → 4 800 s; `mean_reversion_m5_v1.py:27`), e o diagnóstico D-P23 (curva de
  movimento após a entrada nas 542 decisões da mãe, +5 … +240 min em ATR, Δ pareado 240−80 com IC
  de blocos de dia, sem atribuição causal) está na fila em [[Hipoteses-do-plantao]] · rascunho
  `.claude/state/plantao/2026-09-11-0935-lane3.md` · parecer `astra-review-plantao-20260911-0935.md`.

O que continua valendo da nota: o edge bruto "never leaves the low single digits of a basis point"
e não paga nem a banda maker de 5 bp — o adendo não muda o veredito, muda a **pergunta** a medir.
