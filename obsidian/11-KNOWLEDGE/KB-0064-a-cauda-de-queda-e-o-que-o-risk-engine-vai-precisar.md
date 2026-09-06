---
tags: [knowledge, nota, memecoins, risco, m3, m4]
tema: meme coins / risco específico
fonte: medição própria na VPS + Xiang et al. (arXiv 2512.00377)
fonte_url: https://arxiv.org/abs/2512.00377
lido_em: 2026-09-06
evidencia: replicado (SQL colado) + preprint lido em resumo
hipotese_testavel: sim — mas o destinatário é o Risk Engine, não o Lab
astra: pendente
---

# A cauda de queda — e o que o Risk Engine vai precisar

## O que afirma

Em 42 horas, a queda máxima mediana das memes foi de **−5,66%**, com a pior em **−29,75%**. O mesmo
cálculo no resto do universo dá **−6,65%** de mediana e **−58,67%** de pior caso.

**O que sobrevive à revisão é bem menos do que eu tinha escrito.** Eu tinha concluído "a cauda ruim
não está nas memes, está fora delas" e "as memes concentram os dois extremos ao mesmo tempo". A
Astra derrubou as duas:

- Só sobrevive: **"a maior queda observada entre os mercados incluídos pertence ao `E_resto`"**.
  Comparar extremos de **19** contra **133** mercados dá muito mais oportunidade ao grupo maior de
  produzir um extremo, e medianas não resolvem comparação de caudas.
- "Concentram os dois extremos" **não tem apoio nenhum**: a amplitude mediana da coorte A é
  **11,51%** contra **12,10%** do resto — e amplitude não determina a ordem subida→queda.
- **Cenário de falha dela, e é o que importa:** transformar essa abertura em justificativa para
  limites **menos** conservadores para memes.

O que fica de pé, porque vem de outra medição e não desta: pela
[[KB-0058-spread-e-profundidade-o-custo-de-sair-de-uma-meme]], as memes têm o livro mais fino para
sair. O risco a registrar não é volatilidade — é **volatilidade com saída estreita**.

Esta nota **não propõe nada para o Lab**: o Lab de sombra não dimensiona posição, `PnL de carteira`
é *não aplicável*, e por isso tudo aqui é registro para o Risk Engine do M3/M4.

## Onde foi mostrado

**Medição própria, VPS, mesma janela de 42 h**, sobre barras de 15 min completas, exigindo ao menos
150 barras por mercado.

```sql
s AS (SELECT market_id, b15, cl,
        max(cl) OVER (PARTITION BY market_id ORDER BY b15 ROWS UNBOUNDED PRECEDING) AS pico,
        ln(cl/nullif(lag(cl) OVER (PARTITION BY market_id ORDER BY b15),0)) AS ret,
        count(*) OVER (PARTITION BY market_id) AS nb
      FROM b WHERE n1m = 15),
perm AS (SELECT market_id, min(cl/pico - 1) AS max_dd, min(ret) AS pior_15m,
           (max(cl)/min(cl) - 1) AS amplitude FROM s WHERE nb >= 150 GROUP BY 1)
```

```
      grupo       | mercados | dd_max_mediano_pct | pior_dd_pct | pior_barra_15m_mediana_pct | pior_barra_absoluta_pct | amplitude_mediana_pct
------------------+----------+--------------------+-------------+----------------------------+-------------------------+-----------------------
 A_meme           |       19 |              -5.66 |      -29.75 |                      -2.35 |                  -10.03 |                 11.51
 B_meme_nao_ascii |        4 |             -19.86 |      -32.99 |                      -5.96 |                   -7.79 |                 26.70
 C_btc            |        1 |              -0.73 |       -0.73 |                      -0.21 |                   -0.21 |                  0.80
 D_majors         |       23 |              -2.87 |       -7.35 |                      -1.00 |                   -3.62 |                  7.17
 E_resto          |      133 |              -6.65 |      -58.67 |                      -2.03 |                  -31.11 |                 12.10
```

Três leituras:

1. **A coorte B é a única que se destaca de fato**: queda máxima **mediana** de −19,86% em menos de
   dois dias, e pior barra de 15 min mediana de −5,96%. Quatro mercados. Com a ressalva de sempre —
   ser meme e ser listagem recente estão confundidos ali
   ([[KB-0056-meme-coin-como-ativo-e-o-rotulo-que-nao-e-medida]]).
2. **A pior barra isolada observada (−31,11% em 15 minutos) está no `E_resto`**, e isso é uma
   **observação individual**, não uma afirmação sobre caudas: comparar mínimos entre 19 e 133
   mercados favorece o grupo maior por construção — a mesma ressalva que a Astra impôs na
   [[KB-0059-funding-em-memes-a-cadencia-antes-do-sentimento]]. A comparação que valeria é
   **frequência de perdas acima de limiares comuns**, com cobertura comparável, e ela não está
   feita.
3. **O BTC nesta janela caiu 0,73% no pior momento.** Um stop de 1,5 ATR nele seria de ~0,19% do
   preço, o que só reforça o que a [[KB-0057-a-volatilidade-das-memes-e-o-piso-que-bane-o-btc]] achou
   sobre o piso.

**O que a literatura acrescenta, e é o único ponto em que ela vai além do que medimos.** O ME2F
(Xiang et al., arXiv 2512.00377) coloca **dominância de baleias** como uma das três dimensões de
fragilidade — concentração de posse entre os maiores detentores. Isso é on-chain, está do outro lado
da linha da [[KB-0063-social-e-on-chain-a-linha-que-nao-atravessamos]], e é o mecanismo que a nossa
medição de preço **não consegue ver**: um livro fino com posse concentrada é uma queda de 30% que
não avisa.

## Como mediríamos aqui

Nada disto muda o Lab. Muda o que o Risk Engine vai ter de checar quando o M3 e o M4 existirem, e o
sentido de registrar agora é que a `packages/risk-core` **ainda não foi escrita com estes casos em
mente**.

Cinco regras que este dado sugere, todas como **requisito a debater**, nenhuma como decisão:

1. **Teto de exposição por profundidade, não por notional fixo.** Três dos 21 livros de meme não
   comportam 20.000 USDT em 20 níveis. Um limite em dólares que ignora o livro é um limite que não
   limita.
2. **A saída é o problema, não a entrada.** Entrar em CHILLGUYUSDT com 3.186 USD de profundidade
   total é fácil; sair durante uma queda de 10% numa barra de 15 min é outra coisa. Qualquer conta
   de risco que use o custo de entrada como proxy do custo de saída está errada nesta coorte.
3. **Delistagem e queda de ranking são eventos distintos.** O nosso código já os separa
   (`universe_repo.py:106-127` marca `delisted_at` só na delistagem; cair do top 200 apenas
   desmonitora), e a [[KB-0062-o-primeiro-dia-que-nao-conseguimos-ver]] mostra que 14 mercados
   saíram do universo em 15 h. Para o Risk Engine, uma posição aberta num mercado que saiu do
   universo é um caso que precisa de regra escrita.
4. **Barra grande é o cenário de teste do stop — e não é prova de gap.** Eu tinha escrito que uma
   barra de −10,03% "atravessa qualquer stop de 1,5 ATR sem tocar no preço do stop". Errado nos dois
   pedaços: uma queda de 10% pode acontecer **negociando continuamente através do stop** (não é
   salto), e a distância do stop depende do ATR **naquele instante**, então "qualquer" é falso. O
   que fica é a magnitude, como cenário a dimensionar. A [[KB-0005-stops-quando-eles-param-perdas]]
   já dizia que stop não é seguro.
5. **Correlação em stress.** A [[KB-0060-correlacao-com-o-btc-e-a-meme-season]] mediu beta mediano de
   2,80 das memes contra o BTC numa janela **sem** stress. Limite de exposição agregada que assuma
   independência entre posições de meme está assumindo o contrário do que a literatura de crise
   descreve — e a nossa janela não contém a evidência para nenhum dos dois lados.

## Hipótese testável no Lab

**`D-MEME-GAP` (diagnóstico, roda hoje, sem pré-requisito) — com o desenho corrigido pela Astra,
porque a minha primeira versão mediria a coisa errada.** Para os outcomes com `result = 'stop'`, a
distribuição do preço de saída contra o preço de stop, por coorte — **decomposta em quatro termos
separados**: `exit_at_open`, `exit_base`, a barreira, e os custos assumidos.

Motivo: no simulador, um stop tocado dentro da barra sai **na barreira**, e uma abertura abaixo dela
sai **na abertura** (`walker.py:71,155`); depois disso o preço recebe o acréscimo adverso de custo
(`pricing.py:53`). Ou seja, `stop − exit_price` **mistura gap com custo assumido, inclusive quando
não houve gap nenhum**. Cenário de falha dela: medir o déficit em stops sem gap e usar isso como
estimativa empírica de gap para dimensionar posição real.

E o nome do resultado tem de dizer o que ele é: **gap observado na resolução do modelo**, não custo
de execução real. É o `EXEC-D` da quinta rodada
([[KB-0039-tipos-de-ordem-e-o-que-a-sombra-assume-sem-dizer]]) estratificado por coorte, com a mesma
ressalva: **descreve contexto, não valida simetria de execução**.

**Registro para o M3/M4, não candidata:** os cinco requisitos acima vão para a página do Risk Engine
com a marcação de que nasceram de 42 h de observação e nenhum evento de stress.

## Por que pode falhar

- **Quarenta e duas horas, um regime, sem crise.** Falar de cauda de risco com dois dias de dado é o
  limite do que se pode fazer com um instrumento novo. O pior caso observado é o pior caso **desta
  janela**, e nada mais.
- **Queda máxima depende da janela, e a formulação precisa ser exata** (correção da Astra): ao
  **estender** uma trajetória preservando as observações anteriores, a queda máxima só pode piorar
  ou ficar igual — com a convenção negativa que usei, fica **mais negativa**. Isso não é "viciada
  para baixo em magnitude", e janelas móveis diferentes não obedecem à monotonicidade. Além disso,
  mesma janela nominal **não** garante mesma cobertura, especialmente com o filtro de 150 barras.
  Comparar coortes na mesma janela é legítimo; comparar com qualquer número publicado sobre "queda
  de 80-95% em meme coin" **não é**, e por isso nenhum número desses entrou aqui.
- **Dezenove mercados na coorte A e quatro na B.** Os quantis extremos são ruído.
- **`min(cl/pico − 1)` usa fechamentos de 15 min**, então subestima a queda intrabarra — a queda
  real dentro da barra é pelo menos tão ruim quanto a medida.
- **O mecanismo de baleias eu não medi nem posso medir.** É citação de resumo de preprint, e está
  aqui como explicação candidata, não como fato nosso.

## Segunda opinião (Astra)

Revisão de 2026-09-06 (`.claude/state/astra-review-KB-0062-0065-memecoins.md`).

1. **Derrubou a afirmação sobre a cauda.** Só sobrevive "a maior queda observada entre os mercados
   incluídos pertence ao `E_resto`"; 19 contra 133 mercados não decide caudas. Cenário de falha:
   usar isso para justificar limites **menos** conservadores em memes.
2. **Derrubou "as memes concentram os dois extremos"** com o número que eu mesmo tinha publicado:
   amplitude mediana 11,51% na coorte A contra 12,10% no resto.
3. **Corrigiu a ressalva de janela** — extensão preserva o passado, então a queda máxima piora ou
   fica igual; janelas móveis não são monótonas; e mesma janela nominal não é mesma cobertura.
4. **Derrubou "atravessa qualquer stop de 1,5 ATR"** — queda de 10% pode ser contínua, e a distância
   do stop depende do ATR do instante.
5. **Reprojetou o `D-MEME-GAP`**: `stop − exit_price` mistura gap e custo assumido
   (`walker.py:71,155`, `pricing.py:53`), e o resultado tem de se chamar **gap observado na
   resolução do modelo**.
6. **Sugeriu o que eu deveria ter feito primeiro:** frequência de perdas acima de limiares comuns,
   com cobertura comparável, deixando mínimos como observações individuais.
7. **Concordou** que não há base aqui para alterar risco nem declarar vantagem, e que os cinco
   requisitos ficam como **propostas** para o Risk Engine, com evidência de preço distinguida de
   evidência de execução.

## Relacionados

[[KB-0058-spread-e-profundidade-o-custo-de-sair-de-uma-meme]] ·
[[KB-0060-correlacao-com-o-btc-e-a-meme-season]] ·
[[KB-0062-o-primeiro-dia-que-nao-conseguimos-ver]] ·
[[KB-0063-social-e-on-chain-a-linha-que-nao-atravessamos]] ·
[[KB-0005-stops-quando-eles-param-perdas]] ·
[[KB-0039-tipos-de-ordem-e-o-que-a-sombra-assume-sem-dizer]] ·
[[Risk Engine]] · [[Strategy Backlog]] · [[Index]]
