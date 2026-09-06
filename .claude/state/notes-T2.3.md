# Notas de desenho — T2.3 (`baselines`, `anomalies`, `stage/`)

Decisões tomadas ao implementar `.claude/state/brief-T2.3-anomalies-baselines.md`, com a segunda
opinião da Astra (`.claude/state/astra-review-T2.3-anomalies.md`). Onde a "Decisão conjunta" de
`docs/plans/M2.md` (linhas 48–61) manda, ela manda; onde ela era omissa, a escolha está aqui com o
motivo e com o rótulo **suposição** quando é escolha minha, não contrato.

## 1. Quatro camadas, não uma
`baselines/` separa de propósito o que a Astra pediu que ficasse separado:

1. **cálculo** (`compute.py`): mediana e MAD exatos em `Decimal`, contagens e `input_fingerprint`.
   Puro, sem relógio: `window_start/end` e `available_at` vêm do chamador — é isso que torna
   "recalcular amanhã reproduz o score de hoje" verificável;
2. **usabilidade** (`revision.py`): o gate (>= 3 dias distintos **E** >= 120 observações válidas) é
   aplicado pelo **leitor**, com limiares de `opportunity_weights.weights["baseline_gate"]`. A linha
   guarda contagens cruas (`docs/DATABASE.md` §17.2);
3. **projeção causal** (`projection.py`): as revisões que um consumidor pode ver num corte, validadas
   **na construção** e passadas por valor — é o que mantém o detector função pura;
4. **porta** (`store.py` Protocol + `InMemoryBaselineStore`, `sql.py` adaptador).

**Correção aceita da Astra (must-fix 1):** uma baseline abaixo do gate **não** vira ausência de
revisão. Só população vazia devolve `BaselineUnavailable` (`no_observations`); o resto é revisão
gravada e o leitor recusa com `insufficient_history`. Uma revisão magra existe — "em construção" é
estado que o Radar mostra, não linha faltando.

## 2. Corte causal, seleção e identidade
- As duas condições (`available_at <= as_of` **E** `window_end < observation_ts`) entram no **WHERE**,
  antes do `DISTINCT ON`. Filtrar depois de selecionar deixaria uma revisão ainda inadmissível
  esconder uma antiga elegível (must-fix 1 da Astra; teste
  `test_an_older_admissible_revision_is_still_found`).
- A projeção **revalida** o corte e levanta. Não é duplicação: projeção também é montada de cache, de
  fixture e de replay, e uma entrada fora do corte ali é bug que tem de aparecer como erro.
- Desempate determinístico **compartilhado**: `(available_at, window_end, id)` decrescente.
  Postgres compara `uuid` byte a byte e `uuid.UUID` compara por `.int` — mesma ordem —, então
  `ORDER BY ... id DESC` e `max(..., key=selection_key)` escolhem a mesma linha.
- `append()` devolve **o que está gravado**: numa colisão de `ON CONFLICT DO NOTHING` o adaptador SQL
  relê por `input_fingerprint` e devolve o id existente. Devolver o uuid que este processo cunhou
  colocaria um `baseline_id` órfão dentro de um envelope de oportunidade.
- `load_ids()` é a porta do replay: o envelope nomeia `baseline_ids` e reproduzir o `d` de ontem lê
  exatamente aquelas linhas, não a mais nova (`test_weights_contract.py`).
- Perfil por instância de store (`algo_version`, `sampling`): mediana de outro algoritmo é outra
  população, não valor mais novo da mesma.

## 3. Números que o banco tem de conseguir guardar
`median`/`mad` são quantizados a 10 casas (`NUMERIC(28,10)`) e `coverage` a 6 (`NUMERIC(9,6)`) **no
cálculo**, não na escrita (must-fix "replay numérico" da Astra). Um MAD de 5e-11 em memória é 0 no
Postgres: sem quantizar, o replay lido do banco entraria no ramo `mad_zero` e a avaliação ao vivo
não. Teste: `test_statistics_are_quantized_to_the_persisted_resolution`.

Severidade em 2 casas (`NUMERIC(5,2)`) e confidence em 4 (`NUMERIC(5,4)`), ROUND_HALF_EVEN, sob
`hunter_core.strategies.numeric.CONTEXT`.

## 4. Estágio (`stage/`, ver §14)
- `r = |return_1h| / atr_14_pct`, **retorno de barra**, nunca `return_1h_live`: o estágio é
  persistido junto do score e o `_live` o faria mudar dentro do minuto. Teste de não-vazamento:
  `test_no_lookahead_t23.py` muda a vela em formação de forma violenta (preço 100 → 200, volume
  10 → 9999), prova que as features `_live` **mudam** e que estágio, detector e população de baseline
  **não**.
- **EARLY exige as quatro confirmações** (`relative_volume_1h >= 3`, `trade_velocity_1m >= 2×`
  baseline, `open_interest_change_1h >= +2%`, fluxo alinhado). Leitura conservadora da Astra (item 8),
  aceita: a decisão conjunta liga as quatro com "e", e "feature indisponível não confirma" tira uma
  confirmação, não tira a exigência. **Consequência operacional declarada:** enquanto o loader da
  T2.2 não preencher `covered_until` (notes-T2.2 §13), `trade_velocity_1m` e `buy_pressure_5m` saem
  `insufficient_coverage` e **nenhum mercado publica EARLY** — o candidato cai para `none` com
  `not_confirmed`. DEVELOPING e EXTENDED não são afetados. Liberar EARLY com três confirmações seria
  mudança explícita de contrato e não foi feita aqui.
- Direção pelo sinal de `return_1h`; retorno zero → `NEUTRAL` e nenhuma confirmação de fluxo.
- Precedência EXTENDED > DEVELOPING > EARLY > none aplicada ao **candidato**, antes da histerese.
- Histerese de 2 `observation_ts` distintos e estritamente crescentes; duplicata e evento atrasado
  não confirmam nem retrocedem (`state_out == state_in`).
- **Perda de qualidade invalida na hora**, inclusive `degraded`: se um insumo do estágio *publicado*
  deixa de ser `ok`, o publicado volta a `none` no mesmo instante e a contagem zera. Esperar duas
  observações para **parar** de afirmar algo é o inverso do que a histerese protege. Quais insumos
  contam depende do estágio e do `basis` (`ratio` ou `exhaustion`), que por isso viaja no estado.
- Limiares de `weights["stage"]` (`from_weights` lê os campos da própria dataclass, então acrescentar
  um limiar não cria uma segunda lista para divergir). `test_weights_contract.py` carrega o vetor
  **do próprio `infra/scripts/seed_reference.py`** e alimenta os três leitores (gate, normalização,
  estágio): se um perfil futuro renomear uma chave, quebra ali e não no scanner.

## 5. Severidade, direção e confidence
- `d = (x − mediana)/MAD`, **MAD cru, sem 1,4826**: a decisão escreve MADs e não alega
  probabilidade; o fator de consistência normal afirmaria uma normalidade que ninguém estabeleceu
  sobre volume de cripto.
- `severidade = clip((|d| − 1)/(6 − 1) × 100, 0, 100)`, com `deadband`/`saturação`/`teto` lidos de
  `weights["normalization"]` (`mad_piecewise_v1`). A identidade gravada é o **par**
  `mad_piecewise_v1@v2` — a mesma transformação sob outro perfil dá outra severidade.
- **Unilateralidade antes do disparo** (must-fix 2 da Astra): um detector `UP` usa `max(d, 0)`, então
  um colapso de volume de −6 MADs não vira `VOLUME_SPIKE` com severidade 100. Direção continua
  gravada à parte.
- **MAD zero:** `x == mediana` → desvio 0 e severidade 0 (a exceção da checklist do diálogo,
  `dialogue-M2.md:245`); `x != mediana` → componente indisponível com `mad_zero`. **Nenhum
  `min_scale` é declarado na v1.** Considerei `funding_rate = 0,0001` (taxa base da Binance) e a
  Astra desmontou o argumento: aquilo é um componente de juros por intervalo de 8 h, com exceções
  por símbolo, e não demonstra escala mínima de **dispersão**. Um `min_scale` inventado é número
  fabricado; quando existir, virá com justificativa e versão próprias.
- `confidence = min(coverage, dias_distintos/7)`, 4 casas — **só maturidade da baseline**. O frescor
  do dado corrente vive em `evaluation_state` (`ok|stale|unknown`), eixo separado de propósito.
  Registro da Astra (item 5): com amostragem por minuto, `sample_size <= 60 × dias`, logo
  `coverage <= dias/7` e o mínimo é sempre a cobertura; ficou como mínimo mesmo assim porque
  `expected_size` é parâmetro versionado e um perfil futuro pode quebrar essa desigualdade.

## 6. Os dez detectores
| Tipo | Feature lida | Lado | Observação |
|---|---|---|---|
| `VOLUME_SPIKE` | `relative_volume_5m` | up | **suposição**: a janela mais reativa das três |
| `PRICE_ACCELERATION` | `momentum_acceleration` | both | |
| `MOMENTUM_SHIFT` | `momentum_15m` | both | |
| `VOLATILITY_EXPANSION` | `atr_14_pct` | up | |
| `ORDERBOOK_IMBALANCE` | `orderbook_imbalance_20` | both | |
| `TRADE_VELOCITY_SPIKE` | `trade_velocity_1m` | up | indisponível hoje (cobertura do tape) |
| `OPEN_INTEREST_SPIKE` | `open_interest_change_1h` | up | **suposição**, ver abaixo |
| `FUNDING_ANOMALY` | `funding_rate` | both | "anomaly", não "spike": os dois lados |
| `LIQUIDATION_CLUSTER` | `liquidation_pressure_1h` | up | **registrado e desarmado**: `feature_not_implemented` |
| `CROSS_EXCHANGE_DIVERGENCE` | `price_divergence_vs_bybit` | both | **registrado e desarmado**: `single_exchange_until_m1b` |

- **`OPEN_INTEREST_SPIKE` é unilateral (`up`)** para casar com o nome do tipo. Lacuna declarada: um
  desmonte grande de OI (variação muito negativa) **não** é coberto por nenhum detector da v1. É
  escolha versionada, não descuido; um `OPEN_INTEREST_UNWIND` (ou lado `both`) é decisão de produto.
- **Limiares no próprio detector, versionados** (`detector_version = "VOLUME_SPIKE@v1"`):
  `fire_min_severity = 40` (= 3 MADs), `hold_min_severity = 20` (= 2 MADs), resolução em 5 min,
  expiração em 4 h (`docs/PIPELINE.md` §3). São **política declarada, não calibração**: nenhum estudo
  histórico sustenta os 3 MADs, e a string de versão existe para que um estudo os substitua. A Astra
  ratificou não ampliar o escopo para criar um bloco `weights["anomalies"]` no seed (item 3).
- A avaliação grava **os dois** versionamentos (detector e normalização) porque a severidade depende
  do par.

## 7. Máquina de estados das anomalias
Transição pura dirigida pelo `observation_ts` da avaliação — sem relógio, para que watchdog, scanner
e replay percorram o mesmo caminho.

- `ok` + severidade >= `fire` e sem anomalia aberta → **OPEN**;
- severidade >= `hold` → **UPDATE**;
- severidade < `hold` com dado válido → inicia/avança `below_hold_since`; 5 min consecutivos →
  **RESOLVE**;
- `stale` ou `unknown` → **HOLD**: continua `active`, **não** atualiza severidade (o último valor
  acreditado permanece) e **zera** a sequência abaixo do limiar. Aceite do must-fix da Astra
  (item 7): "o relógio não corre" tem de significar *zerar*, não *pausar e somar trechos* — 4 min
  abaixo, 10 min cego e mais 1 min abaixo não são 5 minutos comprovados;
- `observation_ts − detected_at >= 4 h` → **EXPIRE**, qualquer que seja a qualidade. Sem isso, uma
  anomalia `active + unknown` num mercado que emudeceu ficaria aberta para sempre. **Requisito para a
  T2.5**: a função pura não acorda sozinha — o watchdog precisa chamá-la com `no_data(...)` mesmo sem
  evento;
- reentrega/evento antigo (`observation_ts <= state.observation_ts`) → **NONE**;
- linha fechada (`resolved`/`expired`) não é reaberta: uma nova observação válida abre **outro**
  episódio, com `detected_at` novo;
- dedupe por `(market, type)` em `advance_all`, espelhando
  `uq_anomalies_active_per_market_type`; duas avaliações do mesmo par levantam.

## 8. Bootstrap: o que ele produz e o que ele recusa
- Reexecuta `compute_features` da T2.2, um corte por minuto, carregando o checkpoint de ATR entre os
  cortes (reancorar por corte daria número diferente e irrepetível).
- **Elegível = feature cujas entradas ⊆ {`candles:1m`, `state:atr_15m`} e sem sufixo `_live`** —
  derivado do registry, não de uma lista à mão. Toda feature registrada que não é elegível sai como
  `BootstrapExclusion` com motivo **estruturado**: `semantic_equivalence_unproven`
  (`trade_velocity_1m` — `trade_count` do candle não tem a mesma semântica nem a mesma janela do tape;
  notes-T2.2 §11), `partial_candle_not_reproducible` (todas as `_live`) e
  `historical_source_unavailable` (book, trades, derivativos). Teste garante que produzidas ∪
  excluídas = registradas, sem interseção.
- **Equivalência bootstrap/live: provada, e o escopo é bar-only.** `canonical_bytes()` do vetor
  bootstrap == do vetor live no mesmo corte, **e** o `FeatureState` de saída bate ao longo de uma
  sequência de 20 cortes (o checkpoint de ATR não viaja dentro do vetor — dois caminhos podem
  concordar num corte e divergir no próximo; ressalva da Astra, item 10). Um teste explícito registra
  que um live com book/tape **não** é igual, para ninguém ler a prova como mais larga do que é.
- Warm-up fica **fora** dos sete dias amostrados: as candles entregues têm de alcançar mais fundo que
  a janela amostrada, ou o primeiro dia produz silenciosamente menos (item 10). Teste mostra o
  warm-up aparecendo como rejeição contada (`{"warmup": 20}`), nunca como número inventado.
- `available_at` é **quando esta computação passa a valer**, nunca a idade das candles lidas.

## 9. Cadência do refresh (fecha a pendência de `docs/DATABASE.md` §17.2)
Recomputar **apenas o bucket da hora que fechou**, por mercado e feature: ~4 mil linhas/hora,
~96 mil/dia com 200 mercados × 20 features. É a segunda alternativa do §17.2, que é justamente a que
a decisão de **não particionar** `feature_baselines` assume. Recomputar todos os 24 buckets a cada
hora (2,3 milhões de linhas/dia) traria o particionamento mensal por `available_at` de volta à mesa.
Consequência: a baseline da hora H fica pronta logo depois de H:59 e, pelo corte
`window_end < observation_ts`, serve às observações da hora H **do dia seguinte** em diante.

## 10. O que ficou como requisito para outras tarefas
- **T2.5 (scanner):** (a) watchdog que chama `advance` com `no_data` para expirar anomalias sem
  evento; (b) preencher `covered_until` do tape — sem isso `TRADE_VELOCITY_SPIKE` e EARLY não
  existem na prática; (c) mapear `market_id` (UUID) para os pares `exchange/symbol` das features —
  as baselines são chaveadas por `market_id`; (d) fornecer ao estágio a mediana de
  `trade_velocity_1m` e as leituras de `relative_volume_15m` nos últimos 4 fechamentos de 15 min
  (`StageInputs`); (e) persistir/recuperar `AnomalyState` e `StageState` — o estado agora carrega
  `below_hold_readings` e `direction`/`candidate_direction`, e recarregar sem eles perde a prova da
  calmaria e o lado do estágio publicado; (f) o protocolo de lock da retenção (§17.2) ao gravar
  envelopes; (g) **índice em `feature_baselines.input_fingerprint`** — o caminho de colisão do
  `SqlBaselineStore.append` relê por `input_fingerprint IN (...)` e não há índice para isso (a
  unique constraint cobre a tupla inteira e o fingerprint é a última coluna dela, então não serve de
  prefixo); em `append` de lote é um seq scan por retry na tabela mais longa do esquema, e a
  correção é migração — fora dos arquivos permitidos aqui; (h) **teste de integração contra Postgres
  do `SqlBaselineStore`** — `test_baselines_sql.py` compila as instruções e exercita o retry contra
  uma conexão falsa, o que prova a *forma*, não o comportamento: `DISTINCT ON`/`ORDER BY`,
  `ON CONFLICT DO NOTHING` sobre `uq_feature_baselines_revision`, os CHECKs de
  `sample_size`/`coverage` e o trigger `feature_baselines_immutable` só se verificam com banco de
  verdade, e a T2.5 é quem terá um.
- **T2.2 (features), registrado aqui como o brief manda, sem tocar em `features/**`:** faltam
  `liquidation_pressure_1h` (`LIQUIDATION_CLUSTER` fica desarmado até existir) e a fonte de
  liquidações no `MarketContext`; `quote_volume_1h` e o grupo cross também não existem. Nenhum
  adaptador foi criado para fingir que existem.
- **T2.4 (scorer):** `BaselineProjection` já entrega `baseline_ids` por consulta, que é o que o
  envelope precisa; `StageDecision.as_wire()` já traz `state_in`/`state_out`, `r`, confirmações e os
  valores lidos.
- ~~**`packages/indicators/pyproject.toml` não declara `sqlalchemy`**~~ — **fechado (2026-09-06)**: o
  pyproject já declara `sqlalchemy[asyncio]>=2.0.36`, com o comentário apontando `baselines/sql.py`.
  A dependência deixou de ser transitiva via `hunter-core`; nada a fazer.

## 11. Suposições numéricas declaradas (nenhuma vem da decisão conjunta)
1. `fire_min_severity = 40` e `hold_min_severity = 20` (3 e 2 MADs).
2. `VOLUME_SPIKE` lê `relative_volume_5m` (e não 15m/1h).
3. `OPEN_INTEREST_SPIKE` é unilateral para cima.
4. Observação válida = `quality == ok` por feature; `degraded` fica de fora da população e aparece
   como rejeição contada (`degraded_sample`). Custo declarado e aceito com a Astra (item 6): horas de
   instabilidade ficam sistematicamente mais magras, e isso tem de aparecer como cobertura baixa, não
   ser "corrigido" com números que não descrevem o mercado.
5. `confidence` usa janela de 7 dias como denominador dos dias distintos.

## 12. Segunda opinião da Astra
Consulta de desenho antes de implementar: `.claude/state/astra-review-T2.3-anomalies.md`. Aceitos e
implementados: corte antes da seleção, `append` devolvendo identidade real, gate que não apaga a
revisão, unilateralidade antes do disparo, sem `min_scale` na v1, exceção de igualdade no MAD zero,
`stale` inelegível, sequência zerada por ausência, expiração absoluta, EARLY com as quatro
confirmações, `observation_ts` como identidade, quantização antes do uso, exclusões estruturadas do
bootstrap e comparação de `FeatureState` além do vetor. Rejeitado: nada de fundo. Não implementado
por escopo: bloco `weights["anomalies"]` no seed (fora dos arquivos permitidos) e a correção da
referência do brief a `seed_weights.py` (a configuração está em `seed_reference.py`) — registrada
aqui.

## 13. Revisão de diff da Astra (`astra-review-T2.3-diff.md`) — sete achados, todos corrigidos
Ela reproduziu cada um com probe em memória antes de reportar. Cada correção tem teste que falhou
antes (classe `TestAstraDiffReview*` nos arquivos correspondentes).

1. **Evento antigo reabria episódio encerrado.** A guarda de ordem só rodava para estado *aberto*:
   abrir às 10h, expirar às 14h e reprocessar a avaliação das 10h devolvia `OPEN` com
   `detected_at = 10h`. A guarda passou a valer para qualquer estado recebido, inclusive
   `resolved/expired` (`lifecycle.py::advance`).
2. **Evidência parcial.** Os ramos abaixo do limiar de manutenção trocavam `severity`/
   `current_value`/`deviation` e mantinham `baseline`, `baseline_ids`, `confidence` e versões
   anteriores — o estado guardava um desvio calculado contra a revisão B ao lado da mediana de A, e a
   explicação gravada deixava de reproduzir. Agora `_with_evidence` troca o **conjunto inteiro** a
   cada avaliação acreditada; o que é do episódio (`detected_at`, `status`, `below_hold_since`) fica
   com o chamador.
3. **`append` devolvia a revisão tentada, não a gravada.** Numa colisão o adaptador SQL aproveitava
   só o `id` da linha existente e devolvia o objeto da tentativa — cujo `available_at` é mais novo
   (não faz parte da identidade). Uma projeção montada dessa resposta recusaria uma baseline que
   estava disponível desde a publicação original. Agora a linha é reconstruída do banco.
4. **Identidade temporal era horário de recomputação.** `vector.ts` é `ctx.as_of`. Duas
   recomputações do mesmo minuto contavam como duas observações distintas — fabricando uma
   confirmação de estágio — e sessenta recomputações de um minuto entravam como sessenta observações
   na população, o que atravessaria o gate sem 120 minutos vistos. Correções: `classify_stage`
   recebe `observation_ts` explícito (padrão = o **minuto** de `vector.ts`), e
   `compute._check_inputs` deduplica por **minuto**, não por timestamp exato.
5. **Invalidação do estágio ignorava os insumos externos.** Um EARLY publicado que perde a mediana de
   `trade_velocity` (ou um EXTENDED por exaustão que perde o histórico de `relative_volume_15m`)
   continuava publicado até a histerese. `_lost` passou a olhar features **e** `StageInputs`, e o
   envelope (`StageDecision.as_wire()["inputs"]`) grava a mediana e as quatro leituras usadas — sem
   elas, "a confirmação disparou" não é reproduzível.
6. **Recorte do ring de 1500 no bootstrap.** `bisect_left(corte − 1500 min)` com
   `bisect_right(corte)` seleciona **1501** fechamentos numa série contínua: o replay via um minuto
   que o hot state nunca teve. Agora o recorte é por **contagem de entradas**
   (`start = end - buffer_minutes`), que é como o loader decide `truncated`. Teste com 1600 candles
   compara byte a byte contra `candles[-1500:]` e falha com a lógica antiga.
7. **Projeção não validava versões.** O caminho de cache/`load_ids` contorna o SELECT que fixa
   feature/algoritmo. A projeção passou a recusar outro `algo_version` na construção, e `resolve()`
   devolve `baseline_version_mismatch` quando a revisão é de outra `feature_version` — o detector
   passa a sua própria versão.

Nice-to-have aceitos: `eligible` entra em `AnomalyEvaluation.as_wire()` (a propriedade bloqueava o
uso mas não aparecia na amostra); `StageThresholds.from_weights` levanta `TypeError` para uma
anotação sem parser declarado em vez de cair num `int()` silencioso; teste de silêncio dentro da
janela de resolução (o watchdog precisa mesmo alimentar `no_data`).

Não aceito por escopo: prova de equivalência passando pelo loader real do hot state (exige
`packages/indicators/hunter_indicators/features/**`, fora dos arquivos permitidos) — fica como
requisito da T2.5, junto do `covered_until`.

## 14. `stage.py` virou `stage/` (pacote)
Depois das correções acima o módulo bateu 393 linhas e o gate de 350
(`infra/scripts/check_file_size.py`) é regra dura do CLAUDE.md. Dividido em `stage/model.py`
(contrato: limiares, insumos, estado, decisão) e `stage/classifier.py` (a função pura), com
`stage/__init__.py` reexportando tudo — **a porta pública `from hunter_indicators.stage import
classify_stage` não mudou**. É o mesmo remédio que `analysis_baselines.py` aplicou a `analysis.py` e
que `vector.seconds_between` aplicou a `context.py` (notes-T2.2 §17). Desvio declarado do brief, que
nomeia o arquivo `stage.py`: o caminho de import é o que o brief protege, e o teto de linhas não é
negociável.

## 15. Revisão cruzada de quant (2026-09-06) — dois must-fix e quatro nice-to-have
Segundo quant-engineer revisou o diff. Cada item abaixo tem teste que falhou antes da correção.

### MF-1 — a janela virou semiaberta `[window_start, window_end)` (`baselines/compute.py`)
Fechada nos dois extremos, o bucket cuja hora coincide com `window_end` conta um minuto duas vezes:
421 observações em 7 dias contra `expected_size = 420`, `coverage = 1,002381`. `feature_baselines`
tem `CHECK sample_size <= expected_size` e `CHECK coverage BETWEEN 0 AND 1`, e como o adaptador
insere o mercado inteiro num lote, **uma** linha fora da linha aborta o bootstrap de todos os outros
buckets. Duas mudanças: `_check_inputs` aceita `window_start <= ts < window_end` e levanta quando
`len(observations) > expected_size` (a checagem do tamanho vem **primeiro**, para o erro ser o que o
banco recusaria, e não o do bucket errado). O corte causal `window_end < observation_ts` da projeção
já supunha a semiabertura: a revisão da hora H contém os minutos de H e nunca o primeiro minuto da
janela seguinte. Teste: janela natural de 7 dias com uma observação por minuto → 24 buckets, 420
cada, `coverage = 1.000000`, `distinct_days = 7`; observação exatamente em `window_end` levanta; 421
observações levantam citando `expected_size`. Consequência para os chamadores: quem passava
`window_end = último corte` passa agora `último corte + 1 min` (ajustado nos testes de bootstrap,
de pipeline e de contrato de pesos).

### MF-2 — o coletor deduplica por minuto (`baselines/collect.py`)
`Observation.ts` era `vector.ts`, que é `ctx.as_of` e carrega segundos. Ao vivo, mais de um vetor por
minuto é o caso normal (tick-features com throttle de 1 s), então duas leituras de 14:03 chegavam a
`compute._check_inputs` como duas observações do mesmo minuto, levantavam, e o refresh **daquele
mercado** morria sem escrever baseline nenhuma. Agora `observations_from_vector` trunca o `ts` ao
minuto (aceitas e rejeições) e o coletor chaveia por `(feature, minuto)`.

**Fica a primeira leitura válida recebida do minuto, não a última** — primeira na ordem de chegada,
não a cronologicamente mais antiga dentro do minuto, e uma leitura rejeitada por qualidade não ocupa
o slot. O motivo é **replay determinístico**, não causalidade (correção da Astra na revisão deste
fix-pass, §16): o coletor consome vetores em ordem de chegada, "primeira" não depende do que vem
depois e o mesmo fluxo escolhe o mesmo valor duas vezes. Truncar uma leitura de 14:03:40 para 14:03
não prova que ela estava disponível às 14:03:10, e não é isso que se afirma — a causalidade é
garantida por `available_at` e pelo corte `window_end < observation_ts`, em outro lugar de propósito. A leitura extra não é erro: é descartada e **contada** em
`rejections()` como `duplicate_minute`. Teste: 14:03:10 + 14:03:40 + 126 minutos bons = 128 leituras
→ 127 observações, `{"duplicate_minute": 1}`, `compute_revision` passa (o brief da revisão dizia
"128 observações"; 2 leituras de um minuto + 126 minutos são 127 observações, e o teste afirma os
três números para não deixar dúvida). Um minuto rejeitado por qualidade **não** ocupa o slot: se a
primeira leitura era `degraded`, a `ok` seguinte do mesmo minuto entra.

### (a) O estado carrega a direção do estágio **publicado** (`stage/`)
`StageDecision.direction` é o sinal do `return_1h` **desta** observação; o estágio publicado foi
confirmado duas observações atrás e tem lado próprio. Sem isso no `StageState`, o lado se perdia no
restart (o scanner recarregava o estado, recebia uma duplicata e só sabia dizer `NEUTRAL` para um
EARLY que continuava publicado) e uma inversão de sinal repintava silenciosamente um long publicado
como short. `StageState` ganhou `direction` (o lado publicado) e `candidate_direction`, ambos no
`as_wire()`; `StageDecision.published_direction` lê o do `state_out` e entra no envelope.

**A histerese passou a valer sobre o par `(estágio, direção)`**: "EARLY long" e "EARLY short" são
afirmações diferentes sobre o mercado, então republicar a segunda custa as mesmas duas observações
distintas que custaria ir de EARLY para DEVELOPING. Sem isso, o candidato "mesmo estágio, outro lado"
caía no ramo de reafirmação e o lado publicado envelhecia para sempre. Testes: duplicata depois de um
restart (estado reconstruído do wire) mantém `LONG`; inversão de sinal mantém `LONG` publicado com
`candidate_direction = SHORT` e 1 confirmação; a segunda observação invertida republica `SHORT`;
invalidação por perda de qualidade zera o lado junto com o estágio.

### (d) Resolver anomalia exige leituras comprovadas (`anomalies/`)
`below_hold_since` sozinho mede **tempo decorrido**: duas leituras a sete minutos de distância o
satisfaziam e uma anomalia era declarada encerrada com base em duas amostras. `AnomalyState` ganhou
`below_hold_readings` (no `as_wire()`) e `DetectorDefinition` ganhou
`resolve_min_readings = RESOLVE_MIN_READINGS = 5` (**suposição declarada**: a amostragem é
`PER_MINUTE`, então cinco minutos de calma são cinco leituras distintas; um detector com outra
cadência tem de trazer o número junto). Resolver exige as **duas** condições — decorrido
`>= resolve_after` **e** `>= resolve_min_readings` leituras acreditadas abaixo do `hold` — e
`no_data`/`stale` zeram a contagem junto com `below_hold_since`, pela razão de sempre: um mercado que
não vimos não é um mercado que estava calmo. Cenário do revisor (10:00, 10:02, mudo até 10:07): 7
minutos decorridos, 3 leituras → `HOLD`, `active`. Em cadência perfeita de 1 min a resolução acontece
na sexta leitura, que é o comportamento anterior; a contagem só morde quando o dado é esparso. Dois
testes antigos que resolviam com duas leituras passaram a alimentar a série minuto a minuto.

### (e) `atr_warmup` ≠ `atr_degraded` (`stage/classifier.py`)
`_ok_value` devolve `None` tanto para "ainda não há ATR" quanto para "há ATR e esta leitura não é
confiável", e o estágio gravava `atr_warmup` nos dois casos — o operador ia procurar histórico curto
onde o problema era coleta. `_atr_reason` separa: ausente do vetor, `WARMUP`,
`INSUFFICIENT_SAMPLE`/`INSUFFICIENT_COVERAGE` ou ATR zero (sem escala ainda) → `atr_warmup`;
qualquer outra coisa (qualidade `degraded`, `gap`, `stale_input`, `missing_input`, `corrupt_input`)
→ `atr_degraded`. **Suposição declarada:** a lista de motivos de warm-up é minha, não da decisão
conjunta; um motivo novo em `Reason` cai por padrão em `atr_degraded`, que é o lado conservador
("não confie nesta leitura") em vez de alegar imaturidade que ninguém verificou.

### (b) `select_projection` distingue por `feature_version` e `algo_version`
O `DISTINCT ON` era `(market_id, feature, hour_of_day)` enquanto o `InMemoryBaselineStore` casa
também por `feature_version` e pelo `algo_version` da instância. Um lote pedindo duas versões da
mesma feature devolvia duas linhas em memória e uma no Postgres — a mesma projeção discordando de si
mesma conforme o adaptador que o chamador tivesse na mão. As duas colunas entraram no `DISTINCT ON` e
no prefixo do `ORDER BY` (exigência do Postgres). Teste sobre a string compilada no dialeto real.

### O que a revisão cruzada **não** mudou
Nada de contrato: gate, quantização, unilateralidade, ausência de `min_scale`, EARLY com as quatro
confirmações e expiração absoluta continuam como nas §§1–13.

## 16. Segunda opinião da Astra sobre este fix-pass (`astra-review-T2.3-fixes.md`)
Ela rodou os cinco arquivos de teste (117 passed) e reproduziu cada achado com probe em memória.

### Must-fix aceito e corrigido — retirada ≠ substituição (`stage/`)
Cenário dela, reproduzido: publicar `DEVELOPING long`, depois só observações de `r = 0,005` com as
quatro confirmações válidas **alternando o lado** a cada minuto. Todo candidato vira EARLY, mas cada
troca de lado reinicia a contagem em 1, a contagem nunca chega a 2 e o `DEVELOPING long` de meia hora
atrás continua publicado indefinidamente. A histerese sobre o par consertou a direção e criou esse
buraco (o mesmo padrão já existia para alternância de **estágio**, e agora aparecia com estágio
constante).

Correção: `StageState.unsupported` conta observações consecutivas que **não** sustentam o par
publicado. Publicar continua exigindo `confirmations` observações do mesmo par; **retirar** exige o
mesmo número de observações que não o sustentam, e leva o publicado a `none` com
`reason = stage_withdrawn` e direção `NEUTRAL`. Uma reafirmação do par publicado zera os dois
contadores — é exatamente o flapping que a histerese existe para absorver. Testes:
`TestAstraFixesReviewWithdrawal` (alternância retira na segunda observação e nunca republica; um
candidato estável volta a publicar depois da retirada; uma observação isolada não retira nada).

### Nice-to-have aceito — a linha recusa o que o CHECK recusa (`baselines/revision.py`)
`compute_revision` guarda o caminho calculado, mas `BaselineRevision` é dataclass e `insert_revisions`
serializa o que receber: a Astra construiu à mão `sample_size = 421` / `coverage = 1,002381` e o
INSERT compilou. `__post_init__` passou a validar `expected_size > 0`,
`0 <= sample_size <= expected_size`, `0 <= coverage <= 1` e `distinct_days <= sample_size`;
`_check_inputs` também recusa `expected_size <= 0` antes de dividir. Testes:
`TestAstraFixesReviewRowInvariants`.

### Correções de **justificativa** (o código não mudou)
- **"primeira leitura" (item b).** Ela está certa: primeira é a primeira leitura *válida recebida*,
  não a cronologicamente mais antiga do minuto, e truncar uma leitura de 14:03:40 para 14:03 **não**
  prova que ela estava disponível às 14:03:10. A escolha continua sendo a primeira, mas o motivo
  escrito agora é o correto — **replay determinístico**, não causalidade. A causalidade é garantida
  em outro lugar de propósito: `available_at` e o corte `window_end < observation_ts`.
- **"cinco leituras" (item d).** A contagem prova cinco *leituras*, não cinco minutos **contíguos**:
  leituras nos minutos 0, 1, 2, 3 e 60 resolvem. A contiguidade depende do watchdog entregar
  `no_data` nos minutos mudos (requisito T2.5 (a), §10) — a função pura não pode inferir uma lacuna
  que ninguém lhe contou, e inventá-la seria ler o relógio. Limitação documentada em
  `lifecycle.py`, não "corrigida" com política nova.

### Registrado, não implementado
- Anomalia em mercado de cadência muito baixa pode terminar em `expired` em vez de `resolved`. É
  aceitável e explícito (a expiração absoluta de 4 h tem precedência), **desde que o watchdog chame
  `advance`**: sem chamada, quatro horas não são um timer autônomo. Já está na §10 como T2.5 (a).
- `algo_version` no `DISTINCT ON` é redundante sob o `WHERE` atual (que o fixa). Ficou porque a
  redundância é a que faz a chave da projeção ser lida igual à do `InMemoryBaselineStore` sem
  depender de o `WHERE` continuar como está; não custa nada e não muda plano.
- Testes de integração SQL: T2.5, §10 (g)/(h). (A chegada fora de ordem no coletor **saiu** desta
  lista — ver §17: nunca precisou de Postgres e foi fechada aqui.)

## 17. Fechamento do fix-pass (2026-09-06) — as duas provas que faltavam

O código do fix-pass (§§15–16) já estava inteiro na árvore; o que faltava era a parte que a Astra
listou em "o que eu faria diferente" e que **não** depende de Postgres. Duas lacunas de teste, ambas
fechadas aqui, ambas verificadas por mutação (o teste falha quando a propriedade é quebrada de
propósito — um teste que nunca vi falhar não é prova de nada).

### Chegada fora de ordem no coletor (`test_baselines_collect.py::TestOutOfOrderArrival`)
A justificativa escrita de "fica a primeira leitura **recebida**" (§16, item b) só é falsificável num
fluxo em que ordem de chegada e ordem cronológica **discordam** — e não havia nenhum. Três testes:

1. **14:03:40 chega antes de 14:03:10 → fica o valor de :40.** É o caso que separa "primeira
   recebida" de "instante mais antigo do minuto"; sem ele, a política estava afirmada na docstring e
   provada em lugar nenhum.
2. Um minuto que chega atrasado continua caindo no seu bucket (o coletor não supõe fluxo monótono).
3. **Ordem de chegada não muda a identidade da revisão.** O mesmo conjunto de leituras consumido ao
   contrário tem de dar a mesma mediana, o mesmo MAD e o mesmo `input_fingerprint`. Isto é o que
   separa *seleção* de *identidade*: a seleção pode depender da chegada (e depende, por replay), o
   digest não pode — senão um retry que consumiu as mesmas leituras noutra ordem entraria como
   **segunda revisão** em vez de colidir em `uq_feature_baselines_revision`.
   Mutação: remover o `sorted(observations, key=lambda o: o.ts)` de `input_fingerprint` → falha com
   dois digests diferentes. Mutação da política: fazer a **última** leitura do minuto ganhar → falham
   o teste (1) e o de MF-2.

### A lacuna é trabalho do watchdog (`test_anomaly_lifecycle.py::TestCrossReviewGapsAreTheWatchdogsJob`)
A limitação do item (d) — cinco *leituras* não são cinco minutos **contíguos** — estava documentada
na docstring de `lifecycle.py` e em nenhum teste. Documentar limitação sem teste é deixá-la mudar
sozinha no próximo refactor. Agora as duas metades estão fixadas:

1. A série exata da Astra (leituras abaixo do `hold` nos minutos 0, 1, 2, 3 e 60) **resolve** — é o
   comportamento declarado, não um bug tolerado em silêncio;
2. a mesma série com um `no_data` no minuto 30 **não** resolve: a contagem zera e o minuto 60 começa
   uma sequência nova. É a prova de que o remédio declarado (watchdog, T2.5 (a) da §10) funciona de
   verdade, e não só na intenção.

**Achado ao escrever (2):** a primeira versão do teste montou a série com `opened()` no minuto 0 e
leituras em 1, 2, 3, 60 — quatro leituras abaixo do limiar, não cinco — e o `advance` devolveu `HOLD`.
Não é bug: é `resolve_min_readings = 5` mordendo exatamente onde tem de morder. O teste foi corrigido
para abrir o episódio antes do início da calmaria, que é o cenário que a Astra reproduziu.

### O que **não** mudou
Nenhuma linha de `hunter_indicators/**`. As duas mutações usadas como prova foram revertidas; o único
código tocado nesta passagem são os dois arquivos de teste e estas notas.
