---
tags: [knowledge, nota, analise-tecnica, candlestick, padroes, medicao-propria, m3]
tema: "padrões de candlestick medidos no nosso dado — 217 mercados monitorados, 16 com 31 d de histórico, 15 m e 1 h, retorno futuro contra baseline pareada"
fonte: "medição própria sobre a exportação somente-leitura da VPS (`candles` de 1 min `is_final`, dobradas em SQL com exigência de completude); SQL verbatim em `infra/scripts/sql/research/2026-09-09-t355-*.sql`; protótipo e bootstrap em `.claude/state/exp-drafts/t355/`"
fonte_url: "—"
lido_em: 2026-09-09
as_of: 2026-09-08T00:00:00Z
read_at: 2026-09-09T02:58:29Z
evidencia: "medição própria sobre 58 224 barras utilizáveis (46 880 de 15 m + 11 344 de 1 h) em 16 perpétuas da Binance × 31 dias, com dois conjuntos independentes de definição, baseline pareada por (mercado, hora do dia), bootstrap de blocos por dia e Holm sobre a união das duas famílias"
hipotese_testavel: sim
astra: pendente
status: rascunho
owner: sexta-feira
updated: 2026-09-09
confiança: "?"
---

# Candlestick no nosso dado: nada sobrevive, e o único que sobrevive tem o sinal errado

> **RASCUNHO do quant-engineer (T3.55b, 2026-09-09).** Escrito em `.claude/state/exp-drafts/`
> para a Sexta-feira arquivar em `obsidian/11-KNOWLEDGE/`. **Nada foi commitado, nada de produção
> foi tocado**: nenhum arquivo de `packages/`, nenhum `code_ref`, nenhum `feature_set_version`.
> O protótipo mora em `.claude/state/exp-drafts/t355/` e não é importado por
> `hunter_core.strategies.*`.
> Par desta nota: [[KB-0080-candlestick-evidencia]] (o que a literatura diz).
> **Corte (`as_of`): velas de 1 min com `open_time < 2026-09-08T00:00Z`.**
> **Leitura (`read_at`): 2026-09-09 02:58:29Z = 08/09 23:58 Brasília**, numa transação
> `repeatable read read only`, para que todas as tabelas compartilhem um snapshot.

## O que afirma

Sobre 31 dias de 16 perpétuas da Binance, em 15 m e 1 h, **nenhum dos 14 padrões clássicos
definidos pela parte (b) carrega informação direcional que sobreviva à correção de Holm** — nem
sozinho, nem encostado numa linha de tendência, nem cortado pelo regime do BTC. Repetindo a medição
com as **outras** definições (as 18 da [[KB-0080]] §7, constantes diferentes, contexto de tendência
por EMA10), o resultado é o mesmo com **uma** exceção: o *marubozu de baixa* em 1 h prevê alta —
`+0,20 ATR` na hora seguinte, ao contrário do que o padrão afirma —, e essa reversão, operada ao
contrário e com stop de 1 ATR, rende **+0,005 R por operação** (IC95 `[−0,104; +0,112]`), isto é,
**exatamente o pedágio e mais nada**.

A frase que resume: *não é que os padrões percam para o custo; é que, antes do custo, eles não
dizem nada — e o único que diz alguma coisa diz o contrário do que está escrito no livro.*

## Como foi medido (o protocolo, congelado antes dos números)

1. **Dado.** `candles` de 1 min `is_final`, `2026-08-08T00:00Z → 2026-09-08T00:00Z`, dobradas
   **no servidor** em baldes de 15 m e 1 h com **exigência de completude** (`date_bin` desde a
   época, `count(*) = 15` / `= 60` e último minuto exatamente em `bucket + n−1 min`). Balde
   incompleto não é exportado — não existe barra "quase fechada". SQL:
   `2026-09-09-t355-q01-barras.sql`. Saíram **2 961 baldes de 15 m e 740 de 1 h por mercado**,
   contra 2 976 e 744 possíveis: os que faltam são as ~3 h 45 min iniciais da janela, antes de o
   coletor existir, e por isso a série de cada (mercado, timeframe) é **uma corrida contígua só**
   (provado por `test_pipeline.py::test_a_serie_exportada_e_contigua`).
2. **Universo.** O brief pedia "os 20 perpétuos mais líquidos + os 4 de replay". **Só 16 têm os 31
   dias**: `q00` mostra que do 5º ao 40º lugar em liquidez quase todo mundo tem 22–30 % de
   cobertura (backfill de ~9 dias). Os 16 com 99,53 % são exatamente BTC, ETH, ZEC, SOL, XRP, BNB,
   DOGE, SUI, NEAR, UNI, ARB, TAO, LINK, DASH, PROM, SAHARA — e contêm os quatro de replay
   (ETH, SOL, XRP, DOGE). **É o universo, e é uma limitação declarada, não uma escolha.**
3. **Detecção no fechamento, nunca antes.** `detectar(bars, atr, i)` lê `bars[: i+1]`. Um padrão de
   três barras terminando em `i` é conhecido no fechamento de `i`. A régua é `ATR[i−n]` — o ATR
   fechado **antes** da primeira barra do padrão —, porque `ATR[i]` deixaria a barra inflar a
   própria régua (um marubozu de 3 ATRs engorda o ATR e reaparece como um de 1,8).
4. **Retorno futuro** em 1, 4 e 16 barras, medido em ATRs do fechamento da decisão, com o sinal do
   padrão (`+1` long, `−1` short). As 16 últimas barras de cada corrida saem do estudo — do padrão
   **e** da baseline.
5. **Baseline pareada**: média do mesmo retorno na célula (mercado, hora do dia UTC) sobre as barras
   **sem** aquele padrão, subtraída linha a linha.
6. **Bootstrap de blocos por dia** (`t342-blocos/blocos.py`, **reusado sem uma linha de alteração**),
   10 000 reamostragens: reamostram-se dias inteiros com reposição e, dentro do dia, **todos os
   mercados vão juntos**, porque em 16 perpétuas correlacionadas o choque é do dia ([[KB-0010]]).
7. **Holm** sobre a família declarada, com portão de raridade: rótulo com menos de 30 ocorrências ou
   presente em menos de 10 dias distintos **não recebe IC** (recebe `raro`) — com uma ou duas
   ocorrências o bootstrap degenera e cospe `p = 0,0001` sobre uma observação só.

## Os números

### 1. Quantas vezes cada padrão aparece (a frequência antes de qualquer retorno)

58 224 barras utilizáveis: 46 880 de 15 m e 11 344 de 1 h. Definições da parte (b):

| padrão | 15 m | 1 h | | padrão | 15 m | 1 h |
|---|---:|---:|---|---|---:|---:|
| doji | 4 220 | 1 048 | | harami_baixa | 374 | 84 |
| engolfo_baixa | 740 | 214 | | harami_alta | 219 | 49 |
| martelo | 689 | 132 | | tres_soldados | 91 | **11** |
| marubozu_alta | 683 | 101 | | estrela_noite | 77 | **22** |
| engolfo_alta | 666 | 135 | | tres_corvos | 59 | **0** |
| estrela_cadente | 655 | 166 | | estrela_manha | 53 | **9** |
| enforcado | 549 | 152 | | marubozu_baixa | 531 | 87 |

**Os padrões de três barras praticamente não existem em 1 h** (0 a 22 ocorrências em 31 dias × 16
mercados). Em negrito, os que o portão de raridade tirou da família. É o primeiro achado da nota e
não depende de nenhum retorno: *não há amostra para medir estrela da manhã em 1 h nesta casa.*

### 2. O contraste principal — `saida-estatistica.txt`

84 rótulos-horizonte medidos, 12 raros, **família de Holm = 72**. **Nenhum sobrevive** (nem com
Holm por horizonte, m = 24 cada). As cinco maiores evidências brutas, todas mortas pela correção:

| padrão | tf | h | n | Δ (ATR) | IC95 | p bruto | Holm |
|---|---|---:|---:|---:|---|---:|---:|
| marubozu_baixa | 1 h | 1 | 87 | **−0,1562** | [−0,2844; −0,0309] | 0,0142 | 1,000 |
| enforcado | 15 m | 4 | 549 | **−0,1592** | [−0,3138; −0,0212] | 0,0202 | 1,000 |
| doji | 15 m | 1 | 4 220 | **−0,0243** | [−0,0472; −0,0017] | 0,0362 | 1,000 |
| tres_corvos | 15 m | 4 | 59 | +0,3090 | [−0,0117; +0,6578] | 0,0572 | 1,000 |
| engolfo_alta | 15 m | 4 | 666 | −0,1148 | [−0,2370; +0,0152] | 0,0836 | 1,000 |

Dos 81 contrastes com `n > 0`, **46 (56,8 %) têm Δ negativo** e **5 têm `p < 0,05`** — contra ~4
esperados por acaso em 81 testes. **Os cinco são negativos.** Sob a hipótese nula, cinco em cinco
com o mesmo sinal é 1 em 32; é sugestivo de uma reversão sistemática *contra* a direção do padrão,
e não é evidência de nada sozinho.

### 3. O confronto literal com o `blocos.py` — `saida-confronto.txt`

A tabela usa um atalho por estatística suficiente (soma e contagem por dia) porque 84 × 10 000 ×
47 000 linhas é meia hora de concatenação. Ele consome a **mesma** sequência do mesmo gerador na
mesma ordem e por isso devolve os mesmos números — provado em população sintética
(`test_bootstrap.py`) e **no dado real**:

```
contraste               fonte       n_var   exp_pai   exp_var     delta   IC baixo   IC alto    seg
tres_soldados|1h|h1     atalho         11  -0.00065  -0.66853  -0.66788   -1.32320  -0.13605    0.4
tres_soldados|1h|h1     blocos.py      11  -0.00065  -0.66853  -0.66788   -1.32320  -0.13605    1.1
                        identicos
doji|15m|h1             atalho       4220  -0.00241  -0.02674  -0.02433   -0.04717  -0.00166    0.6
doji|15m|h1             blocos.py    4220  -0.00241  -0.02674  -0.02433   -0.04717  -0.00166    4.2
                        identicos
```

### 4. O nulo é medido, não é cegueira — `saida-controle.txt`

| controle | tf | n | Δ (ATR) | IC95 | p |
|---|---|---:|---:|---|---:|
| trapaça que lê a barra seguinte | 15 m | 23 092 | **+0,5047** | [+0,4739; +0,5412] | 0,0001 |
| a mesma trapaça com `n` de martelo | 15 m | 689 | **+0,9212** | [+0,8531; +0,9926] | 0,0001 |
| marca sorteada, mesmo `n` | 15 m | 689 | −0,0185 | [−0,1366; +0,1043] | 0,7538 |
| trapaça que lê a barra seguinte | 1 h | 5 787 | +0,4954 | [+0,4254; +0,5715] | 0,0001 |
| a mesma trapaça com `n` de martelo | 1 h | 132 | +1,0412 | [+0,7350; +1,3638] | 0,0001 |
| marca sorteada, mesmo `n` | 1 h | 132 | +0,0653 | [−0,2174; +0,3254] | 0,6218 |

Com **689 ocorrências** — o `n` de um martelo de 15 m — a máquina enxerga um efeito de 0,92 ATR com
IC de largura 0,14. Ela não está cega.

E a **resolução contra o pedágio**: metade da largura do IC de cada padrão, dividida pela distância
de stop natural dele, é o menor efeito em R que este estudo distinguiria de zero. Em **12 dos 14
padrões de 15 m** essa resolução é **menor** que o `custo_R` que o próprio padrão cobra — ou seja,
uma vantagem grande o bastante para pagar o pedágio teria aparecido. Exemplos: `engolfo_alta` 15 m
resolve 0,101 R contra custo 0,335 R; `doji` 15 m resolve 0,096 R contra 0,667 R. **Em 1 h só o
doji tem essa resolução** — 31 dias não dão amostra de 1 h, e isso é limite do estudo, não do
padrão.

### 5. A lente de pedágio (KB-0076) — `saida-pedagio.txt`

`custo_R = 0,0020 / risco%`, com `risco% = |entrada − stop| / entrada` e o stop na **invalidação
natural** do padrão. Saída por horizonte de 4 barras, **sem caminho intrabarra** (não é backtest).

| padrão | tf | n | stop (ATR) | risco % | **custo_R** | R bruto | R líquido | IC95 |
|---|---|---:|---:|---:|---:|---:|---:|---|
| tres_soldados | 15 m | 91 | 2,78 | 1,277 | **0,157** | +0,101 | −0,233 | [−0,554; +0,038] |
| tres_corvos | 15 m | 59 | 2,43 | 1,460 | **0,137** | +0,152 | −0,123 | [−0,343; +0,060] |
| estrela_manha | 15 m | 53 | 1,35 | 0,697 | 0,287 | +0,269 | −0,101 | [−0,334; +0,122] |
| engolfo_alta | 15 m | 666 | 1,25 | 0,598 | 0,335 | −0,007 | −0,473 | [−0,587; −0,350] |
| martelo | 15 m | 689 | 0,81 | 0,437 | 0,457 | +0,135 | −0,526 | [−0,785; −0,279] |
| doji | 15 m | 4 220 | 0,56 | 0,300 | **0,667** | +0,057 | −0,853 | [−1,126; −0,582] |
| **enforcado** | 15 m | 511 | **0,13** | **0,072** | **2,779** | — | — | (38 com `stop = entrada`) |
| tres_soldados | 1 h | 11 | 4,75 | 5,948 | **0,034** | +0,074 | +0,026 | [−0,361; +0,302] |
| marubozu_alta | 1 h | 101 | 1,81 | 1,842 | 0,109 | +0,110 | −0,035 | [−0,387; +0,237] |
| engolfo_alta | 1 h | 135 | 1,09 | 1,142 | 0,175 | +0,282 | **+0,049** | [−0,133; +0,251] |

**O achado estrutural desta seção não é sobre vantagem, é sobre geometria: o enforcado não tem
invalidação.** A forma dele é corpo pequeno no topo da barra com pavio inferior longo, então o
fechamento fica colado na máxima — que é exatamente onde o stop clássico vai. Mediana de **0,13 ATR
de distância**, `risco% = 0,072 %`, **`custo_R = 2,78 R`**, e em **38 das 549 ocorrências de 15 m o
stop é o próprio preço de entrada** (operação que não existe). Um padrão cujo stop natural custa
2,78 R por operação não é um candidato ruim: é um candidato **impossível**, e nenhum tamanho de
vantagem o salva. O mesmo vale, em menor grau, para o doji (0,56 ATR → 0,667 R).

No outro extremo, os padrões de **três barras** são os únicos com pedágio civilizado (0,034 a
0,157 R) porque a invalidação natural deles é larga — e são justamente os que quase não ocorrem.
*A frequência e a economia do padrão são inversas.*

### 6. Os recortes condicionais — `saida-condicional.txt`

Horizonte de 4 barras declarado antes; tolerância de 0,25 ATR (o `tolerance_atr` do `DEFAULT_PARAMS`
da T3.34, a mesma régua que decide se um toque é toque); linhas do `tl_scan` **congelado**, janela
de 96 baldes contíguos terminando na barra, corte aplicado uma vez no topo — o mesmo que
`render_operations.py` §3 usa. Padrões agrupados por direção (o doji fica de fora: não afirma
direção). Família de 8.

| fatia | tf | n padrão | Δ (ATR) | IC95 | p | Holm(8) |
|---|---|---:|---:|---|---:|---:|
| encostado na linha | 15 m | 476 | **+0,0642** | [−0,0796; +0,2195] | 0,406 | 1,000 |
| solto | 15 m | 4 509 | −0,0424 | [−0,1016; +0,0172] | 0,170 | 1,000 |
| alinhado ao regime | 15 m | 698 | −0,0558 | [−0,2888; +0,1784] | 0,688 | 1,000 |
| contra o regime | 15 m | 749 | −0,0080 | [−0,1347; +0,1196] | 0,965 | 1,000 |
| encostado na linha | 1 h | 97 | −0,0537 | [−0,3766; +0,3262] | 0,747 | 1,000 |
| solto | 1 h | 895 | +0,0312 | [−0,2475; +0,2996] | 0,798 | 1,000 |
| alinhado ao regime | 1 h | 146 | +0,0853 | [−0,2447; +0,5248] | 0,599 | 1,000 |
| contra o regime | 1 h | 159 | −0,2965 | [−0,8064; +0,0590] | 0,109 | 0,872 |

Nada. A única célula com direção interessante — padrão encostado numa linha em 15 m, `+0,064` contra
`−0,042` de quem está solto — tem IC que cobre zero com folga; **a diferença entre as duas fatias é
menor que a largura de qualquer uma delas**. Base de comparação: **10,9 % das barras de 15 m estão a
≤ 0,25 ATR de um suporte** e 9,7 % de uma resistência, então "encostado na linha" não é um evento
raro que a amostra não alcance — é um décimo da fita.

Sobre o regime: `market_regimes` cobre a janela (756 horas), mas com **206 `UNKNOWN`** e só **55
`BTC_BEAR`** contra 150 `BTC_BULL` — 31 dias contêm um regime de baixa e meio, o que por si só
limita o que "alinhado ao regime" pode significar.

### 7. O segundo conjunto de definições — `saida-kb0080.txt`

A parte (a) desta task ficou pronta às **00:16 Brasília**, depois de a varredura da (b) ter
começado às 23:58. Em vez de trocar as constantes e publicar um número só, rodei **as duas**:
`padroes_v1` (14 rótulos, contexto por variação em ATR) e `padroes_kb0080_v1` (18 rótulos, contexto
por EMA10 com inclinação — a régua de Marshall —, amplitude mínima 0,8 ATR em vez de 0,5, marubozu
por corpo em ATR, harami estritamente dentro, mais martelo invertido e três-dentro).

Efeito de trocar as constantes, medido: `martelo` sai de 689 para 502 ocorrências em 15 m,
`enforcado` de 549 para 303, `engolfo_alta` de 666 para **1 013** (a (a) não exige contexto tão
forte), `marubozu_alta` de 683 para 758. **É outra medição, não um ajuste da mesma.**

Resultado: 108 rótulos-horizonte, 36 raros, família de 72, e **dois sobrevivem ao Holm daquele
braço**:

| rótulo | tf | h | n | Δ (ATR) | IC95 | p | Holm(72) |
|---|---|---:|---:|---:|---|---:|---:|
| `a_doji_baixa` | 15 m | 1 | 1 931 | **+0,0527** | [+0,0232; +0,0843] | 0,0006 | 0,043 |
| `a_marubozu_baixa` | 1 h | 1 | 90 | **−0,2021** | [−0,3011; −0,1011] | 0,0001 | 0,007 |

Os dois braços **concordam no sinal**: o `doji` da (b), que agrega os dois contextos com sinal
`+1`, dá `−0,0243` — que é o mesmo fato do `a_doji_baixa` com o sinal virado (doji em tendência de
alta cai); e o `marubozu_baixa` da (b) dá `−0,1562` contra `−0,2021` da (a). **Não é um artefato de
constante.**

### 8. Holm conjunto e a economia do sobrevivente — `saida-sobreviventes.txt`

Quem olhou os dois braços olhou **144 testes não-raros** sobre a mesma série. Corrigir cada braço
isolado subestima a busca. Sobre a união:

```
familia da parte (b): 72 | da KB-0080: 72 | uniao: 144
sobrevivem ao Holm conjunto (m=144, alfa 0,05): ['a/a_marubozu_baixa|1h|h1']
  a/a_marubozu_baixa|1h|h1       p=0.0001  Holm=0.0144
  a/a_doji_baixa|15m|h1          p=0.0006  Holm=0.0858
  b/marubozu_baixa|1h|h1         p=0.0142  Holm=1.0000
```

**Um sobrevivente em 144.** E ele tem o sinal errado: o marubozu de baixa afirma queda, e o mercado
sobe 0,20 ATR na hora seguinte. A economia dele:

| leitura | n | Δ (ATR) | ATR% | stop nat. | custo nat. | R nat. | custo (stop 1 ATR) | **R líquido** | IC95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| como o livro manda (short) | 90 | −0,2037 | 1,005 % | 1,30 ATR | 0,155 R | −0,157 R | 0,199 R | **−0,403 R** | [−0,510; −0,294] |
| **ao contrário (long)** | 90 | +0,2037 | 1,005 % | — | — | +0,157 R | 0,199 R | **+0,005 R** | [−0,104; +0,112] |

Ler o marubozu de baixa como o livro manda custa **0,40 R por operação**, com IC que não chega perto
de zero. Lê-lo ao contrário rende **meio milésimo de R** — o pedágio come a vantagem inteira e o IC
cobre zero dos dois lados. E note que a leitura invertida usa um stop **declarado** de 1 ATR, não a
invalidação natural: a invalidação natural de "comprar depois de um marubozu de baixa" fica abaixo
da mínima da barra, que num marubozu está a ~0,1 amplitude do fechamento — de novo o problema do
enforcado.

## Por que pode falhar (o que eu faria diferente com mais tempo)

1. **31 dias e 16 mercados.** Não é amostra para 1 h: quatro dos catorze padrões nem chegam a 30
   ocorrências ali. Um estudo honesto de 1 h precisa de 6 a 12 meses, e o `candles` da VPS não os
   tem — o backfill dos outros mercados parou em ~9 dias.
2. **Uma janela, um regime e meio.** 150 horas de `BTC_BULL` contra 55 de `BTC_BEAR`. Qualquer
   afirmação sobre "funciona em queda" está fora do alcance deste dado.
3. **Saída por horizonte, sem caminho intrabarra.** A lente de pedágio supõe que a operação vive as
   4 barras. Uma que teria batido o stop no meio aparece aqui pelo fechamento. É deliberado (esta
   task não escreve produção e um backtest de verdade reusa `Strategy`/`RiskEngine`/
   `PaperExecutionAdapter`), mas torna o R bruto **otimista** para os padrões de stop curto.
4. **A baseline é fixada na amostra inteira** e o erro de estimá-la não entra no bootstrap. Em 15 m
   a célula tem ~124 barras e é ruído de segunda ordem; em 1 h tem ~31 e a ressalva vale.
5. **Duas famílias, e a segunda escolhida depois de a primeira existir.** O Holm conjunto sobre 144
   corrige a busca *que eu fiz*, não a busca que a literatura já fez sobre estes mesmos padrões —
   e ela é enorme ([[KB-0080]] §2). O prior verdadeiro é pior que o meu p.
6. **Nada disto testa o que um humano faz com uma vela.** Um trader olha o padrão *dentro* de um
   contexto que ele mesmo escolhe. O recorte por linha e por regime é a aproximação mais próxima que
   eu sei escrever de forma determinística, e ela também não achou nada.

## Portão de desenho (C1–C8) — **rascunho, autoavaliação**

**Declaração de processo:** escrito pelo mesmo quant que fez a medição, no mesmo dia. É
autoavaliação, não revisão viva. A revisão da Astra está **pendente**.

| # | Critério | Veredito | Justificativa |
|---|---|---|---|
| C1 | Plausibilidade da vantagem | **FAIL** | O mecanismo declarado ("a vela mostra quem ganhou a barra") não sobreviveu ao teste na fonte: 144 testes, um sobrevivente, e com o **sinal invertido**. A literatura concorda ([[KB-0080]] §6: nada nas grandes em cripto diário; o único "sim" intradiário não foi lido). Não há hipótese a promover |
| C2 | Risco de sobreajuste | **FAIL se alguém insistir** | Foram medidos 32 rótulos em 2 timeframes e 3 horizontes com **duas** parametrizações. Escolher agora o `a_marubozu_baixa` invertido é escolher o máximo de 144 — exatamente o data snooping que [[KB-0003]] descreve. Só valeria com **janela nova** (out-of-sample de verdade) |
| C3 | Adequação da amostra | **FAIL em 1 h, REVISE em 15 m** | Em 1 h: 0 a 22 ocorrências para quatro padrões, e o portão de raridade tirou 12 dos 84 rótulos. Em 15 m há amostra (531 a 4 220), e é lá que o nulo é informativo |
| C4 | Dependência de regime | **PASS por medição, com ressalva** | Foi medido (§6) e não mudou nada. Ressalva: 206 h de `UNKNOWN` e 55 de `BTC_BEAR` em 756 |
| C5 | Calibração das saídas | **FAIL** | A invalidação natural de metade dos padrões é curta demais para o pedágio: enforcado 0,13 ATR (`custo_R` 2,78, com 38 ocorrências de risco **zero**), doji 0,56 ATR (0,667 R), martelo 0,81 ATR (0,457 R). Só os de três barras têm stop civilizado, e são os que não ocorrem |
| C6 | Concentração de risco | **n/a** | `research_only`, sem carteira, sem ordens. Custo computacional medido: a varredura completa (59 216 barras de duas grades, `Decimal` do começo ao fim) leva **6,6 s**; o `tl_scan` em janela de 96 barras custa 7 ms/barra, e as 55 664 varreduras do recorte de linha levaram **7 min** |
| C7 | Realismo de execução | **PASS na hipótese, FAIL no resultado** | Mesmos 20 bps ida-e-volta das outras versões, mesma identidade da [[KB-0076]] verificada. O resultado é que os padrões não cabem nela |
| C8 | Qualidade da invalidação | **FAIL** | Ver C5. Além da distância, há o caso degenerado: `entrada == stop` em 38 enforcados de 15 m e 3 de 1 h. Uma invalidação que coincide com a entrada não é invalidação |

**Veredito do portão: `FAIL` — 2026-09-09, quant-engineer, autoavaliação.** Não há contrato a
abrir. Isto é **painel**, e há uma pergunta aberta sobre se merece nem isso (§ Relacionadas).

## Veredito (≤ 10 linhas)

1. **Nenhum dos 14 padrões da parte (b) carrega informação** que sobreviva a Holm em 72 testes
   não-raros; nem em 15 m, nem em 1 h, nem em 1, 4 ou 16 barras.
2. **O nulo é medido, não é cegueira:** com o `n` de um martelo, a mesma máquina enxerga um efeito
   plantado de 0,92 ATR (`p = 0,0001`), e em 12 dos 14 padrões de 15 m a resolução do estudo é
   melhor que o pedágio que o próprio padrão cobra.
3. **Encostar numa linha de tendência não muda nada** (Δ +0,064 contra −0,042 em 15 m, ICs que se
   sobrepõem inteiros), e **o regime do BTC também não**.
4. **Repetindo com as definições da [[KB-0080]] §7, o resultado se mantém**, com um único
   sobrevivente do Holm conjunto sobre 144: `marubozu de baixa` em 1 h, `Δ = −0,20 ATR`.
5. **Esse sobrevivente tem o sinal errado.** Operado como o livro manda: **−0,40 R** por operação.
   Operado ao contrário, com stop de 1 ATR: **+0,005 R**, IC `[−0,104; +0,112]` — o pedágio inteiro.
6. **O achado mais útil não é estatístico, é geométrico:** o enforcado e o doji **não têm
   invalidação** (0,13 e 0,56 ATR do fechamento), o que cobra 2,78 R e 0,67 R por operação. Nenhuma
   vantagem plausível paga isso.
7. **Padrão de três barras é economicamente viável e estatisticamente inexistente:** stop de 2,4 a
   4,8 ATR (pedágio 0,03 a 0,16 R) e 0 a 91 ocorrências em 31 dias × 16 mercados.
8. **Não há estratégia a contratar.** O portão C1–C8 sai `FAIL` em C1, C2, C3, C5, C7 e C8.
9. **Isto é painel**, e mesmo como painel precisa carregar o `custo_R` ao lado do nome do padrão —
   um radar que mostra "martelo" sem mostrar "0,457 R de pedágio" está mentindo por omissão.
10. **O que mudaria a resposta:** 6–12 meses de 1 h nos mesmos mercados, ou o artigo de Moser &
    Brauneis (2026) lido de verdade ([[KB-0080]] §2.7), que é a única evidência intradiária com
    correção de snooping e diz que harami e enforcado sobrevivem — o oposto do que eu medi.

## Segunda opinião (Astra)

Pendente. Quatro perguntas, nesta ordem:

1. **A baseline pareada é a certa?** (mercado, hora do dia UTC) sobre barras sem o padrão. A
   alternativa seria parear por bucket de ATR% ou por regime. Qual erra menos?
2. **Holm sobre 144 é severo demais ou de menos?** As séries dos dois braços são a **mesma** fita e
   os testes são fortemente correlacionados; Holm supõe o pior caso de dependência. SPA stepwise de
   Hansen (o que a Moser & Brauneis usa) seria mais poderoso — vale implementar?
3. **O portão de raridade em 30/10 é defensável** ou está escondendo os padrões de três barras,
   justamente os únicos com economia viável?
4. **A leitura invertida do marubozu** (`+0,005 R`) merece uma janela nova de teste ou é
   exatamente o tipo de coisa que a [[KB-0003]] manda descartar?

## Relacionadas

[[KB-0080-candlestick-evidencia]] (o par literatura desta nota) ·
[[KB-0076-por-que-perdemos-2026-09-08]] (a identidade `custo_R = 0,0020 / risco%`) ·
[[KB-0077-linhas-de-tendencia]] (o `tl_scan` congelado usado no recorte condicional) ·
[[KB-0003-rompimento-de-canal-e-data-snooping]] · [[KB-0010]] (bloco de dia) ·
[[KB-0078-o-radar-preve]] · [[Strategy Backlog]]
