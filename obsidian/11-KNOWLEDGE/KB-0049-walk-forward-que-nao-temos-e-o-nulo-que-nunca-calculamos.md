---
tags: [knowledge, nota, livros, metodo, backtest]
tema: validação e estatística de backtest
fonte: Robert Pardo, *The Evaluation and Optimization of Trading Strategies* (walk-forward); David Aronson, *Evidence-Based Technical Analysis* (viés de garimpo, teste de permutação, Reality Check de White)
fonte_url: https://onlinelibrary.wiley.com/doi/book/10.1002/9781118268315
lido_em: 2026-09-06
evidencia: misto — o ferramental estatístico (permutação, Reality Check de White) é estudo revisado; os dois livros são texto de praticante, lidos aqui **só** em página de editora e resumo de capítulo
hipotese_testavel: sim
astra: concorda
---

# O walk-forward que não temos e o nulo que nunca calculamos

## O que afirma

**Pardo:** um backtest em que os parâmetros foram escolhidos olhando o mesmo período é ajuste, não
teste. A resposta dele é o *walk-forward*: otimizar numa janela, validar na janela seguinte que não
foi vista, rolar, repetir — e medir a razão entre o desempenho fora da amostra e o desempenho dentro
dela como indicador de quanto do resultado era ajuste.

**Aronson:** duas coisas, e a segunda é a que importa aqui. Primeiro, só regras **objetivas** podem
ser testadas — o que é subjetivo não é falsificável e portanto não é conhecimento. Segundo, quando se
testam muitas regras sobre o mesmo histórico, a melhor delas parece boa **mesmo que nenhuma tenha
valor**; o remédio é comparar o resultado observado com a distribuição do que um "sem-habilidade"
produziria, por **teste de permutação de Monte Carlo** ou pelo *Reality Check* de White, que ajusta
para o número de regras tentadas.

## Onde foi mostrado

Pardo é texto de praticante, com o argumento de otimização válido para qualquer série. Aronson aplica
o método a **mais de 6.400 regras** de análise técnica sobre o S&P 500, com barras diárias — isso a
página da editora confirma. **O resultado estatístico eu não verifiquei em fonte primária:** o resumo
público do capítulo de resultados não o expõe, e a lembrança de que "quase nada sobrevive ao ajuste
para multiplicidade" fica marcada como **de memória, a confirmar**, e não pode ser usada como
evidência contra a análise técnica em geral (**correção da Astra**).

O ferramental (permutação de Monte Carlo, Reality Check de White) é estatística estabelecida e
revisada; a aplicação dele à AT é o livro. E o Reality Check **não é** apenas uma correção pelo número
de tentativas: ele compara o melhor modelo com um benchmark usando a **distribuição conjunta** dos
candidatos. Ter o [[Registro de Tentativas]] completo é necessário para executá-lo, e não suficiente.

## Como mediríamos aqui

Duas conclusões honestas, e elas puxam em direções opostas.

**A primeira: o walk-forward clássico não tem o que rolar aqui.** O Lab de sombra **não otimiza
parâmetros em amostra**. A `momentum_v1` roda com os `default_parameters` congelados numa
`strategy_version` auditada; não há busca, não há janela de treino. A `walk-forward efficiency` de
Pardo precisa de um desempenho "dentro da amostra" que simplesmente não existe. O que existe é a
janela futura reservada do [[Registro de Tentativas]], que já é o equivalente honesto — e que a
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] instalou antes desta rodada.

Onde Pardo volta a morder é **quando as candidatas desta rodada rodarem**: o θ da `ER`, o
`exit_lookback` do canal, o multiplicador do alvo. Cada valor escolhido depois de olhar dado é uma
otimização, e aí a janela reservada deixa de ser burocracia e vira a única coisa que separa
descoberta de ilusão.

**A segunda, e é a contribuição de fato desta nota: o Lab não tem um grupo de comparação.** Hoje,
quando uma avaliação diz "expectancy líquida hipotética de −0,08 R", a única referência é o **zero**.

Zero não é o nulo errado — **correção da Astra, e eu tinha escrito o contrário.** Zero continua sendo
a referência certa para a pergunta "isto é lucrativo depois de custos?", e ganhar de um controle de
−0,30 R com −0,08 R **não demonstra rentabilidade nenhuma**. O que falta é uma **segunda** referência,
que responde outra pergunta: *o que as mesmas regras de saída produziriam sobre os mesmos mercados,
nos mesmos horários, se a seleção do instante não fosse a nossa?* Sem ela não dá para separar o que
vem da regra de entrada do que vem das regras de saída, dos custos ou da deriva do mercado no
período.

## Hipótese testável no Lab

**`D-NULL` — benchmark aleatório condicionado, sobre a mesma maquinaria.** Não é braço de estratégia
e não altera decisão nenhuma. **O nome importa:** não é um teste de permutação validado, porque o
sorteio não demonstra a intercambialidade que um p-valor exigiria (**correção da Astra**).

Para cada sinal real, sortear `K` instantes de entrada alternativos **no mesmo mercado, no mesmo
balde de hora UTC e no mesmo bloco de calendário**, e rodar sobre eles exatamente o mesmo
acompanhamento: stop, alvo, horizonte, invalidação, custos assumidos, convenção de saída na abertura
seguinte.

**A pergunta que ele responde, escrita sem margem:** *dentro da população elegível — mesma `rvol`,
mesma faixa de `atr_pct`, mesmo retorno positivo —, selecionar o rompimento melhora o resultado sob
esta política de saída?* Isso **não** é "entrada sem informação nenhuma": os filtros preservados podem
carregar informação por conta própria. E a escolha fica explícita: o controle **não exige** o
rompimento; ele **não exige a ausência** dele — são desenhos diferentes, e este é o primeiro.

Cinco requisitos, e os quatro primeiros vieram da revisão da Astra:

1. **A invalidação depende do rompimento, e isso contamina o controle.** Sem rompimento, a referência
   pode estar **abaixo** de `B` (o máximo dos 20 fechamentos anteriores), e o walker invalida quando
   um fechamento posterior fica abaixo desse nível, mesmo sem cruzamento de cima para baixo
   (`walker.py:136`). Consequência: controles encerrados no primeiro fechamento de 15 min só porque
   já nasceram abaixo de `B`. **Cenário de falha:** vender isso como poder preditivo da entrada,
   quando o que se mediu foi a interação entre entrada e invalidação. Ou se declara que o contraste
   inclui essa interação, ou se acrescenta uma comparação com saídas independentes do rompimento.
2. **Deriva e regime não se equilibram com mercado e hora.** Se os sinais se concentram numa semana
   de alta e os controles numa de queda, o contraste mistura seleção temporal, regime e rompimento.
   Blocos de calendário fixos são obrigatórios, e **blocos para calcular incerteza não corrigem esse
   desequilíbrio** — são coisas diferentes.
3. **A estatística tem de ser declarada antes de `K`.** `K × N` outcomes **não** são observações
   independentes; tratar assim produz precisão fictícia. Antes de escolher `K`: qual é a estatística
   (média por sinal? diferença pareada?), a ponderação, se há reposição, como os blocos são conjuntos
   entre mercados, e o que se faz quando um sinal não tem candidatos suficientes. Se a pretensão for
   reproduzir a estratégia completa, é preciso reproduzir também ocupação e rearme de episódios
   (`episodes.py:62`).
4. **Elegibilidade histórica não vem só das velas.** As avaliações sem sinal não persistem observação
   individual (`decide.py:155`) e o universo é sobrescrito no refresh (`universe_repo.py:169`). Logo
   os controles são **replay reconstruído**, e têm de ser rotulados assim, publicando cobertura,
   `no_entry`, censura e funding indisponível junto.
5. **Reamostragem em blocos de tempo** para a incerteza, porque mercados simultâneos são dependentes
   (`SHADOW-LAB.md` §9, detalhado em
   [[KB-0051-tres-barreiras-mais-uma-e-a-amostra-que-nao-e-independente]]).

**Critério, declarado antes:** o quantil da distribuição de controle contra o qual o observado será
lido, escrito no [[Registro de Tentativas]] antes de rodar. "Cair no corpo da distribuição" não é
critério, e **não rejeitar não demonstra equivalência**.

## Por que pode falhar

1. **Custo computacional.** Centenas de réplicas por sinal, com o acompanhamento inteiro, é uma
   ordem de grandeza acima de tudo que o Lab roda hoje. `K` menor tem menos resolução na cauda —
   mas `K` só é escolhido **depois** da especificação do item 3 acima.
2. **O controle pode ser mal especificado.** Se o sorteio ignorar que a estratégia só dispara sob
   `rvol ≥ 1,5` e `atr_pct` na faixa, ele mistura instantes que a estratégia jamais consideraria — e
   a comparação fica fácil demais a nosso favor. A versão defensável **condiciona o sorteio aos
   filtros de elegibilidade**, deixando de fora só a condição de rompimento; e isso muda a pergunta,
   como está escrito acima.
3. **O benchmark não corrige multiplicidade.** Ele dá a referência de **uma** regra; o Reality Check
   de White é o que compara o melhor candidato com o benchmark usando a distribuição conjunta, e
   para isso é preciso que o [[Registro de Tentativas]] esteja completo — necessário, não suficiente.
4. **Não é `walk-forward`.** Chamar este diagnóstico de validação fora da amostra seria errado: ele
   roda na mesma população, e a confirmação continua exigindo janela futura reservada.
5. **Aronson testou outra coisa.** Índices de ações, barras diárias, regras univariadas. O resultado
   negativo dele é prior desfavorável para análise técnica em geral, não refutação da nossa
   estratégia.

## Segunda opinião (Astra)

Na curadoria da rodada ela pôs Pardo, Aronson e López de Prado juntos numa categoria explícita:
"entram como **protocolo**, não como três candidatas de alpha — validação temporal, regras
falsificáveis, controle da busca e tratamento de dependência". E nomeou as armadilhas: **escolher a
janela pelo resultado**, **omitir tentativas** e **separar aleatoriamente observações dependentes**;
acrescentou que purgar intervalos não torna a amostra inteira independente.

Foi essa classificação que fez esta nota deixar de ser resenha e virar uma proposta única — o
benchmark — em vez de três diagnósticos concorrentes.

Na revisão da nota ela **derrubou duas coisas minhas e reescreveu uma terceira**:

- **"zero é o nulo errado" é falso.** Zero segue sendo a referência para "isto é lucrativo?"; o
  benchmark responde outra pergunta, e ganhar de um controle negativo não demonstra rentabilidade.
- **"teste de permutação" é nome grande demais** para o que eu descrevi: é um **benchmark aleatório
  condicionado**, e sorteio não estabelece intercambialidade para interpretar p-valor.
- E listou os quatro defeitos concretos da especificação — invalidação dependente do rompimento,
  deriva de calendário, estatística indefinida com `K × N` tratado como independente, e elegibilidade
  histórica que não vem só das velas —, todos incorporados como requisitos 1 a 4. Também concordou em
  **não** calcular eficiência walk-forward fictícia sem otimização em amostra.

## Relacionados

[[Strategy Backlog]] · [[Registro de Tentativas]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] ·
[[KB-0051-tres-barreiras-mais-uma-e-a-amostra-que-nao-e-independente]] ·
[[KB-0048-o-teste-antes-da-regra-e-o-filtro-que-ja-estava-dentro]] ·
[[KB-0003-rompimento-de-canal-e-data-snooping]] · [[Experiments Index]]
