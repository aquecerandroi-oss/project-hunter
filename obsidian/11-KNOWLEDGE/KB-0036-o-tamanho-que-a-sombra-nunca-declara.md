---
tags: [knowledge, nota, execucao, microestrutura, custos]
tema: Execução e microestrutura do preenchimento
fonte: Medição própria sobre os 200 livros `depth20` do hot state (Redis local) + `services/strategy-worker/hunter_strategy_worker/pricing.py` + `packages/core/hunter_core/strategies/envelope.py`
fonte_url: https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-api-general-info
lido_em: 2026-09-06
evidencia: medição própria (duas leituras de 200 livros, segundos de diferença, saídas coladas; o trecho de script é o núcleo do cálculo, não o script inteiro)
hipotese_testavel: sim
astra: concorda após correções (recusou a primeira versão)
---

# O tamanho que a sombra nunca declara

## O que afirma

`AssumedCosts` tem `spread_bps`, `slippage_bps`, `fee_bps` e `max_entry_delay_s`
(`envelope.py:54-57`). **Não tem tamanho.** E os 6 bps por lado de
`cost_bps() = spread_bps/2 + slippage_bps` (`pricing.py:36-38`) só são uma hipótese
verificável depois que alguém diz *de quanto era a ordem*: atravessar o book custa uma coisa para
500 dólares e outra para 20 mil, no mesmo livro, no mesmo segundo.

Medido agora, nos 200 livros de 20 níveis que o `market-worker` mantém no Redis: para **500 USDT** a
mediana do custo de atravessar o ask é **2,53 bps**; para **1.000**, **3,47 bps**; para **5.000**,
**6,85 bps** — já acima da hipótese —; para **20.000**, **10,65 bps**, e **68 dos 200 livros nem
comportam** 20 mil dólares nos 20 níveis publicados. A hipótese de 6 bps por lado não é otimista nem
pessimista: ela é **muda sobre um parâmetro sem o qual não pode ser conferida**. Tamanho não é o
único que decide — instante, lado e política de execução também decidem
([[KB-0039-tipos-de-ordem-e-o-que-a-sombra-assume-sem-dizer]]) —, mas é o que hoje não existe em
lugar nenhum do contrato.

## Onde foi mostrado

Não é literatura; é o nosso próprio book, agora. Amostra: 200 livros `mkt:binance:*:book`
(`hot_state.py:_book_payload`, 20 níveis por lado, `BOOK_TTL_S = 10`), idade do snapshot **p50 3,88 s,
p90 5,23 s, máximo 9,43 s**. Custo definido como `VWAP(ordem a mercado) / mid − 1`, em bps, andando o
ask nível a nível até completar o notional.

```
livros_no_redis=200   livros_usaveis=200
idade_do_snapshot_s: p50=3.88 p90=5.23 max=9.43

notional no melhor ask (USDT):     p10=26  p25=107  p50=352  p75=1246  p90=6326
notional acumulado nos 20 niveis:  p10=4827 p25=11990 p50=37663 p75=118640 p90=300644

custo de atravessar o ask (VWAP vs mid), em bps, por tamanho:
   tamanho   n_ok  nao_cobre      p25  mediana      p75      p90
       100    200          0    0.748    1.638    2.693    4.076
       500    200          0    1.235    2.528    4.265    6.233
      1000    197          3    1.532    3.467    5.739    8.083
      5000    178         22    2.892    6.853   11.059   15.974
     20000    132         68    4.220   10.650   19.138   32.758
    100000     60        140    7.749   15.182   27.206   38.184
```

Estratificado — **e isto é uma segunda leitura do Redis, poucos segundos depois da primeira, não um
recorte da mesma amostra**. A Astra pegou a inconsistência que prova isso: no agregado acima, **68**
livros não comportam 20 mil; na leitura estratificada, 28+41 = **69** e 5+64 = **69**. Um livro
mudou de lado entre as duas chamadas. Nenhuma linha de uma tabela pode ser combinada com a outra:

```
com sinal (n=97)             500: med 2.054 p90  5.440 | 1000: 2.892  6.948 | 5000: 4.937 11.707 | 20000:  7.554 20.287 (28 nao cobrem)
sem sinal (n=103)            500: med 3.168 p90  7.205 | 1000: 4.173  9.174 | 5000: 8.786 18.955 | 20000: 14.281 42.209 (41 nao cobrem)
top 20 por volume (n=20)     500: med 0.693 p90  2.070 | 1000: 0.836  2.483 | 5000: 1.116  3.681 | 20000:  2.190  6.084 (5 nao cobrem)
fora do top 20 (n=180)       500: med 2.922 p90  6.641 | 1000: 3.714  8.780 | 5000: 7.456 16.837 | 20000: 12.615 35.955 (64 nao cobrem)
```

O **notional mediano no melhor ask é 352 USDT**. Quer dizer: uma ordem de mil dólares já anda além do
topo em mais da metade dos mercados que monitoramos. Isso diz que o **preço médio** sobe, não que a
ordem não execute — e "custo baixo" também não prova preenchimento inteiro no melhor nível, porque a
fila naquele nível não é minha.

## Como mediríamos aqui

O núcleo do cálculo — não o script inteiro, que também faz a varredura das chaves, os quantis e a
estratificação — é este, e roda contra o Redis de dentro do container `api` (o Redis local não expõe
porta):

```python
# para cada mkt:binance:*:book, anda o ask ate completar `size` em USDT
for pr, q in asks:
    take = min(pr * q, remaining); cost += take; filled += take / pr; remaining -= take
    if remaining <= 0: break
custo_bps = (cost / filled - mid) / mid * 10000 if remaining <= 0 else None
```

```
docker compose -f infra/docker/docker-compose.yml exec -T api python - < book_walk.py
```

**Três ressalvas de comparabilidade, e sem elas a tabela vira uma identidade falsa.**

1. O meu número é `VWAP contra o mid`, então **já inclui o meio spread**. Os 6 bps do Lab são somados
   ao **`open` da vela**, que é o preço de um **negócio**, não o mid — pode ter saído no bid ou no
   ask. Se aquele `open` foi uma compra no ask, o Lab cobra 6 bps **em cima de um preço já
   atravessado**; se foi uma venda no bid, cobra de menos.
2. Eu medi o **ask no instante da leitura**. A entrada do Lab acontece na **abertura de uma barra
   posterior** (`plan.py`), 60 a 120 s depois ([[KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio]]).
   E eu **não** medi o **bid da saída**, que é a outra metade da ida e volta — e que, num stop,
   acontece com o mercado indo contra.
3. Os quantis são **condicionais aos livros que comportam o tamanho**. A mediana de 20 mil é a
   mediana dos 132 que couberam, não dos 200.

Ou seja: o que este número mede é **custo estático de atravessar o ask observado**, e é só isso.

## Hipótese testável no Lab

**Em duas etapas, e a primeira não é uma variante.**

**1. Declarar o tamanho (mudança de contrato, não de estratégia).** Acrescentar
`assumed_notional_usd` a `AssumedCosts`, congelado na versão como os outros três campos. Sem ele,
"6 bps por lado" não é falsificável — não existe medição que possa contrariá-lo. Com ele, existe:
para cada sinal, o custo do book no instante da decisão contra os 6 bps assumidos.

**2. Diagnóstico prospectivo `EXEC-A` (não muda decisão nenhuma).** Persistir, junto de cada sinal,
o custo de atravessar o book para uma grade fixa de tamanhos (100 / 500 / 1.000 / 5.000 USDT) e o
notional do melhor nível, lidos do book **antes** da abertura de entrada. Depois, publicar:

- distribuição do custo medido contra os 6 bps assumidos, por tamanho e por decil de liquidez;
- fração de sinais em que o tamanho pretendido **não cabe** nos 20 níveis (hoje, para 20 mil, seria
  34% do universo — mas o universo não é a população dos sinais);
- e a diferença entre o custo no book e o custo que o Lab cobrou, por sinal.

**Refutação, com o escopo estreito que a medição suporta:** se, na população dos **sinais** (não do
universo), o **custo estático de atravessar o ask no instante da decisão**, para o tamanho declarado,
ficar dentro de ±2 bps da hipótese na mediana e no p90, **e** a cobertura (fração de sinais cujo
tamanho cabe nos 20 níveis) for publicada junto e alta, então a hipótese de 6 bps é adequada **para a
perna de entrada, no instante da decisão**. Ela continua não dizendo nada sobre a abertura posterior
em que a entrada realmente ocorre nem sobre a perna de saída — essas duas ficam abertas em
[[KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio]] e
[[KB-0039-tipos-de-ordem-e-o-que-a-sombra-assume-sem-dizer]]. **Nada de reparametrizar
`slippage_bps` com base neste diagnóstico**: calibrar o custo na amostra que revelou o problema é o
erro de [[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] com outra roupa.

## Por que pode falhar

- **O book de 20 níveis não é o book.** A Binance publica `depth20`; existe profundidade além dele.
  "Não cobre nos 20 níveis" significa *não sei o preço*, não *impossível executar*.
- **O snapshot tem 4 segundos.** A p50 da idade é 3,88 s e o TTL é 10 s. O livro que eu ando não é o
  livro do instante do fill; para um mercado que se move, essa diferença é da ordem do próprio custo
  que estou medindo.
- **Andar o book é o custo de uma ordem única e imediata.** Não é o custo de uma metaordem
  ([[KB-0040-a-lei-da-raiz-quadrada-e-o-regime-que-nao-e-o-nosso]]) nem inclui o que acontece
  **depois** do fill ([[KB-0043-selecao-adversa-o-custo-que-so-aparece-depois-do-fill]]).
- **Um instante não é uma distribuição.** São 200 livros de um único segundo de uma quarta-feira à
  tarde. A cauda do book em stress (o momento em que a `momentum_v1` dispara) pode ser
  qualitativamente outra, e esta medição **não** diz nada sobre isso.
- **O universo não é a população dos sinais.** Os mercados que sinalizam são mais líquidos (2,05 bps
  contra 3,17 para 500 USDT). Usar a mediana do universo para prever o custo dos sinais superestima.

## Segunda opinião (Astra)

Concorda que a ausência de tamanho no contrato é o achado, e que a etapa 1 é mudança de contrato, não
de estratégia. **Não aprovou a primeira versão desta nota.** Cinco correções, todas aceitas:

1. **A inconsistência 68 contra 69** entre a tabela agregada e a estratificada: são **duas leituras
   do Redis** em segundos diferentes, e eu as tinha apresentado como a mesma amostra. Declarado no
   corpo. Cenário de falha que ela deu: escolher um tamanho misturando populações de instantes
   diferentes.
2. **O critério de aprovação media outra coisa** — ask na decisão, não a abertura de entrada, e nunca
   o bid da saída; e os quantis são condicionais aos livros que cobrem o tamanho. O veredito foi
   estreitado para "custo estático da perna de entrada no instante da decisão", com cobertura
   obrigatória.
3. **O trecho de script não reproduz as tabelas** (falta varredura, quantis, estratificação).
   Rotulado como núcleo do cálculo, não como script completo.
4. **"Acima de 5.000 o `depth20` recusa mais da metade dos livros" era falso** — em 20 mil são 34%;
   "mais da metade" só vale para 100 mil (140 de 200). Corrigido abaixo.
5. **Cortada** a frase "o único parâmetro que decide se está certa" e a generalização de que ordem
   pequena "executa no toque" no top 20 — custo baixo não prova preenchimento inteiro no melhor
   nível.

Divergência que fica: ela preferia grade de tamanhos até 50 mil. Mantive até 5.000, agora com o
motivo correto — em 20 mil já **34%** dos livros não cobrem e em 100 mil **70%**, e um quantil
calculado só sobre os que couberam mede seleção, não custo.

## Relacionados

[[Strategy Backlog]] · [[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] ·
[[KB-0037-o-spread-assumido-contra-o-spread-medido]] ·
[[KB-0040-a-lei-da-raiz-quadrada-e-o-regime-que-nao-e-o-nosso]] ·
[[KB-0044-o-que-morre-em-dez-segundos]] · [[EXP-0001-momentum-v1]] · [[Risk Engine]] ·
[[Market Collector]]
