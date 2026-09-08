# T3.33f — `--explain-ledger` no replay, `breakout v2` por parâmetro (a geometria medida) e `session_orb` **parada** antes de escrever

**Data:** 2026-09-08 (UTC; horário de Brasília = UTC−3).
**Executor:** quant-engineer. **Base:** `main` em `cf51c7d`; VPS rodando `hunter-api:cf51c7d` em
api/web/strategy-worker. **Nada commitado.** **Nenhum container parado ou recriado.** **Nenhum
`.env*` tocado.** Escritas **no banco** da VPS: apenas `derive_variant.py`,
`activate_strategy_version.py` e os dois replays. Tudo o mais foi lido em transação
`REPEATABLE READ, READ ONLY`. Fora do banco, os scripts de medição e o `--ledger` dos replays
gravaram JSONL em `/tmp` **dentro** do `hunter-strategy-worker-1` (`t33f-*.jsonl`), como na T3.33e;
nenhum arquivo foi copiado para dentro de container nenhum. Última conferência às **18:35 UTC**:
`hunter-strategy-worker-1` em `hunter-api:cf51c7d`, `Up 2 hours (healthy)`, heartbeat de
`2026-09-08T18:35:23Z`.

## STATUS

`DONE_WITH_CONCERNS`.

| Passo do brief | Resultado |
|---|---|
| 1. `--explain-ledger <path>` em `replay.run` | **OK** — módulo novo `replay/explain.py`, ligado em `replay_market` e no CLI; 15 testes próprios (unidade + integração + a prova de não-antecipação com contraprova). **Não está na imagem `cf51c7d`** (ver CONCERN 1 e como a medição foi feita mesmo assim) |
| 2. `breakout v2` por parâmetro | **OK** — medi primeiro (livro-razão sobre as mesmas 11 904 barras), medi também a alternativa (`squeeze_window_bars` 2–6) e **descartei** a alternativa com número; derivada `stop_atr` 1,25 → 3,5 (`params_hash 0e6abf1114cb`), ativada **17:35:22,628 UTC** |
| 2b. `--supersede` para aposentar a `v1` | **NÃO EXECUTÁVEL** — `--supersede` é a via de *código novo*, não de *parâmetro novo*: recusou com `breakout v1 is already frozen against this code`. A `v1` continua **ativa** e custando avaliações (CONCERN 2) |
| 3. Replay da `v2` | **OK** — duas fatias, mesma coorte, 4 mercados, 11 904 barras, 0 erros; **8 decisões**, 6 recusas de geometria; avaliação contra K1–K5, banda de ATR e bucket de `squeeze_ratio` abaixo |
| 4. `session_orb v1` | **PARADO, como o brief manda** — a chave `session_orb` **não existe** em `strategies` (o `seed.py` é do operador). Nenhuma ativação, nenhum replay, nenhuma escrita |
| 5. Rascunhos EXP datados | **OK** — EXP-0008 (avaliação da `v2` + linhagem `v1→v2` na tabela de variantes) e EXP-0010 (registro datado da parada). `obsidian/**` **não** foi tocado |

## FILES

**Criados**

| Arquivo | O que é |
|---|---|
| `C:\dev\project-hunter\services\strategy-worker\hunter_strategy_worker\replay\explain.py` | o livro-razão de explicação: `ExplainRow` (5 campos), `ExplainLedger` (um *shard* por mercado, JSONL append-only), `shard_path`, `merge_shards`, `ledger_for` (o shard ou nada, sempre como context manager) e `merge_markets` (junta os shards da corrida e avisa se faltou linha) |
| `C:\dev\project-hunter\services\strategy-worker\tests\test_replay_explain.py` | 15 testes: contrato da linha, shards/merge (inclusive um merge que não consegue escrever e preserva os shards), a bandeira do CLI, uma linha por barra avaliada sobre replay real, e a mutação de não-antecipação **com contraprova** |
| `C:\dev\project-hunter\.claude\state\notes-T3.33f.md` | este arquivo |

**Modificados**

| Arquivo | Mudança |
|---|---|
| `C:\dev\project-hunter\services\strategy-worker\hunter_strategy_worker\replay\simulate.py` | `replay_market(..., explain: ExplainLedger | None = None)`; grava a **mesma** `Evaluation` que o contador de estados leu |
| `C:\dev\project-hunter\services\strategy-worker\hunter_strategy_worker\replay\run.py` | `--explain-ledger`; cada processo de mercado abre seu shard (`ledger_for`), o pai concatena na ordem de despacho (`merge_markets`) e confere `linhas == bars_evaluated`. Ficou em 328 linhas (teto 350) — a lógica do livro-razão mora em `explain.py`, não aqui |
| `C:\dev\project-hunter\.claude\state\exp-drafts\EXP-0008-breakout-compressao-de-volatilidade.md` | seção `Avaliação de 2026-09-08 (2)` (replay da `v2`) + duas linhas em `Variantes tentadas` + frontmatter |
| `C:\dev\project-hunter\.claude\state\exp-drafts\EXP-0010-session-orb-faixa-de-abertura.md` | seção datada da **parada** antes de escrever + frontmatter |

Fora do repositório (scratchpad, descartáveis): `explain_pass.py` (o livro-razão calculado dentro da
imagem antiga, somente leitura), `base_width.py` (largura da base por `squeeze_window_bars`),
`analyze_geometry.py` (distribuição e candidatos de `stop_atr`), `roquery.py` (SQL somente leitura).

## TESTS (saída real)

Estado final, **depois** dos ajustes pedidos pela Astra (seção adiante):

```
$ uv run pytest services/strategy-worker/tests/test_replay_explain.py -v
============================= test session starts =============================
… TestTheRow::test_it_is_the_five_fields_and_nothing_else PASSED [  6%]
… TestTheRow::test_the_detail_stays_an_object_and_the_instant_is_utc PASSED [ 13%]
… TestTheRow::test_a_naive_instant_is_refused PASSED [ 20%]
… TestTheRow::test_a_ledger_that_recorded_nothing_still_exists_and_is_empty PASSED [ 26%]
… TestTheShards::test_a_shard_is_named_after_its_market PASSED [ 33%]
… TestTheShards::test_merge_concatenates_in_dispatch_order_and_removes_the_shards PASSED [ 40%]
… TestTheShards::test_a_merge_that_cannot_write_keeps_every_shard PASSED [ 46%]
… TestTheShards::test_a_second_slice_appends_to_the_same_ledger PASSED [ 53%]
… TestTheFlag::test_it_is_off_by_default PASSED [ 60%]
… TestTheFlag::test_the_path_reaches_the_run PASSED [ 66%]
… TestOverARealReplay::test_one_line_per_evaluated_bar PASSED [ 73%]
… TestOverARealReplay::test_the_bar_that_decided_says_so_and_the_others_say_why_not PASSED [ 80%]
… TestTheLedgerCannotReadTheFuture::test_rewriting_every_later_candle_changes_no_line PASSED [ 86%]
… TestTheLedgerCannotReadTheFuture::test_a_candle_that_is_not_final_changes_no_line_either PASSED [ 93%]
… TestTheLedgerCannotReadTheFuture::test_the_cheat_is_caught_by_the_ledger_too PASSED [100%]
======================== 15 passed in 76.43s (0:01:16) ========================
```

(o prefixo `services/strategy-worker/tests/test_replay_explain.py::` foi elidido em cada linha para
caber na página; o resto é verbatim.)

Regressão do módulo de replay (nenhum teste existente foi tocado):

```
$ uv run pytest services/strategy-worker/tests/test_replay_engine.py \
      services/strategy-worker/tests/test_replay_contract.py \
      services/strategy-worker/tests/test_replay_lookahead.py -q
...................................................                      [100%]
51 passed in 250.07s (0:04:10)

$ uv run pytest services/strategy-worker/tests/test_replay_arms.py \
      services/strategy-worker/tests/test_replay_reproduce.py -q
................................                                         [100%]
32 passed in 70.76s (0:01:10)
```

Portões:

```
$ uv run ruff check services/strategy-worker/hunter_strategy_worker/replay/ services/strategy-worker/tests/test_replay_explain.py
All checks passed!

$ uv run ruff format --check <os 4 arquivos>
1 file already formatted   (os outros três: "3 files left unchanged")

$ uv run pyright services/strategy-worker/tests/test_replay_explain.py services/strategy-worker/hunter_strategy_worker/replay/
0 errors, 0 warnings, 0 informations

$ uv run python infra/scripts/check_file_size.py
scanned 549 files; 0 over budget, 0 grandfathered
```

### O que os testes provam (e o que deliberadamente não provam)

1. **contrato da linha**: exatamente `bar_close, market, state, reason, detail`, nessa ordem, com o
   instante normalizado para UTC (um `datetime` ingênuo é **recusado**, não convertido);
2. **shards**: um por mercado (dois processos escrevendo no mesmo arquivo não é atômico no Windows),
   concatenados na ordem de despacho; a segunda fatia **acrescenta** ao mesmo livro-razão; e um merge
   que **não consegue escrever** no destino preserva todos os shards (a única outra cópia);
3. **uma linha por barra avaliada**: sobre um replay real, o histograma do arquivo é *idêntico* ao
   `states` da corrida — não por comparação, por construção (a linha é escrita a partir do mesmo
   objeto `Evaluation` que o contador leu);
4. **não-antecipação**: reescrever toda vela **a partir do próprio corte** (e também marcá-las
   não-finais) não move **uma** linha do livro-razão; e a contraprova — o motor trapaceiro com o
   corte 30 min à frente — **é pega** pela mesma comparação, senão os dois testes acima seriam
   decoração;
5. o que **não** é testado: nada aqui lê o arquivo de volta. O livro-razão é saída de diagnóstico e
   não realimenta decisão nenhuma.

## COMANDOS e RECIBOS (saída real, verbatim)

### 0. Estado da VPS antes de qualquer passo

```
$ ssh hunter-vps 'hostname; date -u; cd /opt/project-hunter && git log --oneline -1; docker ps --format "{{.Names}}\t{{.Image}}\t{{.Status}}"'
vmi3483069
Tue Sep  8 17:04:36 UTC 2026
cf51c7d T3.33e: breakout v1 e mean_reversion v1 ativadas …
hunter-web-1	hunter-web:cf51c7d	Up 22 seconds (healthy)
hunter-strategy-worker-1	hunter-api:cf51c7d	Up 22 seconds (healthy)
hunter-api-1	hunter-api:cf51c7d	Up 22 seconds (healthy)
hunter-execution-worker-1	hunter-api:b5d4f9b	Up 49 minutes (healthy)
hunter-scanner-worker-1	hunter-api:b5d4f9b	Up 49 minutes (healthy)
hunter-market-worker-*	hunter-api:1ca7cf5	Up About an hour (healthy)
…
$ ssh hunter-vps 'docker exec hunter-strategy-worker-1 python -c "import hunter_core.strategies.session_orb_v1 …"'
import ok session_orb_v1 v1
```

`strategy-worker` está em `cf51c7d` e o módulo `session_orb_v1` importa — as duas condições do brief.

### 1. O livro-razão sobre a `breakout v1` (somente leitura, dentro da imagem)

A bandeira `--explain-ledger` é desta tarefa e **não está na imagem publicada**. Em vez de copiar
código para dentro de um container vivo (o que quebraria a identidade "imagem = código auditado"),
rodei a **mesma medição** por um script de leitura que chama `Strategy.explain` sobre o mesmo
`build_market_context` e o mesmo `WindowCache` do replay, em transação `REPEATABLE READ, READ ONLY`.
A fidelidade não é afirmada, é **conferida** (ver a tabela de equivalência adiante).

```
$ ssh hunter-vps 'docker exec -i hunter-strategy-worker-1 python - --version breakout:v1 \
    --from 2026-08-08 --to 2026-09-08 --markets ETHUSDT --out /tmp/t33f-explain-breakout-v1.jsonl' < explain_pass.py
{"version": "breakout v1", "code_ref": "hunter_core.strategies.breakout_v1@sha256:4c920b0c…64ff1",
 "window": ["2026-08-08T00:00:00+00:00", "2026-09-08T00:00:00+00:00"], "markets": ["binance:ETHUSDT"],
 "bars": 2976, "states": {"unavailable": 112, "not_triggered": 2864},
 "reasons": {"warmup": 112, "not_compressed": 2409, "no_breakout": 437, "rvol_low": 6, "atr_out_of_range": 12},
 "seconds": 48.885}

… SOLUSDT: "states": {"unavailable": 112, "not_triggered": 2858, "rejected": 6}   (geometry_invalidation 6)
… XRPUSDT: "states": {"unavailable": 112, "not_triggered": 2861, "rejected": 3}   (geometry_invalidation 3)
… DOGEUSDT:"states": {"unavailable": 112, "not_triggered": 2859, "rejected": 5}   (geometry_invalidation 5)
```

**Equivalência com o replay da T3.33e** (o mesmo código, as mesmas barras, contadas por dois
caminhos diferentes):

| | barras | `unavailable` | `not_triggered` | `rejected` |
|---|---:|---:|---:|---:|
| replay T3.33e (recibos `replay_runs`, 2 fatias) | 11 904 | 448 | 11 442 | 14 |
| passada de explicação (T3.33f, somente leitura) | 11 904 | 448 | 11 442 | 14 |

### 2. A geometria medida — por que `stop_atr = 3,5`

```
$ ssh hunter-vps 'docker exec -i hunter-strategy-worker-1 python - /tmp/t33f-explain-breakout-v1.jsonl' < analyze_geometry.py
{"bars": 11904, "states": {"unavailable": 448, "not_triggered": 11442, "rejected": 14},
 "reasons": {"warmup": 448, "not_compressed": 9816, "no_breakout": 1575, "rvol_low": 25,
             "atr_out_of_range": 26, "geometry_invalidation": 14}}

geometry_invalidation bars: 14
bar_close                  market                 atr%  base_atr needs_stop_atr
2026-08-27T08:15:00+00:00  binance:DOGEUSDT     0.5113     4.100          4.100
2026-08-27T08:45:00+00:00  binance:DOGEUSDT     0.5435     4.676          4.676
2026-08-27T09:00:00+00:00  binance:DOGEUSDT     0.5915     4.456          4.456
2026-08-31T05:30:00+00:00  binance:DOGEUSDT     0.5664     2.194          2.194
2026-09-06T03:45:00+00:00  binance:DOGEUSDT     0.5404     2.505          2.505
2026-08-19T21:00:00+00:00  binance:SOLUSDT      0.6186     3.341          3.341
2026-08-19T21:15:00+00:00  binance:SOLUSDT      0.8571     5.583          5.583
2026-08-23T11:30:00+00:00  binance:SOLUSDT      0.5935     2.536          2.536
2026-08-24T11:45:00+00:00  binance:SOLUSDT      0.5877     3.571          3.571
2026-08-26T21:15:00+00:00  binance:SOLUSDT      0.5007     2.541          2.541
2026-09-06T09:30:00+00:00  binance:SOLUSDT      0.5061     4.157          4.157
2026-08-23T21:30:00+00:00  binance:XRPUSDT      0.9576     3.271          3.271
2026-08-24T11:45:00+00:00  binance:XRPUSDT      0.8620     2.862          2.862
2026-08-27T08:15:00+00:00  binance:XRPUSDT      0.6013     3.346          3.346

distribution of the base distance in ATR (close -> base_low):
  n = 14   min 2.194   p25 2.541   median 3.344   p75 4.157   max 5.583   atr% med 0.5896%

candidate stop_atr -> bars whose guard becomes satisfiable, R per target, toll:
 stop_atr  passes   share  R@target1  toll_R@atr%med
     1.25       0    0.0%      2.000          0.2714
      1.5       0    0.0%      1.667          0.2261
     1.75       0    0.0%      1.429          0.1938
        2       0    0.0%      1.250          0.1696
     2.25       1    7.1%      1.111          0.1508
      2.5       1    7.1%      1.000          0.1357
        3       5   35.7%      0.833          0.1131
```

A alternativa do brief (`squeeze_window_bars` para baixo) foi medida nas **mesmas 14 barras**, com os
auxiliares congelados da própria versão (`_min_previous_low`, `_true_ranges`, `aggregate`,
`wilder_atr`, `median` — nada reimplementado):

```
$ ssh hunter-vps 'docker exec -i hunter-strategy-worker-1 python - --ledger /tmp/t33f-explain-breakout-v1.jsonl --version breakout:v1' < base_width.py
base distance in ATR by squeeze_window_bars (distance / compression ratio):
  N     min  median     max  ratio_med  ratio<=0.75
  2   1.393   2.663   4.973      0.844       5/14
  3   1.393   2.841   5.163      0.660      10/14
  4   1.393   2.899   5.217      0.644      10/14
  5   1.840   3.137   5.298      0.654      11/14
  6   2.126   3.176   5.474      0.684      11/14
  8   2.194   3.344   5.583      0.682      14/14
```

**Conclusão da medição:** a base não é larga por causa da janela — é larga porque o rompimento
acontece vários ATR acima de qualquer mínima recente. Encurtar a janela para 2 barras ainda exigiria
`stop_atr` > 2,66 na mediana **e** mudaria a população (a compressão deixa de ser observada em 9 das
14). Sobra `stop_atr`, no primeiro passo de 0,25 ATR acima da mediana medida: **3,5**.

### 3. `--supersede` — a via que o brief pediu, e a recusa

```
$ ssh hunter-vps "docker exec hunter-api-1 python infra/scripts/activate_strategy_version.py breakout v1 --supersede --changelog T3.33f_tentativa_de_aposentar_v1_pela_via_auditada --dry-run"
REFUSED: breakout v1 is already frozen against this code (hunter_core.strategies.breakout_v1@sha256:4c920b0c…64ff1)
```

`--supersede` copia o conteúdo congelado do pai para `v<n+1>` sob um **`code_ref` novo**; é a via de
*código novo*, e recusa por construção quando o código não mudou. Uma variante de **parâmetro** não
cabe nela (e, depois de `derive_variant`, ainda colidiria com a `v2` já existente). Registrado como
CONCERN 2 — nada foi contornado.

### 4. Derivação e ativação da `breakout v2`

```
$ ssh hunter-vps "docker exec -i hunter-api-1 python - breakout v1 --set stop_atr=3.5 --changelog '…' --dry-run" < infra/scripts/derive_variant.py
derivaria breakout v2 de v1 (purpose research_only, draft, nada ativado) em code_ref
hunter_core.strategies.breakout_v1@sha256:4c920b0cc412429c2c4a6a19ca389aca8a215a638f0ff750a8caf61b16264ff1:
stop_atr 1.25 -> 3.5 [params_hash 0e6abf1114cb]

$ ssh hunter-vps "date -u; docker exec -i hunter-api-1 python - breakout v1 --set stop_atr=3.5 --changelog '…'" < infra/scripts/derive_variant.py
Tue Sep  8 17:33:42 UTC 2026
derivada breakout v2 de v1 (purpose research_only, draft, nada ativado) em code_ref …4c920b0c…: stop_atr 1.25 -> 3.5 [params_hash 0e6abf1114cb]

$ ssh hunter-vps "docker exec hunter-api-1 python infra/scripts/activate_strategy_version.py breakout v2 --changelog T3.33f_variante_de_geometria_EXP-0008_ativada_como_pesquisa --dry-run"
would activate breakout v2 (purpose research_only) with code_ref …breakout_v1@sha256:4c920b0c…64ff1 (20 parameters)

$ ssh hunter-vps "date -u; docker exec hunter-api-1 python infra/scripts/activate_strategy_version.py breakout v2 --changelog T3.33f_variante_de_geometria_EXP-0008_ativada_como_pesquisa"
Tue Sep  8 17:35:20 UTC 2026
activated breakout v2 (purpose research_only) at 2026-09-08T17:35:22.628018+00:00 with code_ref …breakout_v1@sha256:4c920b0c…64ff1
```

O `changelog` congelado da `v2` (linhagem legível **e** analisável, lida depois no banco):
`variante de v1 | derived_from=v1 | overrides=stop_atr=3.5 | params_hash=0e6abf1114cb | T3.33f: geometria medida no explain ledger …`.

### 5. Os dois replays da `v2` (uma coorte, duas fatias contíguas)

```
$ ssh hunter-vps "docker exec hunter-strategy-worker-1 python -m hunter_strategy_worker.replay.run --version breakout:v2 \
    --from 2026-08-08 --to 2026-08-23 --markets ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT --workers 3 \
    --cohort replay:0def121f-070b-4ce0-ab14-6bb6b9840faa --dry-run"
{'cohort': 'replay:0def121f-070b-4ce0-ab14-6bb6b9840faa', 'version': 'breakout v2', 'markets': 4, 'bars_planned': 5760, 'workers': 3}

$ … (sem --dry-run, --ledger /tmp/t33f-replay-breakout-v2-a.jsonl)
{'run_id': '0def121f-…', 'version_label': 'breakout v2', 'window_from': '2026-08-08T00:00:00+00:00',
 'window_to': '2026-08-23T00:00:00+00:00', 'market_count': 4, 'bars_evaluated': 5760, 'signals': 1,
 'outcomes_resolved': 1, 'outcomes_open': 0, 'seconds': 91.065, 'bars_per_second': 63.25,
 'decision_lag_s': 2, 'workers': 3,
 'evaluations_by_state': {'unavailable': 448, 'not_triggered': 5310, 'triggered': 1, 'rejected': 1}, 'errors': 0}

$ … --from 2026-08-23 --to 2026-09-08 … --ledger /tmp/t33f-replay-breakout-v2-b.jsonl
{'bars_evaluated': 6144, 'signals': 8, 'outcomes_resolved': 8, 'outcomes_open': 0, 'seconds': 105.03,
 'bars_per_second': 58.5, 'evaluations_by_state': {'not_triggered': 6132, 'triggered': 7, 'rejected': 5}, 'errors': 0}
```

**Atenção ao denominador (mesma armadilha da T3.33e):** `signals`/`outcomes_resolved` do recibo são
contados **da coorte inteira**, então `1` na fatia A e `8` na fatia B **não somam**: a população final
da coorte é **8 decisões**, confirmada por consulta às linhas.

Recibos em `replay_runs` (lidos do banco):

```
coorte | versao | de | ate | mercados | bars | signals | outcomes | open | seg | workers | lag | estados | erros
replay:0def121f-070b | breakout v2 | 2026-08-08 | 2026-08-23 | 4 | 5760 | 1 | 1 | 0 | 91.1 | 3 | 2 | {"rejected":1,"triggered":1,"unavailable":448,"not_triggered":5310} | 0
replay:0def121f-070b | breakout v2 | 2026-08-23 | 2026-09-08 | 4 | 6144 | 8 | 8 | 0 | 105.0 | 3 | 2 | {"rejected":5,"triggered":7,"not_triggered":6132} | 0
```

`system_events` da janela (componentes `activate_strategy_version` e `replay_engine`):

```
warning | activate_strategy_version | strategy_version_activation_refused | breakout v1 is already frozen against this code (…4c920b0c…) | 2026-09-08 17:32:58.517154+00
info    | activate_strategy_version | strategy_version_variant_derived     | breakout v2 derived from v1 (variante, purpose research_only) code_ref=…4c920b0c… | 2026-09-08 17:33:44.012961+00
info    | activate_strategy_version | strategy_version_activated           | breakout v2 (purpose research_only) activated with its already-copied code_ref=…       | 2026-09-08 17:35:22.628018+00
info    | replay_engine             | replay_run_finished                  | replay breakout v2 4 mercados 2026-08-08…2026-08-23: 5760 barras, 1 sinais, 1 desfechos, 91.065 s | 2026-09-08 17:41:13.135635+00
info    | replay_engine             | replay_run_finished                  | replay breakout v2 4 mercados 2026-08-23…2026-09-08: 6144 barras, 8 sinais, 8 desfechos, 105.03 s | 2026-09-08 17:46:33.444368+00
```

**Isolamento (a coorte é a cerca, e ela segurou):**

```
outbox_com_coorte | sinais_coorte | sinais_v2_fora_da_coorte | slots
                0 |             8 |                        0 |     4
```

### 6. Terceira contagem das mesmas barras: o livro-razão da `v2`

```
$ … explain_pass.py --version breakout:v2 --markets ETHUSDT,SOLUSDT   → bars 5952, {"unavailable":224,"not_triggered":5722,"triggered":3,"rejected":3}
$ … explain_pass.py --version breakout:v2 --markets XRPUSDT,DOGEUSDT  → bars 5952, {"unavailable":224,"not_triggered":5720,"triggered":5,"rejected":3}
$ … analyze_geometry.py /tmp/t33f-explain-breakout-v2.jsonl 3.5
{"bars": 11904, "states": {"unavailable": 448, "not_triggered": 11442, "triggered": 8, "rejected": 6},
 "reasons": {"warmup": 448, "not_compressed": 9816, "no_breakout": 1575, "rvol_low": 25,
             "atr_out_of_range": 26, "signal": 8, "geometry_invalidation": 6}}
distribution … n = 6   min 3.571   p25 4.100   median 4.307   p75 4.676   max 5.583
```

Idêntico, estado por estado, à soma dos dois recibos do replay. E os motivos anteriores à geometria
(`not_compressed` 9 816, `no_breakout` 1 575, `rvol_low` 25, `atr_out_of_range` 26, `warmup` 448) são
**os mesmos da `v1`**, como tem de ser: `stop_atr` só é lido depois das quatro portas de entrada.

### 7. Capacidade — 25 min de vigia com 7 versões vivas

```
$ ssh hunter-vps 'docker exec hunter-strategy-worker-1 python -c "… load_active_versions …"'
1 breakout v1 research_only 15m ceed5b7c0580
2 breakout v2 research_only 15m 0e6abf1114cb
3 mean_reversion v1 research_only 15m 8918b39b73fb
4 momentum v3 paper 15m 40e1688e6b5f      <- paper primeiro dentro da chave
5 momentum v2 research_only 15m 40e1688e6b5f
6 momentum v4 research_only 15m 46635ed2bff2
7 volume_anomaly v2 research_only 5m fa5dce78173b

monitored_perp | versions_active
           200 | 7
```

| relógio (UTC) | `evaluated_bars` | `last_iteration` | `outbox_lag_s` | `outbox_pending` | `errors` |
|---|---:|---|---:|---:|---:|
| 17:37:31 | 3 937 | 17:37:04 | 0,0 | 0 | 0 |
| 17:41:51 | 5 053 | 17:41:04 | 0,0 | 0 | 0 |
| 17:59:04 | 7 861 | 17:59:04 | 0,0 | 0 | 0 |

Sem erro, sem `unrunnable`, `outbox_lag_s` 0 o tempo todo, `/ready` 200 em toda a janela, e a
`momentum v3` (paper) continua **antes** das irmãs de pesquisa no roster. Os replays rodaram dentro
do orçamento (3 de 12 vCPU) sem degradar a faixa viva.

### 8. `session_orb` — a parada

```
$ … roquery.py "select s.key, v.version, v.status, v.purpose, v.activated_at, … from strategy_versions v join strategies s …"
breakout       | v1 | active     | research_only | 2026-09-08 16:23:39 | stop_atr 1.25
breakout       | v2 | active     | research_only | 2026-09-08 17:35:22 | stop_atr 3.5
derivatives    | v1 | draft      | research_only |                     |
ensemble       | v1 | draft      | research_only |                     |
mean_reversion | v1 | active     | research_only | 2026-09-08 16:32:33 | stop_atr 1
momentum       | v1 | deprecated | research_only | 2026-09-06 03:36:36 |
momentum       | v2 | active     | research_only | 2026-09-08 04:33:56 |
momentum       | v3 | active     | paper         | 2026-09-08 05:57:30 |
momentum       | v4 | active     | research_only | 2026-09-08 13:05:13 |
narrative      | v1 | draft      | research_only |                     |
order_flow     | v1 | draft      | research_only |                     |
volume_anomaly | v1 | deprecated | research_only | 2026-09-06 03:36:47 |
volume_anomaly | v2 | active     | research_only | 2026-09-08 04:32:42 |
(13 rows)
```

**Não há linha `session_orb`.** O brief manda parar e reportar — parei **antes** do `--dry-run` (que
só produziria uma recusa gravada em `system_events`, ruído sem informação nova). O código está na
imagem (`import ok session_orb_v1 v1`); o que falta é o catálogo. Comando do operador, uma linha:

```
docker exec hunter-api-1 python infra/scripts/seed.py
```

## TABELAS — a avaliação da `breakout v2`

### As 8 decisões (todas `terminal`, cobertura de `R_net` 100 %)

| mercado | decisão (UTC) | resultado | ATR% | `squeeze_ratio` | rvol | R bruto | R ex-funding | R líquido |
|---|---|---|---:|---:|---:|---:|---:|---:|
| SOLUSDT | 2026-08-19 21:00 | alvo | 0,6186 | 0,653 | 14,31 | +0,6421 | +0,5543 | **+0,5543** |
| SOLUSDT | 2026-08-23 11:30 | alvo | 0,5935 | 0,692 | 2,32 | +0,6296 | +0,5389 | **+0,5389** |
| XRPUSDT | 2026-08-23 21:30 | stop | 0,9576 | 0,710 | 1,55 | −0,9828 | −1,0391 | **−1,0419** |
| XRPUSDT | 2026-08-24 11:45 | invalidada | 0,8620 | 0,739 | 2,17 | −0,9235 | −0,9924 | **−0,9959** |
| SOLUSDT | 2026-08-26 21:15 | alvo | 0,5007 | 0,750 | 1,75 | +0,6624 | +0,5532 | **+0,5532** |
| XRPUSDT | 2026-08-27 08:15 | alvo | 0,6013 | 0,672 | 5,09 | +1,0299 | +0,9186 | **+0,9186** |
| DOGEUSDT | 2026-08-31 05:30 | horizonte | 0,5664 | 0,693 | 3,64 | +0,0060 | −0,0931 | **−0,0956** |
| DOGEUSDT | 2026-09-06 03:45 | stop | 0,5404 | 0,708 | 3,45 | −0,9678 | −1,0741 | **−1,0794** |

### Agregados

| recorte | n | R bruto médio | custo R médio | R líquido médio | soma líquida | acerto | PF |
|---|---:|---:|---:|---:|---:|---:|---:|
| **total** | 8 | +0,0120 | 0,0912 | **−0,0810** | **−0,6479** | 50,0 % | **0,798** |
| alvo | 4 | +0,7410 | 0,0998 | +0,6412 | +2,5650 | — | — |
| stop | 2 | −0,9753 | 0,0813 | −1,0607 | −2,1213 | — | — |
| invalidada | 1 | −0,9235 | 0,0689 | −0,9959 | −0,9959 | — | — |
| horizonte | 1 | +0,0060 | 0,0991 | −0,0956 | −0,0956 | — | — |

O custo médio medido (0,0912 R) fecha com a identidade da T3.32 (`custo_R = 0,0020 / risco%`) no
ATR% mediano das decisões: `0,0020 / (3,5 × 0,005974) = 0,096 R`.

### Banda de ATR do revisor e bucket de compressão

| recorte | n | faixa | R bruto médio | R líquido médio | soma líquida | acerto |
|---|---:|---|---:|---:|---:|---:|
| ATR% em [0,0050 ; 0,0059) | 3 | 0,5007–0,5664 | −0,0998 | **−0,2073** | −0,6218 | 33,3 % |
| ATR% fora da banda | 5 | 0,5935–0,9576 | +0,0791 | −0,0052 | −0,0260 | 60,0 % |
| `squeeze_ratio` < 0,70 | 4 | 0,653–0,693 | +0,5769 | **+0,4790** | +1,9161 | 75,0 % |
| `squeeze_ratio` 0,70–0,75 | 4 | 0,708–0,750 | −0,5529 | **−0,6410** | −2,5640 | 25,0 % |

Com n = 3 e n = 4 nada disso é evidência; é a única direção que a amostra permite apontar, e está
registrada como hipótese (um `squeeze_max` menor), não como achado.

### Registro de Tentativas — carimbos desta tarefa

| Quando (UTC) | Quando (BRT) | O quê |
|---|---|---|
| 2026-09-08 17:32:58 | 14:32:58 | `--supersede` da `breakout v1` **recusado** (código não mudou) |
| 2026-09-08 17:33:44 | 14:33:44 | `breakout v2` derivada (`stop_atr` 1,25 → 3,5, `params_hash 0e6abf1114cb`) |
| 2026-09-08 17:35:22 | 14:35:22 | `breakout v2` **ativada** (`research_only`) |
| 2026-09-08 17:41:13 | 14:41:13 | replay `v2` fatia A (2026-08-08→08-23) concluído |
| 2026-09-08 17:46:33 | 14:46:33 | replay `v2` fatia B (2026-08-23→09-08) concluído |
| 2026-09-08 17:36 | 14:36 | `session_orb` **não** ativada: chave ausente em `strategies` |

## VEREDITOS

1. **`--explain-ledger` entregue e provado localmente**, incluindo a prova de não-antecipação **com
   contraprova**. Ainda **não roda na VPS** porque a imagem publicada é anterior; a medição que ele
   existia para permitir foi feita mesmo assim, por leitura, e a equivalência com os recibos do
   replay foi conferida três vezes (v1 e v2). No próximo deploy o comando passa a ser
   `--explain-ledger /tmp/x.jsonl` e o script de scratchpad deixa de ser necessário.
2. **`breakout v2`: `inconclusivo`, recomendação `descartar`.** K1 dispara (8 < 20 decisões) e o
   critério específico da versão também (6/14 = 42,9 % ainda recusadas por geometria). Mas — e este é
   o ganho da tarefa — **a hipótese passou a ser testável** e respondeu: bruta +0,0120 R (praticamente
   zero) contra um pedágio de 0,0912 R, ou seja **líquida −0,0810 R por operação**, exatamente o
   mecanismo da KB-0076. A população não é pequena por causa da guarda de invalidação (essa foi
   consertada); é pequena porque **82,5 % das barras nunca chegam comprimidas**.
3. **A troca de geometria foi paga como previsto.** `stop_atr` 3,5 baixou o pedágio de 0,32 R para
   0,11 R e baixou o alvo de 2,0 R para 0,714 R; o acerto de equilíbrio subiu de 44 % para 64 % e a
   amostra entregou 50 %. Declarado **antes** do replay, confirmado depois.
4. **`breakout v1` deve ser aposentada e hoje não há via auditada para isso** (CONCERN 2). Enquanto
   não houver, ela custa 200 avaliações por fechamento de 15 min por nada.
5. **`session_orb v1` não entrou no Lab**; a parada é do brief e o desbloqueio é uma linha do
   operador.
6. **Nenhuma escrita fora do previsto**, nenhuma linha de outbox para a coorte, nenhum sinal da `v2`
   fora dela, `paper` continua avaliada primeiro, `outbox_lag_s` 0 durante toda a janela.

## Segunda opinião (Astra)

`bash infra/scripts/astra.sh ask T3.33f-ledger …` (revisão do diff; transcrição em
`.claude/state/astra-review-T3.33f-ledger.md`). Ela não rodou testes — sessão de leitura.

| O que ela levantou | O que fiz |
|---|---|
| **must-fix 1** — se um processo do pool falhar, `gather` propaga e o merge não acontece; uma retomada com o mesmo caminho trunca os shards (`"w"`) | **Rejeitado com razão declarada.** O shard sobrevive à falha (fica no disco) e a retomada **reescreve** exatamente as mesmas linhas: um replay é determinístico por construção (mesma versão, mesmas velas, mesmo corte), então o que a retomada trunca é uma cópia idêntica à que vai gravar. Preservar tentativa por tentativa criaria arquivos que ninguém sabe qual ler |
| **must-fix 2** — não apagar shards antes de confirmar a gravação; validar a contagem | **Aceito, os dois.** `merge_shards` agora só apaga **depois** de fechar o livro-razão (teste novo: um destino que não abre mantém os shards intactos), e `merge_markets` compara `linhas` com `bars_evaluated` e loga `replay_explain_ledger_incomplete` em nível **warning** quando diferem |
| **nice-to-have** — a mutação de não-antecipação começa 5 min depois do corte, deixando a fronteira sem cobertura | **Aceito.** `FUTURE_FROM` passou a ser o **próprio corte** (`TRIGGER_BAR`): o minuto que abre no corte já é futuro para a barra sob teste. Os três testes continuam passando, agora cobrindo a fronteira |
| **nice-to-have** — testar várias barras e vários cortes numa janela maior | **Não feito nesta tarefa.** A janela de uma barra é o que torna a diferença inequívoca; com a hora inteira as barras posteriores leem legitimamente as velas reescritas (medi: foi assim que o primeiro rascunho deste teste falhou). Um teste com prefixo comparado é trabalho próprio, e fica anotado |
| **concorda** — reusar a mesma `Evaluation` para contador e diagnóstico; a contraprova do corte antecipado | — |

## CONCERNS

1. **O livro-razão não está na imagem da VPS.** `--explain-ledger` é código desta tarefa e não foi
   commitado (o brief proíbe commit). Para não quebrar a identidade "imagem publicada = código
   auditado", **não** copiei arquivo nenhum para dentro de container: a medição saiu de um script de
   leitura que chama a **mesma** `Strategy.explain` sobre o **mesmo** contexto, em transação
   `READ ONLY`, e a equivalência foi conferida contra os recibos (11 904 barras, mesmos quatro
   estados, três vezes). O risco residual é o de sempre com dois caminhos: eles coincidem hoje. Some
   quando o commit virar imagem.
2. **Não existe via auditada para aposentar uma versão substituída por parâmetro.**
   `activate_strategy_version.py --supersede` só serve para `code_ref` novo (recusou por isso, com
   recibo). Consequência medida: `breakout v1` e `v2` avaliam as mesmas 200 barras a cada 15 min e a
   `v1` já está condenada por K1 desde a T3.33e. **Pedido:** um brief pequeno para um
   `--deprecate <key> <version> --changelog …` (ou aceitar em `--supersede` um sucessor derivado por
   parâmetro), com recibo em `system_events` como todo o resto. Não improvisei nada.
3. **`unavailable` na faixa viva está alto e não foi atribuído.** Desde o restart das 17:04 o
   heartbeat acumulou 2 030 `unavailable` em 7 861 avaliações (25,8 %), enquanto o replay das mesmas
   estratégias fica em 3,76 %. A causa mais provável está medida pela metade: `market.universe.changed`
   é publicado **a cada 15 min** (17:22:21, 17:37:22, 17:52:24, sempre um mercado entrando e outro
   saindo), e `eligibility.universe_changed_after` transforma em `unavailable` toda avaliação de uma
   barra anterior à mudança. Se for isso, a faixa prospectiva está perdendo uma fração grande das
   avaliações **por construção**, e nenhuma versão nova conserta. Não confirmei a atribuição (o
   contador não guarda o motivo) e não mexi em nada: fica como pedido de medição própria.
4. **Amostra minúscula.** 8 decisões, 7 dias distintos, 4 mercados. Nenhum recorte desta página
   (banda de ATR, bucket de compressão, por resultado) tem poder estatístico; todos estão aqui porque
   o brief e o revisor pediram o recorte, e todos estão rotulados como direção, não como achado.
5. **`seed.py` continua sem `--dry-run`** (CONCERN 1 da T3.33e, ainda aberto). É o que impede este
   agente de destravar a `session_orb` sozinho — e é a trava certa: o seed escreve em oito tabelas de
   referência sem portão.
6. **A `v2` nasceu com alvo menor que o stop** (2,5 ATR contra 3,5 ATR). A tabela `CONSTRAINTS` de
   `breakout_v1` não ordena `stop_atr` contra `target_atr`, então nada recusou — e, para o
   experimento, era o ponto: medir o preço da guarda. Mas uma `v3` que mantenha essa assimetria
   invertida deveria ser recusada no portão C1–C8, não no replay.
