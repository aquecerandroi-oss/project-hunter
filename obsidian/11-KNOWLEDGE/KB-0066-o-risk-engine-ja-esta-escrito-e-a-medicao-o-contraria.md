---
tags: [knowledge, nota, risco, sizing, risk-engine, m3, m4]
tema: dimensionamento e risco / o contrato que já existe
fonte: docs/RISK_ENGINE.md + medição própria na VPS (livros do hot state, agent_signals, signal_outcomes, candles_1m)
fonte_url: —
lido_em: 2026-09-06
evidencia: replicado (SQL e leitura de livro colados) + leitura de contrato
hipotese_testavel: sim
astra: discorda em parte (correções aplicadas)
---

# O Risk Engine já está escrito — e a medição contraria cinco dos seus limites

## O que afirma

Antes de propor regra nova é preciso dizer o que já existe: **o Risk Engine do M3/M4 não é uma
página em branco**. `docs/RISK_ENGINE.md` tem 116 linhas com vinte checks numerados, uma fórmula de
sizing com **seis** limitantes (mais o arredondamento `floor_to_step`, que é operação posterior e não
limitante — correção da Astra), três perfis de risco com valores, e a máquina de estados do kill
switch.
O que **não** existe é código: `packages/risk-core/hunter_risk/` tem um `__init__.py` de 3 linhas e
nada mais. O contrato é anterior a tudo que este projeto mediu.

Confrontado com 16 h de sinais reais, 200 livros de ordens e 232 mercados da VPS, ele produz cinco
resultados que ninguém previu ao escrevê-lo:

1. **`risk_per_trade_pct` nunca vence `max_position_pct`** — e, **corrigida pela Astra**, a
   conclusão é mais forte e não depende da amostra: nos presets atuais, com os multiplicadores em 1,
   o termo de risco só venceria com distâncias de stop de 10% a 12,5%, **acima do
   `max_stop_distance_pct` de cada perfil (3% / 5% / 8%)** — o check 5 reprovaria a proposta antes.
   Isso **não** significa que `max_position_pct` decida o tamanho: exposição total, por ativo, por
   exchange e caixa podem dar um número menor.
2. **981 das 992 entradas do Lab chegaram quando havia ao menos 6 acompanhamentos anteriores abertos
   na sombra** (906 com ao menos 12). **Isto não é uma taxa de rejeição** — correção da Astra: a
   consulta conta acompanhamentos que uma carteira limitada nem teria aberto.
3. **182 das 232 somas observadas de volume de cotação de 24 h ficam abaixo do piso de 50 M USD** do
   perfil Conservative — **com completude não verificada** (a soma é sobre as barras presentes).
4. **A banda `[min_stop_distance_pct, max_stop_distance_pct]` do Conservative recusa ~14% dos sinais
   de cada estratégia**, pelos dois lados.
5. **O check de correlação (`beta > 0.8`) marca 147 de 232 mercados como correlacionados** — mas a
   correlação mediana entre pares é **0,062**. O critério mede escala de volatilidade, não
   co-movimento.

Nenhum desses cinco é, sozinho, prova de que o limite está errado. Todos são prova de que **o limite
nunca foi confrontado com o dado** — e de que a população que o Lab estuda e a população que o
produto operaria **não são a mesma**.

## Onde foi mostrado

Tudo na **VPS**, em 2026-09-06 entre 19:45 e 20:00 UTC. Janela do Lab: `agent_signals` vai de
2026-09-06 03:40:04 a 19:45:07 UTC — **16 horas**, 1.034 sinais. As velas de 1 min cobrem desde
2026-09-04 21:40 (600.056 linhas, 232 mercados).

### O sizing: qual limitante vence, na aritmética do próprio contrato

A fórmula de `docs/RISK_ENGINE.md` §4 toma o **mínimo** de seis quantidades. Duas delas competem
sempre:

```
qty_by_risk     = (equity × risk_per_trade_pct) / (entry_ref × stop_distance)
qty_by_position = (equity × max_position_pct)   /  entry_ref
```

`qty_by_risk < qty_by_position` **se e somente se**
`stop_distance > risk_per_trade_pct / max_position_pct`. Esse quociente é:

| Perfil | `risk_per_trade_pct` | `max_position_pct` | quociente = distância de stop a partir da qual o risco vira o limitante |
|---|---|---|---|
| Conservative | 0,0025 | 0,02 | **12,5%** |
| Balanced | 0,005 | 0,05 | **10,0%** |
| Aggressive | 0,01 | 0,10 | **10,0%** |

E as distâncias de stop que as nossas estratégias produzem, medidas na **entrada efetiva**
(`virtual_entry`, `virtual_stop` — que é exatamente o par `entry_ref`/`stop` do check `stop_distance`):

```sql
WITH s AS (
  SELECT st.key || ' ' || sv.version AS estrategia, o.virtual_entry AS e, o.virtual_stop AS sp
  FROM signal_outcomes o
  JOIN agent_signals a ON a.id = o.signal_id
  JOIN strategy_versions sv ON sv.id = a.strategy_version_id
  JOIN strategies st ON st.id = sv.strategy_id
  WHERE o.virtual_entry IS NOT NULL AND o.virtual_stop IS NOT NULL AND o.virtual_entry > 0
)
SELECT estrategia, count(*) AS entradas,
  round((100*percentile_cont(0.10) WITHIN GROUP (ORDER BY ((e-sp)/e)::numeric))::numeric,4) AS p10_pct,
  round((100*percentile_cont(0.50) WITHIN GROUP (ORDER BY ((e-sp)/e)::numeric))::numeric,4) AS mediana_pct,
  round((100*percentile_cont(0.90) WITHIN GROUP (ORDER BY ((e-sp)/e)::numeric))::numeric,4) AS p90_pct,
  round((100*max((e-sp)/e))::numeric,4) AS max_pct,
  count(*) FILTER (WHERE (e-sp)/e < 0.003) AS abaixo_0_003,
  count(*) FILTER (WHERE (e-sp)/e > 0.03) AS acima_0_03,
  count(*) FILTER (WHERE (e-sp)/e > 0.05) AS acima_0_05,
  count(*) FILTER (WHERE (e-sp)/e > 0.08) AS acima_0_08
FROM s GROUP BY 1 ORDER BY 1;
```

```
    estrategia     | entradas | p10_pct | mediana_pct | p90_pct | max_pct | abaixo_0_003 | acima_0_03 | acima_0_05 | acima_0_08
-------------------+----------+---------+-------------+---------+---------+--------------+------------+------------+------------
 momentum v1       |      309 |  0.8349 |      1.5174 |  3.5194 |  6.3661 |            0 |         50 |          8 |          0
 volume_anomaly v1 |      683 |  0.3722 |      0.9576 |  2.3673 |  9.3238 |           44 |         35 |          6 |          1
```

**A maior distância de stop observada em 992 entradas é 9,32%** — abaixo dos 10% de que o
`qty_by_risk` precisaria para vencer.

**E há um argumento mais forte, que a Astra apontou e que não depende de amostra nenhuma:** os
limiares de 12,5% / 10% / 10% estão **acima do `max_stop_distance_pct` de cada perfil**, que é 3% /
5% / 8% (`docs/RISK_ENGINE.md` §2). Uma proposta com distância de stop grande o bastante para o
termo de risco vencer seria **reprovada pelo check 5 antes de chegar ao sizing**. Nos presets
atuais, com os multiplicadores em 1, `qty_by_risk` **não pode** ser o mínimo — isso é propriedade da
tabela de limites, não da nossa população.

Daí sai a quantidade que o rótulo esconde. **Nome correto, exigido pela revisão: risco bruto no
stop, supondo a posição limitada exclusivamente pelo teto por posição e sem arredondamento.** Não é
risco observado — custos e gaps ficam de fora, e os outros quatro limitantes podem dar um número
menor ainda:

| Perfil | `risk_per_trade_pct` (rótulo) | `max_position_pct × 1,5174%` | razão |
|---|---|---|---|
| Conservative | 0,25% do equity | **0,030348%** | 8,2× menor |
| Balanced | 0,50% | **0,075870%** | 6,6× menor |
| Aggressive | 1,00% | **0,151740%** | 6,6× menor |

Isso não é bug de implementação — não há implementação. É uma propriedade da tabela de limites que
só aparece quando se põe `risk_per_trade_pct`, `max_position_pct` e `max_stop_distance_pct` lado a
lado, e ninguém tinha posto.

**Ressalva de instrumento, também da revisão:** `virtual_entry` é o preenchimento sintético do Lab
(`next_1m_open`, `persist.py:54`). O `entry_ref` do contrato é o meio da `entry_zone` ou o último
preço dentro dela. **São referências diferentes**, e a igualdade entre elas é suposição minha, não
fato. O que a medição acima sustenta é a distribuição de `(entrada − stop)/entrada` como a
estratégia a produz; se o Risk Engine usar outra referência, a distribuição muda.

### Concorrência: quantas entradas chegaram com N acompanhamentos anteriores abertos

**Título corrigido na revisão.** A consulta abaixo **não** simula uma carteira: ela conta quantos
acompanhamentos anteriores da sombra ainda estavam abertos quando cada entrada aconteceu — inclusive
acompanhamentos que uma carteira com teto **nem teria aberto**. Ela mede **demanda**, não taxa de
rejeição. Cenário que a Astra usou para derrubar a minha leitura original: seis operações aceitas
terminam, mas acompanhamentos que a carteira teria recusado continuam abertos na sombra; a consulta
acusa lotação onde a carteira teria slot livre. A taxa de rejeição exige simulação sequencial com
regra de desempate declarada — e entradas no mesmo minuto (houve um com 31) precisariam competir
entre si.

```sql
WITH iv AS (
  SELECT o.signal_id, o.entry_ts, coalesce(o.exit_ts, o.tracked_until, now()) AS fim
  FROM signal_outcomes o WHERE o.entry_ts IS NOT NULL
), arr AS (
  SELECT i.signal_id, i.entry_ts,
         (SELECT count(*) FROM iv j WHERE j.entry_ts < i.entry_ts AND j.fim > i.entry_ts) AS abertos_antes
  FROM iv i
)
SELECT count(*) AS entradas,
  count(*) FILTER (WHERE abertos_antes >= 3)  AS bloqueadas_teto_3,
  count(*) FILTER (WHERE abertos_antes >= 6)  AS bloqueadas_teto_6,
  count(*) FILTER (WHERE abertos_antes >= 12) AS bloqueadas_teto_12,
  count(*) FILTER (WHERE abertos_antes >= 25) AS bloqueadas_teto_25
FROM arr;
```

```
 entradas | bloqueadas_teto_3 | bloqueadas_teto_6 | bloqueadas_teto_12 | bloqueadas_teto_25
----------+-------------------+-------------------+--------------------+--------------------
      992 |               981 |               981 |                906 |                453
```

E a curva de ocupação (`entry_ts` até `exit_ts`, ou `tracked_until`, ou agora):
**mediana 27 abertos, p95 44, máximo 50**, num intervalo de 16 h. Houve um minuto com **31 entradas
simultâneas**.

### Liquidez de 24 h: o piso do contrato contra o universo real

```sql
WITH v AS (
  SELECT c.market_id, sum(c.quote_volume) AS qv_24h, count(c.quote_volume) AS barras_com_qv,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY c.quote_volume) AS qv_1m_mediana
  FROM candles_1m c WHERE c.open_time >= now() - interval '24 hours' GROUP BY 1
)
SELECT count(*) AS mercados, count(*) FILTER (WHERE barras_com_qv = 0) AS sem_quote_volume,
  round(percentile_cont(0.10) WITHIN GROUP (ORDER BY qv_24h)::numeric) AS p10_qv24h,
  round(percentile_cont(0.50) WITHIN GROUP (ORDER BY qv_24h)::numeric) AS mediana_qv24h,
  round(percentile_cont(0.90) WITHIN GROUP (ORDER BY qv_24h)::numeric) AS p90_qv24h,
  round(percentile_cont(0.50) WITHIN GROUP (ORDER BY qv_1m_mediana)::numeric,2) AS mediana_qv_1min,
  round(percentile_cont(0.10) WITHIN GROUP (ORDER BY qv_1m_mediana)::numeric,2) AS p10_qv_1min,
  count(*) FILTER (WHERE qv_24h < 5000000) AS abaixo_5M,
  count(*) FILTER (WHERE qv_24h < 20000000) AS abaixo_20M,
  count(*) FILTER (WHERE qv_24h < 50000000) AS abaixo_50M
FROM v;
```

```
 mercados | sem_quote_volume | p10_qv24h | mediana_qv24h | p90_qv24h | mediana_qv_1min | p10_qv_1min | abaixo_5m | abaixo_20m | abaixo_50m
----------+------------------+-----------+---------------+-----------+-----------------+-------------+-----------+------------+------------
      232 |                0 |   2746595 |      13853954 | 156762105 |         4605.10 |     1024.13 |        45 |        142 |        182
```

**Cobertura de `quote_volume`: 232 de 232 mercados têm o campo somável nas velas de 1 min.** Isso
confirma, com dado e não com leitura de código, o caminho alternativo que a Astra abriu para a `M-B`
no [[Registro de Tentativas]] (T-031): o volume de cotação de 24 h **é reconstruível somando velas**.
A ressalva do *nullable* continua valendo para barras individuais — aqui nenhum mercado ficou com
zero barras preenchidas, mas a fração de barras nulas por mercado não foi medida.

O que o contrato faz com isso: `min_liquidity_usd_24h` = 50 M / 20 M / 5 M deixa abaixo do piso,
respectivamente, **182, 142 e 45** das 232 **somas observadas**. **Correção da revisão:** isto é
soma sobre as barras **presentes**, e 34 mercados têm lacunas nas últimas 24 h
([[KB-0074-risco-operacional-as-regras-de-nao-operar-quando]]) — um mercado com 40 M observados e
barras faltando que valeriam 20 M seria classificado abaixo de 50 M sem estar. A leitura correta é
**"182 somas observadas abaixo do piso, com completude não verificada"**, e reconciliar barras
esperadas, presentes, ausentes e nulas é pré-requisito de qualquer decisão sobre o piso.

## Como mediríamos aqui

Os cinco resultados acima não são "erros do contrato" — são **três coisas diferentes**, e a diferença
importa:

| Achado | Natureza | O que fazer |
|---|---|---|
| `risk_per_trade_pct` nunca vence `max_position_pct` nos presets | **incoerência interna** da tabela: a banda de stop admissível exclui, por construção, o regime em que o termo de risco morderia | escolher qual é o instrumento de sizing e dizer isso na página; é decisão do Everton |
| Concorrência na sombra | **diferença de população**: o Lab não tem carteira, então nunca competiu por slot de capital | não muda o limite; muda o que a sombra pode alegar sobre o produto |
| Piso de liquidez de 24 h | **desalinhamento entre o universo e o perfil** | ou o universo encolhe, ou o piso desce; ver a medição de capacidade em [[KB-0070-a-tabela-de-capacidade-quantos-mercados-suportam-cada-tamanho]] |
| Banda de distância de stop | **interação com a estratégia**, não com o mercado | a `volume_anomaly_v1` usa a mínima da barra como stop (`volume_anomaly_v1.py:183`), e é ela quem produz os 44 stops abaixo de 0,3% |
| `beta > 0.8` como correlação | **erro de medida** | ver [[KB-0071-beta-maior-que-0-8-nao-separa-nada-no-nosso-universo]] |

**Correção de leitura que eu mesma tive de fazer no meio da medição:** a primeira versão desta
consulta calculava a distância de stop como `(ref − stop)/ref` com `ref = (stop + alvo1)/2`,
supondo a simetria `stop_atr = target_atr = 1,5`. Isso vale para a `momentum_v1`
(`momentum_v1.py:217-218`), e **não vale** para a `volume_anomaly_v1`, cujo stop é a **mínima da
barra do sinal** (`volume_anomaly_v1.py:183`) e cujo alvo é `close + 1,5 × ATR`. A linha de
`volume_anomaly` daquela primeira consulta foi descartada; os números publicados acima são os da
entrada efetiva, que não dependem dessa suposição.

## Hipótese testável no Lab

**Não é hipótese de estratégia.** É um requisito de contrato, e o mais barato desta rodada:

`R-PROV-1` — **publicar o limitante vencedor**. Quando o `RiskEngine.evaluate` existir, ele já deve
gravar `sizing.binding_constraint` (o contrato pede, §4). O acréscimo é ter uma consulta padrão que
publique a **distribuição** do limitante vencedor sobre a população de propostas, junto com o
`stop_distance` de cada uma. Sem isso, "risco de 0,5% por operação" continua sendo uma frase que
nenhum dado pode contrariar — exatamente o defeito que a
[[KB-0036-o-tamanho-que-a-sombra-nunca-declara]] apontou no custo.

O que a refutaria: nada. É proveniência, não previsão.

## Por que pode falhar

- **A janela é de 16 h, num regime só, sem stress.** Toda a aritmética de qual limite vence depende
  da distribuição de `stop_distance`, e essa distribuição muda com a volatilidade. Num dia de queda
  de 15% o ATR sobe, os stops ficam mais largos, e o `qty_by_risk` pode passar a vencer.
- **A população do Lab não é a população do produto.** O Lab abre acompanhamento em todo sinal
  elegível; o produto teria teto de posições, teto de exposição e caixa finito. Comparar as duas é
  informativo sobre **o que mudaria**, não sobre o que aconteceria.
- **`signal_outcomes` cobre 16 h e 992 entradas**, e o piso editorial (100 outcomes e 30 dias) não
  foi atingido em dias. Tudo aqui é descrição da amostra, não inferência.
- **A concorrência de 27 medianos é da sombra sem restrição.** Se o Risk Engine existisse, ele
  próprio reduziria a concorrência — o número mede a demanda, não a ocupação futura.

## Segunda opinião (Astra)

Revisão de 2026-09-06 (`.claude/state/astra-review-KB-sizing-risk-1.md`). Ela conferiu as duas
tabelas principais recomputando-as com `Decimal` e confirmou os números; **derrubou quatro
conclusões minhas**, todas já corrigidas acima:

1. **"`max_position_pct` sempre vence" não decorre da comparação feita.** Exposição total, por
   ativo, por exchange e caixa podem dar quantidade menor. Cenário: equity 10.000, preço 100,
   Balanced, stop 1,5%, caixa disponível 100, `max_leverage = 2` → `qty_by_risk = 33,33`,
   `qty_by_position = 5`, **`qty_by_cash = 2`**. Quem decide é o caixa.
   **E ela ofereceu uma conclusão melhor que a minha:** os limiares (12,5 / 10 / 10%) estão acima do
   `max_stop_distance_pct` de cada perfil (3 / 5 / 8%), então o termo de risco não pode vencer
   **independentemente da amostra** — o check 5 reprova antes.
2. **A tabela de "risco efetivo" está com o nome errado.** É *risco bruto no stop, supondo posição
   limitada exclusivamente pelo teto por posição e sem arredondamento*. Custos e gaps ficam fora.
3. **"Recusaria 98,9% das entradas" confunde demanda irrestrita com carteira simulada.** Corrigido
   para "981 entradas chegaram quando havia ao menos 6 acompanhamentos anteriores abertos na
   sombra".
4. **A soma de `quote_volume` das barras presentes não prova volume completo de 24 h.** Corrigido
   para "182 somas observadas abaixo do piso, com completude não verificada".

Também corrigiu **"sete limitantes" → seis** (`floor_to_step` é operação, não limitante) e apontou
que **`virtual_entry` não é comprovadamente o `entry_ref`** do futuro Risk Engine (o contrato usa a
zona/preço atual; a sombra persiste `next_1m_open`, `persist.py:54`).

**Concordou com:** as contas das duas tabelas sob as condições explicitadas; que a sombra não
demonstra PnL nem drawdown de carteira; e que o dado apresentado **não** justifica alterar limite
nenhum automaticamente.

## Relacionados

[[Strategy Backlog]] · [[Registro de Tentativas]] · [[Index]] ·
[[KB-0067-a-fracao-de-risco-por-operacao-e-o-preco-de-errar-a-expectancy]] ·
[[KB-0068-sizing-por-volatilidade-a-posicao-sai-do-atr]] ·
[[KB-0070-a-tabela-de-capacidade-quantos-mercados-suportam-cada-tamanho]] ·
[[KB-0071-beta-maior-que-0-8-nao-separa-nada-no-nosso-universo]] ·
[[KB-0064-a-cauda-de-queda-e-o-que-o-risk-engine-vai-precisar]] ·
[[KB-0036-o-tamanho-que-a-sombra-nunca-declara]] · [[KB-0046-r-multiplos-e-o-r-que-a-simetria-esconde]]
