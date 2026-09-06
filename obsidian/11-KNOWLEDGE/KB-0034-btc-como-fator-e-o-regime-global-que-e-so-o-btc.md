---
tags: [knowledge, nota, regime, fator, btc]
tema: regime de mercado e volatilidade
fonte: Liu, Tsyvinski & Wu, "Common Risk Factors in Cryptocurrency" (NBER WP 25882, 2019; Journal of Finance 77(2):1133-1177, 2022) — lido em **resumo**; e o nosso `scanner-worker/regime.py`, `regime/breadth.py`, `docs/PIPELINE.md`
fonte_url: https://www.nber.org/papers/w25882
lido_em: 2026-09-06
evidencia: estudo revisado (lido só o resumo — o PDF não foi aberto) + leitura de código próprio
hipotese_testavel: sim
astra: pendente
---

# BTC como fator, e o "regime global" que é só o BTC

## O que afirma (a literatura)

Liu, Tsyvinski & Wu mostram que **três fatores — mercado de cripto, tamanho e momentum — dão conta
do corte transversal dos retornos esperados** em cripto: dezenas de características que geram
estratégias long-short com excesso de retorno significativo são explicadas por esse modelo de três
fatores. O primeiro deles, o **fator de mercado**, é o análogo do mercado acionário — e em cripto
ele é dominado pelo BTC.

Duas leituras que essa evidência **autoriza** e uma que ela não autoriza:

- **autoriza:** tratar o estado do BTC como proxy do estado do mercado de cripto tem base;
- **autoriza:** esperar que os retornos das altcoins tenham forte componente comum;
- **não autoriza:** presumir que essa correlação seja estável no tempo ou que ela suba
  especificamente em estresse. Material de praticante repete uma correlação média em torno de 0,7
  entre BTC e altcoins; **não usei esse número em nenhuma hipótese**, porque a fonte é comercial e
  o período não é declarado.

## Onde foi mostrado

Corte transversal de centenas de criptomoedas, retornos semanais/diários, da década de 2010 até o
fim da amostra do artigo. É formação de preço no corte transversal, com carteiras rebalanceadas —
**não** é intradiário, não é perpétuo, e não tem custo de funding.

## O que nós fazemos com isso hoje (sem ter decidido)

O `regime_v0` chama o seu escopo de `global`, e ele é, literalmente, o BTC:

- `scanner-worker/regime.py:64`: `BTC_SYMBOL = "BTCUSDT"`;
- `scanner.py:319-320`: `regime_scope()` devolve sempre `RegimeScope.GLOBAL`;
- a `RegimeObservation` que alimenta o classificador tem `return_4h`, `return_1d`, `atr_pct` e
  `volatility` **do BTC**; o único insumo que olha o resto do universo é a amplitude.

Três consequências que ninguém tinha escrito:

1. **`RegimeScope.BTC` existe no enum e nunca é usado** (`domain/enums.py:217-221`). Ou seja: a linha
   gravada como `global` **é** a leitura do BTC, e a distinção que o schema previa está vazia. Quem
   ler `market_regimes` daqui a seis meses vai supor que `global` agrega o universo. Não agrega.
2. **A confirmação por amplitude pode não ser independente.** Se o universo tem beta alto contra o
   BTC, a fração de mercados subindo é quase uma função da tendência do próprio BTC — e então a
   `confidence` não confirma nada, mede a mesma coisa duas vezes
   ([[KB-0033-amplitude-de-mercado-a-nossa-e-condicionada-a-volume]]).
3. **As features que testariam isso não existem.** `docs/PIPELINE.md` §2 lista um grupo "Cross" com
   `btc_correlation_1h`, `market_beta_1h` e `relative_strength_vs_btc_1h`. Uma busca por esses três
   nomes em `packages/` e `services/` **não retorna nada**: são planejadas, não implementadas. E
   `classify_market_trend` / `MarketTrendReading` — a tendência **por mercado**, que existe e está
   exportada em `regime/__init__.py` — **não tem nenhuma chamada em produção**: só a definição e os
   testes. A leitura por mercado é código morto hoje.

## Hipótese testável no Lab

**H-KB0034 (diagnóstica, em duas partes que não dependem uma da outra).**

**(a) Quanto do universo é BTC.** Sobre as velas de 1 min já persistidas, para cada mercado com
cobertura suficiente, regredir o retorno de 5 min do mercado contra o retorno de 5 min do BTCUSDT na
mesma janela e reportar a distribuição transversal de R² e de beta, com o número de mercados e de
janelas em cada célula.

- **Confirmação de que "global = BTC" é defensável:** R² mediano alto (digamos, acima de 0,5).
- **Refutação:** R² mediano baixo — nesse caso chamar de `global` uma leitura do BTC é rótulo
  errado, e o conserto é de **nomenclatura e schema** (usar `RegimeScope.BTC`, que já existe), não
  de estratégia.

**(b) Discordância como informação.** Para os sinais de sombra, gravar (junto do carimbo pedido em
[[KB-0030-o-regime-nao-chega-ao-sinal]]) a tendência **do próprio mercado** pela mesma regra
`trend_of` — o que exige apenas chamar a função que já existe. Depois perguntar: entre os toques
resolvidos, a taxa de alvo difere entre "mercado concorda com o BTC" e "mercado discorda"?

- **Denominadores obrigatórios em cada célula**, e o limiar editorial de 100 outcomes e 30 dias
  distintos vale igual. Com a coorte de hoje isso é `inconclusivo` por construção.

## Por que pode falhar

- **Beta medido em 1-5 min é microestrutura, não fator.** Em janelas curtas, o R² contra o BTC é
  contaminado por assincronia de negócios e por spread; o resultado pode dizer mais sobre liquidez
  do que sobre co-movimento econômico. Medir também em 1 h ajuda a separar.
- **Correlação não é constante, e a instabilidade é o ponto.** O folclore de "altseason" é
  exatamente a afirmação de que a relação muda de estado. Testá-la exige janelas longas — mais do
  que temos, e mais do que teremos em um mês.
- **Confundir fator de precificação com sinal de tempo.** Liu-Tsyvinski-Wu é sobre **corte
  transversal** de retornos esperados. Nada nele diz que saber o estado do BTC ajuda a cronometrar
  entrada num altcoin em 15 minutos. A transferência de horizonte é a mesma armadilha da
  [[KB-0001-momentum-academico-e-o-que-nao-se-transfere]].
- **Sobrevivência.** Qualquer estudo transversal de cripto que use o universo de hoje para olhar o
  passado herda viés de sobrevivência brutal. O nosso universo é o de mercados ativos agora.

## Segunda opinião (Astra)

Revisão de 2026-09-06. **Confirmou** os três fatos de código: `RegimeScope.BTC` existe e nunca é
usado, `classify_market_trend` não tem chamada em produção, e `btc_correlation_1h` /
`market_beta_1h` / `relative_strength_vs_btc_1h` estão em `docs/PIPELINE.md` §2 e **não existem** no
código.

**Onde eu me segurei de propósito:** a correlação média "em torno de 0,7" entre BTC e altcoins
aparece em material comercial sem período declarado, e por isso **não entra em nenhuma hipótese**
desta nota — a mesma disciplina que a terceira rodada aplicou aos números de cascata de liquidação
([[KB-0025-o-nosso-detector-de-open-interest-so-olha-para-cima]]).

## Relacionados

[[KB-0033-amplitude-de-mercado-a-nossa-e-condicionada-a-volume]] ·
[[KB-0030-o-regime-nao-chega-ao-sinal]] ·
[[KB-0002-momentum-e-reversao-em-cripto]] ·
[[KB-0001-momentum-academico-e-o-que-nao-se-transfere]] · [[Strategy Backlog]]
