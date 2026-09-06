---
tags: [knowledge, nota, volume, fluxo, dado-proprio]
tema: Volume e fluxo de ordens
fonte: "Documentação de klines da Binance USDⓈ-M (campo 9, 'Taker buy base asset volume') + medição própria sobre o banco da VPS"
fonte_url: https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data
lido_em: 2026-09-06
evidencia: documentação da corretora + medição própria verificada (SQL colado)
hipotese_testavel: sim
astra: concorda com correções (limiar reclassificado; leitura de 1 min retirada)
---

# `taker_buy_volume`: o que temos, medido

## O que afirma

Cada kline da Binance traz, além de OHLCV, o **volume em que o comprador foi o agressor**
(`taker buy base asset volume`, campo 9 do array; `V` no stream de kline). Com ele, o desequilíbrio
agressor da barra é aritmética direta:

```
desequilíbrio = 2 · taker_buy_volume / volume − 1        ∈ [−1, +1]
```

`+1` = todo o volume da barra foi comprador levantando a oferta; `−1` = todo vendedor batendo no
bid; `0` = metade e metade. **Isto não é inferência.** A maior fragilidade metodológica das medidas
clássicas de fluxo (regra de tick, bulk-volume classification — ver
[[KB-0013-vpin-e-a-disputa-sobre-toxicidade]]) é justamente classificar o agressor por heurística. A
corretora nos entrega a classificação pronta.

## Onde foi mostrado

Aqui, sobre o nosso próprio banco. Esta nota fecha a pendência deixada em
[[KB-0009-o-efeito-do-quarto-de-hora]] ("cobertura ainda não conferida no banco").

**Cobertura** — VPS, `read_at = 2026-09-06T14:2xZ`:

```sql
select count(*) total, count(taker_buy_volume) com_taker,
       count(*) filter (where taker_buy_volume is not null and volume>0) usavel,
       count(*) filter (where taker_buy_volume is not null and volume>0
                          and taker_buy_volume>volume) inconsistentes,
       min(open_time) primeiro, max(open_time) ultimo, count(distinct market_id) mercados
from candles where timeframe='1m';
```

```
 total  | com_taker | usavel | inconsistentes |        primeiro        |         ultimo         | mercados
--------+-----------+--------+----------------+------------------------+------------------------+----------
 519422 |    519422 | 518451 |              0 | 2026-09-04 21:40:00+00 | 2026-09-06 14:23:00+00 |      222
(1 row)
```

**Cobertura de 100%** (519.422 de 519.422), zero linhas com `taker_buy_volume > volume`, 222
mercados, ~41 h de série. As 971 linhas fora de "usável" são barras com `volume = 0` — mercado sem
negócio no minuto, onde o desequilíbrio é **indefinido**, não zero.

**Distribuição em 1 minuto** — mesmo corte (`timeframe='1m'`, `volume>0`, `taker_buy_volume` não
nulo), estatísticas de `2·taker_buy_volume/volume − 1`:

```
   n    | media  |   p05   | mediana |  p95   | acima_de_zero
--------+--------+---------+---------+--------+---------------
 518462 | 0.0016 | -0.8752 |  0.0000 | 0.8818 |        259208
(1 row)
```

**Distribuição agregando em 5 minutos** — baldes de 300 s por mercado, **só os com as 5 barras
presentes** e `Σ volume > 0`:

```
   n    |  media  |   p05   | mediana |  p95
--------+---------+---------+---------+--------
 103749 | -0.0131 | -0.5654 | -0.0146 | 0.5505
(1 row)
```

**O que estes números mostram, e só isso:** a dispersão **marginal** é menor em 5 min (±0,56) do que
em 1 min (±0,88). E é preciso dizer em seguida o que eles **não** mostram, porque a minha primeira
redação concluía demais:

- **não medem quanto da redução é efeito mecânico da agregação.** Somar cinco janelas reduz variância
  por construção; separar "menos ruído" de "menos janelas independentes" exigiria comparar contra uma
  linha de base de agregação aleatória, que não fiz;
- **não provam que a maioria dos minutos tem poucos negócios** — isso exigiria a distribuição de
  `trade_count`, que não medi;
- **não estabelecem utilidade preditiva de nenhum dos dois horizontes.** Uma distribuição centrada em
  zero pode conter informação direcional forte; largura marginal não é o teste.

Portanto **não** concluo que "1 minuto é inútil e 5 minutos serve" — era o que eu tinha escrito, e é
uma inferência que estes percentis não sustentam. O que fica: os dois horizontes são calculáveis, o
de 5 min é menos disperso, e qual deles informa é pergunta em aberto. Os 50,0% de minutos acima de
zero (259.208 de 518.462) dizem apenas que não há viés de lado embutido na população inteira.

## Como mediríamos aqui

O caminho do dado, verificado linha a linha:

| Etapa | Estado | Onde |
|---|---|---|
| Normalização REST | preserva | `hunter_exchanges/binance/normalize.py:201` |
| Stream de kline | preserva | `hunter_exchanges/binance/streams.py:251` |
| Persistência | preserva | `services/market-worker/.../persist_rows.py:127` |
| Leitura do strategy-worker | **já seleciona** | `services/strategy-worker/.../repo.py:97` (repassa ao `NormalizedCandle` na 124) |
| Montagem do contexto | preserva | `strategy-worker/context.py:60` → `hunter_core/strategies/base.py:189,197` (`candles_1m`) |
| Agregação 1m → 5m | **descarta** | `hunter_core/strategies/aggregate.py:40` (`Bar` sem o campo) e `_fold` na linha 77 (soma só `volume`) |

Ou seja: o dado **chega** ao `StrategyContext.candles_1m` de toda avaliação hoje e não é transportado
para as barras agregadas. Não é um problema de coleta — é um campo faltando num dataclass e uma linha
de soma. Ressalva: o domínio admite `None` (`hunter_core/domain/market.py:266`), então "chega" não
garante "tem valor" em toda avaliação; a cobertura de 100% medida acima é do **banco**, não do
caminho em memória.

**Correção sobre `buy_pressure_5m` / `sell_pressure_5m` / `trade_velocity_1m`** — eu tinha escrito
que continuam indisponíveis porque nenhum worker preenche `covered_until`. **Isso deixou de ser
verdade durante esta própria rodada.** Já existe código na árvore de trabalho (ainda **não
commitado** quando escrevi isto) que produz e consome a prova: o coletor calcula e publica
`covered_until` no Redis (`market-worker/coverage.py:153`), o scanner lê a prova
(`scanner-worker/coverage.py:102`) e a aplica ao `SourceEntry`, avaliando em
`as_of = covered_until` (`scanner-worker/context.py:96,122`). O que **não** está demonstrado é a
disponibilidade operacional — se as features de fita efetivamente publicam com que frequência e com
que atraso. Isso é medição pendente, não conclusão. O `taker_buy_volume` da vela continua sendo o
caminho mais curto porque não depende dessa prova.

## Hipótese testável no Lab

**H-KB0014 — filtro de desequilíbrio agressor na barra do sinal.** Braço único sobre a
`volume_anomaly`, com tudo mais congelado:

```
taker_imbalance_5m = 2 · Σ taker_buy_volume / Σ volume − 1   (as 5 velas de 1 min da barra do sinal)
entrar apenas se taker_imbalance_5m ≥ taker_imbalance_min
taker_imbalance_min = 0.10        (proposta; ver justificativa abaixo)
```

**O que 0,10 é, sem eufemismo.** Não é "escolha neutra": é uma escolha **derivada de inspeção de
dado** — os percentis da população **inteira** (mediana −0,0146, p95 +0,5505). E a população que
importa não é essa: é a **condicionada a pico de volume**, que eu não medi. Então 0,10 é um chute
informado por um recorte errado, e tem de ser registrado como tal em [[Registro de Tentativas]],
com data, junto do protocolo, **antes** de qualquer coleta. Ele não é resultado de outcomes — e é
exatamente por isso que não pode ser ajustado depois de ver outcomes e reapresentado como se fosse
o corte original ([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]).

**Consequência prática:** a ordem correta inverte o que eu tinha escrito. Primeiro **observar sem
decidir** (persistir o desequilíbrio no envelope), depois **medir a retenção** do corte na população
candidata, e só então congelar **um** protocolo com o limiar que essa medição indicar — declarado
antes da janela futura.

**Passo obrigatório antes do braço** (e a parte que vale mesmo sem ele): **persistir
`taker_imbalance_5m` no envelope imutável** de todo sinal, como mais um `FeatureEvidence`, sem mudar
a decisão. Isso é observabilidade, não variante: em poucos dias teremos a distribuição do
desequilíbrio **condicionada a pico de volume**, que é exatamente a população que interessa e que a
medição acima (população inteira) não descreve.

**A hipótese em uma frase:** um pico de volume com fechamento acima do meio da barra **mas com
desequilíbrio agressor negativo** é distribuição vendendo no repique, e os dois filtros de preço que
a `volume_anomaly_v1` tem — `close > bar_mid` (linha 162) e `0 ≤ return_5m ≤ 2·atr_pct_15m`
(linha 172) — são ambos **de preço**, então nenhum dos dois consegue distinguir quem cruzou o spread
para produzir aquele preço.

**Alvo declarado:** entre os sinais com desequilíbrio negativo, taxa de `invalidated` maior e
expectancy menor que entre os de desequilíbrio positivo. **Refutação — e com o cuidado que a Astra
exigiu:** expectancy indistinguível entre as faixas **com precisão suficiente para excluir uma
diferença que importaria**. Ausência de diferença detectada numa amostra pequena é **inconclusivo**,
não prova de redundância; ler as duas coisas como a mesma descartaria uma feature útil por falta de
poder estatístico.

## Por que pode falhar

- **`close > bar_mid` pode já ser um proxy do desequilíbrio.** Se forem quase a mesma informação, o
  filtro só encolhe a amostra. É o mesmo risco de redundância que bloqueou a candidata #8 em
  [[Strategy Backlog]], e o teste é o mesmo: medir a **retenção** antes de rodar o braço.
- **Barras finas.** Com poucos negócios, o desequilíbrio de 5 min ainda é ruidoso; o corte pode
  selecionar liquidez, não intenção.
- **Agressor não é informado.** Comprador agressor pode ser um short se cobrindo, uma liquidação
  forçada ([[KB-0017-liquidacoes-o-fluxo-forcado-que-observamos-por-amostragem]]) ou execução de carteira. O
  campo diz **quem cruzou o spread**, não quem sabia de algo.
- **Mudança de código no caminho congelado.** Somar um campo em `Bar` toca a agregação usada também
  pela `momentum_v1`. Exige revisão do `quant-engineer`, `code-reviewer`, e um `strategy_version`
  novo com `code_ref` novo — não é edição no lugar.
- **Janela curta.** 41 h de série e 1 dia com outcome avaliável. As distribuições acima descrevem
  este recorte, não o mercado.
- **Uma tentativa a mais** sobre a mesma população: entra em [[Registro de Tentativas]] antes de
  rodar, com janela futura declarada.

## Segunda opinião (Astra)

`.claude/state/astra-review-KB-0014-taker.md`. Confirmou o caminho do dado com as linhas exatas
(`repo.py:97,124` → `context.py:60` → `base.py:189,197`; `aggregate.py:40` e `_fold` na 77 sem o
campo) e **quatro must-fix, todos aceitos**:

1. **A afirmação sobre `covered_until` estava desatualizada.** O `git status` dela mostrou
   `market-worker/coverage.py` e `scanner-worker/context.py` na árvore, ainda não commitados: o
   publicador e o consumidor da prova **existem agora**. Cenário de falha: duplicar trabalho já
   feito, ou declarar as features de fita operacionais só porque achei o publicador, sem verificar as
   chamadas. Corrigido no corpo, com a disponibilidade marcada como **não demonstrada**.
2. **Retirar a conclusão de que 1 minuto é inútil.** Dispersão marginal maior não é inutilidade, e a
   redução em 5 min pode ser efeito mecânico da agregação. Cenário de falha: descartar a informação
   do **último minuto do pico** — justamente o que a agregação dilui — por causa de uma distribuição
   marginal larga.
3. **Reclassificar o 0,10.** É escolha derivada de inspeção da população **errada** (a inteira, não a
   condicionada a pico), e tem de ser registrada como tal antes da coleta. Cenário de falha: o corte
   preservar quase todos ou quase nenhum candidato, ser ajustado depois de ver outcomes e o
   resultado ser apresentado como confirmação do corte original.
4. **Ausência de diferença detectada ≠ redundância.** Pode ser inconclusivo por amostra pequena.

Aceitei também o *nice-to-have* de registrar o corte exato das consultas e a advertência de que
falta a distribuição de `trade_count` e a separação entre população inteira, picos e candidatos que
passam pelos demais filtros. E adotei a sequência dela: **observar sem alterar decisões → medir
retenção na população candidata → congelar um protocolo único → avaliar em janela futura**, com
custos e com a dependência entre mercados considerada.

**Divergência:** nenhuma. Ela concorda que a hipótese merece teste e que os percentis atuais não a
validam — que é precisamente a distância entre o que eu tinha escrito e o que o dado permite.

## Relacionados

[[Strategy Backlog]] · [[Registro de Tentativas]] · [[Index]] ·
[[KB-0009-o-efeito-do-quarto-de-hora]] · [[KB-0011-volume-magnitude-e-a-ponte-para-direcao]] ·
[[KB-0013-vpin-e-a-disputa-sobre-toxicidade]] ·
[[KB-0015-volume-relativo-e-o-pico-como-exaustao]] · [[EXP-0002-volume-anomaly-v1]] ·
[[Volume Agent]] · [[Features]] · [[Market Collector]] · [[Data Flow]]
