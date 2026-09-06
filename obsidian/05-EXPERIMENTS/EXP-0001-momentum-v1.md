---
tags: [experimento, momentum, shadow-lab]
updated: 2026-09-06
status: em-andamento
---

# EXP-0001 — momentum em modo sombra (perfil "por barras" v0)

> Experimento aberto em **2026-09-06** com a primeira ativação auditada de `momentum v1`
> (2026-09-05 23:19:56 UTC). A seção "Protocolo" é escrita uma vez e **nunca** muda; as avaliações
> são **acrescentadas** abaixo, datadas. Ver [[Experiments Index]], [[Momentum Agent]] e
> [[Dialogos/SHADOW]].

## Hipótese (congelada)

Um rompimento de 15 minutos acompanhado de volume relativo alto, em regime de volatilidade
intermediária, é seguido por continuação suficiente para alcançar um alvo a 1,5 ATR da referência
antes de tocar um stop simétrico a 1,5 ATR, líquido dos custos assumidos.

## Protocolo (congelado na primeira ativação — nunca editar)

- **Strategy:** `strategies.key = momentum`; coortes de versão `v1` (ativada 2026-09-05
  23:19:56.334638+00, `deprecated` em 2026-09-06 02:08:13.332014+00) e `v2` (ativada 2026-09-06
  02:08:13.332014+00, `active`).
- **code_ref:**
  - `v1` — `hunter_core.strategies@sha256:13dfa32298cbc2dbbe54aac4cd785be4a85246cdf5daaa9564a4cf29301ea0b5` (digest da árvore inteira)
  - `v2` — `hunter_core.strategies.momentum_v1@sha256:c012f75cdd8492d3eb46aa9abd536320220c3bf71788e47e6b6b73218b0ba823` (digest do módulo + fecho transitivo dos imports)
- **params_hash / params_format:** `40e1688e6b5f6385674cb47a81e542b215b320eb5643a1375f6401f5c41ac2f3` / `1` — **idêntico nas duas versões**, porque `default_parameters` e `parameters_schema` são bit a bit os mesmos (verificado por SQL). O que separa v1 de v2 é **só** o `code_ref`; a população é separada pelo `strategy_version_id`, que entra no `uuid5` de cada sinal.
- **Parameters (`default_parameters` congelados, nada implícito):**

```json
{
  "assumed_spread_bps": "2", "atr_bars": "97", "atr_pct_max": "0.05", "atr_pct_min": "0.003",
  "atr_period": "14", "atr_timeframe": "15m", "base_confidence": "0.5", "fee_bps": "4",
  "horizon_s": "14400", "lookback_closes": "20", "max_entry_delay_s": "120", "return_min": "0",
  "rvol_min": "1.5", "rvol_window": "96", "slippage_bps": "5", "stop_atr": "1.5",
  "target2_atr": "3", "target3_atr": "4.5", "target_atr": "1.5"
}
```

- **Timeframe de decisão / de outcome:** 15 min (fechamentos distintos, UTC) / 1 min.
- **Agregação e ATR:** 1 m → 15 m só com barras UTC contíguas e finais até `source_bar_close`;
  ATR = Wilder(14) de 15 min com seed/âncora persistidos. Um único minuto ausente na janela torna
  a avaliação `unavailable: gap` — é recusa deliberada de agregar sobre buraco.
- **Entrada:** open da primeira barra de 1 min estritamente posterior a `decision_at`, com
  `entry_bar_open − source_bar_close ≤ 120 s` (`max_entry_delay_s`), decisão persistida **antes**
  daquela abertura; senão `no_entry: late:*`. Geometria revalidada com `P_entry`
  (`stop < P_entry < target1`), senão `no_entry: geometry`.
- **Saída:** gap na abertura primeiro, depois toques intrabar; stop e alvo na mesma barra →
  **stop** (convenção pessimista); prioridade na mesma abertura `stop > target > expired >
  invalidated`; horizonte **4 h** contado da entrada.
- **Custos assumidos (hipóteses declaradas, não tarifas verificadas):** spread total 2 bps,
  slippage 5 bps por lado, taxa 4 bps por lado, funding assinado; `R_net = null` com motivo quando
  o funding aplicável não é apurável, preservando `meta.r_ex_funding`.
- **Política de reentrada:** um acompanhamento `pending_entry|active` por
  `(strategy_version_id, market_id, cohort)`; rearme só após barra elegível com a condição falsa
  **depois** do término anterior (barreira em `shadow_episodes.last_bar_close`).
- **Cohort:** `prospective` (nenhum replay foi rodado).
- **Universo elegível:** top 50 por volume 24 h do `market-worker` (override do T1.6b), com a
  composição do instante gravada no envelope imutável de cada sinal
  (`agent_signals.supporting_features`); `tracking_hold` mantém a coleta de um mercado excluído
  enquanto houver acompanhamento aberto.
- **Markets:** Binance USDS-M, perpétuos USDT, **LONG apenas**.
- **Data de início da coleta:** 2026-09-06 (primeiro sinal `v1` às 00:30:11 UTC; primeiro `v2` às 02:15:29 UTC).
- **Isolamento:** todo sinal carrega `purpose = research_only` e sai no stream próprio
  `shadow.signals.emitted`. Nada aqui pode ordenar coisa alguma.

## Avaliações (acrescentadas, nunca reescritas)

### Avaliação de 2026-09-06 — `as_of = 2026-09-06T02:55:00Z`, `read_at = 2026-09-06T03:13:03.911076Z`

**Semântica do corte, sem eufemismo.** A população é congelada por `emitted_at <= as_of`. Os estados
dos acompanhamentos são os do instante `read_at`, lidos num **único snapshot**
(`BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY`), para que as três consultas desta
avaliação descrevam o mesmo mundo. **Esta leitura não é reconstruível.** `signal_outcomes` avança no
lugar e não há histórico de estados preservado: reexecutar o SQL amanhã devolve a mesma população
com estados **diferentes**, e não existe consulta que recomponha os estados de hoje. É por isso que
a avaliação é acrescentada e datada em vez de recalculada — a página é o único registro do que se
via neste instante.

**SQL usado** (`docker compose -f infra/docker/docker-compose.yml exec -T postgres psql -U hunter -d hunter -f -`):

```sql
\set as_of '2026-09-06T02:55:00Z'
\set skey 'momentum'
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT now() AS read_at;

-- (1) cobertura: contagens completas, motivos exatos, coorte e propósito impostos
WITH pop AS (
  SELECT v.version, v.status, s.id, s.market_id, s.expires_at,
         o.tracking_state, o.result, o.r_multiple, o.entry_ts, o.exit_ts,
         coalesce(o.no_entry_reason, o.censored_reason) AS motivo,
         (o.meta->'funding'->>'reason') AS funding_reason
  FROM agent_signals s
  JOIN strategy_versions v ON v.id = s.strategy_version_id
  JOIN strategies st ON st.id = v.strategy_id
  LEFT JOIN signal_outcomes o ON o.signal_id = s.id
  WHERE st.key = :'skey'
    AND s.emitted_at <= :'as_of'::timestamptz
    AND s.supporting_features->>'cohort'  = 'prospective'
    AND s.supporting_features->>'purpose' = 'research_only'
)
SELECT version, status,
  count(*) AS emitidos,
  count(*) FILTER (WHERE tracking_state='pending_entry') AS pendentes,
  count(*) FILTER (WHERE entry_ts IS NOT NULL)           AS entradas,
  count(*) FILTER (WHERE motivo='late:delay')            AS ne_late_delay,
  count(*) FILTER (WHERE motivo='geometry')              AS ne_geometry,
  count(*) FILTER (WHERE tracking_state='no_entry' AND motivo NOT IN ('late:delay','geometry')) AS ne_outros,
  count(*) FILTER (WHERE tracking_state='active')        AS ativos,
  count(*) FILTER (WHERE result='target')                AS target,
  count(*) FILTER (WHERE result='stop')                  AS stop,
  count(*) FILTER (WHERE result='expired')               AS expired,
  count(*) FILTER (WHERE result='invalidated')           AS invalidated,
  count(*) FILTER (WHERE tracking_state='censored')      AS censurados,
  count(*) FILTER (WHERE tracking_state='terminal' AND r_multiple IS NULL) AS r_nulo,
  count(*) FILTER (WHERE funding_reason IS NOT NULL)     AS funding_indisp,
  count(DISTINCT market_id)                              AS mercados
FROM pop GROUP BY 1,2 ORDER BY 1;

-- (2) métricas, com a maturação do horizonte separada
WITH pop AS (
  SELECT v.version, s.expires_at, o.tracking_state, o.result, o.r_multiple, o.exit_ts
  FROM agent_signals s
  JOIN strategy_versions v ON v.id = s.strategy_version_id
  JOIN strategies st ON st.id = v.strategy_id
  JOIN signal_outcomes o ON o.signal_id = s.id
  WHERE st.key = :'skey'
    AND s.emitted_at <= :'as_of'::timestamptz
    AND s.supporting_features->>'cohort'  = 'prospective'
    AND s.supporting_features->>'purpose' = 'research_only'
), aval AS (
  SELECT * FROM pop WHERE tracking_state='terminal' AND r_multiple IS NOT NULL
)
SELECT version,
  count(*)                                                              AS encerrados_avaliaveis,
  count(*) FILTER (WHERE expires_at <= now())                           AS horizonte_maturado,
  count(*) FILTER (WHERE expires_at >  now())                           AS encerrou_antes_do_horizonte,
  round(count(*) FILTER (WHERE result='target')::numeric
      / NULLIF(count(*) FILTER (WHERE result IN ('target','stop')),0), 4)  AS taxa_alvo_toques,
  round(count(*) FILTER (WHERE r_multiple>0)::numeric / NULLIF(count(*),0), 4) AS taxa_lucro_liquido,
  round(avg(r_multiple), 6)                                             AS expectancy_R,
  round(sum(r_multiple), 6)                                             AS soma_R,
  round(coalesce(sum(r_multiple) FILTER (WHERE r_multiple>0), 0), 6)    AS soma_R_pos,
  round(coalesce(sum(r_multiple) FILTER (WHERE r_multiple<0), 0), 6)    AS soma_R_neg,
  round(coalesce(sum(r_multiple) FILTER (WHERE r_multiple>0), 0)
      / NULLIF(abs(sum(r_multiple) FILTER (WHERE r_multiple<0)), 0), 4) AS profit_factor,
  count(DISTINCT (exit_ts AT TIME ZONE 'UTC')::date)                    AS dias_distintos
FROM aval GROUP BY 1 ORDER BY 1;

-- (3) motivos exatos de exclusão, sem LIKE
WITH pop AS (
  SELECT v.version, o.tracking_state, coalesce(o.no_entry_reason,o.censored_reason) AS motivo
  FROM agent_signals s
  JOIN strategy_versions v ON v.id = s.strategy_version_id
  JOIN strategies st ON st.id = v.strategy_id
  JOIN signal_outcomes o ON o.signal_id = s.id
  WHERE st.key = :'skey'
    AND s.emitted_at <= :'as_of'::timestamptz
    AND s.supporting_features->>'cohort'  = 'prospective'
    AND s.supporting_features->>'purpose' = 'research_only'
    AND (o.no_entry_reason IS NOT NULL OR o.censored_reason IS NOT NULL)
)
SELECT version, tracking_state, motivo, count(*) FROM pop GROUP BY 1,2,3 ORDER BY 1,2,3;
COMMIT;
```

**Saída real (colada):**

```
            read_at
-------------------------------
 2026-09-06 03:13:03.911076+00
(1 row)

 version |   status   | emitidos | pendentes | entradas | ne_late_delay | ne_geometry | ne_outros | ativos | target | stop | expired | invalidated | censurados | r_nulo | funding_indisp | mercados
---------+------------+----------+-----------+----------+---------------+-------------+-----------+--------+--------+------+---------+-------------+------------+--------+----------------+----------
 v1      | deprecated |       72 |         0 |       67 |             5 |           0 |         0 |     17 |     34 |    6 |       0 |           8 |          2 |      0 |              0 |       67
 v2      | active     |       18 |         4 |       11 |             3 |           0 |         0 |      2 |      2 |    2 |       0 |           5 |          0 |      0 |              0 |       18
(2 rows)

 version | encerrados_avaliaveis | horizonte_maturado | encerrou_antes_do_horizonte | taxa_alvo_toques | taxa_lucro_liquido | expectancy_r |  soma_r   | soma_r_pos | soma_r_neg | profit_factor | dias_distintos
---------+-----------------------+--------------------+-----------------------------+------------------+--------------------+--------------+-----------+------------+------------+---------------+----------------
 v1      |                    48 |                  0 |                          48 |           0.8500 |             0.7083 |     0.305274 | 14.653130 |  25.140250 | -10.487120 |        2.3973 |              1
 v2      |                     9 |                  0 |                           9 |           0.5000 |             0.2222 |    -0.436204 | -3.925839 |   1.280940 |  -5.206778 |        0.2460 |              1
(2 rows)

 version | tracking_state |            motivo             | count
---------+----------------+-------------------------------+-------
 v1      | no_entry       | late:delay                    |     5
 v1      | censored       | gap:2026-09-06T00:54:00+00:00 |     1
 v1      | censored       | gap:2026-09-06T01:24:00+00:00 |     1
 v2      | no_entry       | late:delay                    |     3
(4 rows)
```

Consulta auxiliar de excursões (fora do snapshot, com `read_at` próprio de 2026-09-06T02:56:27Z; os
números não mudam entre as duas leituras porque excursão de outcome encerrado não se move):

```sql
select st.key, v.version,
  count(*) filter (where o.mfe is null) as mfe_nulo,
  count(*) filter (where o.mae is null) as mae_nulo,
  count(*) filter (where (o.meta->'excursions'->>'ambiguous')::bool) as ambiguos
from agent_signals s join strategy_versions v on v.id=s.strategy_version_id
join strategies st on st.id=v.strategy_id join signal_outcomes o on o.signal_id=s.id
where s.emitted_at <= '2026-09-06T02:55:00Z'::timestamptz group by 1,2 order by 1,2;
```

```
      key       | version | mfe_nulo | mae_nulo | ambiguos
----------------+---------+----------+----------+----------
 momentum       | v1      |       58 |       31 |       59
 momentum       | v2      |       11 |       11 |        6
```

**Cobertura (contagens completas, motivos exatos, por coorte de versão):**

| Coorte | Emitidos | Pendentes | Entradas | `late:delay` | `geometry` | Outros motivos | Ativos | Target | Stop | Expired | Invalidated | Censurados | Funding indisp. | Mercados |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `v1` (deprecated) | 72 | 0 | 67 | 5 | 0 | 0 | 17 | 34 | 6 | 0 | 8 | 2 | 0 | 67 |
| `v2` (active) | 18 | 4 | 11 | 3 | 0 | 0 | 2 | 2 | 2 | 0 | 5 | 0 | 0 | 18 |

Censura da v1, por minuto exato: `gap:2026-09-06T00:54:00+00:00` (1) e
`gap:2026-09-06T01:24:00+00:00` (1). As contagens fecham: v1 → 17 + 48 + 5 + 2 = 72;
v2 → 4 + 2 + 9 + 3 = 18. "Entradas" é contagem histórica e **se sobrepõe** aos estados: os 2
censurados da v1 já tinham entrado, então estão dentro dos 67.

**Métricas (distintas, com denominador explícito):**

| Métrica | `v1` | `v2` | Denominador | Observação |
|---|---|---|---|---|
| Taxa de alvo entre toques resolvidos | 0,8500 | 0,5000 | `target + stop` (v1: 40; v2: 4) | **não** é taxa de lucro |
| Taxa de lucro líquido | 0,7083 | 0,2222 | encerrados avaliáveis (v1: 48; v2: 9) | `R_net > 0` |
| Expectancy líquida hipotética em R por entrada encerrada avaliável | +0,305274 | −0,436204 | mesma população | média de `R_net` |
| Profit Factor | 2,3973 | 0,2460 | Σ R+ / \|Σ R−\| | v1: 25,140250 / 10,487120 · v2: 1,280940 / 5,206778 |
| MFE/MAE | `mfe` nulo em 58 de 72, `mae` nulo em 31, 59 ambíguos | `mfe` nulo em 11 de 18, `mae` nulo em 11, 6 ambíguos | todos os outcomes da coorte | nulo quando o OHLC não determina o extremo; limites em `meta.excursions.bounds` |
| Soma de R hipotéticos | +14,653130 | −3,925839 | encerrados avaliáveis | soma escalar; **não é equity** e não é trajetória (uma curva exigiria ordenar e supor capital, que não existe) |
| **PnL de carteira** | **não aplicável** | **não aplicável** | — | não há carteira no Shadow Lab |
| **Max Drawdown de carteira** | **não aplicável** | **não aplicável** | — | idem |

**Maturação do horizonte — o achado mais importante desta avaliação:**

| Coorte | Encerrados avaliáveis | Com horizonte de 4 h **maturado** | Encerraram **antes** do horizonte |
|---|---|---|---|
| `v1` | 48 | **0** | 48 |
| `v2` | 9 | **0** | 9 |

**Nenhum** dos 57 acompanhamentos encerrados teve as 4 h de horizonte disponíveis — o primeiro sinal
saiu às 00:30 e a leitura é de 03:13. Logo, **100% da população avaliável é composta de
acompanhamentos que resolveram rápido**, e os que estão demorando continuam `active`, fora de todas
as métricas acima. Não é ruído amostral: é viés de composição com direção conhecida, e ele muda
sozinho conforme o tempo de observação cresce. Todo número desta avaliação deve ser lido como
"entre os que resolveram nas primeiras horas", nunca como "entre os sinais emitidos".

- **Dias distintos com outcome avaliável:** **1** (2026-09-06) nas duas coortes.
- **Janela real de emissões:** v1 de 00:30:11 a 02:01:33 UTC; v2 de 02:15:29 a 02:17:39 UTC.
- **Versão da métrica / proveniência:** `shadow_metrics_v1`; `agent_signals` + `signal_outcomes` +
  `strategy_versions`; banco local `hunter`; coorte `prospective` e `purpose = research_only`
  **impostos na consulta**, não apenas declarados.
- **Cobertura de funding:** 0 outcomes com funding indisponível. `funding_rates` tem 1512 linhas em
  213 mercados entre 2026-09-04 17:00 e 2026-09-06 02:00 UTC e, com horizontes curtos, nenhum
  acompanhamento atravessou uma liquidação (`meta.funding.settlements = 0`). A pendência
  `funding_schedule_unknown` de `.claude/state/notes-S2.md` §14 **não** se materializou.
- **Avaliações recusadas — o que se sabe e o que não se sabe.** O heartbeat `hb:strategy:shadow` às
  02:56:38 UTC marcava `evaluations_by_state = {"unavailable":400,"ineligible":1}` sobre
  `evaluated_bars = 401`. **Esse contador é operacional e não é cobertura deste experimento:** é
  acumulado em memória desde a inicialização do worker e soma as avaliações das **duas** estratégias
  e das quatro versões, sem quebra por estratégia nem por motivo. O que ele permite afirmar é que,
  na janela recente, o worker praticamente não conseguiu avaliar nada; a causa foi medida à parte (o
  `market-worker` local fora do ar de 02:04 a ~02:47 UTC, **773 `ingestion_gaps` `open`**). O que
  **não** existe é a cobertura histórica de avaliações recusadas por estratégia e por motivo — não é
  persistida em lugar nenhum. Registrado em [[Open Bugs]] e como requisito da S3.
- **Result:** **inconclusivo** — o limiar editorial é 100 outcomes avaliáveis **E** 30 dias
  distintos; há 48 (v1) e 9 (v2) em **1** dia, nenhum com horizonte maturado.
- **Conclusion:** o que estes números provam é que o **instrumento** funciona: alvo, stop,
  invalidação, `late:delay` e censura por gap irrecuperável apareceram sobre dado real da Binance,
  sem caso forçado; as contagens fecham; coorte e propósito são impostos pela consulta. O que eles
  **não** provam é nada sobre a estratégia, por três razões nomeadas: (a) **1 dia**, contra os 30 do
  limiar; (b) **nenhum horizonte maturado** — só os que resolveram cedo estão na conta; (c) 67
  mercados que se movem juntos, com a **dependência entre observações simultâneas não estimada** (a
  decisão conjunta pede reamostragem em blocos de tempo, que não foi feita e não faria sentido com
  um único dia). A diferença v1 × v2 também não é diferença de estratégia: mesmo módulo,
  `default_parameters` idênticos, mesmo `params_hash`, e a v2 rodou 2 minutos.
- **Next Action:** deixar rodar e acrescentar uma avaliação por plantão, com este mesmo SQL. Nenhuma
  ativação, desativação ou mudança de parâmetro decorre destes números. A próxima avaliação deve
  destacar a linha de **horizonte maturado** — é ela que diz quando as métricas passam a descrever a
  população inteira. Pré-requisito operacional: o `market-worker` local voltar a `healthy`
  ([[Open Bugs]]) e o Lab da VPS acumular dias distintos (`.claude/state/vps-lab-proof.md`).
- **Segunda opinião (Astra) — `.claude/state/astra-review-S4-obsidian.md`:** cinco must-fix, **todos
  aceitos e corrigidos nesta avaliação antes de publicá-la**. (1) PF com `COALESCE` no numerador —
  soma de conjunto vazio é **0**, não desconhecido, e chamar de "nulo" um resultado inteiramente
  perdedor esconderia o pior caso; a regra de nulo vale quando faltam **perdas** ou população. (2)
  Coorte e propósito impostos no SQL, não só declarados: o mesmo SQL será reusado quando existir
  `replay:<run_id>`, e aí misturaria as duas populações. (3) População de horizonte maturado
  acrescentada — foi ela que revelou os **0 de 57**. (4) Motivos exatos em vez de `LIKE 'late%'`.
  (5) Snapshot transacional único e a não-reprodutibilidade dita de forma dura. Divergência
  registrada: ela sugeriu publicar a versão original e acrescentar uma errata datada; como nada
  disto tinha sido commitado ainda, corrigi **antes** de publicar — a regra de "nunca reescrever"
  protege avaliação já publicada, e uma errata sobre um texto que ninguém leu seria encenação.
### Avaliação de 2026-09-06 (turno da tarde) — **coorte da VPS** — `as_of = 2026-09-06T13:00:00Z`, `read_at = 2026-09-06T13:26:35.681334Z`

**Esta avaliação não continua a série anterior — é outra coorte, em outro banco.** A avaliação de
`as_of = 02:55Z` mediu o banco local desta máquina, com duas versões (`v1` deprecated e `v2` active).
A VPS tem **uma só** versão de momentum, ativada lá pelo script auditado às **2026-09-06
03:36:36.988581+00**, com `code_ref =
hunter_core.strategies.momentum_v1@sha256:6ccbe8b6c8ac18f32e93a6d44e71e0045155646479907b2b1944f39c3cdf4c95`
— digest **diferente** do da `v2` local, pelo motivo já registrado em [[Open Bugs]] (CRLF na árvore
do Windows contra LF na VPS). Somar, comparar ou continuar a série local com estes números seria
misturar populações. `status` da linha na VPS: `active`, sem `deprecated_at`.

**Semântica do corte.** População congelada por `supporting_features->>'decision_at' <= as_of` e
`cohort = 'prospective'` — exatamente o recorte que o `/lab` usa
(`apps/api/hunter_api/repositories/lab_summary.py`), para que estes números sejam conferíveis contra
a tela. `purpose = research_only` em 100% da população (consulta 0 abaixo). Estados lidos num único
snapshot `REPEATABLE READ READ ONLY` em `read_at`. **A leitura não é reconstruível**:
`signal_outcomes` avança no lugar e não há histórico de estados; reexecutar amanhã devolve a mesma
população com estados diferentes.

**Gate de avaliável — idêntico ao `is_evaluable()` da S3a**
(`apps/api/hunter_api/services/lab_summary_metrics.py:66`): `tracking_state = terminal` **e**
`exit_ts <= as_of` **e** `meta.entry_plan.entry_bar_open + meta.horizon_s <= as_of`. Não é
"encerrado": é encerrado **com o horizonte de 4 h inteiro disponível** dentro da janela.

**SQL usado** (`ssh hunter-vps 'docker exec -i hunter-postgres-1 psql -U hunter -d hunter -f -'`):

```sql
\set as_of '2026-09-06T13:00:00Z'
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT now() AS read_at;

-- (0) propósito e coorte: prova de que o filtro do /lab (só cohort) não mistura populações
SELECT st.key, s.supporting_features->>'purpose' AS purpose,
       s.supporting_features->>'cohort' AS cohort, count(*)
FROM agent_signals s
JOIN strategy_versions v ON v.id = s.strategy_version_id
JOIN strategies st ON st.id = v.strategy_id
WHERE (s.supporting_features->>'decision_at')::timestamptz <= :'as_of'::timestamptz
GROUP BY 1,2,3 ORDER BY 1,2,3;

-- (1) cobertura por coorte de versão
WITH pop AS (
  SELECT st.key, v.version, v.status, s.id, s.market_id,
         (s.supporting_features->>'decision_at')::timestamptz AS decision_at,
         o.tracking_state, o.result, o.r_multiple, o.entry_ts, o.exit_ts,
         o.no_entry_reason, o.censored_reason,
         (o.meta->'funding'->>'reason') AS funding_reason
  FROM agent_signals s
  JOIN strategy_versions v ON v.id = s.strategy_version_id
  JOIN strategies st ON st.id = v.strategy_id
  LEFT JOIN signal_outcomes o ON o.signal_id = s.id
  WHERE s.supporting_features->>'cohort' = 'prospective'
    AND (s.supporting_features->>'decision_at')::timestamptz <= :'as_of'::timestamptz
)
SELECT key, version, status,
  count(*) AS emitidos,
  count(*) FILTER (WHERE tracking_state='pending_entry') AS pendentes,
  count(*) FILTER (WHERE entry_ts IS NOT NULL)           AS entradas,
  count(*) FILTER (WHERE no_entry_reason='late:delay')   AS ne_late_delay,
  count(*) FILTER (WHERE no_entry_reason='geometry')     AS ne_geometry,
  count(*) FILTER (WHERE tracking_state='no_entry'
                    AND no_entry_reason NOT IN ('late:delay','geometry')) AS ne_outros,
  count(*) FILTER (WHERE tracking_state='active')        AS ativos,
  count(*) FILTER (WHERE result='target')                AS target,
  count(*) FILTER (WHERE result='stop')                  AS stop,
  count(*) FILTER (WHERE result='expired')               AS expired,
  count(*) FILTER (WHERE result='invalidated')           AS invalidated,
  count(*) FILTER (WHERE tracking_state='censored')      AS censurados,
  count(*) FILTER (WHERE funding_reason IS NOT NULL)     AS funding_indisp,
  count(DISTINCT market_id)                              AS mercados,
  count(DISTINCT (decision_at AT TIME ZONE 'UTC')::date) AS dias_decisao
FROM pop GROUP BY 1,2,3 ORDER BY 1,2;

-- (2) métricas sobre a população AVALIÁVEL (gate de maturação = is_evaluable da S3a)
WITH pop AS (
  SELECT st.key, v.version, o.tracking_state, o.result, o.r_multiple, o.exit_ts,
         (o.meta->'entry_plan'->>'entry_bar_open')::timestamptz AS entry_bar_open,
         (o.meta->>'horizon_s')::int AS horizon_s
  FROM agent_signals s
  JOIN strategy_versions v ON v.id = s.strategy_version_id
  JOIN strategies st ON st.id = v.strategy_id
  JOIN signal_outcomes o ON o.signal_id = s.id
  WHERE s.supporting_features->>'cohort' = 'prospective'
    AND (s.supporting_features->>'decision_at')::timestamptz <= :'as_of'::timestamptz
), aval AS (
  SELECT * FROM pop
  WHERE tracking_state='terminal'
    AND exit_ts IS NOT NULL AND exit_ts <= :'as_of'::timestamptz
    AND entry_bar_open IS NOT NULL AND horizon_s IS NOT NULL
    AND entry_bar_open + (horizon_s || ' seconds')::interval <= :'as_of'::timestamptz
)
SELECT a.key, a.version,
  count(*)                                                                  AS avaliaveis,
  count(*) FILTER (WHERE a.r_multiple IS NULL)                              AS funding_nao_liquidavel,
  count(*) FILTER (WHERE a.result='target')                                 AS aval_target,
  count(*) FILTER (WHERE a.result='stop')                                   AS aval_stop,
  count(*) FILTER (WHERE a.result='invalidated')                            AS aval_invalidated,
  count(*) FILTER (WHERE a.result='expired')                                AS aval_expired,
  round(count(*) FILTER (WHERE a.result='target')::numeric
      / NULLIF(count(*) FILTER (WHERE a.result IN ('target','stop')),0), 4) AS target_rate_among_resolved_touches,
  round(count(*) FILTER (WHERE a.r_multiple>0)::numeric
      / NULLIF(count(*) FILTER (WHERE a.r_multiple IS NOT NULL),0), 4)      AS net_profit_rate,
  round(avg(a.r_multiple), 4)                                               AS hypothetical_net_expectancy_r,
  round(sum(a.r_multiple), 4)                                               AS sum_of_hypothetical_r,
  round(coalesce(sum(a.r_multiple) FILTER (WHERE a.r_multiple>0),0), 4)     AS soma_r_pos,
  round(coalesce(-sum(a.r_multiple) FILTER (WHERE a.r_multiple<0),0), 4)    AS soma_r_neg_abs,
  round(coalesce(sum(a.r_multiple) FILTER (WHERE a.r_multiple>0),0)
      / NULLIF(-sum(a.r_multiple) FILTER (WHERE a.r_multiple<0), 0), 4)     AS profit_factor,
  count(*) FILTER (WHERE a.r_multiple IS NOT NULL)                          AS maturity_evaluable_outcomes,
  count(DISTINCT (a.exit_ts AT TIME ZONE 'UTC')::date)
    FILTER (WHERE a.r_multiple IS NOT NULL)                                 AS maturity_distinct_days
FROM aval a GROUP BY 1,2 ORDER BY 1,2;

-- (3) motivos exatos de no_entry e censura; (4) excursões — texto integral em
--     .claude/state (mesma forma da avaliação de 02:55Z, com o recorte por decision_at)
COMMIT;
```

**Saída real (colada):**

```
            read_at
-------------------------------
 2026-09-06 13:26:35.681334+00
(1 row)

      key       |    purpose    |   cohort    | count
----------------+---------------+-------------+-------
 momentum       | research_only | prospective |   208
 volume_anomaly | research_only | prospective |   459
(2 rows)

      key       | version | status | emitidos | pendentes | entradas | ne_late_delay | ne_geometry | ne_outros | ativos | target | stop | expired | invalidated | censurados | funding_indisp | mercados | dias_decisao
----------------+---------+--------+----------+-----------+----------+---------------+-------------+-----------+--------+--------+------+---------+-------------+------------+----------------+----------+--------------
 momentum       | v1      | active |      208 |         0 |      208 |             0 |           0 |         0 |      6 |     82 |   49 |       0 |          71 |          0 |             29 |      134 |            1
 volume_anomaly | v1      | active |      459 |         0 |      443 |             0 |          16 |         0 |      3 |    133 |  141 |      10 |         156 |          0 |             46 |      134 |            1
(2 rows)

      key       | version | avaliaveis | funding_nao_liquidavel | aval_target | aval_stop | aval_invalidated | aval_expired | target_rate_among_resolved_touches | net_profit_rate | hypothetical_net_expectancy_r | sum_of_hypothetical_r | soma_r_pos | soma_r_neg_abs | profit_factor | maturity_evaluable_outcomes | maturity_distinct_days
----------------+---------+------------+------------------------+-------------+-----------+------------------+--------------+------------------------------------+-----------------+-------------------------------+-----------------------+------------+----------------+---------------+-----------------------------+------------------------
 momentum       | v1      |        105 |                     14 |          40 |        35 |               30 |            0 |                             0.5333 |          0.3956 |                       -0.2102 |              -19.1315 |    29.7283 |        48.8597 |        0.6084 |                          91 |                      1
 volume_anomaly | v1      |        352 |                     36 |         109 |       109 |              124 |           10 |                             0.5000 |          0.3165 |                       -0.2304 |              -72.8206 |   137.6122 |       210.4328 |        0.6539 |                         316 |                      1
(2 rows)

      key       | version | tracking_state |  motivo  | count
----------------+---------+----------------+----------+-------
 volume_anomaly | v1      | no_entry       | geometry |    16
(1 row)

      key       | version | outcomes | mfe_nulo | mae_nulo | ambiguos
----------------+---------+----------+----------+----------+----------
 momentum       | v1      |      208 |       88 |       55 |      136
 volume_anomaly | v1      |      459 |      170 |      145 |      253
(2 rows)

      key       | version |       primeiro_emitido        |        ultimo_emitido         | dias_decisao
----------------+---------+-------------------------------+-------------------------------+--------------
 momentum       | v1      | 2026-09-06 03:45:01.540802+00 | 2026-09-06 12:45:26.879351+00 |            1
 volume_anomaly | v1      | 2026-09-06 03:40:04.45381+00  | 2026-09-06 12:55:07.873883+00 |            1
(2 rows)
```

**Cobertura (`momentum v1`, VPS):**

| Emitidos | Pendentes | Entradas | `late:delay` | `geometry` | Outros | Ativos | Target | Stop | Expired | Invalidated | Censurados | Funding indisp. | Mercados | Dias |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 208 | 0 | 208 | 0 | 0 | 0 | 6 | 82 | 49 | 0 | 71 | 0 | 29 | 134 | 1 |

As contagens fecham: 6 ativos + 82 + 49 + 71 = **208**. Nenhuma recusa de entrada e nenhuma censura
nesta coorte — do lado da VPS o `market-worker` não teve o buraco de ingestão que censurou dois
acompanhamentos aqui em casa (`ingestion_gaps`: 1590 `recovered`, 2 `open`, 2 `failed`; última vela
de 1 min às 13:27Z). Janela de emissões: 03:45:01 a 12:45:26 UTC.

**Métricas (com denominador explícito, nomes da S3a):**

| Métrica | Valor | Denominador |
|---|---|---|
| `target_rate_among_resolved_touches` | **0,5333** | 40 target + 35 stop = 75 avaliáveis com toque resolvido |
| `net_profit_rate` | **0,3956** | 91 avaliáveis com `R_net` (36 com `R_net > 0`) |
| `hypothetical_net_expectancy_r` | **−0,2102** | mesmos 91 |
| `profit_factor` | **0,6084** | 29,7283 / 48,8597 — as duas somas existem, então não é nulo |
| `sum_of_hypothetical_r` | **−19,1315** | 91; soma escalar, **não é equity** |
| MFE/MAE | `mfe` nulo em 88 de 208, `mae` nulo em 55, 136 ambíguos | toda a coorte |
| **PnL de carteira** / **Max Drawdown de carteira** | **não aplicável** | não há carteira no Shadow Lab |

**Contribuição de R por resultado, dentro dos 91 avaliáveis com `R_net`:**

| Resultado | n | Média R | Soma R | Mín | Máx |
|---|---|---|---|---|---|
| `target` | 36 | +0,8258 | +29,7283 | +0,1606 | +2,8851 |
| `stop` | 31 | −1,1296 | −35,0167 | −1,2280 | −1,0258 |
| `invalidated` | 24 | −0,5768 | −13,8430 | −0,9472 | −0,2060 |

- **Maturação:** 105 avaliáveis, dos quais 14 sem `R_net` (funding) → **91** entram nas métricas de
  R. Ao contrário da leitura das 02:55Z (0 de 57 com horizonte maturado), aqui o gate de 4 h está
  cumprido para toda a população medida — a coorte da VPS tem 9 h de emissões atrás de si.
- **Dias distintos com outcome avaliável:** **1** (2026-09-06).
- **Result:** **inconclusivo.** O limiar é 100 outcomes avaliáveis **E** 30 dias distintos; há 91 em
  1 dia. Falham os dois lados.
- **Conclusion:** com o horizonte maturado, a leitura muda de sinal em relação à da madrugada
  (+0,3053 R lá, −0,2102 R aqui) — o que confirma exatamente o que aquela avaliação alertava: os
  números de então descreviam "os que resolveram cedo", não a estratégia. Isso **não** significa que
  agora descrevam a estratégia: 1 dia, 134 mercados que se movem juntos, e a dependência entre
  observações simultâneas não estimada. A única afirmação sustentada é sobre o instrumento: alvo,
  stop e invalidação apareceram sobre dado real, as contagens fecham, e o gate de maturação separa
  as populações como foi projetado.
- **Next Action:** deixar rodar; uma avaliação por plantão. Nenhuma ativação, desativação ou mudança
  de parâmetro decorre destes números. Pesquisa aberta abaixo, em "Hipóteses de falha".
- **Segunda opinião (Astra) — [[S4-hipoteses]]:** cinco must-fix, **todos aceitos e aplicados antes
  de publicar**; estão descritos na seção "Hipóteses de falha".

## Hipóteses de falha (pesquisa — não muda o protocolo, não ativa nada)

> Seção **de pesquisa**, aberta em 2026-09-06 a pedido do Everton. Cada rodada é datada e
> acrescentada; nada aqui altera Hipótese, Protocolo ou parâmetros. Uma hipótese que exija conteúdo
> diferente vira um `EXP-NNNN` novo, linkado — nunca uma edição.

### Rodada de 2026-09-06 — sobre a coorte da VPS de `as_of = 13:00Z`

#### H1 — A invalidação está matando operações que teriam batido o alvo?

**A regra, exatamente.** Em `momentum v1` a invalidação é
`Invalidation(kind="close_below", level=prior_max, timeframe="15m")`
(`packages/core/hunter_core/strategies/momentum_v1.py:282`): fechamento de **15 min** abaixo da
máxima dos 20 fechamentos anteriores — o próprio nível rompido. **Atenção:** a regra do
[[EXP-0002-volume-anomaly-v1]] é **outra** (fechamento de **5 min** abaixo do **meio da barra do
sinal**, `volume_anomaly_v1.py:241`). Os dois experimentos **não** testam a mesma regra de
invalidação, e atribuir a diferença de resultado "à invalidação" seria erro de leitura.

**O peso do fenômeno.** 71 de 202 acompanhamentos resolvidos (35%) terminam por invalidação. Dentro
dos 91 avaliáveis com `R_net`, são 24, somando **−13,8430 R** de um total de **−19,1315 R**.

**Até onde eles chegaram.** MFE aqui é excursão em **preço** desde a entrada
(`services/strategy-worker/hunter_strategy_worker/excursions.py`), e `R_preço = virtual_entry −
virtual_stop`:

| | `momentum v1` |
|---|---|
| Invalidados (coorte inteira) | 71 |
| Com MFE **determinado** | 71 (0 ambíguos) |
| MFE ≥ 1 R | **3** |
| MFE ≥ 0,5 R | 14 |
| MFE médio | **0,2817 R** |
| MFE máximo | 1,1059 R |
| Expectancy dos invalidados | −0,5732 R |
| Invalidados com lucro | **0** |
| Duração média | 1803,4 s, contra `horizon_s` = 14400 s |

Comparação por resultado, só onde o MFE é determinado: `target` 82 outcomes com MFE determinado em
**zero** deles; `stop` 49 de 49, MFE médio 0,2336 R; `invalidated` 71 de 71, MFE médio 0,2817 R.

**Viés de instrumento, nomeado.** Nesta coorte o MFE é indeterminado em 100% dos alvos, porque tocar
o alvo torna a excursão ambígua. Não é uma lei — uma saída na abertura pode ter extremo determinado
(`excursions.py:119`) —, mas nesta coorte a comparação de MFE **existe apenas entre perdedores**.
Qualquer conclusão tirada dela seleciona os outcomes pelo modo de saída.

**O que o dado NÃO responde.** O acompanhamento **para** na invalidação
(`services/strategy-worker/hunter_strategy_worker/walker.py:173`), então o MFE só cobre até a saída:
o que teria acontecido nas horas restantes não está no outcome. Corrigindo o que eu tinha escrito
primeiro (must-fix 2 da Astra): dizer que "não está gravado em lugar nenhum" é forte demais — as
velas de 1 min estão persistidas e um replay é possível **em princípio**; o que falta é verificar
que a cobertura é contínua até o horizonte de cada entrada. Essa verificação é pré-requisito, não
resultado.

**O que dá para afirmar: sensibilidade, não limites.** Mantendo os outros outcomes e o denominador
fixos e substituindo os 24 invalidados avaliáveis:

| Hipótese de substituição | Expectancy resultante (91 avaliáveis) |
|---|---|
| Todos na média dos `target` (+0,8258 R) | **+0,1597 R** |
| Todos na média dos `stop` (−1,1296 R) | **−0,3560 R** |

**Estes dois números não são um intervalo, nem limites, nem intervalo de confiança** (must-fix 1 da
Astra, aceito). Transportar a média de outro grupo para os invalidados é uma imputação não
justificada: eles podem ter outra geometria entrada–stop–alvo, outro tempo restante e outra
exposição a funding; e o modelo admite stop na abertura abaixo do nível (`walker.py:71`), então a
média observada dos stops nem sequer é um piso financeiro. Bootstrap sobre as distribuições de
`target`/`stop` **não** resolveria isso — acrescentaria incerteza amostral a uma imputação que
continua sem identificação.

**O enunciado honesto é o ponto de equilíbrio.** Para a soma desta coorte zerar, os 24 invalidados
precisariam ter rendido, em média, **+0,22035 R**. Eles renderam **−0,5768 R**. A distância é de
0,80 R por operação. Isso responde uma pergunta concreta ("quanto precisariam render sob outra
saída para zerar a coorte") sem estimar a probabilidade de isso acontecer.

**Correção sobre "1 R".** `stop_atr` e `target_atr` valem ambos 1,5, mas medidos a partir da
**referência**, não da entrada — e a entrada é o open da barra seguinte, já com os custos sintéticos
(`momentum_v1.py:217`, `services/strategy-worker/hunter_strategy_worker/pricing.py:47`). Logo
`MFE ≥ 1 R` **não** equivale a ter alcançado o alvo, e os 3 casos ≥ 1 R não são "alvos perdidos".

**Resposta provisória à pergunta.** Não há evidência de que a invalidação esteja matando vencedores:
71 de 71 invalidados terminaram no vermelho, 3 chegaram a 1 R de excursão bruta e nenhum foi
lucrativo. Também **não** há evidência de que ela proteja a estratégia: retirar a invalidação move a
expectancy para qualquer lugar entre −0,36 e +0,16 R conforme a hipótese que se adote, e o dado não
escolhe entre elas. **As duas afirmações fortes estão proibidas por falta de identificação**, e é
isso que fica registrado.

**O que uma v2 precisaria mudar (novo `EXP`, nunca uma edição desta página).** Comparação **pareada
de regras de saída**: congelar as mesmas entradas e acompanhar dois braços — regra atual contra
regra sem invalidação — mantendo stop, alvo, horizonte e custos idênticos, e registrar por entrada a
diferença de `R_net` (perdas evitadas, recuperações até o alvo, expirações, funding, censuras).
Requisitos para valer:

1. Verificar antes a **continuidade das velas** até o horizonte de cada entrada; sem isso o braço
   contrafactual mede cobertura, não estratégia.
2. Checar se o **stop teria ocorrido antes** — ver o preço alcançar o alvo depois não basta.
3. O replay desta coorte é **exploratório**; a confirmação exige um período posterior com protocolo
   congelado.
4. Separar dois objetivos que não são o mesmo: efeito da saída **sobre entradas fixas** (comparação
   pareada) e efeito **sobre a estratégia inteira** — este último muda as entradas seguintes, porque
   o término libera a barreira de reentrada
   (`services/strategy-worker/hunter_strategy_worker/outcomes.py:102`).
5. Um monitor apenas **adicional** (registrar a invalidação como marcador e seguir acompanhando)
   melhora o instrumento; **mudar a saída testada** é hipótese operacional nova e pede outro `EXP`.

#### H2 — Os outcomes com funding não apurável são ausência de dado ou falha de identificação temporal?

**Censo completo** dos 73 outcomes com `meta.funding.reason LIKE 'funding_missing:%'` na coorte
(27 momentum + 46 volume), com evidência graduada (must-fix 3 da Astra, aceito):

| Casos | O que se pode afirmar |
|---|---|
| **69** | Há linha em `funding_rates` do **mesmo mercado** a menos de 2 s do instante pedido, mas não no instante exato — compatível com falha de identidade/grade temporal |
| **3** | Há casamento **exato** na leitura de hoje; a causa histórica permanece por demonstrar |
| **1** | Nada em ±60 s (o vizinho mais próximo está a 2 h) — verificar também se a liquidação prevista era devida |

Deltas exatos entre o instante pedido e a linha mais próxima do mesmo mercado:

```
           pedido           | outcomes | delta_min_ms | delta_max_ms
----------------------------+----------+--------------+--------------
 2026-09-06 04:00:00+00     |       22 |            5 |            5
 2026-09-06 07:59:59.005+00 |        1 |          995 |          995
 2026-09-06 08:00:00+00     |        3 |            0 |            0
 2026-09-06 08:00:00.005+00 |       18 |           -5 |           -5
 2026-09-06 10:00:00+00     |        1 |     -7200000 |     -7200000
 2026-09-06 11:59:59+00     |        3 |         1001 |         1001
 2026-09-06 12:00:00+00     |       25 |            1 |            1
(7 rows)
```

`funding_rates` tem 1883 linhas em 221 mercados, e **851 delas têm parte de segundos diferente de
zero** — a grade real da corretora não é redonda, e o casamento é por igualdade exata de timestamp.
Contando por liquidação em vez de por outcome (nice-to-have da Astra): são **66 liquidações
distintas, em 57 mercados, em apenas 7 instantes** — não 73 falhas independentes.

**O tamanho do efeito, medido.** Entre os outcomes que **têm** `R_net` e `r_ex_funding`:

```
      key       |  n  | com_liquidacao | efeito_medio_do_funding_em_r | efeito_min | efeito_max
----------------+-----+----------------+------------------------------+------------+------------
 momentum       | 173 |              0 |                     0.000000 |   0.000000 |   0.000000
 volume_anomaly | 394 |              9 |                    -0.000195 |  -0.027742 |   0.000036
(2 rows)
```

**Nenhum acompanhamento de momentum atravessou uma liquidação**, e no volume só 9 atravessaram, com
efeito máximo de 0,028 R. Ou seja: o funding é um problema de **correção do instrumento**, não a
causa de uma expectancy de −0,21 R. Quem quiser explicar o vermelho com funding está olhando para o
lugar errado por duas ordens de grandeza.

**Direção do viés da exclusão, medida com o proxy observável** (`r_ex_funding`, a mesma métrica sem
o funding):

| Estratégia | Avaliáveis **com** `R_net` | Média `r_ex_funding` | Excluídos (sem `R_net`) | Média `r_ex_funding` | Expectancy se incluídos pelo proxy | Reportada |
|---|---|---|---|---|---|---|
| momentum | 91 | −0,2102 | 14 | **−0,3526** | −0,2292 | −0,2102 |
| volume | 316 | −0,2302 | 36 | **+0,0225** | −0,2043 | −0,2304 |

As direções são **opostas** entre as duas estratégias e as duas magnitudes ficam abaixo de 0,03 R.
Isto mede **diferença observável de composição**, não o valor verdadeiro: assume que o funding
faltante é ≈ 0, o que a medição acima torna plausível mas não prova para esses outcomes
específicos. Não afirmo que a exclusão enviesou as métricas para cima ou para baixo além disso.

**Ponto de equilíbrio.** Para a soma da população avaliável inteira zerar, os 14 excluídos do
momentum precisariam render **+1,36654 R** cada, e os 36 do volume **+2,02279 R** cada. Nenhum dos
dois é plausível: o funding não resgata a coorte.

**O que NÃO se deve fazer — e este é o must-fix 5 da Astra, aceito.** Corrigir com "casar com a
linha mais próxima dentro de ±2 s" cria dois defeitos novos:

1. **Cobrança dupla.** A grade calculada contém `08:00:00` e o observado contém `08:00:00.005`; a
   função hoje faz a **união** dos dois conjuntos, então dar tolerância só ao `known.get()` permite
   cobrar a mesma liquidação duas vezes
   (`services/strategy-worker/hunter_strategy_worker/funding.py:126`).
2. **Funding depois da saída.** Saída às `08:00:00` e liquidação às `08:00:00.005`: uma janela larga
   passa a cobrar algo posterior ao fim do acompanhamento, enquanto o recorte atual termina em
   `exit_ts` e trata a saída intrabar ambígua à parte (`settle.py:60`).

±2 s é uma **janela diagnóstica** que cobre os desvios observados, não uma tolerância demonstrada. A
documentação da Binance publica `fundingTime` sem garantir jitter. Um protocolo de associação
correto precisa: identificar o evento do mesmo mercado e validar a cadência vigente; exigir
associação **única**, sem reutilizar uma liquidação; preservar o timestamp original, separando
identidade do evento de incidência financeira; recusar ambiguidades nas fronteiras de entrada e
saída; e usar tolerância muito menor que metade do espaçamento mínimo validado entre eventos, com a
magnitude justificada. Registrado em [[Open Bugs]].

**O que NÃO afirmo, com estes dados:** que o contrafactual da H1 está dentro daqueles dois cenários;
que a invalidação destrói vencedores ou que protege a estratégia; que todo `target` tenha
necessariamente MFE indeterminado; que 72 liquidações estão recuperáveis (são outcomes com
**candidatos** — identidade, incidência, preço e eventos adicionais ainda precisam de validação);
que os três deltas de 0 ms provam corrida de leitura; que a exclusão por funding enviesou as
métricas além do proxy medido; e que 134 mercados e centenas de outcomes num único dia equivalem a
centenas de observações independentes.

## Variantes tentadas

| Variante | Quando | Por quê | Onde ficou registrada |
|---|---|---|---|
| `momentum v2` | 2026-09-06 02:08:13 UTC | **Não é variante de pesquisa.** Sucessão obrigatória por correção do `code_ref`: o digest da árvore inteira invalidava toda versão congelada a cada módulo novo (MUST-FIX 1 do `risk-engine-guardian`). Campo congelado não se corrige no lugar (`docs/DATABASE.md` §16.1), então a correção obrigou uma versão nova. | `changelog` das duas linhas em `strategy_versions`; `.claude/state/notes-S2.md` §15 |

## Relacionadas

[[Experiments Index]] · [[EXP-0002-volume-anomaly-v1]] · [[Momentum Agent]] · [[Strategies]] · [[Strategy Performance]] · [[Dialogos/SHADOW]] · [[Workers]] · [[Open Bugs]] · [[Data Flow]]

## Fontes

`docs/plans/SHADOW-LAB.md` (itens 1–11 da decisão conjunta) · `.claude/state/s2-proof.md` ·
`.claude/state/notes-S2.md` §14–19 · `infra/migrations/versions/0002_shadow_lab*.py` ·
`packages/core/hunter_core/strategies/momentum_v1.py` ·
`services/strategy-worker/hunter_strategy_worker/**` · as consultas coladas acima.
