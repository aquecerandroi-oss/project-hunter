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
