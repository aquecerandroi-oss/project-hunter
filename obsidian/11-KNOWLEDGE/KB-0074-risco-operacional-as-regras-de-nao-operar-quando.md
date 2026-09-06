---
tags: [knowledge, nota, risco, operacional, qualidade-do-dado, latencia]
tema: dimensionamento e risco / risco operacional e as regras de não operar
fonte: medição própria na VPS (lacunas de velas, janela do Lab) + docs/RISK_ENGINE.md + notas das rodadas 2 a 7
fonte_url: —
lido_em: 2026-09-06
evidencia: replicado (SQL colado) + leitura de código
hipotese_testavel: sim
astra: concorda
---

# Risco operacional — as regras de "não operar quando…", e o princípio de falhar fechado

## O que afirma

O maior risco do M4 não é o mercado; é o instrumento. Sete rodadas de conhecimento produziram uma
lista de coisas que **não medem o que o nome diz** ou **não estão disponíveis quando a decisão
acontece**, e um Risk Engine que não as trate vai aprovar propostas calculadas sobre dado ausente,
velho ou errado — em silêncio, porque hoje a ausência vira `missing_input` e a avaliação segue.

O princípio que organiza tudo: **na estratégia, dado ausente pode significar "não avalia"; no Risk
Engine, dado ausente tem de significar "rejeita".** Falhar fechado é a única postura defensável para
código que move dinheiro, e é o oposto do comportamento atual do pipeline de features.

## Onde foi mostrado

**Lacunas de velas de 1 min por mercado, últimas 24 h, VPS, 2026-09-06 ~20:00 UTC:**

```sql
WITH c AS (
  SELECT market_id, count(*) AS barras FROM candles_1m
  WHERE open_time >= date_trunc('minute', now()) - interval '24 hours'
    AND open_time <  date_trunc('minute', now())
  GROUP BY 1
)
SELECT count(*) AS mercados,
  round(percentile_cont(0.10) WITHIN GROUP (ORDER BY c.barras)::numeric) AS p10_barras,
  round(percentile_cont(0.50) WITHIN GROUP (ORDER BY c.barras)::numeric) AS mediana_barras,
  max(c.barras) AS max_barras,
  count(*) FILTER (WHERE c.barras < 1440) AS com_lacuna,
  count(*) FILTER (WHERE c.barras < 1400) AS lacuna_maior_40min
FROM c;
```

```
 mercados | p10_barras | mediana_barras | max_barras | com_lacuna | lacuna_maior_40min
----------+------------+----------------+------------+------------+--------------------
      232 |       1109 |           1440 |       1440 |         34 |                 32
```

**34 de 232 mercados perderam ao menos uma vela nas últimas 24 h; 32 perderam mais de 40 minutos; e
o decil inferior perdeu 331 minutos** (1.109 de 1.440). A mediana é perfeita — o problema é
concentrado, não difuso, o que é exatamente o padrão que uma média esconderia.

**A janela do Lab, para dimensionar tudo o mais desta rodada:**

```
          tabela           | linhas |            inicio            |              fim
---------------------------+--------+------------------------------+-------------------------------
 agent_signals             |   1034 | 2026-09-06 03:40:04.45381+00 | 2026-09-06 19:45:07.267683+00
 signal_outcomes(entradas) |    992 | 2026-09-06 03:41:00+00       | 2026-09-06 19:46:00+00
 candles_1m                | 600056 | 2026-09-04 21:40:00+00       | 2026-09-06 19:51:00+00
```

```
 tracking_state |   result    | count
----------------+-------------+-------
 active         | open        |     6
 terminal       | target      |   290
 terminal       | stop        |   292
 terminal       | expired     |    17
 terminal       | invalidated |   387
 no_entry       | open        |    42
```

**16 horas de sinais.** Isso é menos do que a sétima rodada tinha (que reportava a coorte acumulada),
e a diferença não foi investigada nesta rodada — fica registrada como observação, não como
explicação.

**E o inventário do que já se sabia, de rodadas anteriores** (cada item com a nota que o mediu):

| O que | Estado | Nota |
|---|---|---|
| Livro de ordens | vive **10 s**, nunca é gravado; 8 de 200 sinais têm snapshot no próprio minuto | [[KB-0044-o-que-morre-em-dez-segundos]] |
| `bid_qty`/`ask_qty` | vivem 30 s, nunca gravados | [[KB-0044-o-que-morre-em-dez-segundos]] |
| `volume_24h` no hash `ticker` | 6 linhas em 55.709; dois escritores apagam um ao outro | [[KB-0044-o-que-morre-em-dez-segundos]] |
| `funding_change_8h`, `open_interest_change_1h/4h` | `missing_input` em toda barra — `load_deriv_history` sem chamada | [[KB-0020-funding-change-8h-nunca-calcula]] |
| `funding` e `open_interest` no contexto da estratégia | `None` em toda avaliação (`context.py:75`) | sétima rodada, T-029 |
| `regime_id` no sinal | nunca escrito; classificador em warm-up por construção | [[KB-0030-o-regime-nao-chega-ao-sinal]] |
| Deslocamento referência → entrada | mediana absoluta **14,4 bps**, p90 44,1 | [[KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio]] |
| `next_funding_time` | zero linhas persistidas | sétima rodada |
| `markets.metadata` / data de listagem | vazia; exige duas camadas para persistir | [[KB-0062-o-primeiro-dia-que-nao-conseguimos-ver]] |
| Universo | gira 26% em 20 h; 27 sinais em 14 mercados já desmonitorados | [[KB-0062-o-primeiro-dia-que-nao-conseguimos-ver]] |

## Como mediríamos aqui

O contrato já tem um check de qualidade de dado (`docs/RISK_ENGINE.md` §3, check 3: reprova se o
market data está `degraded` ou o último preço tem mais de 10 s). O que ele **não** tem é o que fazer
quando falta o insumo de **outro** check. Exemplos concretos:

- O check 18 (`slippage_estimate`) precisa do livro. O livro vive 10 s. **O que acontece se ele não
  estiver lá?** O contrato não diz. Se a resposta for "pula o check", a proposta passa sem a única
  medida de custo por tamanho que existe.
- O check 10 (`liquidity`) precisa de `quote_volume_24h`. O caminho pelo hash `ticker` está quebrado
  (6 linhas em 55.709). Se a resposta for "pula", o piso de liquidez some.
- O check 17 (`correlation`) precisa de β, que **não existe no código**
  ([[KB-0071-beta-maior-que-0-8-nao-separa-nada-no-nosso-universo]]).

Em todos os três, "pular o check" é uma decisão silenciosa que remove um limite exatamente quando o
sistema está degradado — que é quando o limite mais importa.

## Hipótese testável no Lab

**Nenhuma no Lab de sombra.** Quatro regras propostas ao Risk Engine, no [[Strategy Backlog]]:

- **`R-OPS-1` — falhar fechado, por check.** Todo check declara o insumo de que depende e o que fazer
  se ele faltar; o padrão é **rejeitar**, e cada exceção é nomeada e auditada. `risk_decision.checks`
  ganha o estado `unavailable`, distinto de `passed` e de `failed`. **Cenário de falha se não for
  feito:** o mercado entra em stress, o WebSocket cai, o livro some, e a proposta é aprovada sem
  estimativa de slippage precisamente na hora em que o slippage explode.
- **`R-OPS-2` — idade máxima de cada insumo, declarada no próprio check** (o preço já tem 10 s; o
  livro, o volume de 24 h e o β precisam do seu). Dado: **temos** para preço e livro; **não temos**
  carimbo de idade para o resto.
- **`R-OPS-3` — não abrir com lacuna aberta na janela do próprio mercado.** Medido: 34 de 232
  mercados com lacuna em 24 h, 32 com mais de 40 min. Dado: **temos** — a continuidade é publicada
  pelo market-worker (`coverage.py:153`) e consumida pelo scanner (`context.py:96`); falta ligá-la ao
  Risk Engine. Distinguir **lacuna aberta** de **lacuna recuperada** é parte da regra.
- **`R-OPS-4` — não abrir em mercado que saiu do universo** entre a emissão do sinal e a proposta.
  Medido na sétima rodada: 27 sinais em 14 mercados desmonitorados em 15 h. Dado: existe no stream do
  Redis, com retenção por número de entradas — daí o `H-KB0062b`.

**O que refutaria qualquer uma delas:** nada; são regras de disponibilidade, não previsões. O que as
tornaria **inúteis** é o `unavailable` nunca aparecer — e isso é medível publicando a distribuição
dos estados de check, que é o mesmo `R-PROV-1`.

## Por que pode falhar

- **Falhar fechado tem custo assimétrico e ele não foi medido.** Rejeitar por dado ausente pode
  desligar o sistema justamente nos momentos mais lucrativos. A escolha certa depende da frequência
  de indisponibilidade, que é o que `R-OPS-1` passaria a medir — e antes disso a recomendação é
  conservadora por precaução, não por evidência.
- **As lacunas medidas são de 24 h de uma janela sem incidente conhecido.** Não descrevem uma queda
  de exchange.
- **A tabela de inventário mistura leitura de código e medição.** Cada linha aponta para a nota que a
  sustenta; o estado de algumas pode ter mudado desde então, e nada foi reconferido nesta rodada
  exceto o que está colado acima.
- **O contrato pode já resolver parte disso na implementação**, já que não há implementação. Esta
  nota registra o que a página **não diz**, não um defeito de código.

## Segunda opinião (Astra)

Revisão de 2026-09-06 (`.claude/state/astra-review-KB-sizing-risk-2.md`), na rodada que cobriu as
seis notas de medição. Ela não pediu correção de conteúdo nesta nota, e reforçou o princípio geral
que a atravessa: **manter as medições como diagnósticos condicionais, sem eliminar controles antes
de provar redundância** — o que é exatamente o argumento de `R-OPS-1`.

A ressalva dela que mais atinge esta página, e que vale registrar: **correlações baixas numa janela
não demonstram baixa concentração de carteira**, do mesmo modo que **34 mercados com lacuna numa
janela sem incidente não descrevem uma queda de exchange**.

## Relacionados

[[Strategy Backlog]] · [[Index]] ·
[[KB-0044-o-que-morre-em-dez-segundos]] · [[KB-0020-funding-change-8h-nunca-calcula]] ·
[[KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio]] ·
[[KB-0062-o-primeiro-dia-que-nao-conseguimos-ver]] ·
[[KB-0071-beta-maior-que-0-8-nao-separa-nada-no-nosso-universo]] ·
[[KB-0072-drawdown-e-kill-switch-a-evidencia-e-a-convencao]] ·
[[KB-0075-paper-trading-honesto-o-que-a-sombra-ainda-nao-simula]]
