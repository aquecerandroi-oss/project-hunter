---
tags: [knowledge, nota, memecoins, funding, perpetuos]
tema: meme coins / funding e posicionamento
fonte: medição própria — funding_rates da VPS (2.136 liquidações em 229 mercados na tabela; a análise por coorte cobre os 200 monitorados) + documentação de funding da Binance
fonte_url: https://www.binance.com/en/support/faq/detail/360033525031
lido_em: 2026-09-06
evidencia: replicado (SQL colado) + documentação
hipotese_testavel: sim
astra: pendente
---

# Funding em memes — a cadência antes do sentimento

## O que afirma

"Meme coin tem funding extremo" é uma das frases mais repetidas do mercado. Medi as **2.136 taxas de
funding efetivamente liquidadas** na VPS, e **por liquidação, nesta janela**, a coorte de memes é
**menos** extrema que o resto do universo: média do valor absoluto de **1,07 bps** contra **2,32
bps**, e a cauda negativa profunda (−64,8 bps) apareceu fora das memes.

E antes de qualquer leitura de sentimento vem um fato mecânico: **"funding por liquidação" não é uma
grandeza comparável entre mercados com cadências diferentes.** A taxa base da Binance é 0,01% por
ciclo de 8 h e 0,005% por ciclo de 4 h; um mercado que cobra 0,8 bps a cada hora tem taxa **horária
6,4 vezes maior** que outro cobrando 1 bps a cada 8 h — e ainda aparece oito vezes mais na amostra
de eventos. Comparar medianas por liquidação entre coortes de cadência diferente é comparar
contratos diferentes, e a correção de normalização é da Astra.

**Consequência, escrita antes dos números:** a frase "as memes têm funding menos extremo" vale como
**descrição por liquidação nesta janela**, e **não** como conclusão normalizada sobre memes.

## Onde foi mostrado

**Medição própria, VPS, 2026-09-06**, sobre a tabela `funding_rates` (taxa **liquidada**, não a
estimativa em formação — a distinção é a da [[KB-0019-o-que-a-nossa-funding-rate-mede-de-fato]]).

```sql
SELECT cls.grupo, count(*) AS liquidacoes, count(DISTINCT f.market_id) AS mercados,
  round((10000*percentile_cont(0.5) WITHIN GROUP (ORDER BY f.rate))::numeric,4) AS mediana_bps,
  round((10000*percentile_cont(0.05) WITHIN GROUP (ORDER BY f.rate))::numeric,4) AS p05_bps,
  round((10000*percentile_cont(0.95) WITHIN GROUP (ORDER BY f.rate))::numeric,4) AS p95_bps,
  round((10000*min(f.rate))::numeric,4) AS min_bps, round((10000*max(f.rate))::numeric,4) AS max_bps,
  round((100.0*count(*) FILTER (WHERE abs(f.rate) >= 0.0005)/count(*))::numeric,1) AS pct_acima_5bps,
  round((10000*avg(abs(f.rate)))::numeric,4) AS media_abs_bps
FROM funding_rates f JOIN cls ON cls.id = f.market_id GROUP BY 1 ORDER BY 1;
```

```
      grupo       | liquidacoes | mercados | mediana_bps | p05_bps | p95_bps | min_bps  | max_bps | pct_acima_5bps | media_abs_bps
------------------+-------------+----------+-------------+---------+---------+----------+---------+----------------+---------------
 A_meme           |         204 |       21 |      0.5000 |  0.3355 |  4.7822 |  -0.9817 |  9.9453 |            4.4 |        1.0722
 B_meme_nao_ascii |          47 |        5 |      1.1217 |  0.5000 |  7.0158 |   0.5000 | 19.1238 |            8.5 |        2.4447
 C_btc            |           6 |        1 |      0.2109 |  0.0141 |  0.3395 |  -0.0150 |  0.3589 |            0.0 |        0.1964
 D_majors         |         138 |       23 |      1.0000 | -0.4892 |  1.0556 |  -1.9851 | 15.7967 |            4.3 |        1.0808
 E_resto          |        1491 |      150 |      0.5000 | -8.0194 |  3.3645 | -64.8302 | 15.1404 |            9.8 |        2.3160
```

Três leituras, em ordem de importância:

1. **A mediana das memes (0,50 bps) é metade da mediana das majors (1,00 bps), e as duas coincidem
   exatamente com as taxas base das duas cadências.** Isso é **compatível** com a explicação de
   cadência; medi as contagens, não os intervalos, então a cadência de cada mercado é **inferida** a
   partir do número de liquidações em 45 h, e a parcela da diferença que ela explica **não foi
   medida** (eu tinha escrito "engole metade da diferença" — a razão entre medianas foi medida, a
   atribuição causal não).

```
      grupo       | mercados | min_liq | media_liq | max_liq | cadencia_4h_ou_menor | cadencia_8h
------------------+----------+---------+-----------+---------+----------------------+-------------
 A_meme           |       21 |       6 |      9.71 |      11 |                   16 |           4
 B_meme_nao_ascii |        5 |       3 |      9.40 |      11 |                    4 |           1
 C_btc            |        1 |       6 |      6.00 |       6 |                    0 |           1
 D_majors         |       23 |       6 |      6.00 |       6 |                    0 |          23
 E_resto          |      150 |       3 |      9.92 |      43 |                  106 |          40
```

   **Todas as 23 majors e o BTC liquidam a cada 8 h; 16 das 21 memes liquidam a cada 4 h ou menos.**
   Comparar medianas de funding entre grupos sem normalizar por cadência é comparar a taxa de
   contratos diferentes. Um mercado do `E_resto` teve **43 liquidações** em dois dias — cadência de
   1 h, que é o piso comprimido da Binance quando a taxa bate no teto
   ([[KB-0026-funding-num-horizonte-de-4h-e-o-vies-de-exclusao]]).

2. **O extremo observado ficou fora das memes.** O funding mais negativo do universo foi de
   **−64,8 bps** num mercado do `E_resto`; a meme mais negativa da coorte A ficou em **−0,98 bps**.
   E 9,8% das liquidações do resto passaram de 5 bps em módulo, contra 4,4% das memes.
   **Ressalva de tamanho de grupo (Astra):** comparar o **mínimo** de 21 mercados com o de 150
   favorece o grupo maior por construção. A fração acima de 5 bps não tem esse problema; o mínimo
   tem.

3. **A coorte B é a que mais parece com o folclore**: mediana 1,12 bps, máximo 19,1 bps, 8,5% acima
   de 5 bps, e **nenhuma taxa negativa** — todo mundo comprado, pagando para ficar. Cinco mercados
   novos e ilíquidos, e é exatamente onde a confusão meme × listagem recente da
   [[KB-0056-meme-coin-como-ativo-e-o-rotulo-que-nao-e-medida]] impede atribuir isso a "ser meme".

## Como mediríamos aqui

Custo, não previsão. Para uma posição comprada com o horizonte de 4 h da `momentum_v1`, atravessar
uma liquidação custa a taxa daquele instante. Com a mediana de 0,5 bps das memes e um `R` efetivo
que a [[KB-0038-a-taxa-de-4-bps-nao-e-nem-maker-nem-taker]] estimou na casa de 51 bps para o
exemplo, um atravessamento na mediana consome cerca de **1%** de 1 R. No p95 da coorte B (7,0 bps),
consome cerca de 14%. **Isso é aritmética sobre um exemplo, não medição do nosso resultado.**

O que **não** dá para fazer com estes números: usar funding como filtro direcional. A T-016 já foi
retirada em 2026-09-06 pela evidência direta de que o poder preditivo à frente por ativo é ~zero
([[KB-0022-funding-preve-retorno-a-evidencia-direta-e-fraca]]), e nada aqui contraria aquilo. A
única coisa nova é que a **premissa empírica do folclore de meme também não se sustenta**: elas nem
sequer são o grupo de funding mais extremo.

## Hipótese testável no Lab

**`D-MEME-FUND` (diagnóstico, testável agora, perpétuo da Binance).** Duas perguntas, nesta ordem:

1. **Normalizar antes de comparar.** Para cada mercado, a taxa em **bps por hora de exposição**
   (taxa liquidada dividida pelo intervalo real entre liquidações consecutivas, medido — não pela
   cadência modal), com a distribuição entre mercados publicada com pesos iguais e cobertura
   temporal comparável. Quantis de taxa horária declaram a ponderação por duração. Desenho da Astra.
   **Ressalva dela que precisa entrar no relatório:** taxa horária é **normalização, não cobrança
   proporcional** — quem atravessa um pagamento paga a taxa inteira, não a fração da hora.
2. **Cadência publicada junto.** Para cada mercado com sinal, o número de liquidações por dia e a
   cadência inferida. Nenhuma comparação entre coortes sai sem essa coluna. Convenção, não teste.
3. **Custo de funding realizado por coorte**, sobre os outcomes já colhidos: para cada
   acompanhamento, quantas liquidações ele atravessou (separando **confirmado**, **inferido** e
   **indeterminado**, como a [[KB-0026-funding-num-horizonte-de-4h-e-o-vies-de-exclusao]] exige) e
   quanto isso somou em bps sobre o notional. É o `D-016` da terceira rodada com a estratificação
   por `meme_universe_v1` acrescentada.

**Pré-requisito que continua faltando:** `next_funding_time` tem **zero linhas** em
`market_snapshots` na VPS (medido hoje: `count(next_funding_time) = 0` em 235.457 linhas). Sem ele,
"atravessou uma liquidação" continua sendo inferência a partir da cadência modal, com todo o
problema que a KB-0026 registrou.

**A candidata que saiu daqui — `M-E`, teto de funding extremo em módulo — está bloqueada, e por dois
motivos que a revisão da fila achou.** (a) `build_market_context` **não passa `funding`** ao contexto
(`services/strategy-worker/hunter_strategy_worker/context.py:75`), então ele é `None` em toda
avaliação; o `load_funding` existente serve à apuração do outcome (`settle.py:60`), não à decisão.
(b) Eu tinha justificado a regra como "filtro de custo simétrico"; **isso está errado** — o Lab só
admite LONG e o funding é transferência **assinada** (`base.py:214`, `pricing.py:13,79`): +10 bps
custa e −10 bps **paga**. Um filtro em módulo elimina os dois casos e chama os dois de custo. A regra
pode sobreviver como "exclusão de funding extremo em módulo", mas com **outra** hipótese econômica,
ainda por escrever.

**O que não proponho, e é deliberado:** nenhum braço direcional de funding. Duas rodadas
já registraram que a evidência aponta para poder preditivo nulo, e esta acrescenta que a premissa
descritiva do folclore também é falsa. Gastar tentativa contra duas priors desfavoráveis é o oposto
do que a [[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] pede.

## Por que pode falhar

- **Amostra minúscula.** Seis liquidações para o BTC, 204 para as 21 memes, num intervalo de 45 h.
  Nenhum quantil aqui é estimativa estável, e o p05/p95 de um grupo com 47 observações é ruído.
- **Um regime só.** Dois dias sem stress. Funding extremo é fenômeno de euforia e de cascata; a
  janela não contém nenhuma das duas.
- **`funding_rates` é a taxa liquidada**, então ela **omite** a estimativa em formação — que é o que
  a feature `funding_rate` do M2 lê. As duas não são a mesma grandeza (KB-0019), e esta nota mede a
  primeira.
- **A comparação entre coortes está confundida por cadência, tamanho e idade ao mesmo tempo.** Eu
  publiquei a cadência justamente para não deixar isso implícito, mas publicar não desconfunde.
- **A coorte B tem 47 observações em 5 mercados novos.** Que ela não tenha nenhuma taxa negativa
  pode ser euforia ou pode ser que 47 amostras num mercado recém-listado simplesmente não contenham
  o outro lado.

## Segunda opinião (Astra)

Revisão de 2026-09-06 (`.claude/state/astra-review-KB-0059-0061-memecoins.md`).

1. **Impôs a normalização por hora de exposição** e a distinção entre normalização e cobrança: quem
   atravessa um pagamento paga a taxa inteira. Cenário de falha dela: 0,8 bps por hora "parece menos
   extremo por cobrança" que 1 bps a cada 8 h, quando é 6,4 vezes a taxa horária.
2. **Estreitou a conclusão** para "menos extremo **por liquidação nesta janela**", e derrubou o meu
   "engole metade da diferença": a razão entre medianas é medida, a atribuição causal não é.
3. **Apontou o viés de tamanho de grupo** na comparação de mínimos entre 21 e 150 mercados.
4. **Conferiu a aritmética de R** e confirmou: 0,5/51 = 0,98% de 1 R; 7/51 = 13,73%. Lembrou que
   os 51 bps continuam sendo denominador **sintético** da [[KB-0038-a-taxa-de-4-bps-nao-e-nem-maker-nem-taker]].
5. **Marcou como inferência, não medição**, a cadência de cada mercado — eu contei liquidações, não
   medi intervalos.
6. **Concordou** em separar taxa liquidada de estimativa em formação, em investigar cadência antes
   de interpretar funding, e em não abrir braço de estratégia nenhum a partir desta nota.

## Relacionados

[[KB-0019-o-que-a-nossa-funding-rate-mede-de-fato]] ·
[[KB-0022-funding-preve-retorno-a-evidencia-direta-e-fraca]] ·
[[KB-0023-funding-extremo-como-contrarian-a-afirmacao-mais-repetida]] ·
[[KB-0026-funding-num-horizonte-de-4h-e-o-vies-de-exclusao]] ·
[[KB-0056-meme-coin-como-ativo-e-o-rotulo-que-nao-e-medida]] · [[Strategy Backlog]] · [[Index]]
