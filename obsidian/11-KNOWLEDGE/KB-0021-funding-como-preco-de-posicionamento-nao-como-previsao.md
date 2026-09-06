---
tags: [knowledge, nota, perpetuos, funding, base, carry]
tema: Perpétuos: funding, OI, posicionamento
fonte: He, Manela, Ross & von Wachter, "Fundamentals of Perpetual Futures" (arXiv 2212.06888 / SSRN 4301150); Schmeling, Schrimpf & Todorov, "Crypto carry", BIS Working Paper 1087 (abr/2023, rev. out/2025); Gornall, Rinaldi & Xiao, "Perpetual Futures and Basis Risk" (SSRN 5036933); documentação de Mark Price / Price Index da Binance
fonte_url: https://arxiv.org/abs/2212.06888 · https://ideas.repec.org/p/bis/biswps/1087.html · https://www.binance.com/en/support/faq/detail/360033525071
lido_em: 2026-09-06
evidencia: estudo revisado e working papers **lidos apenas em nível de resumo** (os PDFs não abriram — ver "fontes que não abriram" no [[Index]]); documentação da corretora lida na íntegra
hipotese_testavel: sim
astra: concorda com ressalvas — quatro retiradas aceitas
---

# Funding e base descrevem posicionamento; descrever não é prever

## O que afirma

A literatura converge num ponto que muda o modo de usar a feature: o funding **não é um prognóstico
da corretora**. É o preço que equilibra, a cada intervalo, a demanda por exposição alavancada contra
o capital disponível para arbitrar a diferença entre o perpétuo e o à vista.

- **He, Manela, Ross & von Wachter** derivam o preço sem arbitragem do perpétuo em mercado sem
  atrito e os **limites quando há custos de negociação**. Empiricamente, os desvios em cripto são
  maiores que em derivativos de moeda tradicionais, **correlacionados entre criptomoedas** e
  **diminuem ao longo do tempo**; a estratégia de arbitragem implícita rende Sharpe alto.
- **Schmeling, Schrimpf & Todorov (BIS 1087)** documentam que o *carry* (a diferença futuro−à vista)
  chega a passar de **40% ao ano**, com enorme variação no tempo, e o atribuem a duas forças:
  demanda de investidores menores que perseguem tendência buscando alavancagem, e **capital de
  arbitragem limitado** por atritos regulatórios e de margem. Eles **também** investigam poder
  preditivo do carry — inclusive para quedas futuras —, o que torna a frase "isto é estado, não
  previsão" simples demais.
- **Gornall, Rinaldi & Xiao** descrevem o mesmo mecanismo pelo lado do desenho do contrato: o
  perpétuo usa pagamentos pequenos e frequentes justamente porque capital de arbitragem restrito e
  demanda especulativa volátil afastam o futuro do à vista.

O enunciado que sobrevive à revisão: funding e base **descrevem um desequilíbrio de posicionamento**
e são preço, não contagem. Não dá para ler deles quantas pessoas estão de um lado — todo contrato
aberto tem os dois lados, e intensidade de demanda não é número de participantes. E **estado não
constitui, sozinho, evidência de capacidade preditiva no nosso horizonte de 4 horas**.

## Onde foi mostrado

Bitcoin e as maiores criptomoedas, em várias corretoras, horizonte de dias a meses. Nada disso é o
nosso recorte — 200 perpétuos USDT, decisões a cada minuto, horizonte de 4 h. A transferência de
horizonte é exatamente o erro que a [[KB-0001-momentum-academico-e-o-que-nao-se-transfere]]
catalogou; aqui vale igual.

## Como mediríamos aqui

Se queremos ler o desequilíbrio com resolução maior que a da liquidação, temos dois candidatos, e a
documentação da corretora impede tratar qualquer um dos dois como "a" medida.

**Candidato 1 — `(mark_price − index_price) / index_price`.** Os dois campos existem em
`market_snapshots` (`market_data.py:84-85`) e no `DerivSnapshot` (`context.py:133-134`). O Mark Price
da Binance é a **mediana de três candidatos**: (a) o índice ajustado por
`última taxa de funding × (tempo até a próxima liquidação / período)`; (b) o índice mais uma média
móvel de 30 s do ponto médio bid-ask menos o índice; (c) o preço do contrato. Eu tinha escrito que
`mark − index` "não serve" por embutir o funding. **Está errado como afirmação geral**: a mediana não
é soma, e o termo de funding só entra quando *aquele* candidato é o selecionado. Sem medir qual
candidato prevalece, não dá para dizer que a diferença é funding "em boa parte do tempo".

**Candidato 2 — `last_index_basis_fraction = (price − index_price) / index_price`**, com `price` o
último negociado (`market_snapshots.price`, vindo de `ticker.last`). Evita inserir explicitamente a
fórmula do funding, mas **não é** o Premium Index da Binance, que é calculado com preços de impacto
do livro, e sofre efeito de spread, de lado agressor e de baixa frequência de negócios em mercados
finos.

Os dois são **medidas distintas**, nenhuma delas independente do funding: o funding altera incentivos
de arbitragem e de negociação, o índice é compartilhado pelas duas (movimento comum garantido), e o
Mark Price governa liquidações, que por sua vez alteram fluxo e preço negociado.

**E há um risco de look-ahead que precisa ser resolvido antes de qualquer análise retrospectiva com
essa tabela.** `market_snapshots.ts` é `align_open_time(observed_at, M1)` (`sampling.py:190`): uma
leitura feita às 12:00:40 é gravada com chave `12:00:00`. Juntar essa linha a uma decisão das
12:00:05 pelo timestamp do minuto **usa informação do futuro**. Além disso, `ticker` e `deriv` são
lidos em pipeline sem transação (`sampling.py:184-189`), então `price` e `index_price` da mesma linha
podem ser de instantes diferentes, mesmo que cada um passe individualmente no filtro de frescor.
Qualquer uso desta tabela em pesquisa precisa do recorte **estritamente anterior** — a mesma correção
que a [[KB-0016-quando-o-fluxo-importa-dependencia-de-estado]] exigiu para `spread_pct`.

## Hipótese testável no Lab

**Etapa 1 — instrumentação, sem decisão.** Calcular e persistir as duas medidas no envelope, com
tratamento explícito de `price` ausente, `index_price` ausente e `index_price` não positivo. Duas
perguntas baratas: qual a cobertura de `index_price` no instante das decisões, e as duas medidas se
separam ou são a mesma coisa com ruído? Comparação com o ponto médio bid-ask entra como diagnóstico
de ruído, **sem** presumir que alguma das três é superior.

**Etapa 2 — só se a etapa 1 mostrar dispersão real.** Estratificar a expectancy dos outcomes já
existentes por decil da medida escolhida no instante da decisão, com a especificação congelada
antes: estratégia, versão e horizonte fixos; cobertura sobre **todos** os sinais elegíveis;
expectancy sobre entradas com outcome líquido avaliável, **incluindo expirados**, e com pendentes,
censurados e custos indisponíveis contados à parte; cortes dos decis congelados antes da validação;
incerteza considerando dependência temporal e entre mercados.

*Refutação, restrita ao que ela pode negar:* equivalência entre os decis **dentro de uma margem
econômica declarada antes** refuta **aquela especificação**. Não fecha a linha "funding/base como
regime" — pouca amostra, relação não monotônica, efeito nos decis intermediários e composição
diferente de mercados produzem o mesmo resultado nulo por motivos distintos.

## Por que pode falhar

- **Horizonte.** Todo o corpo de evidência é de dias a meses; o nosso é de 4 h.
- **Carry ≠ direção.** A arbitragem de Sharpe alto dessas fontes é *cash-and-carry* — vender o
  perpétuo, comprar o à vista, **receber** o funding. Não temos à vista, não temos as duas pernas, e
  não é isso que o Lab testa ([[KB-0022-funding-preve-retorno-a-evidencia-direta-e-fraca]]).
- **Os desvios diminuem com o tempo** (He et al.). Uma edge de 2020–2022 pode não existir em 2026.
- **Índice não é "preço justo".** É cesta ponderada de corretoras, com o preço de qualquer uma que
  desvie mais de 3% da mediana **limitado** a 1,03× ou 0,97× dela, e peso zerado para quem cai.
- **Correlação entre moedas** (He et al.): 200 mercados com prêmios que se movem juntos não são 200
  observações independentes — o mesmo alerta de blocos temporais da
  [[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]].
- **Sincronização.** Os dois riscos acima (chave do minuto e leitura não transacional) invalidam
  silenciosamente uma análise retrospectiva mal recortada.

## Segunda opinião (Astra)

Quatro retiradas exigidas e aceitas: (1) **"não serve"** aplicado a `mark − index` — a mediana de três
candidatos não permite essa generalização sem medir qual prevalece; (2) **"prêmio honesto"** e
**"desequilíbrio de fato"** — `last/index − 1` não é o Premium Index da corretora; (3) **"resolução de
1 minuto contra 8 horas do funding"** — confunde amostragem com liquidação: a taxa estimada chega no
stream `markPrice` a cada segundo (`streams.py:261`); (4) **"sem custos na maior parte das
análises"** — He et al. estudam explicitamente os limites **com** custos, e eu li apenas resumos.
Aceita também a correção conceitual: "há mais gente pagando para ficar comprada" não é inferível de
preço, e "estado não é previsão" vira "estado não constitui, sozinho, evidência de capacidade
preditiva no nosso horizonte" — até porque o próprio BIS relata poder preditivo do carry. Achado
próprio dela, incorporado ao corpo da nota: o risco de look-ahead da chave por minuto e a leitura não
transacional de `ticker` e `deriv`.

Divergência: nenhuma que sobreviva às correções — ela manteria **as duas** medidas como distintas em
vez de escolher uma, e eu adotei isso.

## Relacionados

[[KB-0019-o-que-a-nossa-funding-rate-mede-de-fato]] ·
[[KB-0022-funding-preve-retorno-a-evidencia-direta-e-fraca]] ·
[[KB-0024-open-interest-como-posicionamento-evidencia-e-folclore]] ·
[[KB-0016-quando-o-fluxo-importa-dependencia-de-estado]] ·
[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] ·
[[Strategy Backlog]] · [[Features]] · [[Market Collector]]
