---
tags: [knowledge, nota, risco, sizing, volatilidade, atr]
tema: dimensionamento e risco / sizing por volatilidade
fonte: Harvey, Hoyle, Korgaonkar, Rattray, Sargaison & Van Hemert, "The Impact of Volatility Targeting" (JPM 2018); regras públicas dos Turtles; blog aberto de Robert Carver; nosso momentum_v1.py e medição na VPS
fonte_url: https://jpm.pm-research.com/content/45/1/14.abstract
lido_em: 2026-09-06
evidencia: estudo revisado lido em resumo (o PDF do SSRN devolveu 403) + aritmética própria sobre parâmetros do nosso código
hipotese_testavel: sim
astra: pendente
---

# Sizing por volatilidade — a posição já sai do ATR, e o nosso piso decide o tamanho sem dizer

## O que afirma

A família inteira de sistemas de tendência dimensiona pela volatilidade, não pelo preço: a posição é
`risco alvo / (estimador de volatilidade × multiplicador do stop)`. Os Turtles chamam de `N` e
arriscam uma fração fixa por `N`; Carver escreve como previsão contínua dividida por volatilidade
alvo; a literatura acadêmica chama de *volatility targeting*.

**O ponto desta nota é que nós já fazemos isso — sem saber.** Como a `momentum_v1` põe o stop a
`1,5 × ATR` da referência (`momentum_v1.py:217`), qualquer sizing por R **é** sizing por
volatilidade:

```
notional = R / stop_distance = R / (1,5 × atr_pct)
```

E como o Lab admite só `atr_pct ∈ [0,003; 0,05]` (`momentum_v1.py:83-84`), o **notional por 1 R está
confinado numa faixa de 16,7 vezes** — decidida por dois parâmetros que foram escolhidos como filtro
de custo e nunca foram lidos como controle de tamanho.

## Onde foi mostrado

**Harvey et al. (2018), *Journal of Portfolio Management* 45(1):14-33.** 60 ativos, dados diários
desde 1926 até 2017, volatilidade estimada por desvio padrão de retornos diários, alvo de 10%. Dois
resultados que se separam:

- **Sharpe:** carteiras de ações com volatilidade gerida têm Sharpe maior que exposição nocional
  constante — mas isso **só vale para *risk assets*** (ações, crédito), e está ligado ao efeito de
  alavancagem desses ativos. Para títulos, moedas e *commodities* o efeito no Sharpe é **desprezível**.
- **Cauda:** a redução da probabilidade de retornos extremos aparece em **todas** as classes, porque
  os eventos de cauda esquerda tendem a acontecer em volatilidade elevada, quando a carteira alvo de
  volatilidade tem exposição nocional pequena.

**Declaração de leitura:** o PDF do SSRN devolveu **HTTP 403**; li a página de resumo do JPM e o
resumo do próprio artigo. Os únicos números que uso são "60 ativos", "1926-2017" e "alvo de 10%",
todos presentes no resumo. **Nenhum Sharpe, nenhum tamanho de efeito, entrou aqui.**

**Turtles.** A regra pública ([[KB-0045-turtles-a-entrada-que-ja-temos-e-a-saida-que-nao]]) dimensiona
por `N` (que é ATR) e arrisca uma fração fixa da conta por unidade. É a mesma equação com outro nome.

**Carver** ([[KB-0050-previsao-continua-e-o-limite-de-velocidade-de-custo]]) escreve o tamanho como
previsão contínua dividida por volatilidade, o que separa **quanto acreditar** de **quanto arriscar**
— separação que a nossa `confidence` constante e não vinculante torna vazia hoje.

## Como mediríamos aqui

**A aritmética da faixa, com os parâmetros que estão no código.** Para uma unidade de risco `R` em
USDT e stop a `k = 1,5` ATR:

| `atr_pct` | distância do stop | notional por 1 R | custo de ida e volta (20 bps) em fração de 1 R |
|---|---|---|---|
| 0,0030 (o piso) | 0,45% | **222 × R** | 44,4% |
| 0,0060 | 0,90% | 111 × R | 22,2% |
| 0,0084 (mediana medida das memes) | 1,26% | 79 × R | 15,9% |
| 0,0150 | 2,25% | 44 × R | 8,9% |
| 0,0500 (o teto) | 7,50% | **13 × R** | 2,7% |

Duas leituras que só existem quando as colunas ficam lado a lado:

1. **O piso de ATR é o teto de alavancagem implícito.** No piso, uma operação de 1 R abre uma posição
   de 222 R. Com fração de risco de 0,5% do equity, isso é **111% do equity numa única posição** —
   antes de qualquer teto do Risk Engine. É por isso que `max_position_pct` domina a fórmula de
   sizing em toda a nossa população
   ([[KB-0066-o-risk-engine-ja-esta-escrito-e-a-medicao-o-contraria]]): não é coincidência de
   parâmetros, é consequência direta de stops estreitos.
2. **A última coluna é a [[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] escrita de outro jeito**, e
   confirma o motivo do piso — mas mostra que o piso está fazendo **dois** trabalhos ao mesmo tempo:
   limitar o custo em R **e** limitar o tamanho da posição. Um único parâmetro controlando duas
   coisas é exatamente o desenho que a quarta rodada já tinha marcado como suspeito
   ([[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]]).

**A distância entre o alvo de volatilidade da literatura e o nosso desenho.** *Volatility targeting*
controla a volatilidade de uma **carteira** ao longo do tempo; o nosso `1,5 × ATR` controla a
distância do stop de **uma operação**. Só coincidem se o número de posições simultâneas e a
correlação entre elas forem estáveis — e a nossa concorrência vai de 1 a 50 em 16 h
([[KB-0066-o-risk-engine-ja-esta-escrito-e-a-medicao-o-contraria]]). **Chamar o nosso sizing de
"volatility targeting" seria erro de nome**, e a distinção é a mesma que separa risco por operação de
risco de carteira.

## Hipótese testável no Lab

**Nenhuma no Lab de sombra** — pelo motivo já registrado três vezes: a sombra não dimensiona.

O que sai é uma regra proposta ao Risk Engine, `R-SIZE-2` no [[Strategy Backlog]]: **o tamanho vem do
stop declarado pelo sinal, e o estimador de volatilidade usado no sizing tem de ser o mesmo que a
estratégia usou para pôr o stop** — `rolling_window_v1` sobre 15 min com `atr_bars = 97`, não o
`atr_14_pct` do `feature_snapshots`. São dois instrumentos com o mesmo apelido, e a quarta rodada já
tropeçou nisso ([[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]], achado da Astra).

E um **diagnóstico que roda quando o M4 existir**, `R-VOL-1`: publicar, por proposta, a razão
`notional / (R)` — isto é, `1/(k × atr_pct)` — ao lado do limitante vencedor. É a curva acima medida
na população real, e é o que mostra se o piso de ATR está funcionando como controle de tamanho.

## Por que pode falhar

- **A generalização de Harvey et al. para cripto não está demonstrada.** O ganho de Sharpe é
  atribuído ao efeito de alavancagem de ações e crédito; perpétuos de altcoin podem ou não ter a
  mesma assinatura, e nós não medimos. O que se transfere com mais segurança é o resultado de
  **cauda**, que os autores encontram em todas as classes — e ainda assim é extrapolação.
- **O nosso estimador é o mais ineficiente disponível** ([[KB-0028-o-nosso-estimador-de-volatilidade-e-o-mais-ineficiente]]).
  Sizing por volatilidade herda todo o ruído do estimador; um ATR ruidoso vira notional ruidoso.
- **O ATR implementado inclui a barra corrente** (`indicators.py:62,88`), o que introduz uma
  dependência entre o tamanho da barra do sinal e o tamanho da posição. Não é look-ahead — a barra
  fechou —, mas é acoplamento, e foi a Astra quem o apontou na sétima rodada.
- **A tabela acima usa 20 bps de ida e volta como constante.** Ela não é: o spread medido varia de
  0,97 bps no decil mais líquido a 4,93 no menos ([[KB-0037-o-spread-assumido-contra-o-spread-medido]]),
  e o custo de travessia depende do tamanho ([[KB-0058-spread-e-profundidade-o-custo-de-sair-de-uma-meme]]).
  A tabela é ilustração da forma, não medição do custo.

## Segunda opinião (Astra)

Pendente nesta versão.

## Relacionados

[[Strategy Backlog]] · [[Index]] ·
[[KB-0066-o-risk-engine-ja-esta-escrito-e-a-medicao-o-contraria]] ·
[[KB-0067-a-fracao-de-risco-por-operacao-e-o-preco-de-errar-a-expectancy]] ·
[[KB-0069-capacidade-e-impacto-o-teto-que-o-livro-impoe]] ·
[[KB-0050-previsao-continua-e-o-limite-de-velocidade-de-custo]] ·
[[KB-0045-turtles-a-entrada-que-ja-temos-e-a-saida-que-nao]] ·
[[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]] ·
[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] ·
[[KB-0028-o-nosso-estimador-de-volatilidade-e-o-mais-ineficiente]]
