---
tags: [knowledge, nota, execucao, proveniencia, qualidade-do-dado]
tema: Execução e microestrutura do preenchimento
fonte: Medição própria sobre `market_snapshots` e o hot state + `hot_state.py`, `sampling.py`, `streams.py` da árvore
fonte_url: https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams
lido_em: 2026-09-06
evidencia: replicado (SQL colado, contagens exatas) + leitura de código conferida por mim depois do apontamento da Astra
hipotese_testavel: sim
astra: concorda após correções (recusou a primeira versão)
---

# O que morre em dez segundos: o custo não é reconstruível

## O que afirma

Todo o resto desta rodada — o custo por tamanho, o meio spread, o erro de referência, o markout —
depende de dados que **existem no sistema por segundos e não são gravados em lugar nenhum**. Não é
que falte instrumentação futura: é que o instrumento **já lê** o que precisamos e joga fora.

O inventário exato:

| Dado | Onde vive | Quanto tempo | Persistido? |
|---|---|---|---|
| Book de 20 níveis (`depth20`) | Redis, `mkt:<ex>:<sym>:book` | **só o mais recente**, TTL 10 s | **não** |
| Tamanho no melhor bid/ask (`bid_qty`/`ask_qty`) | Redis, hash `ticker` | **só o mais recente**, TTL 30 s | **não** |
| `bid`/`ask` e `spread_pct` | `market_snapshots` | retenção de 30 dias | **sim**, 1/min, 37% dos minutos |
| Ranking de liquidez no instante da decisão | — | — | **não** (achado da segunda rodada) |
| `volume_24h` / `quote_volume_24h` no snapshot | coluna existe | — | **6 linhas em 55.709** |
| `next_funding_time` no snapshot | coluna existe | — | **0 linhas** |

Precisão que a Astra exigiu e que eu tinha errado nas duas primeiras linhas: **TTL não é janela
histórica**. Cada book novo faz `SET` por cima do anterior (`hot_state.py:175`), então "10 segundos"
é o prazo de validade da **única** versão viva, não dez segundos de versões recuperáveis — consultar
dois segundos depois pode já encontrar outro book. E `market_snapshots` **não é permanente**: tem
retenção configurada de 30 dias (`infra/scripts/prune_partitions.py:96`).

## O achado que eu tinha explicado errado: dois escritores disputando o mesmo hash

Eu escrevi que faltava produtor para `volume_24h`. **Falso — o produtor existe**, e o problema é
pior: são **dois** escritores do mesmo hash, com cargas disjuntas e o **mesmo conjunto de campos de
propriedade**. Conferi o caminho inteiro depois que a Astra o apontou:

| Elo | Onde |
|---|---|
| O refresh do universo busca tickers de 24 h | `universe.py:107` |
| Na Binance isso é `GET /fapi/v1/ticker/24hr` | `binance/rest.py:270` |
| O parser preenche volumes e **deixa `bid`/`ask` como `None`** — e o docstring diz isso em voz alta | `binance/normalize.py:212` |
| O refresh escreve esses tickers no Redis para os monitorados | `universe.py:181` |
| O WS `bookTicker` produz `bid`/`ask`/quantidades e **nenhum volume** | `binance/streams.py:168` |
| O coalescer escreve o ticker de WS **no mesmo hash** | `coalesce.py:158` |

Os dois usam `owned=TICKER_FIELDS` (`hot_state.py:48-60`), e a regra do Lua é: **campo de propriedade
que vem `None` é apagado com `HDEL` no mesmo MULTI** (`hot_state.py:83,117`). A regra existe por um
bom motivo — que uma exchange que pare de mandar um campo opcional não deixe valor velho ao lado de
timestamp fresco (H4). Mas com dois produtores complementares ela produz isto:

1. Uma escrita REST aceita grava `volume_24h` e **apaga `bid`/`ask`**.
2. Um snapshot que caia nesse intervalo registra **volume sem spread**.
3. O próximo `bookTicker` aceito grava `bid`/`ask` e **apaga `volume_24h`**.
4. Todos os snapshots seguintes registram **spread sem volume**.

E é por isso que a primeira consulta que escrevi nesta rodada — spread por decil de volume, tudo
dentro de `market_snapshots` — voltou **zero linhas**: os dois campos quase nunca coexistem na mesma
linha. Com refresh de 900 s (`market_universe_refresh_s`) contra `bookTicker` de altíssima frequência,
6 linhas em 55.709 é exatamente o que esse mecanismo prevê. Aumentar TTL não resolve: o problema é o
`HDEL` entre escritores. **Vai para [[Open Bugs]] como conflito de propriedade de campos entre o
ticker REST e o `bookTicker`.**

`next_funding_time` com zero linhas tem causa **diferente e mais simples**: é escrito no hot state
(`hot_state.py:308`) e simplesmente **não entra no dicionário do snapshot** (`sampling.py:202`).

## Onde foi mostrado

Instância local, mesma janela de 24 h da [[KB-0037-o-spread-assumido-contra-o-spread-medido]]:

```sql
SELECT count(*) t, count(price) price, count(bid) bid, count(ask) ask, count(spread_pct) spr,
       count(volume_24h) v24, count(quote_volume_24h) qv24, count(open_interest) oi,
       count(funding_rate) fr, count(mark_price) mk, count(next_funding_time) nft
FROM market_snapshots;
```

```
   t   | price |  bid  |  ask  |  spr  | v24 | qv24 | oi  |  fr   |  mk   | nft
-------+-------+-------+-------+-------+-----+------+-----+-------+-------+-----
 55709 | 52949 | 52943 | 52943 | 52943 |   6 |    6 | 498 | 28513 | 28510 |   0
```

Duas notas de proveniência, porque a Astra reparou na diferença: esta extração tem **52.943**
`spread_pct` e a da [[KB-0037-o-spread-assumido-contra-o-spread-medido]] tem **53.128** —
são **extrações em minutos diferentes** da mesma tabela viva, com o worker escrevendo entre elas.
Nenhuma linha de uma pode ser combinada com a outra. E a consulta acima não tem predicado de tempo:
descreve **toda** a tabela local, que hoje é a janela de 2026-09-05T16:29Z a 2026-09-06T16:44Z.

O decil da KB-0037 só existe porque usei `markets.volume_24h_usd`, que vem do mesmo refresh REST e é
um valor **atual e por mercado**, não histórico por instante.

E o `open_interest` com 498 de 55.709 é a mesma família de problema, do lado dos derivativos que a
[[KB-0025-o-nosso-detector-de-open-interest-so-olha-para-cima]] já tinha aberto.

## Como mediríamos aqui

A pergunta que esta nota fecha é: *dado o que está gravado hoje, quais das perguntas desta rodada
podem ser respondidas retrospectivamente?*

| Pergunta | Retrospectiva? | Por quê |
|---|---|---|
| Qual era o spread cotado na hora do sinal? | **não** | 8 de 200 sinais têm snapshot no seu minuto |
| Quanto custaria atravessar o book para X USDT? | **não** | book vive 10 s, nunca gravado |
| Qual era o tamanho no melhor ask? | **não** | `bid_qty`/`ask_qty` vivem 30 s no hash, nunca gravados |
| O `open` estava dentro do `[bid, ask]`? | **não** | precisaria de book no instante da abertura |
| Qual era o deslocamento referência→entrada? | **sim** | `candles` + `meta.entry_plan` bastam ([[KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio]]) |
| Qual era o decil de liquidez do mercado? | **parcialmente** | `markets.volume_24h_usd` é atual, não histórico |

Cinco não, um sim e um "mais ou menos". Esta é a resposta honesta para a pergunta "o M4 pode começar
sabendo quanto custa executar?": **não com o que está gravado**.

## Hipótese testável no Lab

**`EXEC-I` — carimbo de execução associado ao sinal.** Não é uma hipótese de estratégia; é um
requisito de proveniência, da mesma família do carimbo de regime
([[KB-0030-o-regime-nao-chega-ao-sinal]]) e do ranking de liquidez
([[KB-0018-volume-relatado-e-o-denominador-que-usamos]]).

**Precisão de esquema que a Astra exigiu:** o **envelope da decisão é escrito uma vez** e descreve o
instante da decisão (`envelope.py:3`). A leitura feita perto da abertura de entrada é **posterior** e
não pode entrar nele — tem de ser um **registro separado, associado ao sinal**. Misturar as duas
leituras num campo só apaga a diferença entre "o que eu sabia quando decidi" e "o que era verdade
depois", que é exatamente a distinção que o Lab inteiro existe para preservar.

No instante da avaliação, e num registro separado o mais perto possível da abertura de entrada,
gravar:

- `bid`, `ask`, `mid`, `bid_qty`, `ask_qty` e a **idade** do snapshot de book em milissegundos;
- o custo de atravessar para uma grade fixa de tamanhos (100 / 500 / 1.000 / 5.000 USDT) e a
  cobertura de cada um (cabe nos 20 níveis, sim ou não);
- o `quote_volume_24h` **do instante**, não o da tabela `markets`;
- e o motivo, quando qualquer um deles estiver indisponível — `unavailable` com razão, nunca zero.

**O critério de sucesso não é um número de estratégia; é cobertura.** Mas o carimbo **não resolve
tudo**, e a primeira versão desta nota prometia demais. O que ele **não** entrega:

- **O decil de liquidez histórico.** Volume de um mercado isolado não dá o decil dele: falta a
  população de comparação, ou um **ranking congelado** no instante.
- **O markout.** Carimbo na decisão e na entrada não fornece o mid **depois** da entrada.
- **E o `EXEC-H` não depende dele.** Aquele diagnóstico usa `candles`; cobertura baixa aqui não o
  torna impossível.

O que ele entrega: `EXEC-A` (custo por tamanho), `EXEC-B` (spread na decisão) e `EXEC-G` (erro de
referência) passam de impossíveis a prospectivamente respondíveis.

**Refutação de um item específico:** se a idade mediana do book no instante do carimbo for da ordem
de segundos (hoje é 3,88 s no hot state), o carimbo mede um book que já não existe, e o requisito
verdadeiro é reduzir a idade, não gravar mais.

**O que isto não é:** proposta de gravar todo o book de todos os mercados. Seriam 200 mercados ×
20 níveis × 2 lados a cada atualização — volume de dado que não se justifica para responder a
perguntas sobre **sinais**, que são poucos por dia. O carimbo é por sinal, não por tique.

## Por que pode falhar

- **Um dia, uma instância, um worker que reiniciou.** As contagens descrevem esta janela local, não
  produção; a VPS pode ter cobertura melhor e não foi consultada nesta rodada.
- **O mecanismo do `HDEL` explica as 6 linhas, mas não as identifica.** Atribuir cada uma delas
  exigiria examiná-las e conferir a versão do código que rodava naquele minuto. A explicação é
  **consistente**, não **verificada linha a linha**.
- **`next_funding_time` com zero linhas** já era conhecido ([[KB-0019-o-que-a-nossa-funding-rate-mede-de-fato]]);
  aqui ganha número **e causa** — omissão no dicionário do snapshot, não disputa de escritores.
- **Carimbar custa latência.** Ler o book e calcular quatro caminhadas por sinal, no caminho da
  decisão, é trabalho no lugar mais sensível. Se o custo for material, o carimbo tem de sair do
  caminho crítico — o que reintroduz atraso entre o instante medido e o instante decidido.
- **Gravar o custo não é medir o custo.** O carimbo registra o que o book **oferecia**; o que teria
  sido pago depende de quem mais estava atravessando no mesmo milissegundo.
- **Risco de look-ahead na análise.** Um carimbo tirado depois da abertura de entrada, usado numa
  análise que decide sobre a entrada, é informação do futuro. A separação tem de estar no esquema,
  não na disciplina de quem consulta.

## Segunda opinião (Astra)

**A revisão dela substituiu a explicação central desta nota, e é o melhor achado da rodada inteira.**
Eu tinha escrito "falta produtor para `volume_24h`". Ela mostrou que o produtor existe — o refresh
REST do universo — e que o problema é **disputa entre dois escritores do mesmo hash com o mesmo
conjunto de campos de propriedade**: cada escrita apaga com `HDEL` os campos que o outro produtor
escreve. Percorri o caminho no código antes de aceitar (`universe.py:107,181`, `rest.py:270`,
`normalize.py:212`, `streams.py:168`, `coalesce.py:158`, `hot_state.py:48,83,117`) e confirmei;
o docstring de `parse_ticker_24h` até declara que o endpoint não traz bid/ask.

Outras três correções aceitas: (1) **TTL não é janela histórica** — cada `SET` substitui o book
anterior, e "10 segundos" é a validade da única versão viva; (2) `market_snapshots` **não é
permanente**, tem retenção de 30 dias; (3) o `EXEC-I` **não** torna todas as perguntas respondíveis —
não dá decil histórico sem ranking congelado, não dá mid pós-entrada para markout, e o `EXEC-H` nem
depende dele. E a precisão de esquema: o **envelope da decisão é escrito uma vez**, então a leitura
perto da abertura de entrada tem de ser registro separado.

Nice-to-have aceito: declarar que os 52.943 spreads daqui e os 53.128 da KB-0037 são extrações em
minutos diferentes; e que `next_funding_time` tem causa própria (omissão em `sampling.py:202`).

Acordo que fica: gravar o custo de execução **não melhora nenhuma expectancy**; apenas torna
falsificável uma hipótese que hoje não é. Esse é todo o valor, e já é bastante.

## Relacionados

[[Strategy Backlog]] · [[KB-0036-o-tamanho-que-a-sombra-nunca-declara]] ·
[[KB-0037-o-spread-assumido-contra-o-spread-medido]] ·
[[KB-0042-o-open-nao-e-preco-executavel]] ·
[[KB-0043-selecao-adversa-o-custo-que-so-aparece-depois-do-fill]] ·
[[KB-0018-volume-relatado-e-o-denominador-que-usamos]] ·
[[KB-0030-o-regime-nao-chega-ao-sinal]] · [[Open Bugs]] · [[Market Collector]] · [[Data Flow]]
