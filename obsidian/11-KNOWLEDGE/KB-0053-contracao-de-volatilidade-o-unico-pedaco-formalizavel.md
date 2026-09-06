---
tags: [knowledge, nota, livros, rompimento, volatilidade]
tema: padrões de base antes do rompimento
fonte: Stan Weinstein (estágios), William O'Neil (CANSLIM), Mark Minervini (VCP) — descrições públicas dos métodos
fonte_url: https://www.investors.com/how-to-invest/investors-corner/
lido_em: 2026-09-06
evidencia: anedótico
hipotese_testavel: sim
astra: concorda com ressalva forte
---

# Contração de volatilidade: o pedaço dessa família que dá para formalizar

## O que afirma

Três métodos de ações, com a mesma espinha. **Weinstein** divide o gráfico em quatro estágios — base,
avanço, topo, queda — e compra o rompimento da base (estágio 1 para 2) com volume. **O'Neil**
(CANSLIM) combina critérios fundamentalistas de crescimento com um padrão gráfico de base e um
rompimento acompanhado de **volume bem acima da média**. **Minervini** (VCP) descreve a base como uma
sequência de recuos de **amplitude decrescente**, com volume secando, até o rompimento.

O denominador comum, e a parte que melhor sobrevive à tradução para o nosso mercado: **antes do
rompimento que vale, a volatilidade se contrai**.

Ressalva de fonte e de honestidade: as descrições acima são síntese do que esses métodos publicamente
afirmam, a partir do material aberto que consultei. **No material que li não há teste com grupo de
controle** — não afirmo que não exista em lugar nenhum. A apresentação clássica deles é
**retrospectiva sobre ações que subiram muito**, o que é viés de seleção na forma mais pura.

## Onde foi mostrado

Ações americanas, barras diárias e semanais, horizonte de semanas a meses, décadas de 1960 a 2010.
Boa parte do CANSLIM é fundamento (crescimento de lucro, liderança setorial) e **não existe** para um
perpétuo. Nada do que consultei foi mostrado em cripto, em 15 minutos, ou com custos de perpétuo.

## Como mediríamos aqui

Duas observações, e a primeira é desconfortável.

**A ideia de "rompimento confirmado por volume" já está implementada — mas não é o critério do
CANSLIM.** O nosso filtro é `rvol_min = 1,5` (`momentum_v1.py:79`), medido contra a **mediana** das
96 barras anteriores de 15 min, com a barra corrente excluída (`indicators.py:124`). O material
primário do IBD fala de volume **diário** de rompimento 40 a 50% acima da **média** diária. Isso
sustenta a analogia — confirmação por volume — e **não** equivalência de estatística, de janela nem
de mercado (**correção da Astra**). E a diferença morde: numa distribuição assimétrica, 1,5× a
mediana pode ficar **abaixo da média**, de modo que o nosso filtro aprovaria um sinal que não
satisfaz nem a versão literal de "acima da média".

O que continua valendo é o ponto prático: a confirmação por volume **já roda**, e a utilidade dela
nunca foi isolada.

**O que não está implementado é a contração.** Uma formalização possível, com o dado que temos:

```
contracao = ATR(k barras de 15m) / ATR(4k barras de 15m)      # k a definir, p.ex. 8
```

ou, na versão de amplitude pura, a mediana da amplitude das últimas `k` barras sobre a mediana das
`4k` anteriores. As duas saem das velas de 1 minuto que já agregamos, sem coleta nova.

**Três decisões de instrumento têm de ser fechadas antes de rodar** (exigência da Astra, e a última é
a que muda o sentido da medida):

1. **Qual estimador.** O ATR do código é Wilder, com origem explícita, e exige pelo menos
   `period + 2` barras (`indicators.py:70`). Passar exatamente 8 barras para um ATR de período 8
   devolve indisponível; usar a média de oito TRs é **outro** estimador, e tem de ser dito qual é.
2. **Janelas sobrepostas ou consecutivas**, e quantas barras de aquecimento cada uma consome.
3. **A barra do rompimento entra ou não.** Incluí-la é temporalmente lícito depois do fechamento
   dela, mas mede contração **incluindo o rompimento** — e um rompimento amplo pode apagar a
   contração anterior e **inverter** a seleção. Para a tese "contração **antes** do rompimento", as
   duas janelas terminam em `t−1`. É assim que fica escrito.

**E há uma tensão que precisa ser medida antes de qualquer braço:** a `momentum_v1` já tem um **piso
absoluto** de volatilidade (`atr_pct_min = 0,003`), enquanto a contração é uma medida **relativa à
própria história do mercado**. As duas podem estar puxando na mesma direção ou em direções opostas, e
a [[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]] já mostrou que o piso pode estar
funcionando como filtro de regime sem que ninguém tenha decidido isso. Medir a correlação entre
`contracao`, `atr_pct` e `ER(20)` vem antes — mesma disciplina que a
[[KB-0048-o-teste-antes-da-regra-e-o-filtro-que-ja-estava-dentro]] impôs a `VR` e `ER`.

## Hipótese testável no Lab

**Passo 1 — `D-CONTR`, observar sem decidir.** Calcular a razão de contração no instante de cada
decisão registrada e publicar: a distribuição condicionada a sinal disparado, e a correlação de
postos com `atr_pct` e com `ER(20)`. Sem alterar decisão nenhuma. Vale a mesma ressalva de
proveniência da `ER`: a população `not_triggered` **não está gravada individualmente**
(`decide.py:123,155`), então qualquer grupo de comparação retrospectivo é **replay reconstruído**,
com cobertura publicada.

**Passo 2 — braço `CONTR-A`**, só depois:

```
contraction_estimator = "wilder_atr"   # declarado; aquecimento >= period + 2 barras
contraction_window    = 8              # barras de 15m na janela curta, terminando em t−1
contraction_baseline  = 32             # barras de 15m na janela longa, terminando em t−1
contraction_max       = θ              # de um quantil da distribuição condicionada, declarado antes
```

Aceita o sinal quando `contracao ≤ θ` — isto é, quando a volatilidade recente está **comprimida**
contra a própria base do mercado.

**O nome é o que ele mede.** O braço se chama razão de contração de ATR, **não** "VCP". Reduzir um
método a um indicador e conservar o nome e a evidência do método original é exatamente a armadilha
que a Astra nomeou para esta família inteira.

**Refutação, com os dois denominadores da convenção `C-META`**
([[KB-0052-meta-rotulagem-o-formato-de-todo-filtro-que-propusemos]]): se nem o `delta_por_aceito` nem
o `delta_por_oportunidade` forem positivos na janela futura reservada, o filtro não se sustenta.

## Por que pode falhar

1. **Viés de seleção na fonte.** A evidência a favor de bases e contrações é a apresentação
   retrospectiva de ações que subiram. Não há grupo de controle nas fontes.
2. **Metade do CANSLIM não existe aqui.** Sem fundamento, transportar o método inteiro é impossível;
   transportar um pedaço e manter o nome é desonesto.
3. **A contração pode ser redundante com o piso de ATR**, ou pior, pode brigar com ele: um mercado em
   contração forte tende a ter `atr_pct` baixo, que é justamente o que o piso desliga. O passo 1
   existe para descobrir isso antes de gastar um braço.
4. **Horizonte.** Bases de dias ou semanas em ações contra 8 barras de 15 minutos em cripto: a
   distância é da mesma ordem da que já registrei na
   [[KB-0045-turtles-a-entrada-que-ja-temos-e-a-saida-que-nao]].
5. **`k` e `θ` são duas escolhas**, e cada par é uma tentativa. Entram no
   [[Registro de Tentativas]] antes de rodar; escolher depois de ver o resultado é a
   [[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] outra vez.
6. **A contração pode estar altamente correlacionada com a `ER` na nossa população** — mas **não é a
   mesma medida**: a Astra conferiu que `atr_pct` é amplitude relativa ao preço, contração compara
   amplitudes em horizontes diferentes, e `ER` é deslocamento líquido sobre o caminho entre
   fechamentos; dá para preservar todos os fechamentos e mudar só os pavios, e aí `ER` não muda e a
   contração muda. Se a correlação empírica for alta, uma das duas sai por **parcimônia** — e
   correlação baixa também não demonstra vantagem incremental.

## Segunda opinião (Astra)

Foi a ressalva mais dura da curadoria, e ela vale citada inteira em substância: aceitaria **apenas
uma regra de preço/volume explicitamente formalizada como adaptação nossa**, e **não** colocaria
"Stage Analysis", "VCP" ou "CAN SLIM" como experimentos completos sobre estas entradas. A armadilha
que ela nomeou — "reduzir um método a um indicador e conservar o nome e a evidência do método
original" — é a razão de o braço acima se chamar razão de contração de ATR e nada mais.

Concordou com a fronteira geral: livros devem produzir regras falsificáveis, com a transferência de
mercado e de horizonte **declarada**; e nenhuma dessas fontes valida a adaptação para cripto em 15
minutos.

Na revisão da nota, **derrubou a minha equivalência com o CANSLIM**: o critério primário do IBD é
volume **diário** 40–50% acima da **média**, o nosso é 1,5× a **mediana** de 96 barras de 15 min, e
numa distribuição assimétrica o nosso pode aprovar um sinal abaixo da média. É analogia, não
implementação. Também exigiu fechar o estimador antes de rodar (Wilder precisa de `period + 2`
barras) e — a correção que mais muda o experimento — **encerrar as duas janelas em `t−1`**, porque
incluir a barra do rompimento mede contração *com* o rompimento dentro e pode inverter a seleção.
Confirmou, por construção, que contração, `atr_pct` e `ER` são medidas distintas.

## Relacionados

[[Strategy Backlog]] · [[Registro de Tentativas]] ·
[[KB-0047-razao-de-eficiencia-de-kaufman]] ·
[[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]] ·
[[KB-0052-meta-rotulagem-o-formato-de-todo-filtro-que-propusemos]] ·
[[KB-0015-volume-relativo-e-o-pico-como-exaustao]] ·
[[KB-0004-proximidade-da-maxima-e-confirmacao-por-volume]] · [[EXP-0001-momentum-v1]]
