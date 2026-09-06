---
tags: [knowledge, nota, microestrutura, fluxo, risco]
tema: Volume e fluxo de ordens
fonte: "Easley, López de Prado & O'Hara (2012), Flow Toxicity and Liquidity in a High-Frequency World, RFS 25(5); Andersen & Bondarenko (2014), VPIN and the flash crash, JFM; Easley, López de Prado & O'Hara (2014), VPIN and the Flash Crash: a rejoinder; Andersen & Bondarenko (2013), Reflecting on the VPIN Dispute, CREATES RP 13-42"
fonte_url: https://repec.econ.au.dk/repec/creates/rp/13/rp13_42.pdf
lido_em: 2026-09-06
evidencia: literatura revisada por pares, com resultados e interpretação DISPUTADOS em quatro textos; ganho incremental não demonstrado no nosso contexto
hipotese_testavel: sim
astra: concorda com correções (hipótese reescrita; três erros meus corrigidos)
---

# VPIN e a disputa sobre toxicidade

## O que afirma

VPIN (*Volume-Synchronized Probability of Informed Trading*) mede desequilíbrio entre compra e venda
agressoras num **relógio de volume**: o fluxo é cortado em baldes de volume igual e, dentro de cada
balde, mede-se `|compra − venda| / (compra + venda)`; o VPIN propriamente dito é a **agregação desses
desequilíbrios absolutos ao longo de uma janela de baldes** — a razão de um balde isolado é apenas um
componente, e a leitura como "toxicidade" exige hipóteses adicionais sobre quem está do outro lado. O
argumento é que fluxo tóxico advertiria contra o formador de mercado, que então retira liquidez, e
essa retirada produz o movimento.

**A disputa é parte da fonte, não uma nota de rodapé.** Andersen & Bondarenko mostram que VPIN é, por
construção, correlacionado com volume e volatilidade realizada; que **não** tem poder preditivo
incremental sobre volatilidade futura depois desses controles; e que não atingiu extremo antes do
flash crash de 2010 — atingiu depois. Eles enfatizam também a dependência do resultado da
**classificação de negócios e da implementação**. Os autores originais responderam contestando
metodologia, interpretação e a própria classificação, invocando outras pesquisas; e Andersen &
Bondarenko replicaram de novo em *Reflecting on the VPIN Dispute*. **A controvérsia não termina no
terceiro texto**, e quem cita um lado só está citando um quarto da literatura.

Como registro a evidência: revisada por pares, com **resultados e interpretação disputados**. Revisão
por pares e grau de contestação são atributos diferentes, e esta nota carrega os dois.

## Onde foi mostrado

Futuros E-mini S&P 500 e outros futuros americanos, em torno de 2010, com classificação de agressor
por regra de *bulk volume* — **inferida**, não observada. Nada disso é cripto e nada disso tem
funding.

Uma vantagem observacional nossa, que vale registrar sem exagerar: em perpétuos da Binance o lado
agressor **vem da corretora** (`taker_buy_volume` na vela; `isBuyerMaker → SELL` em
`hunter_exchanges/binance/streams.py:152`, `k.V` em `streams.py:251`). Isso remove **um** dos
problemas da literatura — o de classificação. **Não identifica quem estava informado**, que é a
grandeza que o VPIN pretende capturar.

## Como mediríamos aqui

Duas ideias separáveis, e a separação é o que sobrevive desta nota:

1. **A métrica VPIN — não priorizada.** O motivo honesto não é "já sabemos que ela replica as nossas
   features": eu tinha escrito isso e é extrapolação. O motivo é **custo de validação contra
   benefício incremental incerto**: para ser útil ela teria de se mostrar incremental a
   `relative_volume_*` e `atr_14_pct`, e a literatura que existe sobre esse ponto é disputada e de
   outro mercado. Fica como pesquisa não priorizada, **não como ideia descartada** — se um dia
   alguém propuser desequilíbrio **observado** (não inferido) em perpétuo, essa proposta merece
   teste próprio e não pode ser barrada citando esta nota.
2. **O relógio de volume — ideia de pesquisa, não solução.** Toda a nossa avaliação é em relógio de
   tempo: `volume_anomaly_v1` decide em barras de 5 min, o ATR é Wilder(14) em 15 min, e o
   denominador são 288 barras de 5 min. **Uma armadilha aritmética, apontada pela Astra e que eu não
   tinha visto:** trocar as barras por baldes de volume fixo e manter `volume ≥ 4 × mediana` torna a
   regra vazia — todos os baldes completos têm o mesmo volume, e a razão vira 1. Um gatilho em
   relógio de volume teria de olhar **outra** variável, por exemplo a **duração** do balde. Isso é
   pesquisa em aberto, não conserto pronto.

Também não é verdade, como eu tinha escrito, que o relógio de volume "muda necessariamente ATR,
horizonte e expiração": esses contratos podem continuar em tempo cronológico; só mudam se a
especificação decidir mudá-los.

## Hipótese testável no Lab

**H-KB0013 — "Composição temporal e escala do denominador da `volume_anomaly`"** (renomeada; era uma
hipótese sobre VPIN e virou um diagnóstico sobre o nosso próprio denominador). Duas medições, e o que
cada uma **permite** concluir:

| Medição | Como | O que permite concluir |
|---|---|---|
| **(a) Composição da janela de cada sinal** | Para cada sinal, `t = observation_ts` do envelope (`volume_anomaly_v1.py:199`); a janela do denominador é **`[t − 24h − 5min, t − 5min)`** — a barra do sinal fica fora. Reconstruir as 288 barras e reportar, **separadamente**: contagem de barras com volume zero, contagem de barras abaixo de um limiar absoluto declarado, a **mediana absoluta** e a razão atual/mediana, conferindo esta última contra `volume_ratio_5m` do envelope | Descreve os denominadores dos sinais **emitidos**. Não descreve os não emitidos |
| **(b) Composição por mercado e hora** | Sinais, volume e número de barras completas no mesmo intervalo, separando versão e coorte, com `as_of` fixo e `read_at` registrado | Descreve **concentração**. Não explica a causa dela |

**Três erros meus que a Astra derrubou, e que mudam a medição:**

- **"A mediana é dominada por barras vazias de madrugada" está errado.** 288 barras contíguas cobrem
  24 h, então **cada hora UTC contribui com exatamente 12 barras**. A madrugada não recebe peso extra
  por ser madrugada.
- **"Volume absoluto baixo → razão alta" está errado.** `volume / mediana` é invariante a escala:
  multiplicar todos os volumes por uma constante positiva não muda a razão. Volume baixo e anomalia
  relativa são propriedades que **coexistem**, e têm de ser medidas separadamente.
- **O caso extremo vai no sentido oposto ao que eu supunha:** com mais de 144 barras zeradas a
  mediana é **zero**, e o código devolve `volume_baseline_unavailable` (`volume_anomaly_v1.py:139`) —
  a estratégia fica **indisponível**, não mais fácil de disparar.

**O que (a) e (b) NÃO provam:** que o gatilho seleciona denominador pequeno; que proporcionalidade
entre sinais e volume por hora refuta alguma coisa; e que a execução é pior nos mercados finos —
isso não é demonstrável com velas e sinais, volume baixo é apenas indicador indireto.

**Se (a) mostrar denominadores com composição atípica**, a candidata que isso sugere é um piso
absoluto de liquidez — e, para comparar mercados, o volume tem de estar em **moeda de cotação**
(`quote_volume`, que é *nullable* e exige verificação de cobertura,
`hunter_core/db/models/market_data.py:55`). Somar quantidades de ativos diferentes não produz volume
economicamente comparável. Qualquer piso desses é variante e entra em [[Registro de Tentativas]]
antes de rodar.

## Por que pode falhar

- **Extrapolar a crítica do VPIN para as nossas features** sem teste — o erro que a revisão desta
  nota corrigiu, e que teria descartado por antecipação uma pesquisa futura de desequilíbrio
  **observado**.
- **Confundir baixo volume absoluto com anomalia relativa** — a razão é invariante a escala.
- **Relógio de volume aplicado ingenuamente** torna a regra de razão trivialmente vazia.
- **Um único dia.** Falta repetição para separar sazonalidade horária de acontecimentos daquele dia
  específico; essa é a limitação correta, e é mais fraca do que "hora e dia perfeitamente
  confundidos", que eu tinha escrito.
- **Negócios brutos não são persistidos** (`market_data.py`), então fronteiras intraminuto não são
  reconstruíveis; dividir uma vela proporcionalmente seria aproximação declarada, nunca medição.
- **Volume relatado** pode ter os seus próprios defeitos
  ([[KB-0018-volume-relatado-e-o-denominador-que-usamos]]).

## Segunda opinião (Astra)

`.claude/state/astra-review-KB-0013-vpin.md`. **Aprovou as duas decisões de prioridade — manter
"DISPUTADA" e não construir VPIN agora — e reprovou a minha justificativa e o meu protocolo.** Cinco
must-fix, todos aceitos:

1. **"Já sabemos que replica as nossas features" é extrapolação.** A crítica de Andersen & Bondarenko
   é sobre implementações e amostras específicas e enfatiza dependência da classificação; nada disso
   demonstra redundância em perpétuo. Substituí pelo motivo real (custo de validação × benefício
   incerto) e registrei o quarto texto da disputa, *Reflecting on the VPIN Dispute*. Cenário de falha
   dela: uma pesquisa futura de desequilíbrio observado ser descartada como redundante **sem teste**,
   porque a base registrou uma extrapolação como fato.
2. **A réplica dos autores é mais substantiva** do que eu resumira — contesta metodologia,
   interpretação e classificação de negócios. Registrado mesmo sem me convencer.
3. **A fração de barras quase vazias não identifica denominador artificialmente baixo**, pelos três
   motivos que reescrevi no corpo (invariância de escala; "mediana do mercado" sem período nem
   unidade; e a mediana zero levando a `volume_baseline_unavailable`, o oposto do que eu concluía).
4. **Sinais por hora contra volume por hora não estabelece causa**, e proporcionalidade não é
   refutação.
5. **Comparação entre mercados exige `quote_volume`**, que é *nullable*.

Cortes aceitos: "o relógio de volume corrige" → ideia de pesquisa cujo benefício ainda precisa ser
demonstrado; "a execução é pior" → não demonstrável com velas e sinais; "muda necessariamente ATR,
horizonte e expiração" → só muda se a especificação decidir mudar.

**Divergência:** nenhuma. Adotei também a delimitação dela para a janela do denominador
(`[t − 24h − 5min, t − 5min)`, barra do sinal fora) e o uso de `observation_ts` como âncora de
mercado, deixando a hora de emissão como medida operacional.

## Relacionados

[[Strategy Backlog]] · [[Registro de Tentativas]] · [[Index]] ·
[[KB-0012-ofi-nao-e-o-nosso-orderbook-imbalance]] ·
[[KB-0014-taker-buy-volume-o-que-temos-medido]] ·
[[KB-0015-volume-relativo-e-o-pico-como-exaustao]] ·
[[KB-0018-volume-relatado-e-o-denominador-que-usamos]] · [[EXP-0002-volume-anomaly-v1]] ·
[[Volume Agent]] · [[Features]]
