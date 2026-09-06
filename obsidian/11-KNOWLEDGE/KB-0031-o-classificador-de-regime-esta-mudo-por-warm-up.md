---
tags: [knowledge, nota, regime, operacao]
tema: regime de mercado e volatilidade
fonte: o nosso `regime/model.py`, `regime/series.py`, `scanner-worker/regime.py` e o banco local
fonte_url: —
lido_em: 2026-09-06
evidencia: replicado (leitura de código + SQL executado e colado)
hipotese_testavel: sim
astra: pendente
---

# O classificador de regime está mudo — por construção, não por bug

## O que afirma

O `regime_v0` é código correto, revisado e implantado, e **não classifica nada** hoje. O motivo não
é defeito: é o preço do próprio warm-up, que ninguém tinha somado.

A referência de volatilidade só é utilizável com (`RegimeThresholds`, `model.py:134-139`):

- `volatility_window_days = 30` — a janela;
- `volatility_min_samples = 480` — vinte dias cheios de amostras horárias;
- `volatility_min_distinct_days = 20`;
- `volatility_hour_min_minutes = 60` — uma hora amostrada é uma hora **completa**: sessenta velas
  finais contíguas **mais a vela âncora** do minuto anterior (`series.py:176-183`).

Sem referência utilizável, `_volatility_of` devolve `UNKNOWN` (`classifier.py:67-69`); e `UNKNOWN`
em qualquer dimensão faz o regime inteiro ser `MarketRegime.UNKNOWN`, imediatamente, sem histerese.

**Medido no banco local, 2026-09-06:**

```
 scope  | regime  | linhas |              de               |              ate              | abertas
--------+---------+--------+-------------------------------+-------------------------------+---------
 global | UNKNOWN |      1 | 2026-09-06 15:36:17.055342+00 | 2026-09-06 15:36:17.055342+00 |       1
```

Uma única linha, `global`/`UNKNOWN`, aberta. E o insumo explica o porquê:

```
 velas_1m | mercados |           de           |          ate           | dias
----------+----------+------------------------+------------------------+------
   619644 |      232 | 2026-09-04 15:27:00+00 | 2026-09-06 16:12:00+00 |    3
```

Contando as horas que **de fato** virariam amostra para o BTCUSDT (60 retornos contíguos):

```
 horas_completas | dias_distintos | mediana_bps | min_bps | max_bps | razao_max | razao_min
-----------------+----------------+-------------+---------+---------+-----------+-----------
              47 |              3 |      1.5788 |  0.7979 |  3.5444 |     2.245 |     0.505
```

**47 amostras de 480; 3 dias distintos de 20.** Faltam cerca de 433 horas — ao redor de **18 dias**
de coleta ininterrupta — e isso só se nenhuma hora for perdida.

As três consultas, na íntegra, rodadas com
`docker compose -f infra/docker/docker-compose.yml exec -T postgres psql -U hunter -d hunter -f -`:

```sql
-- (1) o estado publicado
SELECT scope, regime, count(*) AS linhas, min(start_time) AS de, max(start_time) AS ate,
       count(*) FILTER (WHERE end_time IS NULL) AS abertas
FROM market_regimes GROUP BY 1,2 ORDER BY 3 DESC;

-- (2) o insumo bruto
SELECT count(*) AS velas_1m, count(DISTINCT market_id) AS mercados,
       min(open_time) AS de, max(open_time) AS ate,
       count(DISTINCT date_trunc('day', open_time)) AS dias
FROM candles WHERE timeframe = '1m';

-- (3) as horas que virariam amostra (60 retornos contíguos de BTCUSDT)
WITH btc AS (
  SELECT c.open_time, c.close,
         lag(c.close)     OVER (ORDER BY c.open_time) AS prev,
         lag(c.open_time) OVER (ORDER BY c.open_time) AS prev_t
  FROM candles c JOIN markets m ON m.id = c.market_id
  WHERE c.timeframe = '1m' AND c.is_final AND m.symbol = 'BTCUSDT'
), ret AS (
  SELECT date_trunc('hour', open_time) AS hora, abs(close/prev - 1) AS r
  FROM btc WHERE prev IS NOT NULL AND prev > 0 AND open_time - prev_t = interval '1 minute'
), amostra AS (
  SELECT hora, count(*) AS minutos, avg(r) AS mad FROM ret GROUP BY 1 HAVING count(*) >= 59
)
SELECT count(*) AS horas_completas, count(DISTINCT hora::date) AS dias_distintos,
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY mad) * 10000)::numeric, 4) AS mediana_bps,
       round((min(mad) * 10000)::numeric, 4) AS min_bps,
       round((max(mad) * 10000)::numeric, 4) AS max_bps,
       round((max(mad) / percentile_cont(0.5) WITHIN GROUP (ORDER BY mad))::numeric, 3) AS razao_max,
       round((min(mad) / percentile_cont(0.5) WITHIN GROUP (ORDER BY mad))::numeric, 3) AS razao_min
FROM amostra;
```

**Diferença declarada entre a consulta (3) e o código:** eu aceito a hora com `>= 59` retornos e não
exijo a **âncora** do minuto anterior à hora, que `series.py:178` exige. A minha contagem é, portanto,
um **limite superior** do número de amostras que o classificador de fato construiria. Isso reforça a
conclusão em vez de enfraquecê-la: o número real é ≤ 47.

## Onde foi mostrado

Instância local. A VPS roda os mesmos containers há 17 h de `postgres` (e o histórico pode ser
maior), mas **não foi consultada**: `psql` por SSH foi recusado pelo portão de permissão da sessão.
Então o número "47 horas" é local; o **mecanismo** é do código e vale nos dois lugares.

## Como mediríamos aqui

O que falta não é análise, é **instrumento**. Hoje o warm-up é invisível: quem olha a tela vê
`UNKNOWN` e não sabe se falta um dia ou dezenove. `VolatilityReference` já carrega `samples`,
`distinct_days`, `window_days`, `usable` e `reason` (`model.py:180-200`) e o motivo já vai para
`supporting_features` — mas nada disso vira métrica observável nem aparece como previsão de
maturidade.

O mínimo:

- publicar `samples` e `distinct_days` no heartbeat do scanner, ao lado do `reason`;
- na tela, trocar "regime: desconhecido" por "regime: aquecendo — 47/480 amostras, 3/20 dias",
  que é o estado vazio honesto que o `CLAUDE.md` exige (dizer qual marco traz o dado);
- contar as horas **rejeitadas** e por quê (menos de 60 minutos · âncora ausente · não contígua ·
  preço zero), porque uma hora rejeitada por gap é uma hora que nunca volta.

## Hipótese testável no Lab

**H-KB0031 (operacional).** Se a coleta rodar sem interrupção, `distinct_days` cresce um por dia e
`samples` cresce ~24 por dia, e o regime sai de `UNKNOWN` no dia 20 de coleta contínua.

- **Confirmação:** a série `samples` medida diariamente segue ~24/dia com desvio pequeno.
- **Refutação, e é o resultado interessante:** `samples` cresce **menos** de 24/dia — o que
  quantifica quantas horas por dia perdemos por gap. Se a perda for grande (digamos, mais de 2 h/dia),
  a exigência de 480/20 vira inatingível na prática, e a decisão passa a ser do Everton: baixar o
  requisito (com o custo de uma mediana pior) ou consertar a continuidade da coleta.
- **Isto não é otimização de parâmetro.** Baixar `volatility_min_samples` para "acender" a tela mais
  cedo seria trocar corretude por aparência, e mudaria o significado das linhas passadas — por isso
  `RegimeThresholds.identity` já obriga um sufixo de versão quando um limiar é sobrescrito
  (`model.py:152-158`).

## Por que pode falhar

- **A janela é móvel.** Não basta acumular 480 amostras uma vez: elas precisam estar **dentro** dos
  últimos 30 dias. Uma parada de coleta de vários dias não só atrasa — ela também derruba amostras
  antigas pela borda da janela.
- **Toda hora exige a âncora.** `series.py` rejeita a hora se a vela do minuto anterior faltar. A
  primeira hora de qualquer histórico nunca é amostrada (custo declarado no próprio código), e um
  gap de **um** minuto na fronteira mata a hora inteira.
- **Enquanto isso, o `RISK_ENGINE` opera com o rótulo `UNKNOWN`.** O que isso significa para o
  multiplicador de regime (`RISK_ENGINE.md` §2 aplica exatamente um) é uma pergunta para quem é dono
  do contrato de risco, não para esta nota — mas ela precisa ser feita antes do M4.

## Segunda opinião (Astra)

Revisão de 2026-09-06 (`astra.sh ask KB-0030-35-regime`). **Confirmou** o mecanismo do warm-up e os
requisitos (480 amostras, 20 dias distintos, hora completa com âncora). **Uma correção aplicada:**
as notas mostravam resultados sem trazer a consulta que os produziu, contra a regra do turno de Lab
("a consulta mora na página"). As três consultas estão agora no texto, junto da diferença declarada
entre a minha contagem e a do `series.py`.

## Relacionados

[[KB-0030-o-regime-nao-chega-ao-sinal]] ·
[[KB-0032-o-relogio-dentro-do-limiar-de-volatilidade]] ·
[[KB-0029-hamilton-e-o-que-um-limiar-com-histerese-nao-e]] ·
[[KB-0018-volume-relatado-e-o-denominador-que-usamos]] · [[Open Bugs]] · [[Strategy Backlog]]
