---
tags: [knowledge, nota, execucao, custos, taxas, perpetuos]
tema: Execução e microestrutura do preenchimento
fonte: Documentação de taxas da Binance (USDⓈ-M Futures, FAQ 360033544231) + `pricing.py`/`envelope.py`
fonte_url: https://www.binance.com/en/support/faq/detail/360033544231
lido_em: 2026-09-06
evidencia: documentação da exchange (página de tabela de tarifas exige login — registrado) + aritmética própria
hipotese_testavel: sim
astra: concorda após correções (recusou a primeira versão)
---

# A taxa de 4 bps não é nem o maker nem o taker do exemplo

## O que afirma

A documentação da Binance descreve, para USDⓈ-M Futures, o exemplo do **usuário comum**: maker
**0,02%** e taker **0,05%** — isto é, **2 bps** e **5 bps**. E há **10% de desconto** quando as taxas
são pagas em BNB nesses contratos, o que leva o taker do exemplo a **4,5 bps**.

Os `fee_bps = 4` do Lab não correspondem a **nenhum desses dois números de exemplo**: ficam 2 bps
acima do maker e 1 bps abaixo do taker. Isso **não** significa que não correspondam a nenhuma tarifa
real — a tarifa efetiva de uma conta depende de VIP, BNB e promoções, e eu não a conheço. O que se
pode afirmar é mais estreito e ainda assim relevante: **a hipótese do Lab foi escolhida sem
referência a nenhum dos dois lados da tabela, e o modelo de preenchimento que ela acompanha é um
cenário de execução agressiva** — deslocamento adverso sobre a abertura na entrada, saída no toque de
stop ou alvo, sem nenhuma modelagem de fila de maker. O modelo não *identifica* uma ordem nem prova
que ela seria taker; ele simplesmente não contém o mecanismo que permitiria um fill de maker.

Convertido: a ida e volta assumida cobra **8 bps de taxa**; a ida e volta ao taker do exemplo, sem
BNB, cobra **10 bps**; com BNB, **9 bps**. Sobre o custo total assumido de 20 bps, a diferença é de
**1 a 2 bps** — cerca de **5% a 10% do custo**, e, num exemplo com 1 R efetivo de 51 bps
([[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]], piso `atr_pct_min = 0,003`, abertura igual à
referência), entre **2% e 4% de 1 R**. Direção declarada: **contra os cenários de 4,5 e 5 bps**, a
hipótese do Lab favorece a estratégia. Contra a tarifa efetiva desconhecida de uma conta real, não
sei dizer.

## Onde foi mostrado

Documentação do produto que operamos, não estudo. **A página da tabela de tarifas
(`binance.com/en/fee/futureFee`) devolveu "No records found" sem login** — registro isso porque o
número vem do FAQ, na forma de **exemplo** ("a Regular User's maker fee is 0.02% and a Regular User's
taker fee is 0.05%"), e o próprio artigo declara que as taxas dos exemplos são hipotéticas e remete à
tabela real. Um número de exemplo numa página de suporte é boa evidência para a ordem de grandeza e
**não** é a tarifa que a nossa conta pagaria: nível VIP, saldo de BNB, programas promocionais e o par
específico mudam isso.

Precisão que evita erro de citação: as taxas de futuros incidem sobre o **notional** da posição, não
sobre a margem; e são **separadas** do funding, que é transferido entre traders
([[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]]).

## Como mediríamos aqui

`fee_fraction(costs) = costs.fee_bps / 10000` e `r_net` cobra a taxa **fora** dos preços, nas duas
pernas (`pricing.py:41-44,62-79`). Trocar a hipótese é mudar um campo de `AssumedCosts` — que é
**parte da versão congelada** da estratégia (`envelope.py:45-57`). Portanto não é edição: é uma versão
nova, com ativação auditada. Isso é uma feature do desenho, não um obstáculo.

Aritmética **de exemplo**, com o 1 R efetivo de 51 bps do piso `atr_pct_min = 0,003` da
[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]]. **51 bps não é o denominador de todo trade no piso**
— é o do caso sintético com abertura igual à referência:

| Hipótese de taxa | ida e volta (taxa) | custo total ida e volta | fração desse 1 R | ΔR contra o Lab |
|---|---|---|---|---|
| 4 bps/lado (Lab hoje) | 8 bps | 20 bps | 39,22% | — |
| 4,5 bps/lado (taker do exemplo, c/ BNB) | 9 bps | 21 bps | 41,18% | −0,01961 R |
| 5 bps/lado (taker do exemplo) | 10 bps | 22 bps | 43,14% | −0,03922 R |

Para **cada** outcome, o efeito exato de mudar a taxa não passa por essa tabela; passa pela cobrança
implementada em `pricing.py:74`:

```
ΔR = − Δfee × (E + X) / (E − S)
```

com `E = P_entry`, `X = P_exit`, `S` o stop inicial. Um trade cuja entrada ficou longe do stop tem
denominador maior e sente menos; um trade apertado sente mais.

E o efeito sobre o ponto de equilíbrio da [[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] (57,77% de
alvos entre os toques resolvidos, com as médias observadas): o custo maior **desloca a barra para
cima**, não para baixo. A distância entre os 53,73% observados e a barra aumenta.

## Hipótese testável no Lab

**`EXEC-C` — sensibilidade a taxa, não recalibração.** Recomputar `R_net` de **todos** os
encerramentos já avaliáveis com `fee_bps ∈ {4; 4,5; 5}`, mantendo tudo o mais congelado, e publicar
a expectancy líquida hipotética nas três hipóteses lado a lado, com a mesma população e as mesmas
censuras. É análise de sensibilidade sobre resultado já colhido — **não** é variante nova, não gasta
braço de sombra e não sofre o preço de multiplicidade da
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]].

**Alvo declarado antes:** se a expectancy for negativa nas três, a conclusão é que a hipótese de taxa
**não explica** o vermelho, e a nota se encerra. Se ela virar de sinal entre 4 e 5 bps, o resultado
publicado até hoje está dentro do erro da própria hipótese de custo, e **isso** precisa aparecer em
todo relatório do Lab.

**Candidata prospectiva, se e quando houver decisão de execução real:** entrada por **post-only
(GTX)** paga maker (2 bps) em vez de taker, mas troca custo por **risco de não executar** — e isso é
outra estratégia, não a mesma mais barata. Fica em
[[KB-0039-tipos-de-ordem-e-o-que-a-sombra-assume-sem-dizer]], não aqui.

## Por que pode falhar

- **O número é de exemplo, não de tabela.** A tarifa efetiva depende de VIP, BNB, promoções e par.
  Tratar 5 bps como "a taxa" é tão errado quanto tratar 4 como.
- **Tarifas mudam.** A hipótese congelada na versão continua sendo a hipótese daquela versão; comparar
  resultados de versões com hipóteses diferentes exige dizer qual era qual.
- **Nada disso muda a direção do resultado, e o argumento é aritmético, não empírico:** aumentar
  **apenas** a taxa reduz `R_net` de todo trade (`ΔR ≤ 0`), logo **não pode** transformar uma
  expectancy já negativa em positiva. Quem apresentar esta nota como explicação do vermelho está
  usando um sinal que só piora.
- **Não confundir taxa com funding.** Funding é transferência entre traders e já entra separado e
  assinado em `r_net`.

## Segunda opinião (Astra)

Conferiu a aritmética de forma independente com `[decimal]` e confirmou 39,22% / 41,18% / 43,14% e os
ΔR de −0,01961 e −0,03922. Concorda com a classificação: sensibilidade, não recalibração. Correções
aceitas: (1) escrever que a página de tarifas **não abriu** e que 0,02%/0,05% saiu de um **exemplo**
do FAQ, que o próprio artigo declara hipotético; (2) estreitar o título e a afirmação — 4 bps não
corresponde aos **exemplos**, e o viés vale **contra os cenários de 4,5 e 5**, não contra uma tarifa
efetiva desconhecida; (3) trocar "inequivocamente taker nos dois lados" por "cenário de execução
agressiva, sem modelagem de fila maker", porque deslocamento adverso sobre OHLC não identifica ordem
nem condição maker/taker; (4) explicitar que 51 bps é denominador de exemplo e dar a fórmula exata
`ΔR = −Δfee × (E+X)/(E−S)`; (5) **cortar** a comparação com os "14 bps de mediana absoluta" do
deslocamento — movimento absoluto não diz se ajudou ou prejudicou o long, e não se compara com
expectancy média em R; ficou o argumento exato, que é aritmético. Divergência: ela considera que,
sendo `AssumedCosts` parte da versão congelada, o `EXEC-C` deveria
publicar as três hipóteses **sempre**, em todo relatório, e não uma vez. Aceito, com uma ressalva
minha: três colunas fixas em todo relatório convidam a ler a mais favorável — então a coluna
**primária** continua sendo a da hipótese congelada, e as outras duas aparecem rotuladas como
sensibilidade.

## Relacionados

[[Strategy Backlog]] · [[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] ·
[[KB-0039-tipos-de-ordem-e-o-que-a-sombra-assume-sem-dizer]] ·
[[KB-0037-o-spread-assumido-contra-o-spread-medido]] ·
[[KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio]] · [[EXP-0001-momentum-v1]] ·
[[Risk Engine]]
