---
tags: [knowledge, nota, livros, metodo, backtest]
tema: rotulagem e dependência da amostra
fonte: Marcos López de Prado, *Advances in Financial Machine Learning* — método das três barreiras, unicidade da amostra, purga e embargo
fonte_url: https://en.wikipedia.org/wiki/Meta-Labeling
lido_em: 2026-09-06
evidencia: descrição de método em fontes abertas identificadas (o livro não foi lido)
hipotese_testavel: sim
astra: concorda
---

# Três barreiras mais uma — e a amostra que não é independente

## O que afirma

Em vez de rotular um retorno num horizonte fixo, López de Prado propõe rotular pelo **que acontecer
primeiro** entre três barreiras: um nível de lucro, um nível de perda e um limite de tempo. É a
forma correta de rotular quando a posição tem stop e alvo, porque o rótulo passa a corresponder ao
que de fato aconteceria.

A segunda metade do argumento é a que quase todo mundo ignora: rótulos assim **se sobrepõem no
tempo**, e observações que compartilham barras não são independentes. Ele propõe medir a *unicidade*
de cada amostra, reamostrar respeitando essa unicidade, e — na validação cruzada — **purgar** as
observações cujo intervalo intersecta o conjunto de teste e aplicar um **embargo** depois dele. Sem
isso, a validação vaza informação e o modelo parece melhor do que é.

Ressalva de fonte: **o livro não foi lido nesta rodada.** O que li foram descrições abertas do método
(verbete público sobre meta-rotulagem, artigos que o aplicam e o reimplementam). Nenhum número do
livro entra aqui.

## Onde foi mostrado

Séries financeiras em geral, no contexto de aprendizado de máquina, com exemplos do autor. O método
das três barreiras é uma **definição de rótulo**, não um resultado empírico; a parte de unicidade e
purga é estatística, e vale onde as hipóteses valem.

## Como mediríamos aqui

**O nosso acompanhamento tem a forma de três barreiras — e uma quarta.** `target1`, `stop` e o
horizonte de 14.400 s são as três; a **invalidação** (`close_below` do máximo dos 20 fechamentos
anteriores, `momentum_v1.py:282`) é uma quarta saída, observada no fechamento de 15m e paga na
abertura seguinte (`walker.py:77,136`). Somem-se as convenções de execução por OHLC — precedência
`stop > target > expired > invalidated` dentro da barra, gap adverso saindo na abertura, gap
favorável sem crédito acima de `target1` (`walker.py:12-15`) — e o resultado é **um modelo de três
barreiras acrescido de invalidação e de convenções de preenchimento**, não o método do livro. Dizer
"nós já fazemos triple-barrier" seria confortável e errado. **Correção da Astra.**

**E a dependência da amostra não está onde eu tinha escrito.** A máquina de slots impede dois
acompanhamentos abertos no mesmo `(strategy_version_id, market_id, cohort)` — um por slot, e o
rearme exige uma barra `not_triggered` (`episodes.py`). Logo **não há sobreposição temporal dentro do
mesmo slot**, que é o caso clássico do livro.

O que morde aqui é outra coisa: **dependência transversal**. Cem altcoins reagindo ao mesmo
movimento do BTC no mesmo minuto não são cem observações independentes — e a
[[KB-0034-btc-como-fator-e-o-regime-global-que-e-so-o-btc]] já mostrou que o nosso próprio rótulo de
regime "global" é o BTCUSDT medido de novo. O contrato do Lab **já sabe disso**: `SHADOW-LAB.md` §9
exige incerteza por reamostragem em blocos de tempo, "mercados simultâneos são dependentes". O que
falta não é a regra; é o **número**.

## Hipótese testável no Lab

**`D-CONC` — diagnóstico de concentração temporal. Roda hoje, uma consulta, nenhum pré-requisito.**
O nome importa: ele mede **concentração**, e não tamanho efetivo de amostra (correção da Astra; a
minha primeira versão confundia as duas coisas). Sobre os outcomes já persistidos, juntando
`signal_outcomes` a `agent_signals` pelo `signal_id` (`agents.py:108,153`,
`tracking_repo.py:213`):

1. quantos acompanhamentos estão abertos em cada minuto (mediana, p90, máximo), no intervalo
   `[entry_ts, exit_ts)`, dizendo se minutos vazios entram ou não;
2. a distribuição do número de mercados distintos com entrada no **mesmo minuto** e na **mesma
   hora**;
3. o número de **blocos de tempo** disjuntos que a população cobre, com o tamanho de bloco declarado
   antes (por exemplo, 1 h e 4 h), atribuindo cada outcome ao bloco da **entrada**, e quantos
   outcomes caem em cada bloco;
4. **outcomes por bloco** — que é o que a razão `nº outcomes / nº blocos` mede, e nada além disso.

Ressalva de instrumento: saída intrabar recebe `candle.close_time` (`walker.py:104`), então a
ocupação é **convencional, por barras**, não a cronologia exata dos negócios.

**Por que isto importa.** O limiar editorial do Lab é **100 outcomes avaliáveis e 30 dias
distintos**. Passar do limiar **nunca significou independência** — o contrato já exige incerteza por
reamostragem em blocos justamente por isso (`SHADOW-LAB.md` §9). O que `D-CONC` acrescenta é saber,
**antes** de o limiar ser atingido, quão concentrada está a população: 100 outcomes espalhados por
80 blocos e 100 outcomes espalhados por 20 blocos sustentam afirmações de precisão muito diferentes,
mesmo cumprindo os dois critérios.

**O que ele NÃO faz** (e eu tinha escrito que fazia): não estima tamanho efetivo de amostra, não mede
correlação e não quantifica perda de informação. Que 100 outcomes possam conter bem menos informação
que 100 observações independentes é **possibilidade fundamentada**, não resultado medido.

**Refutação:** nenhuma — é medição.

## Por que pode falhar

1. **Concorrência não é dependência.** Dois acompanhamentos no mesmo minuto podem ser independentes,
   e dois separados por horas podem não ser (reação sequencial ao mesmo evento). A contagem **não
   é** medida de informação nem de correlação — é medida de concentração. Para correlação de verdade
   seria preciso o `R_net` conjunto por bloco, que exige mais amostra do que temos.
2. **Purgar não torna a amostra independente** (frase da Astra). Purga e embargo tratam vazamento
   entre treino e teste; não criam independência onde há fator comum.
3. **O tamanho de bloco é uma escolha**, e escolhê-lo depois de ver o resultado é a mesma armadilha
   de todas as outras. Declarar antes, no [[Registro de Tentativas]].
4. **A quarta barreira interage com as três.** Comparar a nossa distribuição de rótulos com qualquer
   coisa da literatura de três barreiras é comparar populações diferentes: a invalidação retira
   observações que teriam ido para `target` ou `stop`, e em proporção desconhecida — que é exatamente
   a pergunta da candidata #1 do backlog.
5. **`exit_ts` não existe para acompanhamento censurado ou aberto**, então o item 1 tem cobertura
   parcial e precisa publicá-la junto, como a
   [[KB-0044-o-que-morre-em-dez-segundos]] exigiu para o carimbo.

## Segunda opinião (Astra)

**As duas correções centrais desta nota são dela**, vindas da curadoria da rodada:

- **"não é literalmente triple-barrier"**: há uma saída adicional por invalidação, observada no
  fechamento de 15 min e paga na abertura seguinte, mais as convenções de OHLC — "modelo de três
  barreiras acrescido de invalidação e convenções de execução";
- **a dependência que importa é transversal, não a sobreposição temporal**: `episodes.py` já impede
  dois acompanhamentos no mesmo slot; o cenário de falha que ela nomeou é "tratar cem altcoins
  reagindo ao mesmo movimento do BTC como cem réplicas independentes", que **estreita artificialmente
  a incerteza**. E acrescentou a simetria: ausência de sobreposição não garante independência.

Também apontou que o contrato já exige blocos de tempo mantendo mercados simultâneos juntos
(`SHADOW-LAB.md:19`) — o que transformou esta nota de "propor uma regra" em "medir o que a regra
existente pressupõe".

Na revisão da nota, **derrubou a leitura que eu tinha dado ao próprio diagnóstico**: `nº outcomes /
nº blocos` mede outcomes por bloco, **não** observações independentes — concentrar 100 outcomes de
100 blocos para 10 blocos faz a razão **subir** de 1 para 10, o que inverte o significado que eu
tinha atribuído. Derrubou também o exemplo dos "100 outcomes em 12 blocos de uma hora", que é
incompatível com o critério de 30 dias distintos, e lembrou que passar do limiar **nunca** significou
independência. Confirmou, em compensação, que o diagnóstico é **executável hoje** no nível do schema,
com as linhas de `agent_signals`, `signal_outcomes` e `tracking_repo`.

## Relacionados

[[Strategy Backlog]] · [[Registro de Tentativas]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] ·
[[KB-0052-meta-rotulagem-o-formato-de-todo-filtro-que-propusemos]] ·
[[KB-0049-walk-forward-que-nao-temos-e-o-nulo-que-nunca-calculamos]] ·
[[KB-0034-btc-como-fator-e-o-regime-global-que-e-so-o-btc]] ·
[[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]] · [[EXP-0001-momentum-v1]]
