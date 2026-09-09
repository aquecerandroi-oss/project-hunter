# Notas T3.55b — padrões de candlestick no NOSSO dado (pesquisa; nada commitado, nada de produção)

**Quando:** 2026-09-08 23:56 → 2026-09-09 01:5x Brasília (UTC−3); em UTC, 2026-09-09 02:56 → 04:5x.
**Owner:** quant-engineer. **Brief:** `.claude/state/brief-T3.55-candlestick.md`, parte (b).
**Par:** parte (a) = `KB-0080-candlestick-evidencia.md` + `notes-T3.55a.md` (gravadas 00:16 BRT,
**depois** do início desta medição — ver §6).

**Nada foi commitado. Nada de `packages/` ou `services/` foi tocado.** Nenhum `code_ref`, nenhum
`feature_set_version`, nenhuma linha em `DEFAULT_REGISTRY`. O protótipo mora em
`.claude/state/exp-drafts/t355/` e não é importado por `hunter_core.strategies.*`.
`t342-blocos/blocos.py` foi **reusado sem uma linha de alteração** (`git status` do arquivo:
inalterado; o confronto literal está na §4).

## 0. Resposta em três linhas

Nenhum dos 14 padrões clássicos carrega informação que sobreviva a Holm sobre 72 testes não-raros,
em nenhum dos três horizontes, em 15 m ou 1 h — e o nulo é **medido**, não é falta de poder
(controle positivo com o mesmo `n` acende com `p = 0,0001`). Repetindo com as **outras** definições
(as 18 da KB-0080 §7) o resultado se mantém, com um único sobrevivente do Holm conjunto sobre 144:
o *marubozu de baixa* em 1 h, que prevê **alta** — e que, operado ao contrário com stop de 1 ATR,
rende `+0,005 R` (IC95 `[−0,104; +0,112]`), ou seja, exatamente o pedágio. **Não há contrato a
abrir; o portão C1–C8 sai `FAIL`.**

## 1. O que ficou escrito, e onde

| arquivo | linhas | papel |
|---|---:|---|
| `infra/scripts/sql/research/2026-09-09-t355-q00-universo.sql` | 38 | universo candidato por liquidez + cobertura de 1 min na janela |
| `…-t355-q01-barras.sql` | 51 | as barras de 15 m e 1 h dobradas no servidor com exigência de completude |
| `…-t355-q02-catalogo-regime.sql` | 19 | `market_regimes` cobre a janela? (sim: 758 linhas, 33 dias) |
| `…-t355-q03-regime-csv.sql` | 14 | o regime horário em CSV para o recorte condicional |
| `.claude/state/exp-drafts/t355/padroes.py` | 389 | detector-protótipo, conjunto (b), 14 rótulos, `Decimal` |
| `…/padroes_kb0080.py` | 329 | detector-protótipo, conjunto da KB-0080 §7, 18 rótulos |
| `…/series.py` | 56 | séries sintéticas com ATR **exatamente 10** (a régua dos valores esperados) |
| `…/medir.py` | 193 | varredura, retornos futuros, `universo.csv` + `ocorrencias.csv` |
| `…/bootstrap_padroes.py` | 192 | bootstrap de blocos por dia (atalho idêntico ao `blocos.py`), média por blocos, Holm |
| `…/estatistica.py` | 183 | contraste principal com portão de raridade |
| `…/linhas.py` | 100 | distância de cada barra às linhas do `tl_scan` congelado |
| `…/condicional.py` | 183 | os dois recortes (linha, regime do BTC) |
| `…/pedagio.py` | 102 | a lente da KB-0076 por padrão |
| `…/controle.py` | 107 | controles positivo/negativo e a resolução contra o pedágio |
| `…/sobreviventes.py` | 111 | Holm conjunto sobre as duas famílias e a economia do que sobra |
| `…/confronto_blocos.py` | 71 | confronto literal com o `blocos.py` no dado real |
| `…/rodar_kb0080.py` | 24 | o braço de robustez de ponta a ponta |
| `…/test_padroes.py` | 336 | 38 testes do conjunto (b) |
| `…/test_padroes_kb0080.py` | 135 | 29 testes do conjunto (a) |
| `…/test_bootstrap.py` | 110 | 10 testes do bootstrap, incluindo a identidade com `blocos.py` |
| `…/test_pipeline.py` | 70 | anti-antecipação **no dado real** + contiguidade da exportação |

Dados gerados (não versionáveis, ficam ao lado): `barras.csv` (59 216 barras), `regimes.csv`,
`universo.csv`, `ocorrencias.csv`, `ocorrencias-a.csv`, `linhas-15m-A/B.csv`, `linhas-1h.csv`,
e as sete saídas `saida-*.txt` que a KB cita.

## 2. Decisões de projeto que valem registro

1. **A régua do padrão é `ATR[i − n]`, o ATR fechado ANTES da primeira barra.** Não é anti-look-ahead
   (`ATR[i]` é conhecido no fechamento de `i`), é significado: com `ATR[i]` a barra infla a própria
   régua e um marubozu de 3 ATRs reaparece como um de 1,8. Custou uma refatoração no meio do
   caminho e está provado por mutação (§5).
2. **A régua do retorno é `ATR[i]`.** São perguntas diferentes — "quão grande é esta barra" e
   "quanto o mercado andou depois" — e usar a mesma para as duas seria confundir escala de forma
   com escala de resultado.
3. **Corrida contígua, nunca costurada.** A série é quebrada nos buracos e cada pedaço é varrido
   sozinho (`atr_series` levanta em buraco, e está certo). Nesta janela cada (mercado, timeframe) é
   **uma corrida só**: os 15 baldes de 15 m que faltam são as 3 h 45 min iniciais, antes de o
   coletor existir. Provado por `test_pipeline.py::test_a_serie_exportada_e_contigua`.
4. **As 16 últimas barras de cada corrida saem do estudo — do padrão E da baseline.** Se saíssem só
   do padrão, a baseline mediria uma janela que o padrão não teve.
5. **Portão de raridade `n >= 30` e `>= 10 dias distintos`** (o número é da própria KB-0080 §7).
   **Isto foi acrescentado depois de ver o resultado**, e por um motivo que precisa ficar escrito: o
   braço da KB-0080 "encontrou" sete sobreviventes de Holm com `n = 1, 2, 3`. Com uma ocorrência,
   toda reamostragem que sorteia aquele dia devolve o mesmo valor, o IC colapsa e o `p` vai a
   0,0001. Não é evidência, é aritmética de amostra minúscula. O portão derrubou seis dos sete; o
   sétimo (`a_marubozu_baixa`, `n = 90`) é o que a nota publica.
6. **A família é a união dos dois braços.** Quem olhou 84 rótulos-horizonte com um conjunto de
   constantes e 108 com outro, sobre a **mesma fita**, olhou 144 testes não-raros. Corrigir cada
   braço isolado subestimaria a busca que eu fiz.
7. **O doji do conjunto (b) não tem direção** e foi medido com sinal `+1`, o que é uma escolha
   declarada e não uma afirmação. O conjunto da (a) resolve isso melhor (dois rótulos, direção =
   reversão do contexto), e os dois concordam: doji em tendência de alta cai.
8. **A lente de pedágio não é backtest e não finge ser.** Saída por horizonte, sem caminho
   intrabarra. Um backtest de verdade reusa `Strategy`, `RiskEngine` e `PaperExecutionAdapter`, e
   esta task não escreve produção.

## 3. Prova de anti-antecipação (a exigência do PIPELINE §2)

Quatro afirmações, três delas com dentes:

1. `test_um_padrao_nao_muda_quando_o_futuro_muda` — para cada `i` de uma série aleatória de 260
   barras, a barra `i+1` é trocada por outra completamente diferente e **todas** as detecções em `i`
   têm de sair idênticas (nome, barra, entrada, stop, escala).
2. `test_o_corte_por_prefixo_e_o_corte_por_indice_sao_o_mesmo` — `detectar(bars[:i+1], …, i)` é
   igual a `detectar(bars, …, i)`.
3. `test_a_trapaca_reprova_exatamente_o_que_o_detector_honesto_passa` — uma trapaça deliberada
   (exigir que a barra **seguinte** confirme o padrão, que é o vazamento clássico de estudo de
   candlestick) quebra a propriedade 1. Sem ele os dois primeiros seriam decorativos.
4. `test_cortar_a_serie_nao_muda_o_passado` (arquivo `test_pipeline.py`) — a mesma propriedade **no
   dado real**, em BTC, DOGE e SAHARA, com cortes em 200, 500, 1 000, 1 500 e 2 500 barras.

O conjunto da KB-0080 tem 1 e 2 replicados, e o 2 lá vale mais: a EMA10 é recursiva e semeada no
índice 9, então "cortar a série não move a EMA" é uma afirmação que podia falhar e não falha.

## 4. Prova de que `blocos.py` foi reusado sem alteração

`bootstrap_padroes.contraste_rapido` calcula o mesmo Δ por estatística suficiente (soma e contagem
por dia) porque 84 contrastes × 10 000 reamostragens × 47 000 linhas é meia hora de concatenação.
Ele consome a **mesma** sequência do **mesmo** gerador na mesma ordem. Dois testes:

- sintético: `test_bootstrap.py::test_o_atalho_reproduz_blocos_numero_a_numero`, `abs < 1e-12` em
  `exp_pai`, `exp_variante`, `delta` e nas duas pontas do IC;
- real: `confronto_blocos.py` sobre quatro populações desta nota — **idênticos** nas quatro
  (saída na §5).

Se um dia divergirem, o número que vale é o do `blocos.py`.

## 5. Comandos rodados (saída colada)

### 5.1 Exportação (VPS **somente leitura**, `repeatable read read only`, consulta pelo stdin do `psql`)

```
$ ssh hunter-vps 'date -u; TZ=America/Sao_Paulo date'
Wed Sep  9 02:58:08 UTC 2026
(= 2026-09-08 23:58:08 -03, Brasília)

$ ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter -v ON_ERROR_STOP=1 -f -" \
    < infra/scripts/sql/research/2026-09-09-t355-q00-universo.sql
             read_at            
 2026-09-09 02:58:29.089191+00
     symbol    | monitor_rank | vol24h_musd | minutos | cobertura_pct | replay
  BTCUSDT      |            1 |     10168.8 |   44428 |         99.53 | f
  ETHUSDT      |            2 |      8122.2 |   44428 |         99.53 | t
  ZECUSDT      |            3 |      1966.9 |   44428 |         99.53 | f
  SOLUSDT      |            4 |      1608.2 |   44428 |         99.53 | t
  SOPHUSDT     |            5 |      1249.8 |   10080 |         22.58 | f     <-- sem historico
  XRPUSDT      |            6 |      1035.8 |   44428 |         99.53 | t
  HYPEUSDT     |            7 |       600.5 |   13260 |         29.70 | f     <-- sem historico
  BNBUSDT      |            8 |       558.4 |   44428 |         99.53 | f
  DOGEUSDT     |            9 |       548.8 |   44428 |         99.53 | t
  ... (40 linhas; so 16 chegam a 99,53 %)

$ ssh hunter-vps "docker exec -i hunter-postgres-1 psql ... -f -" \
    < infra/scripts/sql/research/2026-09-09-t355-q01-barras.sql > t355/barras.csv
exit=0 | 59 221 linhas (59 216 barras + cabecalho + 4 linhas do psql) | stderr vazio
por mercado: 2 961 baldes de 15 m e 740 de 1 h, iguais nos 16

$ ssh hunter-vps "docker exec -i hunter-postgres-1 psql ... -f -" \
    < infra/scripts/sql/research/2026-09-09-t355-q02-catalogo-regime.sql
 linhas |        primeiro        |         ultimo         | dias
    758 | 2026-08-08 23:00:00+00 | 2026-09-09 03:00:00+00 |   33
     regime      |  n
 UNKNOWN         | 207
 SIDEWAYS        | 161
 BTC_BULL        | 150
 HIGH_VOLATILITY | 148
 BTC_BEAR        |  57
 LOW_VOLATILITY  |  35
```

Nada foi escrito na VPS: as quatro consultas entraram pelo stdin do `psql` dentro de
`begin transaction isolation level repeatable read read only; … commit;` e o CSV voltou pelo stdout
do `ssh`.

### 5.2 Testes

```
$ uv run pytest .claude/state/exp-drafts/t355 -q
........................................................................ [ 88%]
.........                                                                [100%]
81 passed in 9.78s
```

**Mutação, para provar que os testes têm dentes** (trocar a régua `ATR[i-1]` por `ATR[i]` em
`padroes.py`, rodar, reverter):

```
FAILED test_padroes.py::test_martelo_em_tendencia_de_baixa
FAILED test_padroes.py::test_a_mesma_geometria_em_tendencia_de_alta_e_enforcado
FAILED test_padroes.py::test_estrela_cadente
FAILED test_padroes.py::test_doji_pega_o_extremo_mais_distante_como_invalidacao
FAILED test_padroes.py::test_marubozu_de_alta
5 failed, 33 passed in 5.31s
--- revertido ---
38 passed in 4.29s
```

### 5.3 Varredura

```
$ uv run python .claude/state/exp-drafts/t355/medir.py
corridas 32 | barras usaveis 58224 | ocorrencias 11816
sinais declarados: 14 padroes
real    0m6.573s

$ uv run python .claude/state/exp-drafts/t355/linhas.py 1h
1h: 10064 barras varridas, 9564 com ao menos uma linha, 70.0 s (7.0 ms/barra)
$ uv run python .claude/state/exp-drafts/t355/linhas.py 15m A
15m: 22800 barras varridas, 21663 com ao menos uma linha, 169.4 s (7.4 ms/barra)
$ uv run python .claude/state/exp-drafts/t355/linhas.py 15m B
15m: 22800 barras varridas, 21809 com ao menos uma linha, 179.2 s (7.9 ms/barra)
```

(O 15 m foi partido em duas metades disjuntas de mercados só para respeitar o teto de 5 min por
comando desta sessão; as metades são concatenadas na leitura.)

### 5.4 Contraste principal

```
$ uv run python .claude/state/exp-drafts/t355/estatistica.py
rotulos medidos: 84 (14 x 2 tf x 3 horizontes) | raros (n < 30 ou dias < 10): 12 | familia de Holm: 72
padrao             tf   h      n  dias     bruto     delta  IC95 baixo  IC95 alto        p     Holm   Holm/h
marubozu_baixa     1h   1     87    31   -0.1574   -0.1562     -0.2844    -0.0309   0.0142    1.000    0.341
enforcado         15m   4    549    31   -0.1611   -0.1592     -0.3138    -0.0212   0.0202    1.000    0.566
doji              15m   1   4220    31   -0.0267   -0.0243     -0.0472    -0.0017   0.0362    1.000    0.833
tres_corvos       15m   4     59    31    0.3094    0.3090     -0.0117     0.6578   0.0572    1.000    1.000
engolfo_alta      15m   4    666    31   -0.1164   -0.1148     -0.2370     0.0152   0.0836    1.000    1.000
... (84 linhas na saida completa; saida-estatistica.txt)
sobrevivem a Holm(m=72) com alfa 0,05: nenhum
sobrevivem a Holm por horizonte: nenhum
```

Contagem de sinais sobre os 81 contrastes com `n > 0`: **46 negativos (56,8 %)**, **5 com
`p < 0,05`** (esperados ~4 por acaso) e **os 5 negativos**.

### 5.5 Confronto com o `blocos.py` (dado real)

```
$ uv run python .claude/state/exp-drafts/t355/confronto_blocos.py
contraste               fonte       n_var   exp_pai   exp_var     delta   IC baixo   IC alto    seg
tres_soldados|1h|h1     atalho         11  -0.00065  -0.66853  -0.66788   -1.32320  -0.13605    0.4
tres_soldados|1h|h1     blocos.py      11  -0.00065  -0.66853  -0.66788   -1.32320  -0.13605    1.1
                        identicos 
marubozu_baixa|1h|h1    atalho         87  -0.00121  -0.15737  -0.15616   -0.28442  -0.03092    0.4
marubozu_baixa|1h|h1    blocos.py      87  -0.00121  -0.15737  -0.15616   -0.28442  -0.03092    1.4
                        identicos 
enforcado|15m|h4        atalho        549  -0.00189  -0.16112  -0.15923   -0.31382  -0.02120    0.5
enforcado|15m|h4        blocos.py     549  -0.00189  -0.16112  -0.15923   -0.31382  -0.02120    3.5
                        identicos 
doji|15m|h1             atalho       4220  -0.00241  -0.02674  -0.02433   -0.04717  -0.00166    0.6
doji|15m|h1             blocos.py    4220  -0.00241  -0.02674  -0.02433   -0.04717  -0.00166    5.7
                        identicos 
```

### 5.6 Controles e resolução

```
$ uv run python .claude/state/exp-drafts/t355/controle.py
A. controles (horizonte 4 barras, mesma baseline pareada)
controle                 tf      n     delta   IC baixo   IC alto        p
trapaca_futuro          15m  23092    0.5047     0.4739    0.5412   0.0001
trapaca_rara            15m    689    0.9212     0.8531    0.9926   0.0001
aleatorio               15m    689   -0.0185    -0.1366    0.1043   0.7538
trapaca_futuro           1h   5787    0.4954     0.4254    0.5715   0.0001
trapaca_rara             1h    132    1.0412     0.7350    1.3638   0.0001
aleatorio                1h    132    0.0653    -0.2174    0.3254   0.6218

B. resolucao contra pedagio (horizonte 4 barras)
padrao             tf     n  meia largura ATR  stop ATR  resolucao R  custo_R  ve o suficiente?
engolfo_alta      15m   666            0.1261      1.25        0.101    0.335               sim
martelo           15m   689            0.1457      0.81        0.179    0.457               sim
doji              15m  4220            0.0539      0.56        0.096    0.667               sim
enforcado         15m   549            0.1463      0.13        1.084    2.779               sim
...  15 m: 12 de 14 padroes com resolucao melhor que o proprio pedagio
...  1 h : 1 de 13 (so o doji) — 31 dias nao dao amostra de 1 h
```

### 5.7 Pedágio (KB-0076)

```
$ uv run python .claude/state/exp-drafts/t355/pedagio.py
custo assumido 20 bps ida-e-volta | saida por horizonte 4 barras | sem caminho intrabarra
padrao             tf     n  deg  stop ATR   risco%  custo_R  R bruto   R liq.  IC baixo  IC alto  acerto%
engolfo_alta      15m   666    0      1.25    0.598    0.335   -0.007   -0.473    -0.587   -0.350     46.2
martelo           15m   689    0      0.81    0.437    0.457    0.135   -0.526    -0.785   -0.279     53.7
enforcado         15m   511   38      0.13    0.072    2.779    2.162   -8.811   -18.340    3.612     44.6
doji              15m  4220    0      0.56    0.300    0.667    0.057   -0.853    -1.126   -0.582     50.3
tres_soldados     15m    91    0      2.78    1.277    0.157    0.101   -0.233    -0.554    0.038     53.8
tres_corvos       15m    59    0      2.43    1.460    0.137    0.152   -0.123    -0.343    0.060     50.8
engolfo_alta       1h   135    0      1.09    1.142    0.175    0.282    0.049    -0.133    0.251     58.5
tres_soldados      1h    11    0      4.75    5.948    0.034    0.074    0.026    -0.361    0.302     45.5
... (28 linhas; saida-pedagio.txt)
```

A coluna `deg` conta as ocorrências em que `entrada == stop` — **38 enforcados de 15 m e 3 de 1 h**.
Elas saem da conta e são declaradas em vez de virar `NaN` calado; a linha do enforcado que sobra é
dominada por denominadores de 0,07 % e **não é estimativa publicável** (é por isso que a KB cita o
`custo_R` mediano, 2,78 R, e não a média de R).

### 5.8 Recortes condicionais

```
$ uv run python .claude/state/exp-drafts/t355/condicional.py
horizonte 4 barras | tolerancia 0.25 ATR | familia 8
fatia                      tf   n_pad   n_pop     bruto     delta   IC baixo   IC alto        p   Holm8
linha:encostado           15m     476    9392    0.0508    0.0642    -0.0796    0.2195   0.4058   1.000
linha:solto               15m    4509   81808   -0.0434   -0.0424    -0.1016    0.0172   0.1700   1.000
regime:alinhado           15m     698   13056   -0.0367   -0.0558    -0.2888    0.1784   0.6884   1.000
regime:contra             15m     749   13056   -0.0322   -0.0080    -0.1347    0.1196   0.9654   1.000
linha:encostado            1h      97    1942   -0.1047   -0.0537    -0.3766    0.3262   0.7474   1.000
linha:solto                1h     895   18186    0.0396    0.0312    -0.2475    0.2996   0.7982   1.000
regime:alinhado            1h     146    3264    0.1122    0.0853    -0.2447    0.5248   0.5994   1.000
regime:contra              1h     159    3264   -0.3193   -0.2965    -0.8064    0.0590   0.1090   0.872
sobrevivem a Holm(8): nenhum
```

`n_pop` é o dobro do número de barras da fatia por construção: cada barra entra duas vezes, uma na
visão long e outra na short, porque a pergunta "padrão de alta encostado num suporte" e "padrão de
baixa encostado numa resistência" são a mesma fatia com réguas diferentes.

Base de comparação: **10,9 % das barras de 15 m estão a ≤ 0,25 ATR de um suporte** e 9,7 % de uma
resistência (1 h: 9,9 % e 9,4 %). "Encostado na linha" não é evento raro.

### 5.9 Braço de robustez (definições da KB-0080 §7) e Holm conjunto

```
$ uv run python .claude/state/exp-drafts/t355/rodar_kb0080.py
corridas 32 | barras usaveis 58224 | ocorrencias 10867
rotulos medidos: 108 (18 x 2 tf x 3 horizontes) | raros (n < 30 ou dias < 10): 36 | familia de Holm: 72
a_doji_baixa      15m   1   1931    31    0.0550    0.0527      0.0232     0.0843   0.0006    0.043    0.014
a_marubozu_baixa   1h   1     90    31   -0.2037   -0.2021     -0.3011    -0.1011   0.0001    0.007    0.002
sobrevivem a Holm(m=72) com alfa 0,05: ['a_doji_baixa|15m|h1', 'a_marubozu_baixa|1h|h1']

$ uv run python .claude/state/exp-drafts/t355/sobreviventes.py
familia da parte (b): 72 | da KB-0080: 72 | uniao: 144
sobrevivem ao Holm conjunto (m=144, alfa 0,05): ['a/a_marubozu_baixa|1h|h1']
  a/a_marubozu_baixa|1h|h1       p=0.0001  Holm=0.0144
  a/a_doji_baixa|15m|h1          p=0.0006  Holm=0.0858
  b/marubozu_baixa|1h|h1         p=0.0142  Holm=1.0000
  a/a_martelo_invertido|15m|h16  p=0.0174  Holm=1.0000
  b/enforcado|15m|h4             p=0.0202  Holm=1.0000
  a/a_estrela_cadente|15m|h16    p=0.0274  Holm=1.0000

economia do que sobra (o horizonte de cada sobrevivente, nao o h=4 da tabela geral)
rotulo                         n  delta ATR    atr%  stop nat. custo nat.   R nat.  custo 1ATR   R 1ATR  IC baixo  IC alto
a/a_marubozu_baixa|1h|h1      90    -0.2037   1.005       1.30      0.155   -0.157       0.199   -0.403    -0.510   -0.294
  ^ operado ao contrario      90     0.2037   1.005          -          -    0.157       0.199    0.005    -0.104    0.112
```

### 5.10 Qualidade

```
$ uv run ruff check .claude/state/exp-drafts/t355 --output-format=concise
39 x T201 (`print` found) — sao scripts de manivela; nenhum outro achado
$ uv run ruff format --check .claude/state/exp-drafts/t355
18 files already formatted
$ uv run pyright .claude/state/exp-drafts/t355/padroes.py .claude/state/exp-drafts/t355/medir.py
0 errors, 0 warnings, 0 informations
```

**Ressalva honesta sobre o pyright:** rodado sobre o diretório inteiro ele acusa ~270 erros, quase
todos em cascata de `Import "blocos" could not be resolved` — o `pyrightconfig` do repositório não
inclui `.claude/state/exp-drafts/`, e o mesmo vale para os rascunhos da T3.42 e da T3.47. Os
módulos que não dependem do `blocos` (`padroes.py`, `padroes_kb0080.py`, `series.py`, `medir.py`)
saem limpos.

## 6. A colisão com a parte (a), e o que eu fiz com ela

O brief dizia: *"implemente as definições de (a) — se (a) não estiver pronta quando você começar,
use o conjunto padrão com definições numéricas explícitas escritas nas notas"*, e *"(a) pode
refiná-las"*. **Quando comecei (23:58 BRT) a (a) não existia**; a `KB-0080` foi gravada às **00:16
BRT**, com a medição já rodando. As definições da (b) estão na docstring de `padroes.py` e na §7 da
KB-0081.

A resposta que dei não foi trocar as constantes e publicar um número só — isso apagaria a diferença
entre "o padrão não informa" e "estas constantes não informam". Implementei **o conjunto da (a)
inteiro** (`padroes_kb0080.py`, 18 rótulos, incluindo os dois que a (b) não tinha: martelo invertido
e três-dentro) e publiquei os dois braços, com Holm sobre a união.

O que muda entre eles, medido: `martelo` cai de 689 para 502 ocorrências em 15 m (a (a) exige
amplitude ≥ 0,8 ATR contra 0,5 da (b)); `enforcado` de 549 para 303; `engolfo_alta` **sobe** de 666
para 1 013 (a régua de contexto da (a), EMA10 com inclinação, é mais permissiva que "variação de
1 ATR em 10 barras"); `marubozu_alta` de 683 para 758. **São medições diferentes**, e o veredito
não se move entre elas — o que é o ponto.

Uma escolha minha que a KB-0080 não fixa e que precisa ficar declarada: a **semente da EMA10** é a
média simples dos dez primeiros fechamentos, com `alfa = 2/11` depois. Uma EMA sem semente declarada
é um número diferente por implementação. Está fixada em teste
(`test_a_ema10_semeia_na_media_simples`).

## 7. Suposições numéricas que eu tive de fazer (todas declaradas)

1. **Universo de 16, não de 24.** O brief pedia os 20 mais líquidos + 4 de replay. `q00` mostra que
   só 16 monitorados têm os 31 dias (99,53 %); do 5º ao 40º lugar em liquidez, a cobertura é de
   22 % a 30 % (backfill de ~9 dias). Os 16 contêm os quatro de replay. **Não relaxei a janela para
   caber mais mercado** — 9 dias não medem padrão de 1 h.
2. **Horizontes 1, 4 e 16 barras**; o brief os fixou. Para os recortes condicionais escolhi **4** (o
   do meio), declarado antes de calcular qualquer número condicional, para não triplicar a família.
3. **Bloco = dia UTC.** Alinhado com a célula de baseline, que é a hora do dia UTC. Usar o dia de
   Brasília deslocaria os blocos em 3 h sem nenhum ganho.
4. **Célula de baseline = (mercado, hora do dia UTC)**, ~124 barras em 15 m e ~31 em 1 h. O
   deslocamento é fixado na amostra inteira e **o erro de estimá-lo não é propagado pelo bootstrap**
   — segunda ordem em 15 m, ressalva real em 1 h.
5. **Tolerância de 0,25 ATR** para "encostado na linha": é o `tolerance_atr` do `DEFAULT_PARAMS` da
   T3.34, a mesma régua que decide se um toque é toque. Não foi calibrada aqui.
6. **Janela de 96 baldes** para o `tl_scan`: o `pattern_bars` de `trendline_breakout_v1`, o mesmo
   que `render_operations.py` usa. As 95 primeiras barras de cada corrida ficam sem varredura e
   saem **só** do recorte condicional.
7. **Regime = a última hora que terminou estritamente antes do fechamento da barra.** Uma decisão às
   11:00 em ponto não pode ler o regime da hora [10:00, 11:00), que só é calculado depois das 11:00.
8. **Custo de 20 bps ida-e-volta** (`0,0020`), a hipótese do Lab, e `custo_R = 0,0020 / risco%` da
   KB-0076. **Stop declarado de 1,0 ATR** na leitura invertida do marubozu, porque a invalidação
   natural do inverso fica colada na entrada.
9. **10 000 reamostragens, seed 20260909** (o `blocos.py` usa 20260908; a semente diferente é
   deliberada, para que uma coincidência de semente não seja confundida com um resultado). O `p`
   mínimo reportável é, portanto, `1/10 000 = 0,0001`.
10. **Portão de raridade 30 ocorrências / 10 dias**, número da KB-0080 §7 — acrescentado **depois**
    de ver o braço (a) produzir sete "sobreviventes" com `n <= 3`. Está na §2 item 5 com o motivo.

## 8. O que fica para quem pegar isto depois

1. **Não abrir contrato.** O portão C1–C8 (rascunho, autoavaliação, na KB-0081) sai `FAIL` em C1,
   C2, C3, C5, C7 e C8. Se alguém quiser insistir no marubozu invertido, o único caminho honesto é
   **janela nova** — não esta.
2. **Se virar painel, o `custo_R` vai junto do nome.** Um radar que escreve "martelo" sem escrever
   "0,457 R de pedágio" está mentindo por omissão. Os números por padrão estão em
   `saida-pedagio.txt` e `saida-pedagio-a.txt`.
3. **Duas perguntas de método para a Astra**, além das quatro da KB-0081 §Segunda opinião: (i) Holm
   sobre 144 supõe o pior caso de dependência e os testes são fortemente correlacionados — o SPA
   *stepwise* de Hansen (o que Moser & Brauneis usam) seria mais poderoso e vale implementar? (ii) o
   portão de raridade em 30/10 está protegendo do artefato ou está escondendo os padrões de três
   barras, justamente os únicos com economia viável?
4. **O buraco de dado que impede a próxima pergunta:** 1 h precisa de 6–12 meses e os mercados fora
   dos 16 param em ~9 dias. `infra/scripts/request_backfill.py` é o caminho, e é uma decisão de
   quota, não de código.
5. **A KB-0081 é rascunho** em `.claude/state/exp-drafts/`, para a Sexta-feira arquivar em
   `obsidian/11-KNOWLEDGE/`. Não editei `obsidian/**`.
