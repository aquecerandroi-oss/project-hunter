---
tags: [knowledge, nota, memecoins, listagem, proveniencia]
tema: meme coins / ciclo de vida e listagem
fonte: leitura de código (universe, backfill, warm-up) + medição própria na VPS
fonte_url: —
lido_em: 2026-09-06
evidencia: leitura de código conferida + SQL rodado
hipotese_testavel: sim
astra: pendente
---

# O primeiro dia que não conseguimos ver

## O que afirma

O efeito de listagem — anúncio, volume, funding extremo nas primeiras horas — é a única parte da
história de meme coin em que o nosso Lab **não pode participar**, e o motivo não é dado de mercado:
é aritmética de aquecimento.

A `momentum_v1` precisa de **97 barras de 15 min** para o seu ATR (`momentum_v1.py:82`), o que são
**24 h 15 min** de histórico contínuo. A `volume_anomaly_v1` precisa de **288 barras de 5 min**
(`volume_anomaly_v1.py:69`), que são **24 h**. E a agregação recusa a janela inteira se **faltar
qualquer minuto** (`aggregate.py:128`). Para um perpétuo que a Binance acabou de listar, não existe
histórico para buscar: o primeiro dia de vida do contrato é, para nós, estruturalmente cego.

E há uma coisa pior, porque é conserto de registro e não limite físico: **não gravamos a data de
listagem, e não gravamos o diff do universo.** Então nem retrospectivamente dá para perguntar "como
se comportam os primeiros N dias".

## Onde foi mostrado

**Como um mercado entra.** O universo é o top 200 por `volume_24h_usd`
(`services/market-worker/hunter_market_worker/universe_repo.py:191`), campo que vem do
`quoteVolume` da Binance (`packages/exchange-adapters/hunter_exchanges/binance/normalize.py:225`),
com tamanho `market_universe_size = 200` (`settings.py:128`) e refresh a cada
`market_universe_refresh_s = 900` (`settings.py:140`). Há allowlist e blocklist
(`universe_repo.py:195-205`).

**O que acontece na entrada.** O evento `market.universe.changed` é enfileirado na mesma transação
que escreve `is_monitored` (`durable.py:268-306`), com payload de `added`, `removed` e `total`
(`durable.py:288-292`), consumido pelo scanner (`registry.py:12`) e pelo strategy-worker
(`eligibility.py:47-74`). O backfill pede uma janela de **1499 minutos** para mercado novo
(`recovery.py:51`) — quase exatamente o aquecimento necessário, e é uma boa escolha de projeto. Só
que ela só ajuda quando **existe** história do lado da Binance.

**O que não sobrevive.** Medi a retenção da `outbox_events` na VPS às 18:46 UTC:

```
        stream         | count | pendentes |              min              |              max
-----------------------+-------+-----------+-------------------------------+-------------------------------
 market.candles.closed |  6400 |         0 | 2026-09-06 18:16:02.808116+00 | 2026-09-06 18:46:05.112851+00
 market.derivatives    |  1200 |         0 | 2026-09-06 18:20:01.328728+00 | 2026-09-06 18:46:02.272687+00
 market.liquidations   |   246 |         0 | 2026-09-06 18:15:17.096283+00 | 2026-09-06 18:46:21.324158+00
 regime.changed        |     1 |         0 | 2026-09-06 18:18:06.912702+00 | 2026-09-06 18:18:06.912702+00
```

**Zero eventos de universo, e nada com mais de 31 minutos.** A outbox é fila, não histórico. O diff
de quem entrou e quem saiu do top 200 **não existe em lugar nenhum** depois de meia hora.

**E não há data de listagem.** `markets.metadata` está vazia — literalmente `{}` para DOGEUSDT e
para USELESSUSDT, os dois que inspecionei. `first_seen_at` é a data em que **nós** vimos o mercado,
não a em que a Binance listou o contrato: **todos os 200 monitorados marcam 2026-09-05**, que é
quando o nosso coletor subiu. A única exceção é 哈基米USDT, com `first_seen_at` de 2026-09-06 e
apenas 41 barras de 15 min na janela — o único mercado que eu consegui observar **entrando** no
universo, e por acidente.

**A saída é igualmente invisível, e tem consequência já mensurável.**

```
 total_sinais | em_mercado_monitorado | em_mercado_nao_monitorado | mercados_que_sairam
--------------+-----------------------+---------------------------+---------------------
         1009 |                   982 |                        27 |                  14

   symbol   | is_monitored | monitor_rank | sinais       symbol   | monitor_rank | sinais
 GOATUSDT   | f            |          249 |      5     AIXBTUSDT  |          224 |      2
 PTBUSDT    | f            |          280 |      5     JSTUSDT    |          234 |      2
 EDUUSDT    | f            |          259 |      3     UBUSDT     |          202 |      2
 (+ 8 mercados com 1 sinal cada)
```

**Vinte e sete sinais em quatorze mercados que já saíram do universo, em menos de um dia** — e o
maior deles, GOATUSDT (Goatseus Maximus), é uma meme que hoje está no rank 249. A saída é
tratada corretamente pelo código (`universe.py:195-229` segura o mercado enquanto houver
acompanhamento aberto; `universe_repo.py:106-127` marca `delisted_at` só em delistagem real, não em
queda de ranking), mas **toda consulta que agrupa por `is_monitored` descarta esses 27 em
silêncio** — inclusive as minhas desta rodada.

## Como mediríamos aqui

Não dá. E é importante escrever exatamente o que falta, porque duas coisas diferentes se misturam:

| Pergunta | Estado |
|---|---|
| "Como se comporta um perpétuo nos seus primeiros N dias?" | **Impossível hoje** — falta a data de listagem, e falta história para o aquecimento |
| "Quantas memes estavam elegíveis no dia X?" | **Impossível hoje** — o diff de universo vive 30 min na outbox |
| "Este sinal foi emitido por uma meme?" | **Possível** — lista estática aplicada à identidade do mercado ([[KB-0056-meme-coin-como-ativo-e-o-rotulo-que-nao-e-medida]]) |
| "Este mercado ainda está no universo?" | Possível, mas só no **presente**; o passado se perde a cada refresh |

## Hipótese testável no Lab

**`H-KB0062a` — persistir a data de listagem.** O `exchangeInfo` da Binance publica um campo de
onboard por contrato; gravá-lo em `markets.metadata` na normalização custa uma linha e transforma
"idade do contrato" de impossível em trivial. **Sem valor de expectancy nenhum**, e sem ele nada
sobre ciclo de vida é perguntável.

**`H-KB0062b` — persistir o diff de universo.** Uma tabela própria (entrou, saiu, rank antes, rank
depois, timestamp do refresh) em vez de só o evento efêmero. É o **denominador** de qualquer análise
por coorte ao longo do tempo, e é o que hoje some em 30 minutos.

**`D-MEME-SAIDA` (diagnóstico, roda hoje):** os 27 sinais de mercados que saíram, separados por
`tracking_state` e `result`, contra os 982 de mercados que ficaram. Não é teste de nada — é medir o
tamanho do viés de sobrevivência que as minhas próprias consultas introduzem, e publicá-lo junto
delas. É o `D-CHAN-b` da sexta rodada ([[KB-0048-o-teste-antes-da-regra-e-o-filtro-que-ja-estava-dentro]])
com número concreto.

**O que esta nota explicitamente NÃO propõe: nenhuma estratégia de listagem.** Não porque a ideia
seja ruim — é a mais citada do mercado de meme —, mas porque a sua refutação é **impossível de
construir** com o que gravamos, e propor hipótese irrefutável é exatamente o que a
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] proíbe.

## Por que pode falhar

- **O campo de onboard da Binance eu não verifiquei em resposta real.** Sei que o `exchangeInfo` de
  futuros publica um campo desse tipo, mas não chamei o endpoint nesta rodada. Antes de virar
  requisito, alguém confere na resposta.
- **1499 minutos de backfill não garantem 1499 minutos de dado.** A janela é o pedido; o que chega
  depende da Binance ter história e do nosso coletor não ter lacuna. Um minuto faltando na fronteira
  mata a janela inteira (`aggregate.py:128`), e isso já apareceu na quarta rodada
  ([[KB-0031-o-classificador-de-regime-esta-mudo-por-warm-up]]).
- **A retenção de 30 min da outbox é uma leitura única.** Não medi a política de limpeza no código,
  só o efeito na tabela num instante. O mecanismo pode ser outro.
- **Os 27 sinais são de 15 horas de operação.** Extrapolar a taxa de rotatividade daí para um mês
  seria inventar.
- **`first_seen_at` uniforme em 2026-09-05 é artefato do nosso deploy**, não do mercado. Qualquer
  conta de "idade" com esse campo estaria errada, e é por isso que a nota existe.

## Segunda opinião (Astra)

_(pendente)_

## Relacionados

[[KB-0056-meme-coin-como-ativo-e-o-rotulo-que-nao-e-medida]] ·
[[KB-0031-o-classificador-de-regime-esta-mudo-por-warm-up]] ·
[[KB-0048-o-teste-antes-da-regra-e-o-filtro-que-ja-estava-dentro]] ·
[[KB-0016-quando-o-fluxo-importa-dependencia-de-estado]] ·
[[KB-0044-o-que-morre-em-dez-segundos]] · [[Strategy Backlog]] · [[Index]]
