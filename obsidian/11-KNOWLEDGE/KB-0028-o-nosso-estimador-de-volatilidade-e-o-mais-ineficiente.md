---
tags: [knowledge, nota, regime, volatilidade, estimador]
tema: regime de mercado e volatilidade
fonte: Parkinson (1980), J. Business 53:61-65; Garman & Klass (1980), J. Business 53:67-78; Rogers & Satchell (1991), Ann. Appl. Prob. 1(4):504-512 — lidos através do resumo técnico do Portfolio Optimizer; e o nosso `regime/series.py`
fonte_url: https://portfoliooptimizer.io/blog/range-based-volatility-estimators-overview-and-examples-of-usage/
lido_em: 2026-09-06
evidencia: estudo revisado (fórmulas e fatores de eficiência lidos em resumo técnico, não nos originais) + leitura de código próprio
hipotese_testavel: sim
astra: pendente
---

# O nosso estimador de volatilidade é o mais ineficiente dos disponíveis — e isso foi escolhido

## O que afirma

Quando se estima volatilidade a partir de barras OHLC, usar **só os fechamentos** desperdiça
informação. Parkinson (1980) mostrou que a amplitude `ln(H/L)` de cada barra dá um estimador com
variância amostral muito menor — o resumo técnico consultado dá **até 5,2×** mais eficiente que
close-to-close. Garman & Klass (1980) somam a abertura e o fechamento e chegam a **até 7,4×**.
Rogers & Satchell (1991) chegam a **até 6×** e, ao contrário dos dois anteriores, são
**independentes do drift**.

O preço dessa eficiência está nas premissas:

- Parkinson e Garman-Klass assumem **drift zero**. Numa barra com tendência forte a amplitude
  atribui ao "ruído" um movimento que era direção, e o estimador enviesa;
- todos assumem **observação contínua**. Como só vemos negócios discretos, a máxima e a mínima
  observadas são **menores** que os extremos verdadeiros, e o estimador subestima sistematicamente;
- nenhum deles vê **saltos entre barras** (o gap do fechamento para a abertura seguinte), o que
  subestima de novo.

## Onde foi mostrado

Ações e índices, barras diárias, literatura dos anos 1980-1990. O fator de eficiência é uma
propriedade do movimento browniano geométrico idealizado, não uma medição de mercado; em dados reais
ele encolhe justamente pelas três razões acima.

## Como mediríamos aqui — e o que o nosso código já faz

`packages/indicators/hunter_indicators/regime/series.py` é explícito: a estimativa é a **média dos
retornos absolutos de 1 minuto** da janela (`_mean_absolute_return`), com o comentário de que foi
escolhida sobre o desvio-padrão por ser **exata em `Decimal`** (sem raiz quadrada, sem depender da
precisão ambiente) e por não reivindicar a normalidade que um sigma implica. Ou seja: é o estimador
mais ineficiente da família, escolhido **de propósito**, por reprodutibilidade.

Três fatos que essa escolha traz e que precisam ficar escritos:

1. **Nós já temos OHLC de 1 minuto.** A tabela `candles` guarda `open`, `high`, `low`, `close`
   (`NUMERIC(28,10)`), então Parkinson e Garman-Klass são computáveis hoje, sem coletar nada novo.
2. **Média absoluta e desvio-padrão não são a mesma escala.** Para `X ~ N(0, σ²)` — e a condição de
   **média zero** é obrigatória, não decoração (correção da Astra) — vale `E|X| = σ·√(2/π) ≈
   0,7979·σ`. Em retornos de 1 minuto a média é numericamente desprezível, mas a fórmula só é essa
   sob média zero; com drift ela subestima o fator. Comparar a nossa mediana de 30 dias com qualquer
   número publicado em unidades de σ sem essa conversão é erro de unidade.
3. **Os fatores 5,2× / 7,4× / 6× NÃO se transferem automaticamente para o nosso estimador**
   (correção da Astra). Eles são a eficiência relativa ao estimador close-to-close **de σ** (soma de
   quadrados), sob movimento browniano. O nosso estimador é um funcional diferente — média de
   valores absolutos, que é mais **robusto** a cauda pesada e menos eficiente sob normalidade. Dizer
   "o nosso é 5× pior" seria inventar um número. O que é legítimo afirmar: ele é, por construção, o
   que usa **menos** informação da barra (só fechamentos), e nada mais que isso sem medição.
4. **A ineficiência do estimador entra direto no limiar.** Quanto maior a variância amostral da
   estimativa horária, mais a razão `volatility / mediana_30d` cruza 2,0 e 0,5 **por ruído**, não por
   mudança de mercado. A histerese de 3 leituras é uma resposta parcial: ela suaviza no eixo do
   tempo, não no eixo do estimador — e leituras consecutivas do mesmo ruído amostral não são
   independentes, porque a janela de 60 minutos se sobrepõe quase inteira entre uma leitura e a
   seguinte.

## Hipótese testável no Lab

**H-KB0028 (diagnóstica).** Calcular, sobre as mesmas horas UTC completas do BTCUSDT, três séries —
a nossa (média do |retorno| de 1 min), Parkinson e Garman-Klass sobre as mesmas 60 velas — e medir:

- a correlação de postos entre as três séries;
- a **taxa de discordância de rótulo**: em que fração das horas a razão contra a respectiva mediana
  de 30 dias cai numa faixa (`LOW` / `NORMAL` / `HIGH`) diferente da nossa;
- o desvio-padrão da própria estimativa horária em cada método (proxy de eficiência empírica).

**O que essa medição mede — e o que ela não mede (correção da Astra).** A taxa de discordância é
**sensibilidade do rótulo ao estimador**. Ela não diz qual estimador é mais **preciso**, porque não
existe volatilidade verdadeira observável para servir de gabarito. Para falar de precisão seria
preciso outro desenho: comparar cada estimador horário contra uma volatilidade realizada de
frequência mais alta da **mesma** hora (por exemplo, soma de retornos quadrados de 1 min como
proxy), e mesmo aí o proxy tem ruído de microestrutura. A H-KB0028 fica, então, deliberadamente
modesta: mede quanto o veredito depende de uma escolha nossa.

- **Confirmação de que a escolha custa pouco:** discordância de rótulo abaixo de 5% das horas.
- **Refutação:** discordância acima de 15% — nesse caso o rótulo publicado depende materialmente de
  um estimador que escolhemos por conveniência aritmética, e isso vira uma decisão do Everton (é
  mudança do que o produto afirma), não uma otimização silenciosa. E a decisão **não** se resolve
  pela discordância: exige o desenho de precisão descrito acima.
- **Regra de nomes:** se algum dia trocarmos, é `regime_v1`, nunca uma edição do `regime_v0` —
  `RegimeThresholds.identity` já obriga isso para limiares, e um estimador diferente é uma mudança
  maior que um limiar.

## Por que pode falhar

- **Comparar maçãs com laranjas.** Parkinson estima σ; nós estimamos E|r|. A comparação só faz
  sentido depois de normalizar cada série pela **própria** mediana de 30 dias — que é exatamente o
  que o classificador faz. Feita assim, a comparação é legítima; feita em nível, é erro.
- **Amplitude de 1 minuto é dominada por microestrutura.** Em barras de um minuto de mercados menos
  líquidos, `H` e `L` podem ser um único negócio no topo do book. Parkinson herda o spread; o
  fechamento também, mas de outro jeito. Isso pode inverter o veredito de eficiência em cripto de
  cauda longa — é justamente o que a medição responde.
- **Custo de manter duas verdades.** Se calcularmos os três e publicarmos um, alguém vai ler o
  errado. Se calcularmos os três e publicarmos os três, criamos três definições do mesmo nome — o
  que o próprio `series.py` já proíbe para features.

## Segunda opinião (Astra)

Revisão de 2026-09-06. **Três correções aceitas e aplicadas acima:**

1. **Os fatores de eficiência não se transferem.** 5,2× / 7,4× / 6× são relativos ao estimador
   close-to-close **de σ**, sob movimento browniano; o nosso é média de |retorno|, outro funcional.
   Eu estava a um passo de escrever "o nosso é 5× pior", que seria número inventado. O texto agora
   diz apenas o que é verificável: usa menos informação da barra.
2. **`E|X| = σ√(2/π)` exige média zero.** Declarado.
3. **A H-KB0028, como estava, media a coisa errada.** Discordância de rótulo é sensibilidade, não
   precisão; sem gabarito observável não há como eleger "o mais preciso". A hipótese foi rebaixada
   de propósito e o desenho que responderia precisão está descrito, sem ser prometido.

**Concordância:** que a escolha do estimador tenha sido deliberada (exatidão em `Decimal`, sem
reivindicar normalidade) é boa engenharia, e a nota não a critica — só torna o custo explícito.

## Relacionados

[[KB-0027-aglomeracao-de-volatilidade-o-que-ela-licencia]] ·
[[KB-0032-o-relogio-dentro-do-limiar-de-volatilidade]] ·
[[KB-0007-atr-e-escala-por-volatilidade]] · [[KB-0018-volume-relatado-e-o-denominador-que-usamos]] ·
[[Strategy Backlog]] · [[Registro de Tentativas]]
