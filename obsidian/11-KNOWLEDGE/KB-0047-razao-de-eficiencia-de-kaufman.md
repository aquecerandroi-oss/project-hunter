---
tags: [knowledge, nota, livros, tendencia, filtro]
tema: qualidade de tendência / filtro de entrada
fonte: artigo aberto do próprio Perry Kaufman sobre casar mercado e estratégia (a Efficiency Ratio); documentação pública da KAMA. O livro *Trading Systems and Methods* é a origem, **não** foi lido nesta rodada
fonte_url: https://kaufmansignals.com/matching-the-markets-to-the-strategy/
lido_em: 2026-09-06
evidencia: anedótico
hipotese_testavel: sim
astra: concorda
---

# A razão de eficiência de Kaufman: o quanto do caminho foi em linha reta

## O que afirma

Kaufman separa duas coisas que a maioria dos indicadores mistura: **quanto o preço andou** e **quão
retilíneo foi o caminho**. A razão de eficiência mede a segunda:

```
ER(N) = |C_t − C_{t−N}| / Σ_{i=1..N} |C_{t−i+1} − C_{t−i}|
```

O numerador é o deslocamento líquido no período; o denominador é a soma dos deslocamentos barra a
barra. `ER → 1` significa que o preço foi de A a B praticamente em linha reta; `ER → 0` significa que
percorreu muito caminho para chegar quase ao mesmo lugar. O uso original é adaptar a suavização de
uma média móvel (a KAMA reage rápido quando `ER` é alto e devagar quando é baixo), e o argumento mais
amplo do livro é que a mesma regra funciona em uns mercados e não em outros — a `ER` é o instrumento
que Kaufman propõe para dizer em qual dos dois estados se está.

A fórmula acima é definição pública, está no artigo do próprio Kaufman e está reproduzida igual em
documentação de várias plataformas (StockCharts, MetaTrader, TradingView) — o que confirma **a
fórmula**, não a existência de vantagem, e muito menos a validade de `ER(20)` como filtro
intradiário nosso. `ER(N)` usa **N diferenças e N+1 fechamentos**.

## Onde foi mostrado

Texto de praticante, catálogo de sistemas, sem estudo controlado publicado com a `ER` como filtro
isolado. Mercados tradicionais, barras diárias. A `ER` é uma **definição**, não um resultado: nada na
fonte estabelece que filtrar por ela melhore expectancy em lugar nenhum, muito menos em perpétuos de
cripto em 15 minutos.

## Como mediríamos aqui

É a candidata mais barata desta rodada em termos de dado: `ER` sai dos **mesmos fechamentos de 15
minutos que a `momentum_v1` já agrega**, sem coleta nova, sem feature nova do M2, sem book, sem
derivativos.

E há um argumento de não-redundância que sustenta a ideia — o mesmo argumento que, aplicado a outra
candidata, a matou. A regra atual é `close_t > max(C_{t−1} … C_{t−20})` (`indicators.py:141`). Isso
diz que o último fechamento é o maior de 21; **impõe restrições ao caminho, mas não o determina**.
Uma nova máxima pode ser atingida por uma subida limpa (`ER` alto) ou por um ziguezague que sobe 3%,
cai 2,8% e sobe de novo (`ER` baixo). São fatos diferentes sobre a **mesma janela** — e é justamente
por serem a mesma janela que a comparação é limpa: não há desalinhamento de horizonte para explicar
diferença.

Compare com a candidata T-001 (`return_4h > 0`), que esta rodada **descobriu ser redundante**:
`close_t > max(C_{t−1} … C_{t−20})` implica `close_t > C_{t−16}`, e 16 barras de 15 minutos são 4
horas — o gate de tendência já está contido na condição de rompimento
([[KB-0048-o-teste-antes-da-regra-e-o-filtro-que-ja-estava-dentro]]). A `ER` não tem esse problema.

## Hipótese testável no Lab

**Passo 1 — `D-ER`, observar sem decidir.** Calcular `ER(20)` sobre os 21 fechamentos de 15m no
instante de cada decisão já registrada e publicar a distribuição **condicionada a sinal disparado**.
Isso dá a população da qual o limiar pode sair — e não dos outcomes, que é o erro que a
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] proíbe.

**Ressalva de proveniência que muda o desenho (achado da Astra).** Eu queria a mesma distribuição
nas barras `not_triggered` do mesmo slot, para ter grupo de comparação. **Elas não estão gravadas
individualmente:** nesse caminho o worker avança o checkpoint e retorna antes de persistir qualquer
sinal, registrando apenas contadores agregados (`decide.py:123,155`). Reconstruí-las com velas
recuperadas depois produz um **replay reconstruído**, não uma avaliação observada naquele instante —
e o próprio envelope avisa que corte por tempo de mercado não prova disponibilidade na decisão
(`record.py:53`). Então: ou o grupo de comparação é rotulado como replay reconstruído, com cobertura
publicada junto, ou a coleta é **prospectiva**. É o mesmo padrão de "observar sem decidir" que a
segunda rodada abriu para o `taker_imbalance_5m`.

**Passo 2 — braço `ER-A`**, só depois:

```
efficiency_window = 20        # 20 diferenças sobre 21 fechamentos de 15m — a janela do rompimento
efficiency_min    = θ         # de um quantil da distribuição condicionada, declarado antes
```

Denominador zero exige os **21** fechamentos iguais, e nesse caso não há rompimento — então, dentro
desta população, `unavailable` por denominador zero é impossível; a regra fica escrita para o caso
geral. (Eu tinha escrito "20 fechamentos idênticos", o que produziria `unavailable` num caso em que
a `ER` correta é 1.)

**Refutação, com os dois denominadores declarados** — porque um filtro tem dois resultados
diferentes e nenhum dos dois é performance de carteira:

- **média por entrada aceita**: `ΔR_net` do braço filtrado contra o braço completo;
- **contribuição por oportunidade da base**: soma de `R_net` dividida pelo número de oportunidades
  da população **não filtrada**, mais a **taxa de retenção**.

Cenário sintético da Astra que mostra por que os dois são obrigatórios: base com 100 entradas a
0,10 R de média; o filtro aceita 10 com média 0,20 R. A média por entrada dobrou e a soma caiu de 10
R para 2 R. Refuta se **ambos** forem ≤ 0 na janela futura reservada. E, se o braço rodar como
estratégia independente em vez de replay, **as entradas não são pareadas**: o rearme depende do
estado `not_triggered` e da ocupação do slot (`episodes.py:57`).

## Por que pode falhar

1. **`ER` baixa pode ser o estado normal.** Se a distribuição condicionada estiver esmagada perto de
   zero, qualquer θ útil desliga quase tudo. Por isso o passo 1 vem antes.
2. **Confundir caminho ruidoso com volatilidade baixa** (armadilha nomeada pela Astra). `ER` é uma
   razão adimensional: um mercado calmo e retilíneo e um mercado violento e retilíneo têm a mesma
   `ER`. Ela não substitui, nem duplica, `atr_pct` — e a análise tem de mostrar isso, medindo a
   correlação entre as duas antes de tratá-las como informações distintas.
3. **`ER` alta pode selecionar movimento já exaurido** — risco **hipotético**, não demonstrado, o
   mesmo que a [[KB-0002-momentum-e-reversao-em-cripto]] registrou para impulso recente excessivo.
   (Escrever "um caminho retilíneo já andou tudo" seria presumir a exaustão em vez de medi-la.)
4. **Só fechamentos.** `ER` sobre closes não enxerga o ruído intrabar; dois caminhos com os mesmos 21
   fechamentos e pavios completamente diferentes têm a mesma `ER`.
5. **Escolher janela e θ na mesma amostra** e apresentar como confirmação. Cada par (janela, θ) é uma
   tentativa, e entra no [[Registro de Tentativas]] antes de rodar.

## Segunda opinião (Astra)

Pôs a eficiência direcional como candidata **4** da fila dela, com a fórmula sobre fechamentos finais
de 15 minutos e um `ER20 ≥ 0,30` explicitamente marcado como "limiar proposto e não validado".
Nomeou três armadilhas, todas incorporadas acima: confundir trajetória pouco ruidosa com baixa
volatilidade; escolher janela e limiar nos outcomes e apresentar como confirmação; e `ER` selecionar
movimentos já exauridos. Acrescentou a regra do denominador zero como indisponibilidade.

Concordou também com a distinção de método que dá a esta nota o seu lugar: a `ER` acrescenta uma
descrição da trajetória que a condição de rompimento **não determina**, enquanto o gate
`return_4h > 0` **já está implicado por ela** — e foi a Astra quem derrubou a T-001 com esse
argumento.

Na revisão da nota, corrigiu ainda três coisas: **21 fechamentos, não 20** (e o cenário em que a
minha regra de denominador zero daria `unavailable` para uma `ER` que vale 1); a **proveniência das
barras `not_triggered`**, que não existem individualmente no banco (`decide.py:123,155`); e a
**ambiguidade do denominador** do contraste, com o cenário sintético dos 100 × 0,10 R contra 10 ×
0,20 R. Pediu também que a fonte fosse o artigo do próprio Kaufman em vez do livro, para não fingir
leitura que não houve.

## Relacionados

[[Strategy Backlog]] · [[Registro de Tentativas]] ·
[[KB-0048-o-teste-antes-da-regra-e-o-filtro-que-ja-estava-dentro]] ·
[[KB-0002-momentum-e-reversao-em-cripto]] ·
[[KB-0001-momentum-academico-e-o-que-nao-se-transfere]] ·
[[KB-0007-atr-e-escala-por-volatilidade]] · [[EXP-0001-momentum-v1]]
