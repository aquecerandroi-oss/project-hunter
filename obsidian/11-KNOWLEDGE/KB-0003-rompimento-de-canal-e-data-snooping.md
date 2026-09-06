---
tags: [knowledge, nota, rompimento, backtest]
tema: Momentum e rompimentos
fonte: Lukac, Brorsen & Irwin (1988); Park & Irwin, "What do we know about the profitability of technical analysis?" (Journal of Economic Surveys, 2007); Hudson & Urquhart, "Technical trading and cryptocurrencies" (Annals of Operations Research, 2021)
fonte_url: https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1467-6419.2007.00519.x · https://link.springer.com/article/10.1007/s10479-019-03357-1 · https://farmdoc.illinois.edu/assets/marketing/agmas/AgMAS05_04.pdf
lido_em: 2026-09-06
evidencia: estudo revisado (revisão de literatura)
hipotese_testavel: sim
astra: concorda
---

# Rompimento de canal: a regra mais testada do mundo, e o problema que isso cria

## O que afirma

O rompimento de canal — comprar quando o preço supera a máxima das últimas N barras — é uma das
regras técnicas mais antigas e mais estudadas. Lukac, Brorsen & Irwin (1988) encontraram, em 12
mercados futuros entre 1978 e 1984, retornos de portfólio estatisticamente significativos da ordem
de 3,8% a 5,6% para vários sistemas técnicos, incluindo o canal de preço, e trabalhos do mesmo grupo
relatam retornos líquidos mensais de 1,89% a 2,78% para os sistemas mais fortes daquele período.

O contraponto é maior que o resultado. Park & Irwin (2007) revisaram 95 estudos modernos: **56
positivos, 20 negativos, 19 mistos** — e concluem que a maior parte sofre de problemas de
procedimento: *data snooping*, seleção **ex post** das regras ou da tecnologia de busca, e
dificuldade em estimar risco e custos de transação. Pouquíssimos estudos tratam correção de
snooping, custos e risco **ao mesmo tempo**. Em cripto, Hudson & Urquhart testaram cerca de 15.000
regras técnicas de cinco classes e, depois de quatro correções de múltiplas hipóteses, entre 20,35%
e 50,41% das regras permaneceram significativas, com custos de equilíbrio acima dos custos
efetivamente praticados.

## Onde foi mostrado

Futuros americanos, dados diários, 1978–1984 e janelas posteriores (Lukac et al.); universo amplo de
mercados e décadas na revisão (Park & Irwin); Bitcoin e outras três criptos, dois mercados de BTC,
em Hudson & Urquhart. Ressalva registrada pela Astra a partir do §5 do artigo — **o PDF completo não
abriu nesta sessão**, então isto está anotado como leitura dela e não como leitura minha: as regras
vencedoras apresentaram desempenho **negativo fora da amostra** nos dois mercados de Bitcoin.
Significância corrigida não é validação prospectiva.

## Como mediríamos aqui

A `momentum_v1` usa `lookback_closes = 20`: o nível é a **máxima dos 20 fechamentos** de 15 minutos
anteriores — rompimento **de fechamentos**, não da máxima intrabar
(`packages/core/hunter_core/strategies/momentum_v1.py`). O 20 não veio de medição; veio de
convenção. A lição de Park & Irwin aplicada ao nosso caso é direta: **um comprimento de janela
escolhido e depois defendido pelo resultado é exatamente o mecanismo que a literatura acusa.**

## Hipótese testável no Lab

**Família pré-especificada `momentum_lookback_10_20_40`** — três coortes idênticas à `momentum_v1`
em tudo (geometria, custos, horizonte, invalidação), diferindo só em `lookback_closes` = 10, 20 e 40,
rodando **ao mesmo tempo**, sobre os mesmos mercados e minutos.

- Três `strategy_version_id` distintos, todos em `cohort = prospective`. É obrigatório: o estado de
  reentrada é isolado pela tripla `(strategy_version_id, market_id, cohort)`
  (`services/strategy-worker/hunter_strategy_worker/slots.py`), então mudar só o parâmetro sob a
  mesma tripla faria uma variante **bloquear** a outra.
- O que se compara não são três parâmetros: são **três políticas completas de entrada e reentrada**,
  porque a janela muda também quando a condição fica falsa e, portanto, quando o episódio rearma
  (`episodes.py`). Os trades **não** serão pareáveis um a um.
- **Publica-se a família inteira, sempre.** Nunca a melhor das três sozinha. O número de tentativas
  entra no critério.
- Métrica primária: expectancy líquida em R por entrada encerrada avaliável. **Não** Sharpe: Sharpe
  exige série de retornos e convenção de capital, e o Lab declara não ter carteira
  (`docs/plans/SHADOW-LAB.md`).
- Inferência: reamostragem em **blocos temporais comuns às três variantes**, carregando todos os
  mercados juntos em cada réplica (é assim que a dependência entre observações simultâneas é
  preservada), com os três contrastes pareados recalculados por réplica. Intervalos **simultâneos**
  de 95% por bootstrap max-t (Romano–Wolf), que tratam dependência e multiplicidade de uma vez.
- **Refutação em três resultados**, com margem `δ` pré-registrada: todos os ICs dentro de
  `[−δ, +δ]` → equivalência prática nesta população; algum IC inteiramente além de `±δ` → diferença
  relevante sustentada; qualquer outro caso → **inconclusivo**.

## Por que pode falhar

- **Confundir inconclusão com irrelevância.** Era o erro da minha proposta original ("se a dispersão
  for da ordem do erro amostral, o parâmetro não é informativo"). Com poucos dias, os intervalos são
  largos por construção; declarar o parâmetro irrelevante descartaria diferenças que a amostra
  simplesmente não resolve.
- **Tratar as três coortes como amostras independentes.** Elas compartilham mercados e minutos: um
  único movimento geral do mercado apareceria como dezenas de confirmações.
- **Comparar expectancy sem frequência.** Uma variante com expectancy alta e pouquíssimas entradas
  não responde qual política é mais útil; frequência, sobreposição, tempo acompanhado e exclusões
  por variante entram no relatório.
- **10/20/40 continuam sendo escolhas experimentais**, não comprimentos que o mercado revelou.
  Precisam ser pré-registradas, junto com o início comum, a regra de encerramento e **todas** as
  tentativas que influenciaram a seleção.

## Segunda opinião (Astra)

Concorda em rodar 10/20/40 simultaneamente como família pré-registrada e em publicar a família
inteira preservando os resultados desfavoráveis. Correções aceitas e incorporadas: (1) a refutação
original estava errada — diferença não significativa é **inconclusão**, não prova de irrelevância;
(2) três `strategy_version_id` distintos são obrigatórios por causa do isolamento em
`slots.py`, e mesmo assim o que se compara são três políticas de reentrada, não três parâmetros;
(3) a dependência entre coortes é vantagem se a inferência for pareada com blocos temporais comuns
e ICs simultâneos max-t, e é armadilha se for ignorada; (4) trocar "expectancy deflacionada" e
"Sharpe" por expectancy em R com inferência ajustada, porque o Lab não tem carteira; (5) nomear
"rompimento **de fechamentos**"; (6) acrescentar a ressalva de desempenho fora da amostra em
Hudson & Urquhart.

Divergência: nenhuma.

## Relacionados

[[Strategy Backlog]] · [[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] ·
[[KB-0004-proximidade-da-maxima-e-confirmacao-por-volume]] · [[EXP-0001-momentum-v1]] ·
[[Strategy Performance]]
