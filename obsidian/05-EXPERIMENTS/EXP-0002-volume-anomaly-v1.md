---
tags: [experimento, volume, shadow-lab]
updated: 2026-09-06
status: em-andamento
---

# EXP-0002 — volume_anomaly em modo sombra (perfil "por barras" v0)

> Experimento aberto em **2026-09-06** com a primeira ativação auditada de `volume_anomaly v1`
> (2026-09-05 23:20:09 UTC). A seção "Protocolo" é escrita uma vez e **nunca** muda; as avaliações
> são **acrescentadas** abaixo, datadas. Ver [[Experiments Index]], [[Volume Agent]] e
> [[Dialogos/SHADOW]].

## Hipótese (congelada)

Um pico de volume de 5 minutos (≥ 4× a mediana das 288 barras anteriores) que fecha na metade
superior da barra, sem que o retorno da própria barra já tenha consumido o movimento, é seguido
por continuação suficiente para alcançar um alvo a 1,5 ATR antes de perder a mínima da barra do
sinal, líquido dos custos assumidos.

## Protocolo (congelado na primeira ativação — nunca editar)

- **Strategy:** `strategies.key = volume_anomaly`; coortes de versão `v1` (ativada 2026-09-05
  23:20:09.899561+00, `deprecated` em 2026-09-06 02:08:19.424473+00) e `v2` (ativada 2026-09-06
  02:08:19.424473+00, `active`).
- **code_ref:**
  - `v1` — `hunter_core.strategies@sha256:13dfa32298cbc2dbbe54aac4cd785be4a85246cdf5daaa9564a4cf29301ea0b5` (digest da árvore inteira)
  - `v2` — `hunter_core.strategies.volume_anomaly_v1@sha256:d8275427c958743bc23dc190b2a8744d3fbf65ea81acf091e043f5ae65410ef2` (digest do módulo + fecho transitivo dos imports)
- **params_hash / params_format:** `fa5dce78173b2b9688578f7c96a5f37544eb504aa7b2227262ad296c32f63bb9` / `1` — **idêntico nas duas versões** (`default_parameters` e `parameters_schema` bit a bit iguais); o que separa v1 de v2 é **só** o `code_ref`, e as populações são separadas pelo `strategy_version_id` dentro do `uuid5` de cada sinal.
- **Parameters (`default_parameters` congelados, nada implícito):**

```json
{
  "assumed_spread_bps": "2", "atr_bars": "97", "atr_period": "14", "atr_timeframe": "15m",
  "base_confidence": "0.5", "fee_bps": "4", "horizon_s": "7200", "max_entry_delay_s": "120",
  "return_max_atr": "2", "return_min": "0", "slippage_bps": "5", "target_atr": "1.5",
  "volume_mult": "4", "volume_window": "288"
}
```

- **Timeframe de decisão / de outcome:** **5 min** (fechamentos distintos, UTC) / 1 min.
- **Agregação e ATR:** 1 m → 5 m só com barras UTC contíguas e finais até `source_bar_close`; ATR =
  **Wilder(14) sobre 15 min** — o timeframe de decisão de 5 min **não** muda implicitamente o
  timeframe do ATR. A janela do volume exige 288 barras de 5 min contíguas (1445 minutos), então um
  único minuto ausente torna a avaliação `unavailable: gap` por até ~24 h naquele mercado.
- **Entrada:** open da primeira barra de 1 min estritamente posterior a `decision_at`, com
  `entry_bar_open − source_bar_close ≤ 120 s`, decisão persistida **antes** daquela abertura; senão
  `no_entry: late:*`. Geometria revalidada com `P_entry` (`stop < P_entry < target1`), senão
  `no_entry: geometry` — aqui esse caminho é mais frequente que no [[EXP-0001-momentum-v1]] porque
  o stop é a **mínima da barra do sinal**, e uma barra de pico com corpo grande deixa o `P_entry`
  perto do alvo.
- **Saída:** gap na abertura primeiro, depois toques intrabar; stop e alvo na mesma barra →
  **stop**; prioridade na mesma abertura `stop > target > expired > invalidated`; horizonte **2 h**
  contado da entrada.
- **Custos assumidos (hipóteses declaradas, não tarifas verificadas):** spread total 2 bps,
  slippage 5 bps por lado, taxa 4 bps por lado, funding assinado; `R_net = null` com motivo quando
  o funding aplicável não é apurável, preservando `meta.r_ex_funding`.
- **Política de reentrada:** um acompanhamento `pending_entry|active` por
  `(strategy_version_id, market_id, cohort)`; rearme só após barra elegível com a condição falsa
  **depois** do término anterior (barreira em `shadow_episodes.last_bar_close`).
- **Cohort:** `prospective` (nenhum replay foi rodado).
- **Universo elegível:** top 50 por volume 24 h do `market-worker` (override do T1.6b), com a
  composição do instante gravada no envelope imutável de cada sinal; `tracking_hold` mantém a
  coleta de um mercado excluído enquanto houver acompanhamento aberto.
- **Markets:** Binance USDS-M, perpétuos USDT, **LONG apenas**.
- **Data de início da coleta:** 2026-09-06 (primeiro sinal `v1` às 00:25:01 UTC; primeiro `v2` às 02:10:28 UTC).
- **Isolamento:** `purpose = research_only` no envelope e no evento; stream próprio
  `shadow.signals.emitted`. Nada aqui pode ordenar coisa alguma.

## Avaliações (acrescentadas, nunca reescritas)

### Avaliação de 2026-09-06 — `as_of = 2026-09-06T02:55:00Z`, `read_at = 2026-09-06T03:13:08.091635Z`

**Semântica do corte, sem eufemismo.** População congelada por `emitted_at <= as_of`; estados lidos
num **único snapshot** (`BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY`), para que as
três consultas descrevam o mesmo mundo. **Esta leitura não é reconstruível:** `signal_outcomes`
avança no lugar e não há histórico de estados preservado — reexecutar o SQL amanhã devolve a mesma
população com estados diferentes, e nenhuma consulta recompõe os de hoje. É por isso que a avaliação
é acrescentada e datada, nunca recalculada.

**SQL usado** — exatamente o de [[EXP-0001-momentum-v1]] (as três consultas coladas lá na íntegra,
com coorte `prospective`, `purpose = research_only`, motivos exatos, maturação do horizonte e PF com
`COALESCE` no numerador), trocando apenas:

```sql
\set as_of '2026-09-06T02:55:00Z'
\set skey 'volume_anomaly'
```

**Saída real (colada):**

```
            read_at
-------------------------------
 2026-09-06 03:13:08.091635+00
(1 row)

 version |   status   | emitidos | pendentes | entradas | ne_late_delay | ne_geometry | ne_outros | ativos | target | stop | expired | invalidated | censurados | r_nulo | funding_indisp | mercados
---------+------------+----------+-----------+----------+---------------+-------------+-----------+--------+--------+------+---------+-------------+------------+--------+----------------+----------
 v1      | deprecated |       92 |         0 |       80 |             9 |           3 |         0 |     13 |     31 |   18 |       0 |          17 |          1 |      0 |              0 |       62
 v2      | active     |       15 |         0 |       11 |             2 |           2 |         0 |      5 |      0 |    4 |       0 |           2 |          0 |      0 |              0 |       15
(2 rows)

 version | encerrados_avaliaveis | horizonte_maturado | encerrou_antes_do_horizonte | taxa_alvo_toques | taxa_lucro_liquido | expectancy_r |  soma_r   | soma_r_pos | soma_r_neg | profit_factor | dias_distintos
---------+-----------------------+--------------------+-----------------------------+------------------+--------------------+--------------+-----------+------------+------------+---------------+----------------
 v1      |                    66 |                 35 |                          31 |           0.6327 |             0.4848 |     0.077965 |  5.145670 |  42.774768 | -37.629098 |        1.1367 |              1
 v2      |                     6 |                  0 |                           6 |           0.0000 |             0.0000 |    -1.281367 | -7.688202 |   0.000000 |  -7.688202 |        0.0000 |              1
(2 rows)

 version | tracking_state |            motivo             | count
---------+----------------+-------------------------------+-------
 v1      | no_entry       | geometry                      |     3
 v1      | no_entry       | late:delay                    |     9
 v1      | censored       | gap:2026-09-06T00:54:00+00:00 |     1
 v2      | no_entry       | geometry                      |     2
 v2      | no_entry       | late:delay                    |     2
(5 rows)
```

Excursões (consulta auxiliar de [[EXP-0001-momentum-v1]], `read_at` próprio 2026-09-06T02:56:27Z):

```
      key       | version | mfe_nulo | mae_nulo | ambiguos
----------------+---------+----------+----------+----------
 volume_anomaly | v1      |       60 |       44 |       62
 volume_anomaly | v2      |       11 |       13 |        9
```

**Cobertura (contagens completas, motivos exatos, por coorte de versão):**

| Coorte | Emitidos | Pendentes | Entradas | `late:delay` | `geometry` | Outros motivos | Ativos | Target | Stop | Expired | Invalidated | Censurados | Funding indisp. | Mercados |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `v1` (deprecated) | 92 | 0 | 80 | 9 | 3 | 0 | 13 | 31 | 18 | 0 | 17 | 1 | 0 | 62 |
| `v2` (active) | 15 | 0 | 11 | 2 | 2 | 0 | 5 | 0 | 4 | 0 | 2 | 0 | 0 | 15 |

Censura da v1: `gap:2026-09-06T00:54:00+00:00` (1). Contagens fecham: v1 → 13 + 66 + 12 + 1 = 92;
v2 → 5 + 6 + 4 = 15. O censurado da v1 já tinha entrado, então está dentro dos 80.

**Métricas (distintas, com denominador explícito):**

| Métrica | `v1` | `v2` | Denominador | Observação |
|---|---|---|---|---|
| Taxa de alvo entre toques resolvidos | 0,6327 | 0,0000 | `target + stop` (v1: 49; v2: 4) | **não** é taxa de lucro |
| Taxa de lucro líquido | 0,4848 | 0,0000 | encerrados avaliáveis (v1: 66; v2: 6) | `R_net > 0` |
| Expectancy líquida hipotética em R por entrada encerrada avaliável | +0,077965 | −1,281367 | mesma população | média de `R_net` |
| Profit Factor | 1,1367 | **0,0000** | Σ R+ / \|Σ R−\| | v1: 42,774768 / 37,629098. **v2: 0 / 7,688202 = 0** — nenhum dos 6 encerrados teve `R_net > 0`, e soma de conjunto vazio é **zero**, não desconhecido. PF só é nulo com motivo quando faltam **perdas** (denominador vazio) ou quando não há população avaliável |
| MFE/MAE | `mfe` nulo em 60 de 92, `mae` nulo em 44, 62 ambíguos | `mfe` nulo em 11 de 15, `mae` nulo em 13, 9 ambíguos | todos os outcomes da coorte | nulo quando o OHLC não determina o extremo; limites em `meta.excursions.bounds` |
| Soma de R hipotéticos | +5,145670 | −7,688202 | encerrados avaliáveis | soma escalar; **não é equity** e não é trajetória |
| **PnL de carteira** | **não aplicável** | **não aplicável** | — | não há carteira no Shadow Lab |
| **Max Drawdown de carteira** | **não aplicável** | **não aplicável** | — | idem |

**Maturação do horizonte (2 h):**

| Coorte | Encerrados avaliáveis | Com horizonte **maturado** | Encerraram **antes** do horizonte |
|---|---|---|---|
| `v1` | 66 | **35** | 31 |
| `v2` | 6 | **0** | 6 |

Aqui o horizonte é de 2 h, então **35 dos 66** acompanhamentos da v1 já tiveram a janela inteira
disponível — é a única sub-população desta avaliação que não sofre o viés de "só os que resolveram
cedo". A v2, com 7 minutos de emissões, não tem nenhum. Comparar a v1 (metade maturada) com a v2
(nenhuma) agrava o erro de leitura que a seção "Variantes tentadas" já descarta por outro motivo.

- **Dias distintos com outcome avaliável:** **1** (2026-09-06) nas duas coortes.
- **Janela real de emissões:** v1 de 00:25:01 a 02:06:11 UTC; v2 de 02:10:28 a 02:17:38 UTC.
- **Versão da métrica / proveniência:** `shadow_metrics_v1`; `agent_signals` + `signal_outcomes` +
  `strategy_versions`; banco local `hunter`; coorte e propósito impostos na consulta.
- **Cobertura de funding:** 0 outcomes com funding indisponível (`funding_rates` com 1512 linhas em
  213 mercados; `meta.funding.settlements = 0` com horizonte de 2 h).
- **Avaliações recusadas:** o mesmo contador operacional descrito em [[EXP-0001-momentum-v1]] —
  `{"unavailable":400,"ineligible":1}` sobre 401 barras às 02:56:38 UTC, **acumulado desde a
  inicialização do worker e somando as duas estratégias**, sem quebra por estratégia nem por motivo.
  A causa foi medida à parte: o `market-worker` local fora do ar de 02:04 a ~02:47 UTC, com 773
  `ingestion_gaps` `open`. A janela de 288 barras desta estratégia é a mais sensível das duas — um
  minuto perdido custa até ~24 h de avaliações naquele mercado (`.claude/state/notes-S2.md` §14). A
  cobertura histórica por motivo não é persistida: [[Open Bugs]].
- **Result:** **inconclusivo** — limiar de 100 outcomes avaliáveis **E** 30 dias distintos; há 66
  (v1) e 6 (v2) em **1** dia.
- **Conclusion:** as três populações de exclusão que a decisão conjunta manda separar apareceram
  todas sobre dado real: `late:delay` (9 + 2), `geometry` (3 + 2) e `gap` (1). O `geometry` é
  informação de desenho, não ruído: com stop na mínima da barra do sinal, uma barra de pico com
  corpo grande coloca a entrada acima do alvo, e a versão recusa entrar em vez de inventar
  geometria. Sobre os números: **evidência insuficiente para concluir qualquer coisa** — 66
  acompanhamentos num único dia, PF 1,14, e a dependência entre mercados simultâneos não estimada.
  A v2, com 6 acompanhamentos, nenhum ganho e nenhum horizonte maturado, não sustenta afirmação
  alguma; e o código dela é o mesmo módulo da v1.
- **Next Action:** deixar rodar e acrescentar uma avaliação por plantão. Nenhuma mudança de
  parâmetro, ativação ou desativação decorre destes números. Quando a S3 entregar as contagens de
  cobertura, verificar se separa `late:delay`, `late:missed_open`, `late:unconfirmed`, `geometry`,
  `gap:*` e `blocked:*` como populações distintas (`.claude/state/notes-S2.md` §14) — e se mostra a
  maturação do horizonte, que foi o achado desta primeira leitura.
- **Segunda opinião (Astra) — `.claude/state/astra-review-S4-obsidian.md`:** os cinco must-fix foram
  aceitos e aplicados antes de publicar. O mais consequente aqui foi o **PF da v2**: a versão
  original dizia "nulo com motivo (Σ positivos vazio)", e ela mostrou que isso apresenta como
  desconhecido um resultado conhecido e ruim — o denominador existe (−7,688202), a soma dos ganhos
  de um conjunto vazio é **0**, e o PF é **0**. A regra correta, agora escrita em
  [[Strategy Performance]], é: PF nulo com motivo quando faltam **perdas** ou população, nunca
  quando faltam ganhos. Detalhe da divergência sobre errata versus correção pré-publicação em
  [[EXP-0001-momentum-v1]].
## Variantes tentadas

| Variante | Quando | Por quê | Onde ficou registrada |
|---|---|---|---|
| `volume_anomaly v2` | 2026-09-06 02:08:19 UTC | **Não é variante de pesquisa.** Sucessão obrigatória por correção do `code_ref` (digest da árvore inteira → digest do módulo mais o fecho dos imports); campo congelado não se corrige no lugar. | `changelog` das duas linhas em `strategy_versions`; `.claude/state/notes-S2.md` §15 |

## Relacionadas

[[Experiments Index]] · [[EXP-0001-momentum-v1]] · [[Volume Agent]] · [[Strategies]] · [[Strategy Performance]] · [[Anomalies]] · [[Dialogos/SHADOW]] · [[Workers]] · [[Open Bugs]]

## Fontes

`docs/plans/SHADOW-LAB.md` (itens 1–11) · `.claude/state/s2-proof.md` ·
`.claude/state/notes-S2.md` §14–19 · `packages/core/hunter_core/strategies/volume_anomaly_v1.py` ·
`services/strategy-worker/hunter_strategy_worker/**` · as consultas coladas em [[EXP-0001-momentum-v1]].
