---
tags: [knowledge, nota, memecoins, manipulacao, microestrutura]
tema: meme coins / pump-and-dump e manipulação
fonte: La Morgia, Mei, Sassi & Stefa (arXiv 2105.00733 e 2005.06610); nosso detectors.py e volume_anomaly_v1.py
fonte_url: https://arxiv.org/abs/2105.00733 · https://arxiv.org/abs/2005.06610
lido_em: 2026-09-06
evidencia: preprint com método declarado (lido em resumo — o PDF não abriu) + leitura de código
hipotese_testavel: sim
astra: pendente
---

# Pump-and-dump — o detector que trabalha em blocos de 25 segundos, e o nosso relógio de 5 minutos

## O que afirma

A detecção de pump-and-dump em cripto opera em **blocos de 25 segundos**: La Morgia, Mei, Sassi &
Stefa reportam F1 de 94,5% com essa granularidade, sobre cerca de 900 eventos coletados e 317
eventos da Binance na avaliação. A `volume_anomaly_v1` decide sobre uma barra agregada de **5
minutos**.

**Correção obrigatória da minha primeira redação, e ela é a mais importante da nota.** Eu tinha
escrito que "o evento se resolve em segundos a poucos minutos" e que portanto "não somos um detector
de pump, somos um observador do que sobrou". A Astra **abriu o artigo completo em HTML** e mostrou
que os 25 segundos são o **tamanho do bloco de detecção**, não a duração do evento — o próprio
trabalho descreve movimentos que se estendem por **horas**, e distingue o esquema coordenado do
"crowd pump". Um detector rápido não implica um evento curto, e a minha conclusão categórica
declarava impossível algo que o artigo não afirma.

O que sobrevive, e é bem menos: **a nossa resolução é de 5 minutos, então nada do que a estratégia
vê distingue o início de um pump do meio dele.** Se entramos antes ou depois do máximo é pergunta em
aberto — e é justamente o diagnóstico que esta nota propõe, em vez da conclusão que ela tinha.

## Onde foi mostrado

- **La Morgia, Mei, Sassi & Stefa, "The Doge of Wall Street" (arXiv 2105.00733, 2021, revisto 2024)**
  — monitoramento de mais de três anos de grupos de Telegram e Discord, cerca de **900 eventos**
  coletados e **317 eventos da Binance** na avaliação; **F1 de 94,5%** com **blocos de 25 segundos**
  e validação cruzada de cinco partes; o trabalho descreve movimentos de **horas** e distingue o
  esquema coordenado do "crowd pump" do tipo GameStop, citando DOGE e XRP. Estes números vêm da
  versão HTML (`arxiv.org/html/2105.00733v2`), seções 4 e 5, **aberta pela Astra** — para mim só o
  resumo abriu, e a minha leitura dele produziu o erro corrigido acima.
- **Os mesmos autores, "Pump and Dumps in the Bitcoin Era" (arXiv 2005.06610, ICCCN 2020)** — a
  versão anterior do método, detecção em tempo real. **O PDF voltou ilegível para a minha
  ferramenta**, duas tentativas; li o resumo na página de abstract, e nenhum número de desempenho
  dele entra nesta nota.
- **Kamps & Kleinberg (2018)** e **Xu & Livshits (2019)** aparecem como a base da literatura em toda
  resenha que li: o primeiro define o evento pela **co-ocorrência** de anomalia de preço e anomalia
  de volume sobre velas de **1 hora**; o segundo prevê qual moeda será alvo a partir de ~200 sinais
  de pump organizados em Telegram. **Não abri nenhum dos dois textos primários**, e por isso nenhuma
  fórmula ou número deles é citado aqui — só o formato do argumento.

**O que é nosso, e é onde a comparação morde.** Os oito detectores armados vivem em
`packages/indicators/hunter_indicators/anomalies/detectors.py`, com `FIRE_MIN_SEVERITY = 40`
(3 desvios absolutos medianos, linha 48) e `HOLD_MIN_SEVERITY = 20` (linha 51). O `VOLUME_SPIKE` lê
`relative_volume_5m`, lado `UP` (linhas 127-132). A `volume_anomaly_v1` **não** usa o detector: ela
recomputa a partir das velas, exigindo volume de 5 min ≥ `volume_mult = 4` vezes a mediana das
`volume_window = 288` barras anteriores, fechamento acima do meio da barra, e retorno de 5 min
dentro de `[0, 2 × ATR%]` (`volume_anomaly_v1.py:68-83`).

A semelhança com a definição de Kamps & Kleinberg (co-ocorrência de anomalia de volume e de preço) é
**de família, não de identidade** — e eu tinha escrito "literalmente a mesma regra", o que a Astra
derrubou com dois argumentos concretos:

- **Fechamento acima do meio da barra não é anomalia de preço contra histórico.** É uma condição
  sobre a forma de uma barra; a deles compara o preço com uma linha de base.
- **A nossa regra tem um teto que a deles não tem.** O retorno de 5 min precisa caber em
  `[0, 2 × ATR%]` (`volume_anomaly_v1.py:150`) — ou seja, a `volume_anomaly_v1` **recusa** movimentos
  explosivos demais. Uma estratégia que rejeita o retorno grande não é um detector de pump com o
  relógio errado; é outra coisa.

## Como mediríamos aqui

A pergunta útil não é "conseguimos pegar o pump" — a resposta é não, e o custo de tentar é a
[[KB-0009-o-efeito-do-quarto-de-hora]] inteira. A pergunta útil é **de que lado do pico nós
entramos**, e isso é medível hoje com o que já está gravado.

Os elementos existem: a barra do sinal, a barra de entrada (uma abertura posterior, com o
deslocamento mediano de 14,4 bps medido na
[[KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio]]), as velas de 1 min, e o
`result` do acompanhamento. O que falta é a pergunta escrita com um denominador.

## Hipótese testável no Lab

**`D-MEME-PICO` (diagnóstico, testável agora; o desenho abaixo é o corrigido pela Astra — a minha
primeira versão era irrecuperável do jeito que estava escrita).**

Para cada sinal da `volume_anomaly_v1`, localizar nas velas de 1 min o **minuto de máximo** dentro
de uma **janela fixa** — do início da barra de referência até `entrada + 2 h` — e publicar
`t_pico − t_entrada` por coorte de `meme_universe_v1` e por decil de `volume_ratio_5m`, com três
números: fração de entradas **antes** do pico, **no minuto** do pico, **depois**.

Seis exigências de desenho, todas dela, e cada uma vale por um resultado errado evitado:

1. **Janela fixa, independente da saída.** O acompanhamento termina quando resolve
   (`services/strategy-worker/hunter_strategy_worker/walker.py:171`); se eu procurar o máximo só até
   a saída, a janela passa a depender do resultado. Cenário de falha dela: um sinal bate o stop
   rápido e o preço faz novo máximo 40 minutos depois — pelo acompanhamento ele é "depois do pico",
   pela janela fixa é "antes".
2. **A janela é assimétrica** — poucos minutos antes da entrada contra duas horas depois. **Não
   existe referência automática de 50% antes / 50% depois**, e publicar a fração sem dizer isso
   convida à leitura errada.
3. **Seleção completa, não só volume.** A barra do sinal foi escolhida por ter volume alto,
   fechamento forte **e** retorno dentro de `[0, 2×ATR]`. Um controle aleatório genérico não isola
   esses três efeitos.
4. **Cobertura e maturação no denominador.** Sinais recentes sem duas horas de futuro, e janelas com
   lacunas, entram como indisponíveis — não somem.
5. **Empates e resolução declarados antes**: `high` ou `close`, o que fazer com máximos repetidos, e
   qual é o "minuto da entrada". OHLC de 1 min **não dá o segundo** do pico.
6. **Dependência**: vários sinais podem compartilhar o mesmo movimento de mercado; não são
   observações independentes (é o `D-CONC` da sexta rodada,
   [[KB-0051-tres-barreiras-mais-uma-e-a-amostra-que-nao-e-independente]]).

**O que este diagnóstico NÃO faz:** identificar exaustão. Eu tinha escrito que uma entrada
sistematicamente depois do pico mostraria a `volume_anomaly_v1` "comprando exaustão" em memes; isso
**saiu**. Entrar depois do máximo é compatível com exaustão, com atraso de execução e com o simples
fato de a barra ter sido escolhida por volume alto — a mesma ambiguidade que a
[[KB-0015-volume-relativo-e-o-pico-como-exaustao]] já registrou. E, sem grupo de comparação
condicionado (a `L5` da sexta rodada,
[[KB-0049-walk-forward-que-nao-temos-e-o-nulo-que-nunca-calculamos]]), o número é **descrição, não
teste**.

Isto é inspeção da mesma população que gerou a suspeita: conta como tentativa, entra no
[[Registro de Tentativas]] **antes** de rodar, com a população, a definição do máximo e os controles
declarados, e nada pode ser confirmado nela
([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]).

**Não proponho braço de detecção de pump.** Detectar em 25 s exigiria decidir sobre o tape ao vivo,
não sobre barras de 5 min fechadas; é outra arquitetura, não um parâmetro. E a
[[KB-0044-o-que-morre-em-dez-segundos]] já mostrou que nem o livro nós gravamos.

## Por que pode falhar

- **A literatura é de outro objeto.** Os ~900 eventos de La Morgia et al. são pumps **organizados
  em canais de Telegram**, em pares de baixa capitalização de corretoras menores, majoritariamente
  em BTC como moeda de cotação. Nada garante que o mecanismo se transporte para perpétuos USDT de
  meme coins no top 200 da Binance — que é um mercado com muito mais fluxo, book mais fundo e
  arbitragem contra o spot.
- **Não li os textos primários de Kamps & Kleinberg nem de Xu & Livshits**, e o PDF de 2005.06610
  não abriu. O que citei como número (25 s, F1 94,5%, ~900 eventos) vem do resumo de 2105.00733.
- **"Comprar exaustão" é explicação, não identificação**, e por isso saiu do corpo da nota.
- **Duas horas não são censura para "o máximo dentro de duas horas"**, desde que a janela esteja
  completa — são limitação só se eu quiser inferir o pico do **evento inteiro**, e aí um máximo
  posterior muda a classificação. Distinção da Astra, que eu não tinha feito.
- **O `VOLUME_SPIKE` e a `volume_anomaly_v1` são instrumentos diferentes** com nomes parecidos — um
  usa `relative_volume_5m` com corte por severidade, o outro recomputa das velas com `volume_mult`.
  Misturá-los num relatório seria repetir o erro dos "dois ATR com o mesmo apelido" da
  [[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]].

## Segunda opinião (Astra)

Revisão de 2026-09-06 (`.claude/state/astra-review-KB-0059-0061-memecoins.md`).

1. **Abriu o artigo completo que a minha ferramenta não abriu** e derrubou a tese central: os 25
   segundos são **tamanho de bloco de detecção**, não duração do evento; o artigo descreve
   movimentos de horas; e a avaliação usa 317 eventos da Binance com validação cruzada de cinco
   partes. Cenário de falha: um movimento dura uma hora, a entrada acontece cinco minutos depois e
   **antes** do máximo — a minha conclusão categórica declarava isso impossível.
2. **Derrubou "literalmente a mesma regra"** com dois argumentos: fechamento acima do meio da barra
   não é anomalia de preço contra histórico, e o teto de `2 × ATR` faz a estratégia **rejeitar**
   movimentos explosivos.
3. **Salvou o `D-MEME-PICO` reescrevendo o desenho** — janela fixa independente da saída
   (`walker.py:171`), assimetria declarada, seleção tripla, cobertura e maturação no denominador,
   regra de empate, e dependência entre sinais.
4. **Mandou tirar "está comprando exaustão"** do corpo, onde contradizia a minha própria ressalva
   final.
5. **Concordou** em manter o diagnóstico como exploratório, registrar a tentativa antes de rodar, e
   não transformar nada disto em braço de estratégia.

## Relacionados

[[KB-0015-volume-relativo-e-o-pico-como-exaustao]] ·
[[KB-0011-volume-magnitude-e-a-ponte-para-direcao]] ·
[[KB-0009-o-efeito-do-quarto-de-hora]] ·
[[KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio]] ·
[[KB-0049-walk-forward-que-nao-temos-e-o-nulo-que-nunca-calculamos]] ·
[[EXP-0002-volume-anomaly-v1]] · [[Strategy Backlog]] · [[Index]]
