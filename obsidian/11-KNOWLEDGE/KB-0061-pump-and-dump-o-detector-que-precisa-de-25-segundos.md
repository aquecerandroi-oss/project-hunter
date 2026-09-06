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

# Pump-and-dump — o detector que precisa de 25 segundos, e o nosso relógio de 5 minutos

## O que afirma

A literatura de detecção de pump-and-dump em cripto converge para uma conclusão que é ruim para nós:
**o evento se resolve em segundos a poucos minutos**. La Morgia, Mei, Sassi & Stefa reportam um
detector que identifica um pump **25 segundos depois de ele começar**, com F1 de 94,5%, sobre cerca
de 900 eventos coletados em mais de três anos.

A `volume_anomaly_v1` decide sobre uma barra agregada de **5 minutos**, e o `VOLUME_SPIKE` compara
contra uma linha de base de 288 barras. **Não somos um detector de pump: somos um observador do que
sobrou depois dele.** Isso não é defeito a consertar — é a descrição honesta do que a nossa
estratégia mede, e ela muda o que se pode esperar dela em memes.

## Onde foi mostrado

- **La Morgia, Mei, Sassi & Stefa, "The Doge of Wall Street" (arXiv 2105.00733, 2021, revisto 2024)**
  — monitoramento de mais de três anos de grupos de Telegram e Discord, cerca de **900 eventos** de
  pump-and-dump identificados; modelo treinado em casos verificados, **F1 de 94,5%**, detecção em
  **25 segundos** a partir do início do pump. O trabalho também distingue o esquema coordenado do
  "crowd pump" do tipo GameStop, citando DOGE e XRP.
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

Ou seja: **o nosso instrumento tem a forma certa e o relógio errado.** A co-ocorrência preço ×
volume que Kamps & Kleinberg usam para *definir* o evento é literalmente a regra da
`volume_anomaly_v1` — volume anômalo mais fechamento na metade de cima da barra. O que difere é a
resolução: eles em 1 h e nós em 5 min descrevem o mesmo fenômeno pós-fato; La Morgia et al. em 25 s
descrevem o fenômeno enquanto ele acontece.

## Como mediríamos aqui

A pergunta útil não é "conseguimos pegar o pump" — a resposta é não, e o custo de tentar é a
[[KB-0009-o-efeito-do-quarto-de-hora]] inteira. A pergunta útil é **de que lado do pico nós
entramos**, e isso é medível hoje com o que já está gravado.

Os elementos existem: a barra do sinal, a barra de entrada (uma abertura posterior, com o
deslocamento mediano de 14,4 bps medido na
[[KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio]]), as velas de 1 min, e o
`result` do acompanhamento. O que falta é a pergunta escrita com um denominador.

## Hipótese testável no Lab

**`D-MEME-PICO` (diagnóstico, testável agora, sem pré-requisito):** para cada sinal da
`volume_anomaly_v1`, localizar nas velas de 1 min o **minuto de máximo do preço** dentro da janela
que vai do início da barra de referência até o fim do horizonte, e publicar a distribuição de
`t_pico − t_entrada` em minutos, **por coorte de `meme_universe_v1` e por decil de
`volume_ratio_5m`**. Três números por coorte: fração de entradas **antes** do pico, fração **no
minuto do pico**, fração **depois**.

O que isso responde: se a nossa entrada cai sistematicamente **depois** do pico em memes, a
`volume_anomaly_v1` está comprando exaustão nessa coorte — que é exatamente a explicação que a
[[KB-0015-volume-relativo-e-o-pico-como-exaustao]] levantou e nunca conseguiu medir, e agora tem uma
população natural onde ela é mais provável.

**Ressalvas que não podem sumir do relatório desse diagnóstico:**
- O máximo dentro de uma janela é **sempre** definido, então "fração antes do pico" tem um valor de
  referência não trivial mesmo sob passeio aleatório. **Sem um grupo de comparação, o número não
  significa nada** — o controle natural é a `L5` (benchmark aleatório condicionado) da sexta rodada
  ([[KB-0049-walk-forward-que-nao-temos-e-o-nulo-que-nunca-calculamos]]), e enquanto ela não existir
  o `D-MEME-PICO` é descrição, não teste.
- Isto é inspeção da mesma população que gerou a suspeita. Conta como tentativa, entra no
  [[Registro de Tentativas]], e nada pode ser confirmado nela
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
- **"Comprar exaustão" é explicação, não identificação.** Entrar depois do pico é compatível com
  exaustão, com atraso de execução e com o simples fato de que a barra do sinal é escolhida por ter
  tido volume alto. A [[KB-0015-volume-relativo-e-o-pico-como-exaustao]] já registrou essa
  ambiguidade e ela não sumiu.
- **O `VOLUME_SPIKE` e a `volume_anomaly_v1` são instrumentos diferentes** com nomes parecidos — um
  usa `relative_volume_5m` com corte por severidade, o outro recomputa das velas com `volume_mult`.
  Misturá-los num relatório seria repetir o erro dos "dois ATR com o mesmo apelido" da
  [[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]].

## Segunda opinião (Astra)

_(pendente)_

## Relacionados

[[KB-0015-volume-relativo-e-o-pico-como-exaustao]] ·
[[KB-0011-volume-magnitude-e-a-ponte-para-direcao]] ·
[[KB-0009-o-efeito-do-quarto-de-hora]] ·
[[KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio]] ·
[[KB-0049-walk-forward-que-nao-temos-e-o-nulo-que-nunca-calculamos]] ·
[[EXP-0002-volume-anomaly-v1]] · [[Strategy Backlog]] · [[Index]]
