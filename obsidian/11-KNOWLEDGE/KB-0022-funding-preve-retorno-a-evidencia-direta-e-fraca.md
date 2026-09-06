---
tags: [knowledge, nota, perpetuos, funding, previsibilidade]
tema: Perpétuos: funding, OI, posicionamento
fonte: Presto Research, "Can Funding Rate Predict Price Change?"; He, Manela, Ross & von Wachter (arXiv 2212.06888); "Cryptocurrency as an Investable Asset Class" (arXiv 2510.14435, **lido só em resumo de busca**)
fonte_url: https://www.prestolabs.io/research/can-funding-rate-predict-price-change · https://arxiv.org/abs/2212.06888 · https://arxiv.org/abs/2510.14435
lido_em: 2026-09-06
evidencia: pesquisa de praticante com método e amostra declarados (não revisada por pares) + estudo revisado sobre arbitragem; **não replicada por nós**
hipotese_testavel: sim — mas a recomendação é **não gastar braço de sombra** com ela
astra: concorda com ressalvas
---

# Funding prevê retorno? A evidência direta é fraca e desaparece no horizonte à frente

## O que afirma

A pergunta que interessa ao Lab não é "funding é caro" (isso é
[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]]) nem "funding descreve posicionamento" (isso é
[[KB-0021-funding-como-preco-de-posicionamento-nao-como-previsao]]). É: **a taxa de funding, lida no
instante da decisão, ajuda a prever o retorno seguinte deste mercado?**

A melhor evidência direta que localizei nas fontes consultadas é da Presto Research, na Binance
USDⓈ-M, entre o início de 2021 e o início de 2024. **A leitura precisa importa mais que a
conclusão**, e a minha primeira redação errou nela (correção da Astra):

- A parte **temporal** do estudo é sobre **BTC**, usa a **variação** da taxa (não o nível) e
  janelas **semanais**. Contemporaneamente, essas variações explicam cerca de **12,5%** da variação
  do preço na mesma janela (R² = 0,125): associação **no mesmo intervalo**, o mesmo tipo de achado
  que a [[KB-0011-volume-magnitude-e-a-ponte-para-direcao]] catalogou para volume — descrição
  simultânea, não previsão.
- **À frente** — variação em `T` prevendo a variação de preço em `T+1` — não há poder preditivo
  aproveitável, e o **p-valor relatado é grande**. (Eu tinha escrito "estatisticamente detectável,
  praticamente irrelevante"; está errado e sai.)
- A parte **transversal** é a que usa os **top 50 líquidos**: um alfa com
  `decay_linear(funding, 24) − decay_linear(funding, 6)`, neutralizado pelo **universo**
  (`IndClass.universe`, não por setor, como eu tinha escrito), com métricas anualizadas favoráveis —
  mas com **giro diário altíssimo** e **sem custo de transação nenhum no teste**. Com 20 bps por
  ida e volta ([[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]]) e giro dessa ordem, "favorável" vira
  uma conta que ninguém mostrou.

**E o estudo não testa o que nós faríamos.** Ele não mede *nível atual de funding → retorno em 4 h
neste mercado*. Ele mede outra variável, noutro universo, noutro horizonte. Serve como **prior
desfavorável**, não como refutação da nossa pergunta — descartar a hipótese com base nele seria
exatamente o erro que esta nota está tentando evitar.

E há uma confusão que precisa morrer aqui, porque ela é a origem de metade do entusiasmo com
funding: **ganhar funding não é prever preço**. As estratégias de *carry* com Sharpe alto que a
literatura relata são *cash-and-carry* — vender o perpétuo e comprar o à vista, ficar neutro em preço
e **receber** a taxa. Duas pernas, dois mercados, exposição direcional zero. Nós temos uma perna, um
mercado e exposição direcional total. Nenhum daqueles números se transfere.

## Onde foi mostrado

Binance USDⓈ-M, 2021–2024: **BTC** e janelas de 7 dias na parte temporal, **top 50 por liquidez** e
dados de 5 min na parte transversal. Perto do nosso universo em mercado e corretora, longe no
horizonte e na variável.

Sobre o carry, o material que encontrei relata Sharpe alto no período completo e queda nos anos
recentes. **Não confirmei nenhum desses números na fonte primária** — o PDF do arXiv não abriu de
forma legível e o que tenho é resumo de busca —, então esta nota **não cita valores** e não apoia
nada neles.

## Como mediríamos aqui

Temos `funding_rate` no `MarketContext` e ela **computa** (ao contrário de `funding_change_8h` —
[[KB-0020-funding-change-8h-nunca-calcula]]), porque só depende do snapshot atual do hash `deriv`.
O que falta é persistir a leitura no envelope imutável do sinal, junto com `funding_kind` e a fase do
ciclo ([[KB-0019-o-que-a-nossa-funding-rate-mede-de-fato]]).

Com isso, e **só com isso**, dá para responder à pergunta de forma barata e sem gastar tentativa de
estratégia: a distribuição de `funding_rate` no instante das nossas decisões, e a associação dela com
o resultado de cada acompanhamento, com todos os modos de saída separados (alvo, stop, invalidado,
expirado, censurado) e com os denominadores que a S4 fixou.

## Hipótese testável no Lab

**A recomendação desta nota é não abrir braço de sombra para funding como filtro direcional.** A
evidência direta, no nosso mercado e na nossa corretora, aponta para ~zero à frente; abrir um braço
seria gastar uma tentativa do orçamento de multiplicidade
([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]) contra uma prior explicitamente
desfavorável.

O que **entra** é um diagnóstico, registrado como tal:

- **D — associação de `funding_rate` (no instante da decisão) com o resultado**, condicionada ao
  sinal da taxa (positiva e negativa são estados diferentes, não extremos de uma escala simétrica),
  sobre a população de outcomes avaliáveis, com cobertura declarada e cortes congelados antes.
- Se — e só se — esse diagnóstico mostrar separação econômica relevante numa direção que faça
  sentido mecanicamente, aí se escreve uma candidata prospectiva, com período futuro reservado.

*O que refutaria a premissa desta nota:* separação clara e monotônica entre faixas de funding na
nossa própria população, com cobertura alta. Aí a evidência externa não descreve o nosso recorte, e
o diagnóstico vira candidata.

## Por que pode falhar

- **Confundir contemporâneo com preditivo.** R² = 0,125 na mesma janela não é 12,5% de previsão. É a
  mesma armadilha da [[KB-0011-volume-magnitude-e-a-ponte-para-direcao]].
- **Confundir nível com variação.** O estudo mede **variação** da taxa; a nossa pergunta é sobre o
  **nível** no instante da decisão. São variáveis diferentes, e tratar uma como evidência sobre a
  outra é o mesmo erro de leitura que a Astra encontrou na primeira redação desta nota.
- **Transversal ≠ por mercado.** O único resultado positivo é comparativo entre moedas. A nossa
  decisão é por mercado, isolada, sem carteira e sem neutralização — a estrutura que gerou o alfa não
  existe no Lab ([[EXP-0001-momentum-v1]]: PnL e drawdown de carteira são "não aplicável").
- **Custos ausentes no teste alheio.** Giro altíssimo sem custo é o cenário clássico de alfa que
  desaparece na primeira taxa.
- **Prior desfavorável não é prova.** Ausência de previsibilidade *naquela* especificação e naquele
  horizonte não demonstra ausência na nossa. Por isso a saída é diagnóstico, não descarte.
- **Fonte não revisada por pares.** O trabalho da Presto tem método e amostra declarados, o que é
  mais do que a maioria do material de corretora, mas não passou por revisão nem foi replicado.

## Segunda opinião (Astra)

Ela achou um erro de leitura da fonte que invertia o alcance da conclusão, e a nota foi reescrita por
causa disso: a análise **temporal** da Presto é de **BTC**, sobre a **variação** do funding, em
janelas semanais; o universo dos **top 50** pertence ao alfa **transversal**. Correções aceitas: (1)
separar as duas análises; (2) retirar "estatisticamente detectável" — o p-valor relatado é grande;
(3) corrigir "neutralizado por setor" para neutralização por **universo** (`IndClass.universe`); (4)
retirar os números de Sharpe do carry, que eu só tinha em resumo de busca; (5) dizer "não localizado
nas fontes consultadas" em vez de "não existe teste".

Must-fix dela com o cenário de falha, aceito e incorporado ao corpo: **descartar a nossa hipótese com
base num teste de outra variável, outro universo e outro horizonte**. Por isso a nota passou a
enunciar a evidência externa como *prior desfavorável* e a manter o diagnóstico próprio.

Divergência: nenhuma. Ressalva registrada: para ela, diagnóstico exploratório **também** consome
multiplicidade — o que já é a regra desta base desde a
[[KB-0015-volume-relativo-e-o-pico-como-exaustao]].

## Relacionados

[[KB-0021-funding-como-preco-de-posicionamento-nao-como-previsao]] ·
[[KB-0023-funding-extremo-como-contrarian-a-afirmacao-mais-repetida]] ·
[[KB-0011-volume-magnitude-e-a-ponte-para-direcao]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] ·
[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] ·
[[Strategy Backlog]] · [[Registro de Tentativas]] · [[EXP-0001-momentum-v1]]
