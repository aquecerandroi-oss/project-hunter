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
**24 h 15 min** de histórico contínuo. E a `volume_anomaly_v1` precisa do mesmo, ou mais: eu tinha
escrito "288 barras de 5 min, que são 24 h", e a Astra corrigiu — ela exige **289 barras de 5 min
E 97 barras completas de 15 min** para o ATR (`volume_anomaly_v1.py:122`), ou seja **também ≥ 24 h
15 min**, com espera adicional possível pelo alinhamento dos buckets. A agregação recusa a janela
inteira se **faltar qualquer minuto** (`aggregate.py:128`). Para um perpétuo que a Binance acabou de listar, não existe
histórico para buscar: o primeiro dia de vida do contrato é, para nós, estruturalmente cego.

E há uma segunda camada, que é conserto de registro e não limite físico: **não gravamos a data de
listagem.** O diff do universo, ao contrário do que eu escrevi na primeira versão, **está
recuperável hoje** — só que num lugar efêmero, e a Astra me obrigou a ir olhar.

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

**O que eu vi na outbox, e a leitura errada que tirei disso.** Às 18:46 UTC a `outbox_events` da VPS
tinha isto:

```
        stream         | count | pendentes |              min              |              max
-----------------------+-------+-----------+-------------------------------+-------------------------------
 market.candles.closed |  6400 |         0 | 2026-09-06 18:16:02.808116+00 | 2026-09-06 18:46:05.112851+00
 market.derivatives    |  1200 |         0 | 2026-09-06 18:20:01.328728+00 | 2026-09-06 18:46:02.272687+00
 market.liquidations   |   246 |         0 | 2026-09-06 18:15:17.096283+00 | 2026-09-06 18:46:21.324158+00
 regime.changed        |     1 |         0 | 2026-09-06 18:18:06.912702+00 | 2026-09-06 18:18:06.912702+00
```

Zero eventos de universo, nada com mais de 31 minutos. **Eu concluí daí que o diff "não existe em
lugar nenhum". Estava errado, e a Astra desmontou por dois lados:**

- **A política real não é de 30 minutos.** `prune_dispatched(session, older_than, batch)`
  (`packages/core/hunter_core/events/outbox_store.py:287`) apaga só linhas já despachadas antes do
  corte que **quem chama** fornece, e nunca as pendentes — a função não fixa prazo. A política
  documentada é de **sete dias após `dispatched_at`**, com job diário previsto para o
  analytics-worker no M5 (`docs/DATABASE.md:70`). O que eu medi foi a **extensão temporal das linhas
  presentes naquele instante**, não o mecanismo. O mecanismo em uso na VPS **continua sem
  identificação**, e não vou inventá-lo.
- **O diff está no Redis, e eu fui conferir.** O stream `market.universe.changed` retém por número
  de entradas (`packages/core/hunter_core/events/streams.py:47`,
  `packages/core/hunter_core/events/produce.py:25`), e na VPS tinha **46 eventos cobrindo de
  2026-09-05 22:41 a 2026-09-06 18:47** — vinte horas de rotatividade, recuperáveis agora.

**E aí a medição que a correção destravou.** Descontando o evento de bootstrap (200 símbolos de uma
vez), esses 46 eventos contêm:

```
janela: 2026-09-05T22:41:10Z a 2026-09-06T18:47:03Z
entradas (fora do bootstrap): 52 em 37 simbolos distintos
saidas:                       52 em 37 simbolos distintos
simbolos que entraram E sairam na janela: 16
  1000RATSUSDT, BIOUSDT, DOODUSDT, HEIUSDT, HUSDT, IMXUSDT, IOTAUSDT, JASMYUSDT,
  JSTUSDT, KAVAUSDT, PLUMEUSDT, SKYUSDT, SOLVUSDT, TURBOUSDT, VETUSDT, ZKPUSDT
mais entradas: SKYUSDT 4x, SOLVUSDT 3x, JSTUSDT 3x
mais saidas:   JSTUSDT 4x, SKYUSDT 3x, HEIUSDT 3x
```

**Em vinte horas, 52 trocas — 26% do tamanho do universo —, e metade delas é o mesmo punhado de
mercados oscilando na fronteira do rank 200.** SKYUSDT entrou quatro vezes e saiu três. Isso não é
listagem nem delistagem: é ruído de ranking, e ele tem consequência real no aquecimento, porque um
mercado que sai e volta perde continuidade de janela.

**O que continua irrecuperável é a data de listagem.** `markets.metadata` está vazia — literalmente
`{}` para DOGEUSDT e para USELESSUSDT, os dois que inspecionei. `first_seen_at` é a data em que
**nós** vimos o mercado (`db/models/markets.py:80`, default do relógio do banco): **todos os 200
monitorados marcam 2026-09-05**, que é quando o coletor subiu. A única exceção é 哈基米USDT, com
`first_seen_at` de 2026-09-06 e apenas 41 barras de 15 min na janela — o único mercado que observei
**entrando**, e por acidente.

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
| "Quantas memes estavam elegíveis no dia X?" | **Possível para as últimas ~20 h**, lendo o stream do Redis; **impossível além da retenção dele**, que é por número de entradas |
| "Este sinal foi emitido por uma meme?" | **Possível** — lista estática aplicada à identidade do mercado ([[KB-0056-meme-coin-como-ativo-e-o-rotulo-que-nao-e-medida]]) |
| "Este mercado ainda está no universo?" | Possível, mas só no **presente**; o passado se perde a cada refresh |

## Hipótese testável no Lab

**`H-KB0062a` — persistir a data de listagem, e são DUAS mudanças, não uma.** O `onboardDate` está
documentado no `exchangeInfo` de futuros da Binance e aparece na nossa própria fixture
(`packages/exchange-adapters/hunter_exchanges/testing/fixtures/exchange_info.json:94`, achado da
Astra). Mas hoje a normalização guarda apenas `contractType` nos metadados
(`binance/normalize.py:137`) **e o upsert não transfere `metadata`** nem na inserção nem na
atualização (`services/market-worker/hunter_market_worker/universe_repo.py:64`). Eu tinha escrito
que "custa uma linha"; custa duas mudanças em camadas diferentes, e o cenário de falha dela é
concreto: acrescentar o campo ao normalizador, achar que a idade passou a ser gravada, e continuar
com `{}` no banco. **Nenhum valor de expectancy**, mas sem isso nada sobre ciclo de vida é
perguntável. Ressalva minha: não chamei o endpoint ao vivo nesta rodada.

**`H-KB0062b` — persistir o diff de universo em tabela própria** (entrou, saiu, rank antes, rank
depois, timestamp do refresh). Não é para "salvar o que se perde em 30 minutos" — essa formulação
minha estava errada —, é porque o Redis retém por **número de entradas**, e com a rotatividade
medida (52 trocas em 20 h) o limite de ~1.000 entradas é da ordem de semanas, não de meses. Uma
análise por coorte ao longo de um trimestre precisa de tabela, não de stream.

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

- **O campo de onboard eu não verifiquei em resposta ao vivo.** Está na documentação e na nossa
  fixture; ninguém conferiu numa chamada real nesta rodada.
- **A retenção do stream do Redis é por número de entradas, e eu não medi o limite configurado** —
  li o código que a define e contei 46 eventos presentes. Quantos dias isso cobre depende da
  rotatividade, que varia.
- **1499 minutos de backfill não garantem 1499 minutos de dado.** A janela é o pedido; o que chega
  depende da Binance ter história e do nosso coletor não ter lacuna. Um minuto faltando na fronteira
  mata a janela inteira (`aggregate.py:128`), e isso já apareceu na quarta rodada
  ([[KB-0031-o-classificador-de-regime-esta-mudo-por-warm-up]]).
- **Os 27 sinais são de 15 horas de operação.** Extrapolar a taxa de rotatividade daí para um mês
  seria inventar.
- **`first_seen_at` uniforme em 2026-09-05 é artefato do nosso deploy**, não do mercado. Qualquer
  conta de "idade" com esse campo estaria errada, e é por isso que a nota existe.

## Segunda opinião (Astra)

Revisão de 2026-09-06 (`.claude/state/astra-review-KB-0062-0065-memecoins.md`). Foi a revisão que
mais mudou uma nota desta rodada, e no sentido bom: ela **recuperou um dado que eu tinha declarado
perdido**.

1. **Derrubou "o diff não existe em lugar nenhum"** e apontou o stream do Redis. Fui conferir: 46
   eventos, 20 h de rotatividade, e a medição de 52 trocas que agora é o número mais concreto da
   nota. Cenário de falha dela: declarar o passado irrecuperável e deixar de recuperar o que ainda
   está lá.
2. **Derrubou os "30 minutos de retenção"** como política: `prune_dispatched` não fixa prazo
   (`outbox_store.py:287`) e o documentado são sete dias (`DATABASE.md:70`). O que eu medi foi o
   estado da tabela num instante; o mecanismo em uso na VPS continua sem identificação — e ela se
   recusou a inventar um, o que é a atitude certa.
3. **Derrubou "custa uma linha"** para a data de listagem: normalização e persistência são dois
   pontos distintos (`normalize.py:137`, `universe_repo.py:64`), e ela **confirmou o `onboardDate`**
   na documentação e na nossa fixture.
4. **Confirmou** que o backfill não supera ausência de história anterior à listagem, que
   `first_seen_at` não representa idade do contrato, e que outbox e Redis não substituem histórico
   durável de composição.

## Relacionados

[[KB-0056-meme-coin-como-ativo-e-o-rotulo-que-nao-e-medida]] ·
[[KB-0031-o-classificador-de-regime-esta-mudo-por-warm-up]] ·
[[KB-0048-o-teste-antes-da-regra-e-o-filtro-que-ja-estava-dentro]] ·
[[KB-0016-quando-o-fluxo-importa-dependencia-de-estado]] ·
[[KB-0044-o-que-morre-em-dez-segundos]] · [[Strategy Backlog]] · [[Index]]
