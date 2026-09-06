---
tags: [knowledge, nota, livros, regime, metodo]
tema: momentum vs reversão / pré-teste de série
fonte: Ernest Chan, *Quantitative Trading* e *Algorithmic Trading* — testes de estacionariedade, Hurst, razão de variâncias, meia-vida
fonte_url: https://www.oreilly.com/library/view/algorithmic-trading-winning/9781118746912/
lido_em: 2026-09-06
evidencia: backtest do autor
hipotese_testavel: sim
astra: concorda
---

# O teste antes da regra — e o filtro que já estava dentro da regra

## O que afirma

Chan inverte a ordem habitual: antes de escolher uma estratégia, **teste em que estado a série
está**. A hipótese de trabalho dele é que uma série com autocorrelação positiva de retornos favorece
momentum, e uma série estacionária favorece reversão. Os instrumentos que ele usa para decidir são
estatísticos e não gráficos — teste de raiz unitária (ADF), expoente de Hurst, **razão de
variâncias**, e a meia-vida da reversão estimada por regressão do retorno contra o desvio. Que
aplicar a regra errada ao estado errado seja *a* causa mais comum de backtest bonito virar prejuízo
é retórica dele, não evidência: eu não tenho fonte que ordene as causas, e a prévia aberta que
consultei não sustenta o superlativo (**correção da Astra**).

A segunda metade do argumento dele é sobre honestidade de teste: viés de sobrevivência (testar só o
que continua listado), look-ahead, viés de garimpo de dados, e custos de transação que costumam ser
maiores que o edge.

## Onde foi mostrado

Ações e ETFs americanos, futuros e pares, barras diárias e intradiárias, com backtests do próprio
autor — evidência de qualidade "backtest do autor", não estudo revisado. A parte de pares e reversão
transversal exige duas pernas, hedge e custo combinado; nada disso existe no nosso Lab, que só emite
LONG de perna única.

## Como mediríamos aqui

A razão de variâncias é calculável com o que já temos: sobre os fechamentos de 15m,
`VR(q) = Var(r_q)/(q·Var(r_1))`, com `VR > 1` indicando persistência e `VR < 1` reversão. Mesmo dado,
mesma janela, nenhuma coleta nova.

**Mas há um risco que esta nota existe para não deixar passar: `VR` e `ER` podem estar altamente
correlacionadas na nossa população, e propor as duas como candidatas separadas gastaria duas
tentativas na mesma ideia — para depois comemorar quando uma "confirmar" a outra.**

Cuidado com a versão forte disso, que eu tinha escrito e a Astra derrubou: **elas não medem a mesma
coisa.** `ER` é deslocamento líquido sobre caminho absoluto; `VR(q) = 1 + 2·Σ_{j<q}(1 − j/q)·ρ_j` é
como a variância cresce com o horizonte, isto é, uma medida de **dependência serial**. O
contraexemplo dela, calculado: vinte log-retornos positivos alternando 1, 2, 1, 2… dão preços
monotônicos, `ER = 1` e `VR(2) = 0`; reordenados em dez "1" seguidos de dez "2", continuam com
`ER = 1` e passam a `VR(2) = 1,894737`. Descartar `VR` como duplicata da `ER` jogaria fora uma
medida de autocorrelação que a `ER` não identifica.

Por isso a proposta desta nota **não é um filtro novo**: é medir a correlação entre `ER(20)` e
`VR(2)`/`VR(4)` na população dos sinais **antes** de qualquer braço, e usar o resultado como **regra
pragmática de priorização** — não como prova de redundância.

### O que esta nota descobriu de fato: a T-001 é redundante

Aplicando o mesmo raciocínio de "isto já não está dentro da regra?" à candidata mais antiga da fila,
o gate de tendência `return_4h > 0` da [[KB-0001-momentum-academico-e-o-que-nao-se-transfere]]:

- a condição de entrada é `close_t > max(C_{t−1} … C_{t−20})` sobre fechamentos de 15m
  (`indicators.py:141`);
- se o último fechamento é maior que **todos** os 20 anteriores, ele é em particular maior que
  `C_{t−16}`;
- 16 barras de 15 minutos são **240 minutos**, e `return_4h` é, por definição, `close_t / close_{t−240min} − 1`
  (`price.py:38`, `indicators.py:147`).

Logo, no instante em que a `momentum_v1` dispara, `return_4h > 0` **já é verdade por construção**,
alinhamento e disponibilidade à parte. O gate não filtraria nada — exceto quando a feature do M2
estivesse indisponível ou defasada, caso em que ele reduziria a amostra por motivo de infraestrutura
e alguém publicaria isso como "benefício da confirmação de tendência".

Ressalva honesta sobre o "à parte": a feature `return_4h` do M2 é calculada sobre velas de **1
minuto** com âncora própria, e o rompimento sobre a agregação de 15m da estratégia. Nos limites de
15 minutos as duas séries coincidem; fora deles, e sob gap, não necessariamente. A redundância é
**quase certa**, não uma identidade demonstrada — e é medível numa consulta.

**Achado da Astra**; conferi as três linhas por conta própria antes de publicar.

### O viés de sobrevivência que não sabemos se temos

Chan insiste no ponto e nós não temos resposta: quando um mercado sai do universo (delist, queda de
liquidez, mudança da regra de seleção), o que acontece com os sinais e outcomes dele? Se a análise
retrospectiva parte de `markets` no estado **atual**, ela mede uma população que exclui exatamente os
mercados que morreram. É o mesmo defeito de proveniência que a
[[KB-0016-quando-o-fluxo-importa-dependencia-de-estado]] registrou para liquidez, só que com
consequência maior. **Não verifiquei o código do refresh de universo nesta rodada** — outra instância
está mexendo nesses arquivos — então isto entra como auditoria, não como afirmação.

## Hipótese testável no Lab

**`D-CHAN-a` — correlação entre medidas de caminho.** Calcular `ER(20)`, `VR(2)` e `VR(4)` sobre os
mesmos 21 fechamentos de 15m no instante de cada decisão registrada; publicar as três distribuições e
a matriz de correlação de postos. **Especificação obrigatória antes de rodar** (exigência da Astra):
log-retornos ou diferenças simples, janelas sobrepostas ou disjuntas, correção de amostra pequena, e
o tratamento de variância zero. Vinte retornos são uma amostra curta para ler `VR > 1` como
evidência de qualquer coisa.

**Regra pragmática de priorização, declarada antes de olhar:** se `|ρ| ≥ 0,8` entre `ER` e algum
`VR`, só a `ER` segue para braço nesta rodada — por parcimônia, e **não** porque a correlação prove
redundância. Correlação alta com `VR(2)` também não elimina informação de `VR(4)`.

**`D-CHAN-b` — auditoria de sobrevivência, no escopo estreito.** Para a população de sinais do Lab:
quantos mercados distintos aparecem, quantos deles ainda estão marcados como monitorados hoje, e
quantos outcomes pertencem a mercados que não estão — separando outcomes **encerrados, censurados e
ainda abertos**. A Astra confirmou que isso é executável com o que existe (`universe_repo.py:106`,
`universe.py:209`, `lab_summary.py:92`, e o resumo do Lab não filtra pelo universo presente). O que
**não** responde: quem saiu e voltou, e se houve viés anterior ao início da coleta. Se nenhum mercado
tiver saído ainda, a pergunta segue **aberta**, não respondida.

**`D-CHAN-c` — redundância da T-001. Não é uma consulta ao envelope** (correção da Astra): a lista de
features que a `momentum_v1` publica inclui `return_15m`, e **não** inclui `return_4h`
(`momentum_v1.py:240`, `record.py:138`). Uma consulta ingênua voltaria "tudo ausente", e alguém leria
isso como indisponibilidade do M2 ou como exceção à redundância. O diagnóstico honesto é
**reconstrução com velas**, com o corte temporal explícito: para cada sinal, recalcular
`close_t / close_{t−240min} − 1` na série de 1 min e publicar a fração positiva, junto com a
cobertura. Previsão declarada: ~100% onde os fechamentos estão alinhados. Se for muito menor, o meu
raciocínio está errado e eu quero saber por qual das três razões (alinhamento, gap, ou a versão
`_live` da feature).

Nenhum dos três é braço de estratégia; nenhum altera decisão.

## Por que pode falhar

1. **`VR` e `ER` medem propriedades diferentes** (ver o contraexemplo acima), e a correlação empírica
   pode ser baixa — caso em que as duas seguem vivas, o que é o resultado certo, não uma falha.
2. **`VR` estimado em 21 pontos é ruído.** A razão de variâncias tem distribuição amostral larga em
   janelas curtas; publicar um número por decisão sem intervalo seria fabricar precisão. O
   ferramental clássico (Lo & MacKinlay) trata explicitamente desses limites amostrais.
2b. **Confundir diagnóstico com autorização.** Que a série esteja "em estado de momentum" não implica
   que uma estratégia de momentum seja lucrativa nela — é hipótese, não licença. Essa conversão
   silenciosa foi o cenário de falha que a Astra nomeou nesta nota.
3. **A parte mais forte de Chan é inaplicável.** Pares, cointegração e reversão transversal exigem
   duas pernas e custo combinado; o Lab emite perna única. Chamar qualquer retorno à média de
   "arbitragem estatística" é o erro que a Astra nomeou.
4. **A redundância da T-001, se confirmada, não valida a `ER` por contraste.** Ela só retira uma
   candidata da fila. São dois fatos independentes.
5. **A auditoria de sobrevivência pode não ter poder ainda**: com poucos dias de história, nenhum
   mercado saiu do universo, e a ausência de evidência não é evidência de ausência.

## Segunda opinião (Astra)

**Foi dela o achado que dá conteúdo a esta nota**: a implicação lógica que torna o gate
`return_4h > 0` redundante com a condição de rompimento, com as linhas (`indicators.py:147`,
`price.py:38`) e com o cenário de falha — "o filtro exclui sinais porque a feature está indisponível
ou atrasada; publicamos isso como benefício da confirmação de tendência". Ela pediu explicitamente a
correção da T-001 no [[Registro de Tentativas]], que esta rodada faz.

Na revisão da nota, **derrubou a minha afirmação mais forte**: "`VR` e `ER` medem quase a mesma
coisa" está errado, e ela provou com dois arranjos dos mesmos vinte retornos que dão a mesma `ER` e
`VR(2)` de 0 e de 1,894737. Também mostrou que a `D-CHAN-c` **não é uma consulta ao envelope**, porque
`return_4h` não está na lista de features que a estratégia publica, e que ler a ausência como
indisponibilidade seria o erro previsível. Confirmou, por outro lado, que a `D-CHAN-b` é executável no
escopo estreito em que ficou escrita, com as linhas.

Sobre Chan, traçou a fronteira: "regras univariadas objetivas podem ser adaptadas; pairs trading e
reversão transversal exigem pernas conjuntas, hedge e custos combinados; entradas LONG já registradas
não avaliam isso". Concordou com o tratamento de Pardo/Aronson/López de Prado como **protocolo**, e
não como três candidatas de alpha — o que é a [[KB-0049-walk-forward-que-nao-temos-e-o-nulo-que-nunca-calculamos]].

## Relacionados

[[Strategy Backlog]] · [[Registro de Tentativas]] ·
[[KB-0047-razao-de-eficiencia-de-kaufman]] ·
[[KB-0001-momentum-academico-e-o-que-nao-se-transfere]] ·
[[KB-0049-walk-forward-que-nao-temos-e-o-nulo-que-nunca-calculamos]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] ·
[[KB-0016-quando-o-fluxo-importa-dependencia-de-estado]]
