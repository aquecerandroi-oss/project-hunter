---
tags: [knowledge, nota, risco, correlacao, exposicao, beta]
tema: dimensionamento e risco / correlação e exposição agregada
fonte: medição própria na VPS (β e R² contra o BTCUSDT, correlação entre pares) + docs/RISK_ENGINE.md
fonte_url: —
lido_em: 2026-09-06
evidencia: replicado (SQL colado)
hipotese_testavel: sim
astra: discorda em parte (correções aplicadas)
---

# `beta > 0.8` não separa nada no nosso universo — e a exposição agregada precisa de outra medida

## O que afirma

O check 17 do contrato (`docs/RISK_ENGINE.md` §3) limita "posições com beta > 0.8 na mesma direção"
a `max_correlated_positions` (2 / 4 / 8 por perfil). Medido na VPS, esse critério marca **147 de 232
mercados** como correlacionados. Ao mesmo tempo, a **correlação** mediana entre pares de mercados
onde o Lab realmente emite sinal é **0,062**, e **nenhum** dos 780 pares passa de 0,8.

A causa é elementar e já tinha sido registrada no [[Registro de Tentativas]] (item 11 da sétima
rodada): `β = ρ · σ_a / σ_b`. Como `σ_altcoin ≫ σ_BTC`, o β fica grande **mesmo com correlação
pequena**. O β mede quanto o ativo se move *por unidade* de movimento do BTC; a correlação mede
quanto do movimento é *explicado* por ele.

> **Correção de 2026-09-06, na revisão da Astra, e ela atinge o título desta nota.** Eu escrevi que
> "o check está medindo escala de volatilidade". **Está errado como afirmação absoluta:** `β` combina
> escala **e** co-movimento — com `ρ = 0`, `β` é zero por maior que seja a volatilidade. O defeito
> real é de **confusão**, não de substituição: `ρ = 0,1` com razão de volatilidades 10 dá `β = 1`, e
> `ρ = 0,9` com razão 0,5 dá `β = 0,45` — o critério trata o primeiro como correlacionado e o segundo
> como não. E **147 de 232 não demonstra "não separa nada"**: demonstra que o critério é quase sempre
> verdadeiro no nosso universo, o que o torna ruim como regra de **agrupamento**, sem torná-lo inútil
> como medida de **sensibilidade ao fator**. **O título desta nota é mais forte que o achado**, e
> fica registrado assim em vez de ser reescrito.

Isso **não** significa que o limite de posições correlacionadas seja desnecessário. Significa que,
como escrito, ele erra nos dois sentidos: marca quase tudo, e não teria como detectar o caso que
interessa — a correlação subir em stress, que é quando o limite existe.

## Onde foi mostrado

**VPS, 2026-09-06 ~19:55 UTC.** Retornos de 5 min montados a partir de `candles_1m` (a tabela
`candles_5m` está **vazia**: zero linhas nas últimas 40 h), janela de 40 h, mínimo de 100
observações pareadas por mercado.

```sql
WITH bars AS (
  SELECT c.market_id,
         to_timestamp(floor(extract(epoch from c.open_time)/300)*300) AS t5,
         (array_agg(c.close ORDER BY c.open_time DESC))[1]::float8 AS px
  FROM candles_1m c WHERE c.open_time >= now() - interval '40 hours' GROUP BY 1,2
), rets AS (
  SELECT market_id, t5, ln(px / lag(px) OVER (PARTITION BY market_id ORDER BY t5)) AS r FROM bars
), btc AS (
  SELECT r.t5, r.r AS rb FROM rets r JOIN markets m ON m.id = r.market_id
  WHERE m.symbol = 'BTCUSDT' AND r.r IS NOT NULL
), j AS (
  SELECT rets.market_id, rets.r AS ra, btc.rb FROM rets JOIN btc ON btc.t5 = rets.t5 WHERE rets.r IS NOT NULL
), reg AS (
  SELECT market_id, count(*) AS n, regr_slope(ra, rb) AS beta, regr_r2(ra, rb) AS r2
  FROM j GROUP BY 1 HAVING count(*) >= 100 AND regr_slope(ra, rb) IS NOT NULL
)
SELECT count(*) AS mercados,
  round(percentile_cont(0.10) WITHIN GROUP (ORDER BY beta)::numeric,3) AS p10_beta,
  round(percentile_cont(0.50) WITHIN GROUP (ORDER BY beta)::numeric,3) AS mediana_beta,
  round(percentile_cont(0.90) WITHIN GROUP (ORDER BY beta)::numeric,3) AS p90_beta,
  round(percentile_cont(0.50) WITHIN GROUP (ORDER BY r2)::numeric,4) AS mediana_r2,
  round(percentile_cont(0.90) WITHIN GROUP (ORDER BY r2)::numeric,4) AS p90_r2,
  count(*) FILTER (WHERE beta > 0.8) AS beta_acima_0_8,
  count(*) FILTER (WHERE beta > 1.5) AS beta_acima_1_5,
  count(*) FILTER (WHERE sqrt(r2) > 0.8) AS corr_acima_0_8,
  count(*) FILTER (WHERE sqrt(r2) > 0.5) AS corr_acima_0_5
FROM reg;
```

```
 mercados | p10_beta | mediana_beta | p90_beta | mediana_r2 | p90_r2 | beta_acima_0_8 | beta_acima_1_5 | corr_acima_0_8 | corr_acima_0_5
----------+----------+--------------+----------+------------+--------+----------------+----------------+----------------+----------------
      232 |    0.130 |        1.137 |    2.360 |     0.0259 | 0.1897 |            147 |             88 |              1 |             12
```

E a correlação **entre pares**, restrita aos 40 mercados que mais emitiram sinal (que é a população
que competiria por slot no Risk Engine):

```sql
WITH top AS (
  SELECT a.market_id FROM agent_signals a GROUP BY 1 ORDER BY count(*) DESC LIMIT 40
), bars AS (
  SELECT c.market_id, to_timestamp(floor(extract(epoch from c.open_time)/300)*300) AS t5,
         (array_agg(c.close ORDER BY c.open_time DESC))[1]::float8 AS px
  FROM candles_1m c JOIN top ON top.market_id = c.market_id
  WHERE c.open_time >= now() - interval '40 hours' GROUP BY 1,2
), rets AS (
  SELECT market_id, t5, ln(px / lag(px) OVER (PARTITION BY market_id ORDER BY t5)) AS r FROM bars
), pairs AS (
  SELECT x.market_id AS a, y.market_id AS b, corr(x.r, y.r) AS rho, count(*) AS n
  FROM rets x JOIN rets y ON y.t5 = x.t5 AND y.market_id > x.market_id
  WHERE x.r IS NOT NULL AND y.r IS NOT NULL
  GROUP BY 1,2 HAVING count(*) >= 100
)
SELECT count(*) AS pares,
  round(percentile_cont(0.10) WITHIN GROUP (ORDER BY rho)::numeric,3) AS p10,
  round(percentile_cont(0.50) WITHIN GROUP (ORDER BY rho)::numeric,3) AS mediana,
  round(percentile_cont(0.90) WITHIN GROUP (ORDER BY rho)::numeric,3) AS p90,
  round(max(rho)::numeric,3) AS maximo,
  count(*) FILTER (WHERE rho > 0.8) AS acima_0_8,
  count(*) FILTER (WHERE rho > 0.5) AS acima_0_5,
  count(*) FILTER (WHERE rho > 0.3) AS acima_0_3
FROM pairs;
```

```
 pares |  p10   | mediana |  p90  | maximo | acima_0_8 | acima_0_5 | acima_0_3
-------+--------+---------+-------+--------+-----------+-----------+-----------
   780 | -0.029 |   0.062 | 0.212 |  0.743 |         0 |         2 |        29
```

## Como mediríamos aqui

**O que estes dois blocos, juntos, autorizam a dizer — e o que não autorizam.**

Autorizam:

- **`β > 0,8` classifica 63% do universo como correlacionado**, incluindo mercados cuja correlação
  com o BTC é pequena. Como critério de **agrupamento**, ele é quase constante nesta amostra — e um
  critério quase constante agrupa mal.
- **Correlação e β discordam nesta amostra.** Só **1** mercado de 232 tem `|ρ| > 0,8` com o BTC
  (a coluna é `sqrt(R²)`, que é o **módulo** de ρ e **perde o sinal**), contra 147 com β acima de
  0,8. Note também que `R² = ρ²`, não `ρ`: a fração de variância explicada mediana de 0,0259
  corresponde a `|ρ| ≈ 0,16`.
- **A concentração medida nesta janela é baixa.** 29 de 780 pares acima de 0,3.

**Não** autorizam:

- **Concluir que o limite de correlação é dispensável.** A janela é de 40 h, num regime só, **sem
  nenhum evento de stress** — e a razão de existir de um limite de exposição correlacionada é
  exatamente o que acontece quando a correlação sobe. Medir correlação baixa em calmaria e concluir
  "não preciso do limite" é o erro clássico, e é o erro que esta nota **não** comete.
- **Ler 0,062 como a correlação verdadeira.** A 5 min há viés de amostragem para baixo (efeito Epps:
  a correlação medida cai conforme a frequência sobe, por assincronia dos negócios). O número correto
  a comparar seria em horizonte igual ao da nossa exposição — **mediana de 12 a 21 min por
  acompanhamento**, medida hoje na VPS. **Não medi em horizonte longo**, e isso fica em aberto.

**A medida certa para o limite, se ele existir, é exposição, não contagem.** Um limite que conta
"quantas posições com β alto" trata uma posição de 500 USDT igual a uma de 10.000. A quantidade que
importa é a **exposição agregada em unidades de fator**:

```
exposição_β = Σ_i |notional_i × β_i|   [módulo, não soma assinada]
```

Usa o β que já dá para calcular, e desfaz o defeito de agrupamento: o β vira **peso**, não rótulo
binário, e a soma é a exposição em equivalente-BTC.

> **Correção da revisão da Astra, em dois pontos.** (a) Eu tinha escrito a soma **assinada**; assim,
> `long A` e `short B` de mesmo notional e `β = 1` **zeram a medida**, e no entanto A caindo e B
> subindo perde nas duas pernas. Por isso o módulo. (b) Mesmo com módulo, **isto não substitui
> integralmente o controle de concentração**: não elimina compensações nem risco residual/setorial. É
> um limite **adicional** de fator, que convive com um teto de exposição bruta e com tetos por
> cluster — e exige validar os próprios β.

## Hipótese testável no Lab

**Nenhuma no Lab de sombra** — o Lab não tem carteira, e sem notional não há exposição agregada.

Duas regras propostas ao Risk Engine, no [[Strategy Backlog]]:

- **`R-CORR-1` — acrescentar `max_beta_exposure_pct`**: `Σ|notional × β| / equity ≤ θ`, **ao lado**
  de um teto de exposição bruta e dos tetos por cluster, não no lugar deles.
  Dado necessário: β por mercado contra o BTC, numa janela declarada, recalculado periodicamente.
  **Temos o dado** (velas de 1 min, 232 mercados); **não temos o cálculo** — `market_beta_1h` está
  em `docs/PIPELINE.md` e **não existe no código**
  ([[KB-0034-btc-como-fator-e-o-regime-global-que-e-so-o-btc]]).
- **`R-CORR-2` — teto por cluster declarado**, com o cluster sendo uma lista versionada (o mesmo
  padrão de `meme_universe_v1`, [[KB-0056-meme-coin-como-ativo-e-o-rotulo-que-nao-e-medida]]) e não
  um agrupamento estatístico estimado na mesma janela. Motivo: estimar cluster e limitar exposição
  com a mesma amostra é calibrar no dado que revelou o problema.

**O que refutaria `R-CORR-1`:** se, medida a série de `exposição_β`, ela nunca for vinculante para
nenhum `θ` razoável (o limite de exposição total sempre mordendo antes), a regra é decoração e sai.
Isso é verificável assim que houver propostas, com o mesmo `R-PROV-1` da
[[KB-0066-o-risk-engine-ja-esta-escrito-e-a-medicao-o-contraria]].

**`θ` é decisão do Everton**, porque é a resposta a "quanto do capital eu aceito que se comporte como
uma aposta única no BTC".

## Por que pode falhar

- **40 h, um regime, sem stress.** Toda a estatística de correlação desta nota tem essa limitação, e
  ela é a limitação que mais importa para o assunto.
- **Efeito Epps não medido.** A correlação a 5 min subestima a correlação em horizontes maiores; não
  quantifiquei o quanto.
- **β estimado por MQO em 40 h é ruidoso**, e o ruído tem direção: com R² mediano de 0,026, o erro
  padrão da inclinação é grande. Usar β como peso propaga esse ruído para a exposição.
- **A regressão é contemporânea e não pareia com o instante da decisão.** Serve para limite de
  carteira, não para atribuir causalidade.
- **`candles_5m` está vazia**, então tudo foi remontado de `candles_1m`. Se alguma vela de 1 min
  faltar dentro do bucket de 5 min, o fechamento do bucket é o da última vela **presente** — e 34 de
  232 mercados têm lacunas nas últimas 24 h
  ([[KB-0074-risco-operacional-as-regras-de-nao-operar-quando]]).

## Segunda opinião (Astra)

Revisão de 2026-09-06 (`.claude/state/astra-review-KB-sizing-risk-2.md`). **Duas correções que
mudam o conteúdo, aplicadas acima:**

1. **"β mede só escala de volatilidade" é falso.** `β = ρ·σa/σb` combina escala **e** co-movimento;
   com `ρ = 0`, β é zero. O defeito é de **confusão** entre os dois, e **147/232 não demonstra "não
   separa nada"** — o título da nota é mais forte que o achado, e isso ficou registrado.
2. **A exposição em β com notional assinado deixa passar exposições negativas grandes.** Cenário:
   long A e short B, mesmo notional, β = 1 → a medida zera, e A caindo com B subindo perde nas duas
   pernas. Corrigido para o módulo, e rebaixado de "substituto" para **controle complementar**.

Mais: `R² = ρ²` (não ρ) e `sqrt(R²)` perde o sinal — a coluna do SQL é `|ρ|`.

**Concordou com:** que β alto **não** equivale a correlação alta, e que exposição ponderada informa
mais que contagem isolada.

## Relacionados

[[Strategy Backlog]] · [[Index]] ·
[[KB-0066-o-risk-engine-ja-esta-escrito-e-a-medicao-o-contraria]] ·
[[KB-0060-correlacao-com-o-btc-e-a-meme-season]] ·
[[KB-0034-btc-como-fator-e-o-regime-global-que-e-so-o-btc]] ·
[[KB-0074-risco-operacional-as-regras-de-nao-operar-quando]] ·
[[Registro de Tentativas]]
