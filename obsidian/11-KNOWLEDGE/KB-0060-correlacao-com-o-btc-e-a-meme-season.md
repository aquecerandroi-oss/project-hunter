---
tags: [knowledge, nota, memecoins, regime, fator]
tema: meme coins / correlação com o BTC e regime
fonte: medição própria na VPS + análise aberta de desempenho de meme coins 2025-2026
fonte_url: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6292920 (não abriu — HTTP 403)
lido_em: 2026-09-06
evidencia: replicado (SQL colado); a fonte externa **não abriu** e nenhum número dela foi citado como verificado
hipotese_testavel: sim
astra: pendente
---

# Correlação com o BTC — e a "meme season" que a nossa janela não contém

## O que afirma

O folclore tem duas versões contraditórias: "memes são o beta do mercado, sobem quando o BTC sobe" e
"na meme season elas descolam de tudo". Medi as duas em barras de 15 minutos, e nesta janela:

- As memes estabelecidas (coorte A) têm **inclinação mediana de 2,80** contra o BTC e **fração da
  variância explicada linearmente** de 0,152 — contra 1,44 e 0,021 do resto do universo. São, ao
  mesmo tempo, mais amplificadoras **e** mais explicadas pelo BTC que a altcoin média.
- As memes de listagem recente (coorte B) têm **inclinação praticamente igual** (2,81) e **R² de
  0,029**.

**Correção que a Astra impôs, e que era o erro central da minha primeira versão.** Eu tinha escrito
que a coorte B "amplifica quando acompanha e na maior parte do tempo não acompanha". Isso **não
decorre dos coeficientes**: numa regressão simples, β = ρ·(σ_ativo/σ_BTC) e R² = ρ². Um processo
`r_meme = 2,8·r_BTC + ε`, com resíduo grande e não correlacionado, produz inclinação 2,8 e R² de
0,029 **sem existir nenhum estado alternando** entre "acompanha" e "não acompanha". A redação que
sobrevive é a dela: *as coortes apresentam inclinações medianas semelhantes, mas a coorte B tem
menor fração da variância explicada linearmente pelo BTC.*

"Dois comportamentos diferentes" fica como **descrição exploratória do contraste**. "Comportamentos
opostos", "dois tipos estáveis de ativo" e qualquer leitura de regime **não estão demonstrados**.

## Onde foi mostrado

**Medição própria, VPS, 2026-09-06**, mesma janela de 42 h. Retornos logarítmicos de barras de 15
min construídas das velas de 1 min, regredidos contra o BTCUSDT do mesmo intervalo, exigindo ao
menos 100 pares por mercado.

A primeira versão desta consulta tinha um defeito que a Astra achou: o filtro `n1m = 15` roda
**antes** do `lag`, então uma barra faltante emparelharia um retorno de 30 min de um mercado com um
retorno de 15 min do BTC. Refiz **exigindo que a barra anterior esteja exatamente 15 minutos
antes**, e o resultado abaixo é o da versão corrigida:

```sql
r AS (SELECT market_id, b15, cl, lag(cl) OVER w AS pcl, lag(b15) OVER w AS pb15
      FROM b WHERE n1m = 15 WINDOW w AS (PARTITION BY market_id ORDER BY b15)),
rc AS (SELECT market_id, b15, ln(cl/nullif(pcl,0)) AS ret FROM r
       WHERE pcl IS NOT NULL AND b15 - pb15 = interval '15 minutes'),   -- correcao
btc AS (SELECT b15, ret FROM rc WHERE market_id =
        (SELECT id FROM markets WHERE symbol='BTCUSDT' LIMIT 1)),
j AS (SELECT rc.market_id, rc.ret AS ra, btc.ret AS rb FROM rc JOIN btc ON btc.b15 = rc.b15
      WHERE rc.ret IS NOT NULL AND btc.ret IS NOT NULL),
perm AS (SELECT market_id, count(*) AS n, corr(ra,rb) AS rho, regr_slope(ra,rb) AS beta,
           regr_r2(ra,rb) AS r2 FROM j GROUP BY 1 HAVING count(*) >= 100)
```

```
      grupo       | mercados | pares_med | corr_mediana | beta_mediano | beta_p25 | beta_p75 | r2_mediano | mercados_r2_abaixo_005
------------------+----------+-----------+--------------+--------------+----------+----------+------------+------------------------
 A_meme           |       21 |       163 |        0.390 |        2.795 |    1.984 |    3.396 |      0.152 |                      8
 B_meme_nao_ascii |        4 |       167 |        0.166 |        2.810 |    1.985 |    4.110 |      0.029 |                      3
 D_majors         |       23 |       167 |        0.447 |        1.821 |    1.418 |    2.436 |      0.200 |                      4
 E_resto          |      148 |       162 |        0.144 |        1.439 |    0.694 |    1.993 |      0.021 |                     96
```

Os números são **idênticos** aos da versão sem a exigência de contiguidade — ou seja, no dado desta
janela não havia pares atravessando lacuna que mudassem as medianas. A correção deixou de ser
ressalva declarada e virou verificação.

O beta mediano de 2,80 da coorte A é o número mais concreto da nota: **um movimento de 1% no BTC
está associado a 2,8% nas memes estabelecidas**, na regressão de 15 min desta janela, com quartis
entre 1,98 e 3,40. Com R² mediano de 0,152, 85% da variância mediana **não** é explicada
linearmente pelo BTC. E a coluna mais honesta é a última: **8 dos 21 mercados da coorte A**, e
**96 dos 148 do resto**, têm R² abaixo de 0,05 — a mediana não classifica os integrantes.

**Comparação com a literatura: retirada.** Eu tinha escrito que análises abertas de 2025-2026
reportam correlação diária de meme coins com o BTC na casa de 0,77-0,78, e explicado a diferença
para os nossos 0,39 pelo efeito Epps (queda da correlação medida em janelas curtas, por assincronia
de negociação). A Astra derrubou os dois pedaços: a fonte (SSRN 6292920) **retornou HTTP 403 para
mim e para ela**, então os números não estão verificados e **saíram**; e Epps explica um mecanismo
possível, mas não atribui a ele a diferença — a outra amostra tem moedas diferentes, outro regime e
uma carteira agregada, e teria correlação diária maior mesmo sem Epps nenhum. O que fica é a frase
mínima: **resultados em frequências diferentes não são diretamente comparáveis**, e com 42 h não
temos amostra diária para investigar isso aqui.

## Como mediríamos aqui

Isto conversa com a quarta rodada. A [[KB-0034-btc-como-fator-e-o-regime-global-que-e-so-o-btc]]
achou que o rótulo `global` do `regime_v0` é **literalmente o BTCUSDT**, e que `RegimeScope.BTC`
existe no enum e nunca é usado. Esta medição acrescenta uma descrição, com o limite dela declarado
na frente: **R² de retorno contemporâneo não valida nem invalida um classificador de regime** —
associação linear contemporânea e utilidade de um rótulo de estado são perguntas diferentes
(ressalva da Astra). O que dá para dizer é só isto:

- Nas **majors** (R² mediano 0,200) e nas **memes estabelecidas** (0,152), a variação do BTC explica
  linearmente uma fração maior da variação de 15 min.
- No **resto** (0,021) e nas **memes novas** (0,029), essa fração é de ~2 a 3%. E **96 dos 148**
  mercados do resto ficam abaixo de 0,05.

O classificador, de todo modo, continua **mudo por warm-up** (`market_regimes` com uma única linha,
`global`/`UNKNOWN` — [[KB-0031-o-classificador-de-regime-esta-mudo-por-warm-up]]).

## Hipótese testável no Lab

**`D-MEME-BETA` (diagnóstico, testável agora, sem pré-requisito):** o `D-023` da quarta rodada (R² e
beta de cada mercado contra o BTCUSDT em 5 min e 1 h) **estratificado por `meme_universe_v1`**, e
com uma coluna que a quarta rodada não pediu: a **distribuição** de β e R² dentro de cada coorte, não
só a mediana. A dispersão da coorte A vai de correlação 0,025 a 0,576 — a mediana esconde que dois
mercados chamados "meme" podem ser ativos completamente diferentes em relação ao fator.

**O que esta nota explicitamente NÃO propõe: nenhum filtro ou braço de "meme season".** Três razões,
e a terceira é decisiva:

1. Quarenta e duas horas não contêm regime nenhum — nem meme season, nem o contrário.
2. O regime **não chega ao sinal**: `agent_signals.regime_id` nunca é escrito
   ([[KB-0030-o-regime-nao-chega-ao-sinal]]), então a estratificação retrospectiva é inexecutável.
3. Mesmo que existisse, a "meme season" é uma afirmação sobre **retorno relativo entre carteiras**,
   e o Lab de sombra **não dimensiona posição** — `PnL de carteira` é *não aplicável*. É a mesma
   barreira que adiou a T-021 para o M4.

## Por que pode falhar

- **Uma janela, um regime, 42 horas.** Beta e correlação são as estatísticas que mais mudam com o
  regime; medir isso num intervalo sem stress é medir o caso fácil.
- **Beta de regressão de 15 min é sensível a assincronia e a valores extremos.** Um único choque de
  meia hora em que a meme e o BTC se moveram juntos pode carregar boa parte do coeficiente. Não
  testei isso, e a Astra apontou que aqui o teste é **outro** do que o da
  [[KB-0058-spread-e-profundidade-o-custo-de-sair-de-uma-meme]]: remover um **mercado** por vez
  testa a mediana da coorte; remover um **intervalo de tempo** por vez testa se um choque domina a
  regressão. Faltam os dois.
- **A coorte B tem 4 mercados** com pelo menos 100 pares. Quatro.
- **O BTC é o denominador e o numerador do enquadramento.** Medir tudo contra o BTC herda a crítica
  da KB-0034: chamar isso de "fator de mercado" é uma escolha nossa, não um fato.
- **Correlação não é o que a estratégia usa.** A `momentum_v1` decide por mercado, isoladamente;
  beta alto não entra em nenhuma decisão hoje. Esta nota descreve a população, não a regra.

## Segunda opinião (Astra)

Revisão de 2026-09-06 (`.claude/state/astra-review-KB-0059-0061-memecoins.md`). Foi a nota mais
corrigida do bloco:

1. **Derrubou a tradução de R² em "frequência de acompanhamento"** — β = ρ·σa/σb e R² = ρ² são
   coisas distintas, com contraexemplo (`r_meme = 2,8·r_BTC + ε` dá inclinação 2,8 e R² 0,029 sem
   nenhum estado alternando).
2. **Achou o defeito de emparelhamento no SQL** (`n1m = 15` filtrando antes do `lag`). Refiz a
   consulta exigindo intervalo anterior de exatamente 15 min: os números não mudaram, e agora está
   verificado em vez de declarado.
3. **Mandou retirar os 0,77-0,78** enquanto a fonte não abrir — e ela também tomou 403 no SSRN —, e
   mostrou que Epps explica um mecanismo possível sem atribuir a diferença a ele.
4. **Corrigiu o denominador**: eu escrevi "154 de 200"; a regressão tem 148 + 4 = 152 nesses grupos,
   e uma mediana não classifica todos os integrantes. Daí a coluna nova de mercados com R² < 0,05.
5. **Proibiu usar R² de retorno para validar classificador de regime.**
6. **Concordou** em publicar beta junto de R² e da dispersão, e em tratar 42 h como descrição local
   que não estabelece meme season nenhuma.

## Relacionados

[[KB-0034-btc-como-fator-e-o-regime-global-que-e-so-o-btc]] ·
[[KB-0030-o-regime-nao-chega-ao-sinal]] ·
[[KB-0031-o-classificador-de-regime-esta-mudo-por-warm-up]] ·
[[KB-0057-a-volatilidade-das-memes-e-o-piso-que-bane-o-btc]] ·
[[KB-0056-meme-coin-como-ativo-e-o-rotulo-que-nao-e-medida]] · [[Strategy Backlog]] · [[Index]]
