---
tags: [knowledge, nota, momentum, cripto]
tema: Momentum e rompimentos
fonte: Dobrynskaya, "Cryptocurrency Momentum and Reversal" (SSRN, working paper); Wen, Bouri, Xu & Zhao, "Intraday return predictability in the cryptocurrency markets: momentum, reversal, or both" (North American Journal of Economics and Finance, 2022)
fonte_url: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3913263 · https://www.sciencedirect.com/science/article/abs/pii/S1062940822000833
lido_em: 2026-09-06
evidencia: estudo revisado (Wen et al.) · working paper (Dobrynskaya)
hipotese_testavel: sim
astra: concorda
---

# Momentum e reversão em cripto: a virada chega muito mais cedo

## O que afirma

Em cripto o momentum existe, mas **azeda muito mais rápido** do que em ações. Dobrynskaya, sobre
cerca de 2.000 criptomoedas entre 2014 e 2020, encontra momentum positivo em horizontes curtos —
até 2 a 4 semanas — e reversão significativa acima de aproximadamente um mês; em ações essa virada
leva cerca de um ano. Wen, Bouri, Xu & Zhao vão para dentro do dia: com dados de alta frequência de
Bitcoin (2013–2020) encontram previsibilidade intradiária com **momentum e reversão ao mesmo
tempo**, dependendo do intervalo do dia, e observam que o padrão muda na presença de saltos de
preço, de anúncios do FOMC, do nível de liquidez e da COVID-19. A reversão intradiária, dizem os
autores, seria peculiar ao mercado cripto e compatível com sobre-reação a informação não
fundamental — **interpretação deles, não mecanismo comprovado**.

## Onde foi mostrado

Painel transversal de criptos em horizontes semanais/mensais (Dobrynskaya) e séries intradiárias de
BTC, ETH, LTC e XRP em spot (Wen et al.). Nenhum dos dois testa perpétuos com funding, rompimento
de 15 minutos ou horizonte de 4 horas. Um detalhe importante: na evidência transversal a reversão é
puxada sobretudo pelas **antigas perdedoras**, o que é diferente de "altas se esgotam".

## Como mediríamos aqui

A leitura que interessa para a `momentum_v1` não é "reversão semanal", é a pergunta operacional: **o
rompimento que já andou muito antes de nós entrarmos vale menos?** Isso é uma hipótese de
**impulso recente excessivo**, e é preciso dizer isso com esse nome — chamá-la de "reversão" seria
importar o rótulo de um horizonte que não é o nosso.

A feature existente para medir impulso normalizado é `momentum_15m`, que é
`return_15m ÷ atr_14_pct` (`packages/indicators/hunter_indicators/features/trend.py`, classes
`Momentum` e `AtrPercent`). Duas limitações que a nota tem de declarar, porque mudam o que o número
significa:

1. Ela mede **os últimos 15 minutos**, não a extensão acumulada desde o começo do movimento. Uma
   alta persistente por várias barras passa pelo filtro se a última barra for pequena.
2. Como `atr_14_pct = ATR/close`, a razão é `(ΔC/ATR) × (C_t/C_{t−n})` — logo "2 ATR exatos" é uma
   **aproximação**, não uma identidade.

## Hipótese testável no Lab

`momentum_v4_impulso_excessivo` — idêntica à `momentum_v1`, com **uma** alteração: recusar a
admissão quando `momentum_15m > K` na decisão.

- `default_parameters`: os de `momentum_v1`, mais `impulse_feature = "momentum_15m"`,
  `impulse_max = "2.0"`. `K = 2` é escolha experimental **pré-registrada**, sem respaldo específico
  dos artigos — está declarado aqui para que ninguém depois a apresente como derivada da literatura.
- Filtro **só de admissão**, congelado na decisão: não muda stop, alvo, invalidação nem rearme, e o
  bloqueado continua sendo o mesmo episódio-base, acompanhado **contrafactualmente** (mesmas
  entradas, saídas e custos hipotéticos) só para medir a diferença.
- Refutação com três resultados possíveis, para `Δ = E_aprovados − E_bloqueados` e `δ`
  pré-registrado: IC95% por blocos de tempo inteiramente acima de `δ` sustenta; inteiramente abaixo
  refuta o ganho mínimo; cruzando `δ` é inconclusivo. Acompanhar **também** `E_aprovados − E_base`:
  separar bem dois grupos não prova ganho relevante nem expectancy positiva.

## Por que pode falhar

- **O filtro pode cortar exatamente os rompimentos verdadeiros.** É o risco central: continuação
  forte é justamente o que anda muito. O diagnóstico é estratificar por faixas de extensão
  **definidas antes de olhar o resultado** e reportar, por faixa, expectancy líquida, alvo antes do
  stop, expirações e invalidações. Se a faixa bloqueada continuar melhor fora da amostra, o filtro
  está descartando continuação, e a candidata morre.
- **Nome errado, conclusão errada:** se registrarmos isso como "reversão", vamos citar Dobrynskaya
  para justificar um corte intrabar que ela não testou.
- Percentil histórico da mesma medida seria outra métrica de raridade — **variante separada**, com
  janela e aquecimento próprios, e mais uma tentativa a contar
  ([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]).
- Só LONG: a evidência de reversão transversal vem sobretudo das perdedoras, que não operamos.

## Segunda opinião (Astra)

Concorda que a candidata merece teste e que os artigos **não** demonstram que romper após 2 ATR
piora a entrada — é hipótese nova. Três must-fix aceitos e incorporados acima: (1) nomear
corretamente a exposição — `momentum_15m` é impulso da última barra normalizado, não extensão
acumulada, e "2 ATR" é aproximação por causa da forma da razão; (2) preservar os episódios-base e
acompanhar os bloqueados contrafactualmente, com o filtro só na admissão, senão o rearme muda o
timing e a comparação deixa de isolar o filtro; (3) refutação com três resultados, não dois. Aceitei
também renomear a hipótese para "impulso recente excessivo" e registrar `K = 2` como escolha
experimental sem respaldo bibliográfico. Sobre ATR versus percentil ela diz que nenhum é
universalmente superior e sugere começar por ATR — foi o que fiz.

Divergência: nenhuma.

## Relacionados

[[Strategy Backlog]] · [[KB-0001-momentum-academico-e-o-que-nao-se-transfere]] ·
[[KB-0009-o-efeito-do-quarto-de-hora]] · [[EXP-0001-momentum-v1]] · [[Features]]
