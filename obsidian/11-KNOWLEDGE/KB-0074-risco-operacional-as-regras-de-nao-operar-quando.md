---
tags: [knowledge, nota, risco, operacional, qualidade-do-dado, latencia]
tema: dimensionamento e risco / risco operacional e as regras de não operar
fonte: medição própria na VPS (lacunas de velas, janela do Lab) + docs/RISK_ENGINE.md + notas das rodadas 2 a 7
fonte_url: —
lido_em: 2026-09-06
evidencia: replicado (SQL colado) + leitura de código
hipotese_testavel: sim
astra: concorda
status: curada
owner: sexta-feira
updated: 2026-09-06
confiança: replicado
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

[[Strategy Backlog]] · [[11-KNOWLEDGE/Index|Index]] ·
[[KB-0044-o-que-morre-em-dez-segundos]] · [[KB-0020-funding-change-8h-nunca-calcula]] ·
[[KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio]] ·
[[KB-0062-o-primeiro-dia-que-nao-conseguimos-ver]] ·
[[KB-0071-beta-maior-que-0-8-nao-separa-nada-no-nosso-universo]] ·
[[KB-0072-drawdown-e-kill-switch-a-evidencia-e-a-convencao]] ·
[[KB-0075-paper-trading-honesto-o-que-a-sombra-ainda-nao-simula]]

## Adendo 2026-09-12 (Astra)

**Registro documental dos plantões, sem nova consulta às APIs nesta execução:** os números abaixo são leituras históricas atribuídas aos arquivos indicados, com janelas distintas preservadas (procedência: `.claude/state/brief-A-obsidian-kb-toques.md`; `.claude/state/plantao/2026-09-11-0935-lane3.md`, item 1; `.claude/state/plantao/2026-09-11-1030-lane4.md`, item 1).

| Evento e horário oficial registrado | Referência anterior / implícito | Realizado registrado e disponibilidade | Procedência |
|---|---|---|---|
| PPI, 10/09/2026, 12:30Z (09:30 BRT) | O run 10 registra DVOL 39,03 doze horas antes do PPI, recuperado na leitura de 11/09 às 11:14Z; é referência histórica anterior ao evento, não carimbo prospectivo de leitura nem estimativa específica do choque. | PPI +0,4% m/m e +5,4% a/a; BTCUSDT perpétuo, barra aberta às 12:30Z: 77.782 → 77.104 (−0,87%), 15.930 BTC; barra 12:45Z: fechamento 76.860 (−0,32%), mínima 76.634; barras já encerradas na leitura de 10/09 às 19:11Z. | `.claude/state/plantao/2026-09-10-1608-lane2.md`, item 1; `.claude/state/plantao/2026-09-11-0815-lane2.md`, item 1; `.claude/state/plantao/2026-09-11-0935-lane3.md`, item 1. |
| CPI, 11/09/2026, 12:30Z (09:30 BRT) | IV ATM 47,15%, lida às 11:14Z antes do print, convertida no run 10 em 1σ terminal ≈ 2,3% nas cerca de 21 h até 12/09 08:00Z; referência primária de consenso: headline 0,4% m/m e 3,4% a/a, núcleo 0,2% m/m e 2,4% a/a. | Headline na referência; núcleo mensal +0,1 pp (0,3%); barra 12:30Z final lida 12:45:37Z: +0,65%, mínima −1,37%, 28.314,8 BTC; barra 12:45Z final lida 13:00:04Z: +0,56%; retorno acumulado 12:30Z→13:00Z: +1,21%. | `.claude/state/plantao/2026-09-11-0815-lane2.md`, itens 1–2; `.claude/state/plantao/2026-09-11-0935-lane3.md`, item 1. |
| CPI, complemento H-P23 disponível às 13:30Z | DVOL 38,97 do bucket 11:00Z, encerrado antes de 12:00Z; escala diária 38,97/√365 = 2,0398%, sem usar o bucket que contém o print. | 60/60 barras finais, lidas 13:30:08Z: 77.058,0 → 77.486,7, retorno +0,556%; índice 0,2727 (≈ 0,27, rótulo < 1); amplitude 2,745%, ou 1,35× a escala, registrada separadamente. | `.claude/state/plantao/2026-09-11-1030-lane4.md`, item 1. |

- **Retificação de janela:** as aberturas dos runs 10/11 citam −1,48% ou −1,5% como retorno de 15 minutos do PPI, mas as barras detalhadas registram −0,87% no fechamento de 12:30Z e mínima perto de −1,5% na barra seguinte; este adendo adota os pares OHLC detalhados e não transforma mínima em retorno de fechamento (procedência: `.claude/state/plantao/2026-09-11-0815-lane2.md`, abertura e item 1; `.claude/state/plantao/2026-09-11-0935-lane3.md`, abertura e item 1).
- **Implícito × realizado aqui é painel, não teste de opções caras/baratas:** σ terminal de cerca de 21 h, retorno de 30/60 minutos e amplitude têm horizontes e definições diferentes; DVOL é volatilidade implícita anualizada de 30 dias e sua conversão diária não calibra surpresa do evento (procedência: `.claude/state/plantao/2026-09-11-0815-lane2.md`, item 1; `.claude/state/plantao/2026-09-11-0935-lane3.md`, item 1; `.claude/state/plantao/2026-09-11-1030-lane4.md`, seção "Astra").
- **Indisponibilidade operacional e restrição de agenda são decisões diferentes:** H-P17 propõe comparar decisões com fechamento em [T+15 min, T+60 min] com controles na mesma hora, separando entradas novas de posições anteriores expostas; bloquear entradas por agenda depende de hipótese de rentabilidade validada, não decorre automaticamente de falhar fechado por dado ausente (procedência: `.claude/state/astra-review-plantao-20260910-1608.md`, "MUST-FIX" 4, "NICE-TO-HAVE" e "OBSIDIAN"; `.claude/state/plantao/2026-09-10-1608-lane2.md`, item 1).
- **A unidade de evidência é o evento:** quatro barras de cada um de aproximadamente dez prints não criam quarenta choques independentes; IC incluindo zero é inconclusivo, vinte eventos são marco de revisão, e o índice H-P23 só pode rotular decisões posteriores à sua disponibilidade às 13:30Z (procedência: `.claude/state/astra-review-plantao-20260910-1608.md`, "MUST-FIX" 3–4; `.claude/state/plantao/2026-09-11-0815-lane2.md`, H-P23).
