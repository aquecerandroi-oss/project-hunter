# T3.88 — `breadth_v2`: a série de amplitude segue o universo sombra (16 mercados com ≥ 90 d)

Quant-engineer, 2026-09-11, 06:10–09:23 BRT (09:10–12:23 UTC). **Nada commitado, nada tocado na
VPS.** Brief salvo verbatim em `.claude/state/brief-T3.88-amplitude-no-universo-de-16.md`.

## 1. O que mudou, em uma frase por peça

| peça | antes | agora |
|---|---|---|
| regra de pertencimento | escrita **duas vezes** (`hunter_strategy_worker.universe` para o universo sombra; um predicado SQL em `breadth_repo` para o produtor) | **uma vez**, em `packages/core/hunter_core/universe.py`, importada pelos dois workers (o scanner nunca importa o pacote do strategy-worker) |
| série | `breadth_v1` = ~200 perpétuas monitoradas | **`breadth_v2`** = as 16 com ≥ 90 d de velas 1 min; `BreadthSpec` liga versão ↔ universo (`packages/indicators/hunter_indicators/breadth/spec.py`) |
| universo na consulta do produtor | sub-select repetido no SQL | lista explícita de ids (`market_id = ANY(:market_ids)`) — texto SQL constante, universo decidido pelo chamador |
| portão | `load_breadth_gate(..., version=BREADTH_VERSION)` (constante de módulo) | `version` é **campo obrigatório da política** (`breadth_policy.py`); sem ele a política é recusada, nunca completada com o padrão do build |
| escrita do backfill | 1 `INSERT` por minuto | 1 statement por lote (insertmanyvalues); mesma semântica `ON CONFLICT DO NOTHING ... RETURNING id` |
| `inputs` da linha | `exchange`, `min_coverage`, `window_minutes` | + `universe_rule`, `universe_as_of` |

`min_history_days` de v2 é **90 congelado na versão da série**, não lido de
`SHADOW_UNIVERSE_MIN_HISTORY_DAYS`: o env é um botão operacional do portão de despacho (um operador
pode pôr `0`) e uma série já gravada não pode mudar de significado porque alguém mexeu num botão. A
**regra** é compartilhada; o **número** é propriedade da versão. Declarado no docstring de
`hunter_core.universe` e em `spec.py`.

## 2. Duas consequências que precisam de olho

1. **O universo sombra estreitou de propósito.** A regra compartilhada exige `markets.status =
   'active'`; a consulta da T3.82 não tinha essa cláusula e a do `breadth_v1` tinha. Ficou a mais
   estrita das duas. Efeito prático: uma perpétua monitorada e **suspensa** sai do universo sombra e
   do denominador — `universe_total` no heartbeat pode reportar um punhado menos que 200. Uma
   suspensa não imprime vela (só baixaria cobertura) e não passaria o funil de replay, então isto é
   correção, mas é **mudança de comportamento de um worker vivo** e está escrita em
   `universe.load_universe_snapshot`, em `docs/PIPELINE.md` §6b e aqui.
2. **`--apply` era 100× mais lento do que precisava.** Medido em testcontainer: 1 440 linhas em
   **67,1 s** (21 linhas/s) → ~100 min para os 129 600 minutos, tudo em round-trips. Depois de
   trocar o laço por um `insert().returning()` sobre a lista de parâmetros: 1 440 linhas em **2,2 s**
   → **~3,4 min** extrapolados. A idempotência não mudou (mesma constraint, mesmo `DO NOTHING`,
   mesma contagem por `RETURNING`).

## 3. Prontidão do backfill (medido local, extrapolado para 90 d)

`infra/scripts/tests/test_backfill_breadth_plan.py` — 16 mercados com 90 d de histórico + 4 sem
(os ~184 da produção), velas densas semeadas por `generate_series`, relógio do script fixado na
meia-noite UTC para o relatório não depender da hora em que a suíte roda.

```
[T3.88] minutos dobrados em 3 dias: ~4320
[T3.88] duração medida: 2.3 s (0.8 s/dia)
[T3.88] extrapolação para 90 dias (129 600 min): 1.1 min
[T3.88] --apply de 1 dia: 1440 linhas em 2.2 s
[T3.88] extrapolação de --apply para 129 600 min: 3.4 min
4 passed in 28.83s
```

- **Linhas esperadas:** 90 × 1 440 = **129 600** (a janela `[cut − 90 d, cut]` inclusive são 129 601
  minutos; o número do brief, 129 600, é o dos 90 dias fechados).
- **Universo:** 16 → piso de 80 % = **13 mercados densos por minuto** (o relatório imprime).
- **NÃO rodado na VPS.** O orquestrador implanta e roda `compose.sh run --rm ops python
  infra/scripts/backfill_breadth.py --days 90` (relatório primeiro; `--apply --reason` depois).

## 4. Comandos e saídas (todos em primeiro plano, `timeout 290`)

```
uv run ruff check .                     -> All checks passed!
uv run ruff format --check .            -> 10 files would be reformatted (NENHUM meu: backfill_funding.py,
                                           request_backfill.py, test_request_backfill.py, 3 notas do obsidian,
                                           test_settings.py, funding_announce.py, test_funding_backfill.py,
                                           KB-0036 — trabalho de outro agente na árvore compartilhada)
uv run pyright <os 9 módulos da tarefa> -> 0 errors, 0 warnings
uv run pyright                          -> 22 errors, todos em 8 arquivos que esta tarefa não tocou
                                           (test_lab_signals_pagination_api, test_risk_limits_api,
                                            test_render_operations, test_mean_reversion_v1, test_no_lookahead,
                                            test_replay_drain_pause, test_replay_role_guard, test_replay_stress)
uv run python infra/scripts/check_file_size.py -> scanned 633 files; 0 over budget, 0 grandfathered
```

```
uv run pytest packages/indicators/tests/unit/test_breadth_spec.py \
              packages/core/tests/unit/test_universe_history.py \
              packages/indicators/tests/unit/test_breadth_series.py \
              services/strategy-worker/tests/test_universe.py -q
-> 38 passed in 1.99s

uv run pytest services/strategy-worker/tests/test_breadth_gate_policy.py -q
-> 48 passed in 0.98s

uv run pytest services/scanner-worker/tests/test_breadth_job.py -q          (testcontainer, 1 arquivo)
-> 11 passed in 55.61s

uv run pytest services/strategy-worker/tests/test_breadth_gate.py -q        (testcontainer, 1 arquivo)
-> 10 passed in 60.99s

uv run pytest services/strategy-worker/tests/test_universe_gate.py -q       (testcontainer, 1 arquivo)
-> 1 passed in 26.47s

uv run pytest infra/scripts/tests/test_backfill_breadth.py \
              services/strategy-worker/tests/test_spot_not_in_shadow_universe.py -q
-> 16 passed in 20.15s

uv run pytest infra/scripts/tests/test_backfill_breadth_plan.py -q -s       (testcontainer, 1 arquivo)
-> 4 passed in 28.83s

uv run pytest services/strategy-worker/tests/test_derive_variant.py \
              services/strategy-worker/tests/test_hours_gate_policy.py \
              services/strategy-worker/tests/test_regime_gate_policy.py -q
-> 119 passed in 51.22s

uv run pytest services/strategy-worker/tests/test_bar_context_engine.py \
              services/strategy-worker/tests/test_hours_gate.py -q          (testcontainer)
-> 14 passed in 102.25s

uv run pytest packages/core/tests/integration/test_schema_privileges.py -q -k breadth
-> 6 passed, 43 deselected in 19.05s

uv run pytest -m unit -q -p no:randomly
-> 2 failed, 3317 passed, 3168 deselected in 281.88s
```

**As duas falhas da suíte unitária são pré-existentes e reproduzem sem nenhum arquivo desta
tarefa:**

```
uv run pytest packages/core/tests/unit/test_runtime.py services/scanner-worker/tests/test_load.py -q -m unit
-> 2 failed, 20 passed in 40.25s
   test_role_registry_starts_empty_for_t03  — dependência de ordem: coletar qualquer teste que
       importe um pacote de worker popula `RoleRegistry` (`hunter_scanner_worker/__init__.py` faz
       `RoleRegistry["scanner"] = run_scanner` no import). Passa sozinho.
   test_two_hundred_markets_...budget      — XPASS(strict) do teste de carga da T2.5 (p99 3,23 s
       contra orçamento de 3,0 s), documentado no próprio teste.
```

## 5. Provas novas que valem citar

- **Fronteira do universo (pura, sem banco):** `packages/core/tests/unit/test_universe_history.py` —
  `<=` inclusivo nos 90 d, um segundo a menos fica fora, "sem vela nenhuma" nunca entra, e
  `candidate_keys` nunca encolhe para o conjunto elegível (o denominador do "16 de 200").
- **v1 × v2 separadas (pura):** `packages/indicators/tests/unit/test_breadth_spec.py` — o mesmo
  minuto com os mesmos candles vale **0,8000 usável** num universo de 10 e
  **`insufficient_coverage`** num de 200; janela e piso idênticos nas duas séries (o teste falha se
  alguém mexer no piso "junto").
- **O produtor dobra o universo da série (testcontainer):**
  `services/scanner-worker/tests/test_breadth_job.py::TestOUniversoDaSerie` — um mercado sem 90 d e
  um **um minuto** dentro da fronteira ficam fora e **caem forte** (se entrassem, 0,2500 → 0,5000);
  o piso de 80 % vale sobre os 5 do universo de v2 (3 cobertos = 60 % → inutilizável); e as duas
  séries do **mesmo minuto** coexistem (v1 = 0,6667 sobre 3 mercados, v2 = 0,5000 sobre 2) sem que
  rodar v2 mova uma coluna da linha de v1.
- **A série é parte da chave (testcontainer):**
  `services/strategy-worker/tests/test_breadth_gate.py::TestASerieEParteDaChave` — uma linha de
  `breadth_v1` **dentro da faixa** no minuto em que v2 não tem linha **não** libera a versão presa a
  v2 (continua `breadth_unavailable`). Antes da T3.88 o portão lia a constante de módulo e aquela
  linha teria liberado a barra.
- Os testes antigos de `test_breadth_job.py` passaram a fixar `spec=V1` explicitamente: eles provam
  a aritmética (fração exata, piso, idempotência, não-antecipação, trava, spot fora), que é a mesma
  nas duas séries, e o universo de v2 ganhou classe própria.

## 6. Suposições numéricas que tive de fazer

1. **"16 mercados" não foi remedido.** É a medida da T3.82 na VPS (2026-09-10). O código não fixa 16
   em lugar nenhum — ele fixa a **regra** (≥ 90 d) e o número é o que a regra der no dia. O
   relatório do backfill é quem vai dizer quantos são em 12/09.
2. **Extrapolação de tempo, não medida de 90 dias.** 0,8 s/dia (dry-run) e 2,2 s/1 440 linhas
   (`--apply`) medidos em Docker no Windows sobre 3 dias e 1 dia; ×90 é aritmética, não observação.
   Na VPS (Linux, pooler local) espero mais rápido, mas o número honesto é "1–4 min", não um valor.
3. **129 600 vs 129 601.** `run_breadth_once` dobra `[cut − back, cut]` **inclusive**, então uma
   janela de `--days 90` tem 129 601 minutos. Usei 129 600 (= 90 × 1 440) onde o brief o usa e disse
   a diferença.
4. **Nenhuma política de `breadth` existe gravada.** Procurei em `infra/` (seeds, SQL de pesquisa) e
   nos testes: não há variante com portão de amplitude em lugar nenhum, por isso `version` pôde
   entrar como campo **obrigatório** sem migração de dados. Se aparecer uma linha antiga sem
   `version`, a versão emudece (recusa na leitura da política) — que é a falha fechada correta, e
   está testado.
5. **`universe_as_of` = o instante da passada, não o minuto histórico.** Escolha, não descoberta:
   perguntar "quem tinha 90 dias" a cada corte de 90 dias atrás responderia "ninguém" (a retenção de
   `candles_1m` é de 90 dias). É o que a coluna `universe_size` já documentava ("evidência sobre o
   fold, não sobre aquele minuto histórico").

## 7. EXP-0027 e H-P18

`.claude/state/exp-drafts/EXP-0027-amplitude.md` reescrito: deixou de ser prospectivo-só e virou
teste histórico de 90 d sobre os 16, com o pai `mean_reversion v10` (coorte da EXP-0025: 798
decisões em 89 dias, ex-funding −0,0293 R, IC [−0,1336; +0,0728]), braço A
`breadth=0.10-0.60@breadth_v2`, braço B de falseamento `breadth=0.60-1.00@breadth_v2` (o que a
KB-0083 diz que deveria ser o pior), tercis fixados em **13/06–31/07** só para a leitura descritiva
(as faixas dos braços são as da T3.77 e não saem dos tercis, por isso os braços podem usar os 90
dias inteiros e cumprir as três janelas de 30 d que a régua exige), e a régua da EXP-0026/0028:
**condicional × incondicional**, IC 95 % por blocos de dia (20 000 reamostragens, semente 20260912),
n ≥ 100 e ≥ 30 dias, positiva em 2 de 3 janelas, LOMO nunca negativo, **mais** o Δ pareado por
(mercado, barra) dentro de ±0,02 R como prova de que "o portão é só um portão". K4 lido no pai
(§4b item 12); eixo primário `r_ex_funding` (cobertura de `R_net` da coorte: 37,59 %).

**H-P18 (dispersão BTC × alts) não cabe nesta série, e não inventei um braço para ela.**
`compute_breadth` compara **o próprio** close de cada mercado em duas pontas de 5 min com `<`
estrito: não tem mercado de referência, não tem horizonte de 24 h e não compara retornos. H-P18
precisa dos três. O caminho é uma série nova — `dispersion_24h` = "fração dos 16 cujo retorno de
24 h ficou abaixo do do BTC" — que **reusa sem mudança** `hunter_core.universe` (o universo é o
mesmo) e a forma `BreadthSpec`/`market_breadth` (versão = aritmética + universo). Fica para um lote
posterior; está escrito na EXP-0027 com o custo estimado.

## 8. `git status --porcelain` — só os arquivos desta tarefa

```
 M .claude/state/exp-drafts/EXP-0027-amplitude.md
 M docs/ACTIVATION.md
 M docs/PIPELINE.md
 M infra/migrations/ddl/breadth.py
 M infra/scripts/backfill_breadth.py
 M packages/core/hunter_core/db/models/breadth.py
 M packages/indicators/hunter_indicators/breadth/__init__.py
 M packages/indicators/hunter_indicators/breadth/series.py
 M services/scanner-worker/hunter_scanner_worker/breadth_job.py
 M services/scanner-worker/hunter_scanner_worker/breadth_repo.py
 M services/scanner-worker/tests/test_breadth_job.py
 M services/strategy-worker/hunter_strategy_worker/breadth_gate.py
 M services/strategy-worker/hunter_strategy_worker/universe.py
 M services/strategy-worker/tests/test_breadth_gate.py
 M services/strategy-worker/tests/test_breadth_gate_policy.py
 M services/strategy-worker/tests/test_universe.py
?? .claude/state/brief-T3.88-amplitude-no-universo-de-16.md
?? .claude/state/notes-T3.88.md
?? infra/scripts/breadth_coverage.py
?? infra/scripts/tests/test_backfill_breadth_plan.py
?? packages/core/hunter_core/universe.py
?? packages/core/tests/unit/test_universe_history.py
?? packages/indicators/hunter_indicators/breadth/spec.py
?? packages/indicators/tests/unit/test_breadth_spec.py
?? services/strategy-worker/hunter_strategy_worker/breadth_policy.py
```

`infra/migrations/ddl/breadth.py` e `packages/core/hunter_core/db/models/breadth.py` mudaram **só em
docstring** (referências a `BREADTH_VERSION`, que não existe mais como constante única, e a nota de
que `breadth_version` agora também nomeia o universo). Nenhuma migração nova: `0019` já tem
`breadth_version` na chave única, que é o que permite as duas séries coexistirem.

Outros arquivos aparecem modificados na árvore compartilhada (`.claude/launch.json`, `docs/DESIGN.md`,
`infra/scripts/tests/test_seed_dry_run.py`,
`packages/core/tests/integration/test_schema_seed_and_partitions.py`) e **não são desta tarefa**.
