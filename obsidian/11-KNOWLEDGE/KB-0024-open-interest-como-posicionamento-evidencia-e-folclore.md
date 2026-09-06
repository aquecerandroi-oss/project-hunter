---
tags: [knowledge, nota, perpetuos, open-interest, posicionamento, folclore]
tema: Perpétuos: funding, OI, posicionamento
fonte: Hong & Yogo, "What Does Futures Market Interest Tell Us about the Macroeconomy and Asset Prices?" (NBER w16712; JFE 2012); Bessembinder & Seguin, "Price Volatility, Trading Volume, and Market Depth: Evidence from Futures Markets" (JFQA 28(1), 1993); material de corretora sobre os "quatro quadrantes" de OI × preço
fonte_url: https://www.nber.org/papers/w16712 · https://www.jstor.org/stable/2331149 · https://zerodha.com/varsity/chapter/open-interest/
lido_em: 2026-09-06
evidencia: estudo revisado (dois, **lidos em resumo** — os textos completos estão atrás de paywall) para a parte que tem evidência; **anedótico** para os quadrantes
hipotese_testavel: sim
astra: concorda com ressalvas
---

# Open interest como posicionamento: o que a evidência sustenta e o que é folclore

## O que afirma

Open interest é o número de contratos abertos. Duas coisas muito diferentes são ditas sobre ele, e
elas têm qualidades de evidência opostas.

**O que tem evidência revisada (e não é sobre cripto nem sobre minutos):**

- **Hong & Yogo.** O interesse agregado no mercado futuro é **mais informativo que o preço futuro**
  quando existe demanda por proteção e capacidade limitada de absorver risco. Movimentos de open
  interest são fortemente pró-cíclicos e **preveem** retornos de commodities, retornos de títulos e
  movimentos de juros curtos, às vezes batendo preditores estabelecidos; para moedas, títulos e ações
  o efeito é mais fraco, mas existe. Horizonte: **mensal**, agregado por mercado, contexto
  macroeconômico. (Um resumo secundário atribuía a esse trabalho um efeito numérico por desvio padrão
  em commodities; como não consegui conferi-lo na fonte, **o número saiu desta nota**.)
- **Bessembinder & Seguin.** Em oito mercados futuros, com dados diários de maio/1982 a março/1990:
  volatilidade cresce com o volume — tanto a parte esperada quanto a inesperada, com choques
  inesperados pesando mais e de forma **assimétrica** (choques positivos pesam mais que negativos) —
  e **open interest grande atenua a volatilidade**, o que eles leem como profundidade de mercado.

O segundo resultado é o mais útil para nós, e aponta na direção contrária ao folclore — mas com o
alcance certo: naquele recorte (oito futuros tradicionais, dados diários dos anos 1980), OI grande
esteve **associado** a menos volatilidade por unidade de volume, de forma **compatível** com uma
leitura de profundidade. Não é uma identidade: "OI alto **é** profundidade" seria presumir livro
profundo numa altcoin com muitos contratos abertos, que é precisamente o erro a evitar aqui.

**O que é folclore:** os "quatro quadrantes" — preço ↑ com OI ↑ = *long build-up* (dinheiro novo
comprador, sinal de alta), preço ↓ com OI ↑ = *short build-up*, preço ↓ com OI ↓ = *long unwinding*,
preço ↑ com OI ↓ = cobertura de vendidos. Todo material de corretora ensina isso; nenhum apresenta
teste, amostra, custo ou controle.

E há um problema lógico antes do empírico: **open interest é simétrico por construção, e a variação
dele também**. Duas aberturas aumentam o OI; dois encerramentos o diminuem; abertura contra
encerramento só transfere a posição. **Nenhum desses casos identifica o agressor.** "Dinheiro novo
comprador" exige saber quem cruzou o spread, e o open interest não carrega essa informação — ele
conta contratos, não iniciativas. Os quadrantes vestem uma identidade contábil de sinal direcional.

**Mas simetria não implica ausência de informação.** Este é o limite que a Astra impôs e que a nota
respeita: ΔOI distingue **expansão de contração** de posições, e essa distinção pode ter associação
empírica com retorno em algum mercado e contexto — Hong & Yogo encontram previsibilidade sem violar
identidade contábil nenhuma. E o caminho inverso também vale: o volume agressor identifica a
iniciativa, mas **sozinho não distingue** abertura de comprado de fechamento de vendido. As duas
medidas respondem perguntas diferentes; nenhuma substitui a outra.

## Onde foi mostrado

Commodities, títulos, moedas e ações, em horizonte mensal (Hong & Yogo) e oito mercados futuros
tradicionais em dados diários dos anos 1980 (Bessembinder & Seguin). Nenhum dos dois é cripto,
nenhum é intradiário, nenhum é perpétuo. A extrapolação para 200 perpétuos USDT com decisões por
minuto é declarada, não demonstrada — o mesmo alerta da
[[KB-0004-proximidade-da-maxima-e-confirmacao-por-volume]].

## Como mediríamos aqui

`open_interest_change_1h/4h` **não computam** no scanner hoje
([[KB-0020-funding-change-8h-nunca-calcula]]), mas o dado **existe**: `open_interest` está no
snapshot do hash `deriv` e em `market_snapshots`, e `open_interest_history`
(`market_data.py:101-108`) é amostrado a cada 5 minutos. Ou seja, o teste dos quadrantes é
executável a partir das tabelas duráveis mesmo com a feature quebrada.

O quadrante de cada sinal seria `sign(Δ open_interest na janela) × sign(return_1h no instante da
decisão)`, com a variação de OI medida entre duas amostras reais de `open_interest_history` — e com a
distância efetiva entre elas registrada, porque com amostragem de 5 min a "variação de 1 h" tem uma
folga que precisa aparecer no resultado (a feature usa tolerância de ±6 min; `deriv.py`).

## Hipótese testável no Lab

**Diagnóstico primeiro, e é um diagnóstico que pode matar uma família inteira de ideias por muito
pouco.**

- **D — distribuição dos outcomes já existentes pelos quatro quadrantes**, com expectancy líquida por
  quadrante, todos os modos de saída separados, cobertura de `open_interest_history` declarada
  (quantos sinais têm as duas amostras dentro da folga), e cortes congelados antes. Como o Lab hoje
  só compra ([[EXP-0001-momentum-v1]]), na prática dois quadrantes concentram quase tudo — o próprio
  desequilíbrio de população é resultado a reportar, não defeito a esconder.
- **Contraste com o volume agressor** ([[KB-0014-taker-buy-volume-o-que-temos-medido]]). Se o
  quadrante tiver associação, a pergunta seguinte é se ela sobrevive ao controle por
  `taker_imbalance_5m`. **Cuidado com a conclusão:** um coeficiente condicional que desaparece
  significa que a informação é **compartilhada ou mediada** pela agressão — não que o quadrante seja
  ruído. "Folclore explicado e descartado de uma vez", como eu tinha escrito, é forte demais e sai.
- **Hipótese separada, vinda da evidência revisada:** OI **em nível** (não em variação) como proxy
  candidato de profundidade — mercados com OI alto teriam movimentos menos violentos por unidade de
  volume, o que interage com o piso de ATR% da [[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] e com
  a escala por volatilidade da [[KB-0007-atr-e-escala-por-volatilidade]]. É a leitura **compatível**
  com Bessembinder & Seguin, exige normalização entre mercados e ninguém no nosso backlog a tinha
  proposto.

*Refutação:* expectancy equivalente entre quadrantes, dentro de margem declarada antes, refuta a
leitura direcional **nesta especificação**. Não refuta a leitura de profundidade, que é outra
hipótese com outro teste.

## Por que pode falhar

- **Comparar níveis entre mercados.** OI absoluto não é comparável entre um perpétuo de BTC e um de
  altcoin. Qualquer uso em nível precisa de normalização declarada (por OI próprio recente, ou por
  `open_interest_value`), e a escolha muda o resultado.
- **Amostragem de 5 min contra eventos de minutos.** Um desfazimento rápido acontece dentro de uma
  amostra. A série que temos não resolve isso
  ([[KB-0025-o-nosso-detector-de-open-interest-so-olha-para-cima]]).
- **Extrapolação de horizonte e de classe de ativo.** Mensal em commodities → 4 h em perpétuos é um
  salto que a nota declara e não justifica.
- **Identidade contábil vestida de sinal.** O risco é achar que se descobriu algo quando só se
  redescreveu que contratos foram abertos.
- **Dependência entre mercados.** Aglomeração acontece ao mesmo tempo em dezenas de perpétuos.

## Segunda opinião (Astra)

Confirmou a simetria contábil — e a estendeu para a **variação**, com o caso a caso (duas aberturas,
dois encerramentos, abertura contra encerramento) que ficou no corpo da nota. Mas impôs o limite que
faltava: **simetria não implica ausência de previsibilidade**, e Hong & Yogo são a prova de que as
duas coisas convivem. Também lembrou o inverso, que eu não tinha escrito: volume agressor sozinho não
distingue abertura de comprado de fechamento de vendido.

Correções aceitas: (1) retirar "OI alto **é** profundidade" como identidade — cenário de falha dela:
presumir livro profundo numa altcoin com OI elevado; (2) retirar "folclore descartado de uma vez" se
o coeficiente sumir ao controlar pela agressão — informação compartilhada ou mediada não é ruído;
(3) retirar o número mensal por desvio padrão que eu só tinha em resumo secundário; (4) dizer "não
localizado nas fontes consultadas" em vez de afirmar que nenhum teste existe.

Divergência: nenhuma.

## Relacionados

[[KB-0025-o-nosso-detector-de-open-interest-so-olha-para-cima]] ·
[[KB-0021-funding-como-preco-de-posicionamento-nao-como-previsao]] ·
[[KB-0014-taker-buy-volume-o-que-temos-medido]] ·
[[KB-0007-atr-e-escala-por-volatilidade]] ·
[[KB-0020-funding-change-8h-nunca-calcula]] ·
[[Strategy Backlog]] · [[Features]] · [[Market Collector]]
