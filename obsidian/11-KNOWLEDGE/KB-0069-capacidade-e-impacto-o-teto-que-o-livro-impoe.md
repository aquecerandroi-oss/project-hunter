---
tags: [knowledge, nota, risco, capacidade, impacto, execucao]
tema: dimensionamento e risco / capacidade e impacto de mercado
fonte: Durin, Rosenbaum & Szymanski (arXiv 2311.18283); Donier & Bonart (arXiv 1412.4503, lido pela Astra na quinta rodada); medição própria na VPS
fonte_url: https://arxiv.org/abs/2311.18283
lido_em: 2026-09-06
evidencia: preprint lido em resumo + medição própria (livros e velas, saídas coladas em KB-0070)
hipotese_testavel: sim
astra: pendente
---

# Capacidade e impacto — o teto de notional que o livro impõe, e o que ele não é

## O que afirma

Existem **dois** tetos de tamanho por mercado, e eles não são o mesmo:

1. **Teto estático de livro** — quanto cabe nos níveis visíveis agora, a um custo de travessia
   aceitável. É o que a [[KB-0036-o-tamanho-que-a-sombra-nunca-declara]] mediu, e o que a
   [[KB-0070-a-tabela-de-capacidade-quantos-mercados-suportam-cada-tamanho]] mede por mercado.
2. **Teto de participação** — quanto do fluxo do período a nossa ordem representa. É uma quantidade
   por unidade de tempo, e é a que a literatura de impacto usa.

A regra folclórica "nunca mais que x% do volume de N minutos" pertence ao segundo teto. Aplicá-la ao
nosso caso dá um número desconfortável: **o volume de cotação mediano de um minuto no nosso universo
é 4.605 USDT** (mediana entre 232 mercados, últimas 24 h na VPS). Uma ordem de 500 USDT é **10,9% do
minuto mediano**. De 2.000 USDT, **43%**. No decil inferior (1.024 USDT por minuto), 500 USDT é
**49%** do minuto inteiro.

Isso é grande. E é grande de um jeito que o teto de livro **não mostra**, porque o livro se recompõe
entre uma leitura e outra.

## Onde foi mostrado

**Durin, Rosenbaum & Szymanski, arXiv 2311.18283, "The two square root laws of market impact"** — o
resumo separa duas leis que costumam ser confundidas: para uma taxa de participação `γ` fixa, o
impacto evolui como raiz do **volume acumulado** ao longo da execução; para um volume total `Q`
fixo, o impacto é proporcional a `√γ` **quando `γ` é grande o bastante**, e a dependência fica mais
linear em taxas de participação pequenas. **Declaração de leitura: li o resumo e a página do arXiv;
não abri o PDF.** Nenhum coeficiente, nenhuma constante de calibração desta fonte entra aqui.

**Donier & Bonart (arXiv 1412.4503)** — a ressalva que a Astra estabeleceu na quinta rodada e que
continua sendo o motivo de esta nota não prometer nada
([[KB-0040-a-lei-da-raiz-quadrada-e-o-regime-que-nao-e-o-nosso]]): **61% das metaordens têm uma única
ordem-filha**, então "somos ordem única" não nos põe fora do regime da lei; a equação normaliza por
volume e volatilidade **diários**; e a medida é impacto de **pico**, não permanente.

**Medição própria (VPS, 2026-09-06 ~19:47 UTC).** Volume de cotação por minuto, últimas 24 h, 232
mercados — a consulta e a saída estão coladas em
[[KB-0066-o-risk-engine-ja-esta-escrito-e-a-medicao-o-contraria]]:

```
mediana entre mercados do volume de cotação mediano de 1 min:   4.605,10 USDT
decil inferior:                                                 1.024,13 USDT
volume de cotação de 24 h, mediana entre mercados:          13.853.954 USDT
```

## Como mediríamos aqui

**A tabela de participação, que é aritmética direta sobre a medição acima:**

| Notional por sinal | % do minuto mediano (4.605 USDT) | % do minuto no decil inferior (1.024 USDT) | % do volume de 24 h mediano |
|---|---|---|---|
| 500 USDT | 10,9% | 48,8% | 0,0036% |
| 2.000 USDT | 43,4% | 195% (não cabe no minuto) | 0,014% |
| 10.000 USDT | 217% (não cabe no minuto) | 977% | 0,072% |

E o contraste com o teto de livro medido no mesmo instante
([[KB-0070-a-tabela-de-capacidade-quantos-mercados-suportam-cada-tamanho]]): o mercado mediano
comporta **2.174 USDT a 5 bps** de custo contra o mid. Ou seja:

> **Os dois tetos discordam por um fator de ~4 no mercado mediano.** O livro diz que 2.174 USDT
> passam a 5 bps; a participação diz que 2.174 USDT são 47% do fluxo de um minuto inteiro. Os dois
> podem estar certos ao mesmo tempo — o livro é um estoque instantâneo e o volume é um fluxo — e é
> exatamente por isso que **usar um só dos dois como limite de capacidade é escolher não ver metade
> do problema**.

**Qual dos dois é o certo para nós?** Nenhum sozinho, e a resposta honesta é que **não sabemos**,
porque nunca executamos nada. O que dá para afirmar:

- O **teto de livro** descreve o custo da nossa ordem **se ela for executada agora e sozinha**. É a
  quantidade certa para o check `slippage_estimate` do contrato (`docs/RISK_ENGINE.md` §3, check 18).
- O **teto de participação** descreve a chance de o nosso próprio fluxo mover o preço de forma
  persistente e de sermos identificados por quem faz mercado. É a quantidade certa para um limite de
  **capacidade da estratégia**, que é uma decisão de produto, não de operação.
- A **lei da raiz quadrada não é aplicável ao nosso caso sem calibração local**, e calibrá-la exige
  execuções nossas. Registrar isso é a única postura defensável — é a mesma conclusão da
  [[KB-0040-a-lei-da-raiz-quadrada-e-o-regime-que-nao-e-o-nosso]], agora com o número de
  participação ao lado.

## Hipótese testável no Lab

**Nenhuma no Lab de sombra.** Duas regras propostas ao Risk Engine, ambas no [[Strategy Backlog]]:

- **`R-CAP-1` — teto de notional por livro**, no instante da decisão: `notional ≤ N*(m, c)`, onde
  `N*` é o maior notional cujo custo de travessia contra o mid fica em `c` bps. Dado necessário: o
  **carimbo de execução** (item 20 da quinta rodada), que hoje não existe. Sem ele a regra é
  inavaliável.
- **`R-CAP-2` — teto de participação**: `notional ≤ p × quote_volume` da janela declarada. Dado
  necessário: **temos** — `quote_volume` das velas de 1 min, cobertura de 232/232 mercados. É a regra
  mais barata das duas e a única implementável hoje sem mudar contrato.

**O que refutaria `R-CAP-2`:** nada, hoje — ela não prevê nada. O que a torna **inútil** seria
descobrir que o `p` escolhido não é vinculante em nenhuma proposta (aí é decoração) ou que é
vinculante em todas (aí é um limite de capital disfarçado). Os dois casos são detectáveis publicando
a distribuição do limitante vencedor (`R-PROV-1`).

**`p` é decisão do Everton**, porque escolhe entre operar pouco em muitos mercados e operar mais em
poucos. A recomendação, e o motivo: **`p = 0,10` sobre a vela de 1 min**, porque é o valor em que a
tabela acima ainda deixa 500 USDT passar no mercado mediano — e porque acima disso a literatura de
impacto entra no regime `√γ`, onde o custo cresce mais rápido que o tamanho.

## Por que pode falhar

- **`quote_volume` da vela é volume dos dois lados**, e a nossa ordem é de um lado só. A
  participação real contra o fluxo contrário é maior que a tabela sugere.
- **Uma leitura de livro de um instante não descreve o livro no instante seguinte.** Os 200 livros
  medidos são de um intervalo de **11 segundos** de uma tarde de domingo, e o livro é justamente o
  que evapora em stress ([[KB-0044-o-que-morre-em-dez-segundos]]).
- **`p` sobre 1 min pune mercados intermitentes injustamente.** Um mercado com 60.000 USDT em uma
  vela e zero nas cinco seguintes tem mediana baixa e capacidade real diferente.
- **A tabela usa a mediana entre mercados de uma mediana dentro do mercado.** É robusta e é
  **duplamente resumida** — a distribuição por mercado, que é o que a regra usaria, não está aqui.
- **Nada disto é impacto medido.** É estoque de livro e fluxo de velas. O impacto do nosso fluxo só
  se mede executando, e nada foi executado.

## Segunda opinião (Astra)

Pendente nesta versão.

## Relacionados

[[Strategy Backlog]] · [[Index]] ·
[[KB-0070-a-tabela-de-capacidade-quantos-mercados-suportam-cada-tamanho]] ·
[[KB-0040-a-lei-da-raiz-quadrada-e-o-regime-que-nao-e-o-nosso]] ·
[[KB-0036-o-tamanho-que-a-sombra-nunca-declara]] ·
[[KB-0058-spread-e-profundidade-o-custo-de-sair-de-uma-meme]] ·
[[KB-0068-sizing-por-volatilidade-a-posicao-sai-do-atr]] ·
[[KB-0044-o-que-morre-em-dez-segundos]]
