---
tags: [knowledge, nota, memecoins, momentum, reversao]
tema: meme coins / momentum vs reversão e a população do Lab
fonte: medição própria — agent_signals e signal_outcomes da VPS
fonte_url: —
lido_em: 2026-09-06
evidencia: replicado (SQL colado), **abaixo do limiar editorial** — inconclusivo por construção
hipotese_testavel: sim, só diagnóstico
astra: discorda em parte (título e duas explicações retiradas)
---

# A coorte de memes não se distingue do resto

> **Esta nota mudou de nome depois da revisão.** Ela se chamava "A população do Lab já é meme", e a
> Astra derrubou o título com o meu próprio número: as coortes A e B somam **92 de 978 sinais** —
> cerca de 9%. "Majoritariamente altcoins" se sustenta; "majoritariamente memes" não. O arquivo foi
> renomeado para `KB-0065-a-coorte-de-memes-nao-se-distingue-do-resto`.

## O que afirma

A pergunta do brief era se meme coins são "mais momentum ou mais reversão" que o resto do universo.
Com a amostra separada por estratégia — que é como ela tem de ser lida —, **a coorte de memes não se
distingue do resto do universo em nenhuma das duas estratégias**, e as majors se distinguem das duas.

E o que **se** distingue não é a coorte: é a estratégia. A `momentum_v1` e a `volume_anomaly_v1` têm
geometrias de risco diferentes o bastante para que somá-las numa tabela só produza uma comparação
sem sentido — foi o que a minha primeira versão fez.

Tudo abaixo está **abaixo do limiar editorial** dos 100 outcomes e 30 dias. Nada aqui é resultado.

## Onde foi mostrado

**Quantos sinais cada coorte produz** (1.009 sinais desde 03:40 UTC de 2026-09-06, ~15 h; o `JOIN`
com `is_monitored` cobre 982 deles — os outros 27 estão em mercados que saíram do universo,
[[KB-0062-o-primeiro-dia-que-nao-conseguimos-ver]]):

```
      grupo       | mercados_no_grupo | sinais | mercados_com_sinal | sinais_por_mercado
------------------+-------------------+--------+--------------------+--------------------
 A_meme           |                21 |     84 |                 18 |               4.00
 B_meme_nao_ascii |                 5 |      8 |                  3 |               1.60
 C_btc            |                 1 |      1 |                  1 |               1.00
 D_majors         |                23 |     71 |                 21 |               3.09
 E_resto          |               150 |    814 |                133 |               5.43
```

**As memes não são a coorte mais prolífica** (4,00 por mercado contra 5,43 do resto). Ressalva de
denominador, da Astra: dividir pelo número **atual** de mercados mistura tempos de exposição
diferentes — o denominador correto seria avaliações elegíveis ou tempo elegível, e não é o que está
acima.

**Resultados, agora separados por estratégia** — e é esta a tabela que vale, não a que eu tinha
publicado misturada. Note a coluna `com_r`: o `r_multiple` pode ser nulo quando o funding não é
apurável (`services/strategy-worker/hunter_strategy_worker/settle.py:83`), então **`n` não é o
denominador de `r_medio`**.

```
   estrategia   |  grupo   |  resultado  |  n  | com_r | r_medio
----------------+----------+-------------+-----+-------+---------
 Momentum       | A_meme   | invalidated |  11 |     8 | -0.4560
 Momentum       | A_meme   | stop        |   4 |     3 | -1.1305
 Momentum       | A_meme   | target      |   6 |     5 |  0.7364
 Momentum       | A_meme   | open        |   2 |     0 |
 Momentum       | D_majors | invalidated |  11 |    11 | -0.6531
 Momentum       | D_majors | stop        |  12 |    12 | -1.1730
 Momentum       | D_majors | target      |   6 |     6 |  0.7863
 Momentum       | E_resto  | invalidated |  91 |    80 | -0.5509
 Momentum       | E_resto  | stop        |  59 |    54 | -1.1049
 Momentum       | E_resto  | target      |  96 |    78 |  0.7967
 Momentum       | E_resto  | open        |  14 |     0 |
 Volume Anomaly | A_meme   | invalidated |  23 |    19 | -0.7515
 Volume Anomaly | A_meme   | stop        |  17 |    17 | -1.1902
 Volume Anomaly | A_meme   | target      |  17 |    14 |  1.5222
 Volume Anomaly | A_meme   | expired     |   1 |     0 |
 Volume Anomaly | A_meme   | open        |   4 |     0 |
 Volume Anomaly | D_majors | invalidated |  23 |    22 | -0.8844
 Volume Anomaly | D_majors | stop        |   9 |     9 | -1.4964
 Volume Anomaly | D_majors | target      |  10 |     8 |  0.9743
 Volume Anomaly | E_resto  | invalidated | 215 |   200 | -0.6944
 Volume Anomaly | E_resto  | stop        | 182 |   171 | -1.3006
 Volume Anomaly | E_resto  | target      | 151 |   132 |  1.4548
 Volume Anomaly | E_resto  | expired     |  15 |     8 |  1.7874
```

**Taxa de alvo entre toques resolvidos**, alvo ÷ (alvo + stop), por estratégia:

| | memes (A) | majors | resto |
|---|---|---|---|
| Momentum | 6/10 = 60,0% | 6/18 = 33,3% | 96/155 = 61,9% |
| Volume Anomaly | 17/34 = 50,0% | 10/19 = 52,6% | 151/333 = 45,3% |

**Dentro de cada estratégia, memes e resto ficam a poucos pontos de distância, com 10 e 34 toques
resolvidos na coorte de memes.** Isso não decide nada, e é exatamente por isso que a nota mudou de
conclusão: a diferença que a tabela misturada sugeria era composição de estratégias, não
comportamento de coorte.

**A separação também revela por que misturar era pior do que eu tinha admitido.** O `r_medio` no
alvo da `momentum_v1` fica em 0,74-0,80 nas três coortes, e o da `volume_anomaly_v1` em 0,97-1,52.
Não é coorte: é geometria. O stop da `volume_anomaly_v1` é a **mínima da barra**
(`volume_anomaly_v1.py:183`), enquanto o da `momentum_v1` é 1,5 ATR (`momentum_v1.py:217`) — dois
riscos iniciais completamente diferentes, e portanto dois "R" diferentes. Achado da Astra.

## Como mediríamos aqui

Três coisas precisam existir antes de qualquer comparação entre coortes valer:

1. **Os 27 sinais de mercados que saíram** têm de entrar, em vez de sumirem no `JOIN` com
   `is_monitored`.
2. **A concentração temporal** (`D-CONC` da sexta rodada,
   [[KB-0051-tres-barreiras-mais-uma-e-a-amostra-que-nao-e-independente]]) tem de estar medida — cem
   altcoins reagindo ao mesmo movimento do BTC não são cem observações, e a
   [[KB-0060-correlacao-com-o-btc-e-a-meme-season]] mediu beta mediano de 2,80 nas memes.
3. **Um grupo de comparação condicionado** (a `L5`,
   [[KB-0049-walk-forward-que-nao-temos-e-o-nulo-que-nunca-calculamos]]). Sem ele, taxa de alvo não
   distingue comportamento de geometria.

## Hipótese testável no Lab

**`D-MEME-POP` (diagnóstico, roda hoje):** o retrato completo por **estratégia/versão × coorte**, com
todos os denominadores da regra do plantão (emitidos · pendentes · entradas · não entradas por
motivo · ativos · alvo · stop · expirados · invalidados · censurados por motivo · mercados distintos
· dias distintos), **incluindo os mercados desmonitorados**, com `count(r_multiple)` ao lado de cada
média, e com custos em R e geometria efetiva publicados junto. É o que esta nota tentou fazer, feito
direito, e é o desenho que a Astra escreveu.

**`D-MEME-ATRPAR` (diagnóstico, roda hoje):** a mesma taxa de alvo pareada por decil de `atr_pct` no
instante da decisão, dentro de cada estratégia. **Com a leitura corrigida:** se a diferença sumir ao
condicionar por volatilidade, isso **não demonstra** que "meme" é redundante — ausência de diferença
detectada numa amostra pequena não é demonstração de redundância (correção da Astra). No máximo,
diminui a prioridade.

**O que esta nota explicitamente NÃO propõe: nenhum braço de estratégia por coorte de meme.** Nem
"só memes", nem "sem memes", nem parâmetro diferente por coorte. Dez toques resolvidos na
`momentum_v1`; a marcação é julgamento meu
([[KB-0056-meme-coin-como-ativo-e-o-rotulo-que-nao-e-medida]]); e os confundidores abaixo tornam
qualquer resultado atribuível a várias causas ao mesmo tempo.

## Por que pode falhar

- **Dez e trinta e quatro toques resolvidos** nas duas estratégias, em **quinze horas** e um dia
  distinto. O limiar editorial é 100 outcomes **e** 30 dias. Inconclusivo por construção.
- **Duas explicações minhas foram retiradas inteiras pela revisão, e as duas eram plausíveis:**
  1. **"O `r_medio` no alvo acima de 1 é gap favorável atravessando a barreira."** Falso: o
     simulador credita **apenas `target1`** mesmo quando a abertura passa dele
     (`walker.py:73,157`). Um `R > 1` vem de entrada abaixo da referência, da geometria da
     `volume_anomaly_v1` ou de funding — e a fórmula divide pelo risco da **entrada efetiva**, não
     pelo ATR nominal (`pricing.py:74`).
  2. **"O confundidor de ATR é de primeira ordem: coorte com ATR maior tem barreiras mais largas em
     preço e horizonte igual em tempo."** Também falso como estava: se movimentos **e** barreiras
     escalam com a volatilidade, o processo em unidades de ATR preserva aproximadamente tempos e
     probabilidades de toque. Barreira maior em preço **não** implica maior distância em tempo. O
     efeito que sobra anda na direção contrária ao que eu disse: **custo fixo em bps pesa menos em R
     quando o risco percentual é maior**, o que aproxima o stop líquido de −1 e melhora o alvo
     líquido **sem vantagem comportamental nenhuma**. Isso, sim, é um mecanismo mecânico que pode
     explicar diferenças entre coortes de ATR diferente.
- **A amostra é a mesma que gerou a suspeita.** Conta como inspeção, entra no
  [[Registro de Tentativas]], e nada pode ser confirmado nela
  ([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]).
- **Contagens a reconciliar:** 978 (soma da tabela por estratégia × coorte) contra 982 (sinais em
  mercados monitorados) contra 1.009 (total). A tabela de sinais foi lida alguns minutos antes das
  outras, e o Lab continuou emitindo. **Declarar o corte temporal por consulta é requisito do
  `D-MEME-POP`**, e não fazê-lo aqui é limitação desta nota.
- **Observações não independentes**, e a `D-CONC` que mediria isso ainda não rodou.

## Segunda opinião (Astra)

Revisão de 2026-09-06 (`.claude/state/astra-review-KB-0062-0065-memecoins.md`). Ela **derrubou o
título e duas explicações**, e a nota foi reescrita inteira:

1. **O título estava errado** — 92 de 978 sinais são meme; "majoritariamente altcoins" se sustenta,
   "majoritariamente memes" não. Arquivo renomeado.
2. **Mostrou que misturar as estratégias era pior do que eu declarei**, porque o stop da
   `volume_anomaly_v1` é a mínima da barra e o da `momentum_v1` é 1,5 ATR — riscos iniciais
   diferentes, "R" diferentes. Confirmou que a separação é recuperável (`agents.py:108,153`), e eu
   refiz a medição.
3. **Retirou a explicação por gap favorável** (`walker.py:73,157`: só `target1` é creditado).
4. **Retirou o confundidor de ATR como "quase determinante"** e apontou o efeito que anda na direção
   contrária (custo fixo em bps pesando menos em R quando o risco percentual é maior).
5. **Retirou "sumiu ao parear por ATR, logo meme não acrescenta informação"** — ausência de
   diferença detectada em amostra pequena não demonstra redundância.
6. **Exigiu `count(r_multiple)` ao lado das médias** (`settle.py:83`) e a reconciliação de 978 × 982
   × 1.009 com o corte temporal declarado por consulta.
7. **Concordou** que comparação de coortes não responde sozinha "momentum ou reversão", e que não há
   base aqui para ativar variante nem declarar vantagem.

## Relacionados

[[KB-0056-meme-coin-como-ativo-e-o-rotulo-que-nao-e-medida]] ·
[[KB-0057-a-volatilidade-das-memes-e-o-piso-que-bane-o-btc]] ·
[[KB-0062-o-primeiro-dia-que-nao-conseguimos-ver]] ·
[[KB-0046-r-multiplos-e-o-r-que-a-simetria-esconde]] ·
[[KB-0051-tres-barreiras-mais-uma-e-a-amostra-que-nao-e-independente]] ·
[[KB-0049-walk-forward-que-nao-temos-e-o-nulo-que-nunca-calculamos]] ·
[[EXP-0001-momentum-v1]] · [[EXP-0002-volume-anomaly-v1]] · [[Strategy Backlog]] · [[Index]]
