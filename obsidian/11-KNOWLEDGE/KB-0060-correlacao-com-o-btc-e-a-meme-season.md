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
"na meme season elas descolam de tudo". Medi as duas em 15 minutos, e **as duas coortes se comportam
de maneira oposta entre si**:

- As memes estabelecidas (coorte A) são **mais** acopladas ao BTC que a altcoin média do universo:
  correlação mediana **0,390** contra **0,144** do resto, com beta mediano de **2,80** contra 1,44.
- As memes de listagem recente (coorte B) têm beta igualmente alto (**2,81**) mas correlação de
  **0,166** e **R² de 0,029** — ou seja, amplificam quando acompanham e, na maior parte do tempo,
  simplesmente não acompanham.

"Meme" não é um regime. São dois comportamentos diferentes debaixo do mesmo rótulo.

## Onde foi mostrado

**Medição própria, VPS, 2026-09-06**, mesma janela de 42 h. Retornos logarítmicos de barras de 15
min construídas das velas de 1 min, regredidos contra o BTCUSDT do mesmo intervalo, exigindo ao
menos 100 pares por mercado.

```sql
r AS (SELECT market_id, b15,
        ln(cl/nullif(lag(cl) OVER (PARTITION BY market_id ORDER BY b15),0)) AS ret
      FROM b WHERE n1m = 15),
btc AS (SELECT b15, ret FROM r WHERE market_id =
        (SELECT id FROM markets WHERE symbol='BTCUSDT' LIMIT 1)),
j AS (SELECT r.market_id, r.ret AS ra, btc.ret AS rb FROM r JOIN btc ON btc.b15 = r.b15
      WHERE r.ret IS NOT NULL AND btc.ret IS NOT NULL),
perm AS (SELECT market_id, count(*) AS n, corr(ra, rb) AS rho,
           regr_slope(ra, rb) AS beta, regr_r2(ra, rb) AS r2
         FROM j GROUP BY 1 HAVING count(*) >= 100)
SELECT cls.grupo, count(*) AS mercados, ... FROM perm p JOIN cls ON cls.id = p.market_id ...
```

```
      grupo       | mercados | corr_mediana | beta_mediano | r2_mediano | corr_min | corr_max
------------------+----------+--------------+--------------+------------+----------+----------
 A_meme           |       21 |        0.390 |        2.795 |      0.152 |    0.025 |    0.576
 B_meme_nao_ascii |        4 |        0.166 |        2.810 |      0.029 |    0.020 |    0.234
 D_majors         |       23 |        0.447 |        1.821 |      0.200 |    0.053 |    0.781
 E_resto          |      148 |        0.144 |        1.439 |      0.021 |   -0.183 |    0.530
```

O beta mediano de 2,80 da coorte A é o número mais concreto da nota: **um movimento de 1% no BTC
está associado a 2,8% nas memes estabelecidas**, na regressão de 15 min desta janela. Com R² de
0,152, porém, 85% da variância delas **não** é explicada pelo BTC. As duas coisas são verdadeiras ao
mesmo tempo, e citar só uma delas é o erro comum.

**Comparação com a literatura, com a ressalva na frente.** Análises abertas de 2025-2026 reportam
correlação **diária** de meme coins com o BTC na casa de 0,77-0,78. A nossa é de 0,39 em barras de
15 min. Isso **não é contradição**: correlação medida em janelas curtas cai por assincronia de
negociação (o efeito que Epps descreveu em 1979), e é esperado que suba com o horizonte. Mas a
principal fonte que reportava aqueles números **retornou HTTP 403 para mim** (SSRN 6292920), então
**nenhum número dela entra nesta nota como verificado** — a comparação acima é qualitativa, sobre
direção e ordem de grandeza, e está declarada como tal.

## Como mediríamos aqui

Isto conversa direto com a quarta rodada. A [[KB-0034-btc-como-fator-e-o-regime-global-que-e-so-o-btc]]
achou que o rótulo `global` do `regime_v0` é **literalmente o BTCUSDT**, e que `RegimeScope.BTC`
existe no enum e nunca é usado. Esta medição diz o que isso custa em cada coorte:

- Para as **majors** (R² 0,200) e para as **memes estabelecidas** (0,152), chamar o BTC de "global"
  é uma aproximação defensável em ordem de grandeza.
- Para o **resto do universo** (R² 0,021) e para as **memes novas** (0,029), o BTC explica ~2% da
  variância. Um classificador de regime que só olha o BTC está, para 154 dos 200 mercados
  monitorados, medindo outra coisa.

E o classificador continua **mudo por warm-up** (`market_regimes` com uma única linha,
`global`/`UNKNOWN` — [[KB-0031-o-classificador-de-regime-esta-mudo-por-warm-up]]), então isto hoje
é diagnóstico sobre um instrumento que ainda não fala.

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
  meia hora em que a meme e o BTC se moveram juntos pode carregar boa parte do coeficiente. Eu não
  removi um mercado por vez para testar isso — é o mesmo cuidado que a Astra pediu para a correlação
  de profundidade da [[KB-0058-spread-e-profundidade-o-custo-de-sair-de-uma-meme]], e ele se aplica
  aqui também.
- **A coorte B tem 4 mercados** com pelo menos 100 pares. Quatro.
- **O BTC é o denominador e o numerador do enquadramento.** Medir tudo contra o BTC herda a crítica
  da KB-0034: chamar isso de "fator de mercado" é uma escolha nossa, não um fato.
- **Correlação não é o que a estratégia usa.** A `momentum_v1` decide por mercado, isoladamente;
  beta alto não entra em nenhuma decisão hoje. Esta nota descreve a população, não a regra.

## Segunda opinião (Astra)

_(pendente)_

## Relacionados

[[KB-0034-btc-como-fator-e-o-regime-global-que-e-so-o-btc]] ·
[[KB-0030-o-regime-nao-chega-ao-sinal]] ·
[[KB-0031-o-classificador-de-regime-esta-mudo-por-warm-up]] ·
[[KB-0057-a-volatilidade-das-memes-e-o-piso-que-bane-o-btc]] ·
[[KB-0056-meme-coin-como-ativo-e-o-rotulo-que-nao-e-medida]] · [[Strategy Backlog]] · [[Index]]
