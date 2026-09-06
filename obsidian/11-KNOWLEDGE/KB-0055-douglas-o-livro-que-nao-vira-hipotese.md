---
tags: [knowledge, nota, livros, processo]
tema: psicologia de trading / regra de processo
fonte: Mark Douglas, *Trading in the Zone* — descrições públicas do argumento
fonte_url: https://www.goodreads.com/book/show/85366.Trading_in_the_Zone
lido_em: 2026-09-06
evidencia: anedótico
hipotese_testavel: não
astra: concorda
---

# Douglas: o livro que não vira hipótese — e o que dele vira regra de processo

## O que afirma

O argumento é sobre a cabeça de quem opera, não sobre o mercado. Cada operação isolada tem resultado
desconhecido; o que existe é uma **distribuição** de resultados ao longo de muitas operações, e a
consistência vem de aceitar o risco **antes** de entrar, em vez de reagir a cada resultado
individual. A maior parte do prejuízo, na tese dele, vem de o operador quebrar as próprias regras
depois de uma sequência ruim — ou boa.

Ressalva de fonte: síntese do argumento a partir de descrições públicas. **O livro não foi lido nesta
rodada**, e por isso nenhum número dele é citado — e eu também **não afirmo** que ele não contenha
medição nenhuma, porque não sei.

## Onde foi mostrado

**No material que consultei, em lugar nenhum** no sentido em que esta base usa a palavra: não vi
amostra, grupo de controle nem teste. É argumento sobre operadores humanos discricionários, dirigido
a eles.

## Como mediríamos aqui

**Não mediríamos, e é por isso que esta nota existe.** O Lab de sombra não tem humano no laço: a
`momentum_v1` é código determinístico, avaliada por um worker, com parâmetros congelados numa
`strategy_version` auditada. Não há hesitação, não há medo de perder, não há vingança depois de um
stop. Atribuir o resultado de um algoritmo a psicologia sem observar decisão humana nenhuma é o erro
que a Astra nomeou para este livro, e é o motivo de esta nota **não ter hipótese**.

O que sobra é real, mas é sobre **nós dois**, não sobre a estratégia — e as quatro regras abaixo já
existem no projeto. (Que já existam não prova que funcionem; prova apenas que a preocupação não é
nova.)

1. **Aceitar o risco antes** vira, aqui, **declarar o critério antes da janela**: parâmetros, δ,
   início e fim, escritos no [[Registro de Tentativas]] antes de qualquer coleta. Distinção que a
   revisão exigiu e que eu tinha apagado: **monitoramento descritivo diário continua permitido** — o
   que é tentativa inválida é a **conclusão inferencial antecipada** ou a parada oportunista quando o
   número fica bonito.
2. **Pensar em distribuição, não em resultado** vira o **limiar editorial**: abaixo de 100 outcomes
   avaliáveis **e** 30 dias distintos, só descrição e "inconclusivo". E, acima dele, ainda é pesquisa
   — nunca promessa.
3. **Não mudar a regra no meio** vira a proibição de reparametrizar uma coorte viva: conteúdo
   diferente é `EXP` novo, ligado ao antigo, e nunca edição do anterior.
4. **A tentação humana que existe de fato neste projeto tem nome:** ativar uma variante porque um
   número ficou bonito. É exatamente o que a regra do plantão proíbe — nenhum turno ativa,
   deprecia ou reparametriza uma `strategy_version` por causa de um número; ativação é ato auditado,
   com pré-requisitos provados, e é decisão do Everton quando muda o que o produto faz.

## Hipótese testável no Lab

**Nenhuma.** Esta é uma **nota de leitura**, não uma nota de estratégia, e a distinção está na regra
da própria base: "uma nota sem hipótese testável é uma nota de leitura". Propor um braço de sombra em
nome de Douglas seria inventar uma hipótese para justificar a existência da nota — o oposto do que
esta rodada deveria produzir.

## Por que pode falhar

O risco desta nota não é errar uma medição; é **virar desculpa**. Um resultado ruim explicado por
"psicologia" ou "disciplina" é um resultado que ninguém precisa investigar. Neste projeto, quando o
Lab dá vermelho, a explicação tem de vir de custo, de amostra, de regra de saída, de proveniência ou
de instrumento quebrado — todas coisas que se medem, e todas com nota própria nesta base.

## Segunda opinião (Astra)

Categoria dela, na curadoria: "disciplina de execução do protocolo; **não proponho hipótese de
retorno de preço em seu nome**". E a armadilha, nas palavras dela: "atribuir resultado de um
algoritmo à psicologia humana sem observar decisões humanas".

Concordamos, sem discussão, que a nota entra na base **sem** linha no [[Strategy Backlog]] e **sem**
linha no [[Registro de Tentativas]].

Na revisão, ela manteve a conclusão e cortou quatro excessos meus: afirmar que o livro "não apresenta
medições" depois de declarar que não o li; chamar o argumento de "experiência clínica" sem fonte;
tratar a existência das regras no projeto como evidência de que elas funcionam; e — o mais
importante na prática — proibir indistintamente "avaliação antes do fim", quando o que o protocolo
proíbe é a **inferência** antecipada, não a leitura descritiva diária
([[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]]).

## Relacionados

[[Index]] · [[Registro de Tentativas]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] ·
[[KB-0046-r-multiplos-e-o-r-que-a-simetria-esconde]] ·
[[KB-0049-walk-forward-que-nao-temos-e-o-nulo-que-nunca-calculamos]] · [[Experiments Index]]
