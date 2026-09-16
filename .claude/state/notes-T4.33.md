# Notas T4.33 — a série de 15 s segue a moeda fixada além de 300 s; o fecho rotula `series_ended` (16/09/2026)

Execução backend-specialist. Brief inline (sem arquivo `brief-T4.33-*.md`). Sem commit; sem deploy; sem push;
`.env*` intocado; Docker em pé, testes com Postgres reais rodados em primeiro plano. Não toquei
`services/meme-worker/hunter_meme_worker/{lab_models,proposals,proposals_reasons,lab_repo_e2b}.py`,
`packages/indicators/hunter_indicators/meme/pedigree_e2b.py`, migração `0044`,
`packages/core/tests/integration/test_migrations.py`, `packages/risk-core/**`, `services/meme-executor/**`,
`.claude/launch.json`, `docs/DESIGN.md`, `packages/core/tests/unit/test_settings.py` (outros agentes/HEAD).

## Desenho (decisões)

1. **`young_mints` ganha `pinned_max_age_s`** (`fast_lane.py`): reusa `tracker.pinned` (já existe desde T4.16b —
   nenhuma query nova, é um `frozenset` em memória). Um mint pinado (aposta de papel aberta, posição real aberta
   ou proposta pendente) fica na via rápida até `pinned_max_age_s` (novo `MemeConfig.fast_lane_pinned_max_age_s`,
   env `MEME_FAST_LANE_PINNED_MAX_AGE_S`, default 1800) em vez do teto de 300 s (`fast_lane_max_age_s`) que
   continua valendo para o resto. `pinned_max_age_s=None` (default do parâmetro) preserva o comportamento antigo
   para quem não passar o argumento. Heartbeat novo: `fast_lane_pinned_mints` (quantos do `fast_lane_mints` estão
   lá só por pin), via `SourcesState.record_fast_cycle(..., pinned=N)`.
2. **`sources.py`/`config.py` já estavam quase no teto de 350 linhas** (349/342 antes de mim) — toda edição
   precisou vir com um corte equivalente em algum docstring próximo (reembalado, nunca removido de conteúdo
   factual) para caber. `check_file_size.py` confirmou 350/350/281 (`sources.py`/`config.py`/`fast_lane.py`) ao
   final — sem baseline, o orçamento é o limite real.
3. **Achado ao ler o CHECK real:** `meme_paper_bets.outcome_quality_reason` é `Text` livre — **não** há CHECK
   enumerando valores (só `outcome_quality IN ('measured','indeterminate')` tem CHECK). O brief previa migração
   `0045` só *se* houvesse um CHECK de motivos; como não há, **nenhuma migração foi criada** — decisão registrada
   aqui em vez de inventar um CHECK que o schema nunca teve. Isso também evita qualquer conflito com a `0044`/
   `test_migrations.py` em voo por outro agente.
4. **Novo script auditado `infra/scripts/meme_reclassify_series_ended.py`**, irmão do
   `meme_reclassify_indeterminate.py` (T4.16): candidato = fecho `time_stop`/`measured` sem nenhuma linha de
   `meme_features_1m` precificada (`mcap_sol IS NOT NULL`) mais de 90 s depois do `exit_at` dentro dos 35 min
   seguintes (definição exata da KB-0113 §2). `--apply` grava `outcome_quality = indeterminate`,
   `outcome_quality_reason = 'series_ended'` — **nome fixo**, não frase (o gêmeo mecânico do
   `no_snapshot_in_window` do laço), porque o critério é a query, não um julgamento — por isso não pede
   `--reason` do operador como o script de `rug_no_snapshot` pede. Dry-run por padrão; `--day`/`--bet-id`
   reaplicam sobre dias já fechados (o "re-run" que o brief pedia).
5. **Achado que quase virou bug: `now()` no lugar errado.** A primeira versão da query filtrava
   `now() >= exit_at + 35 min` — correto em produção, mas **falso positivo garantido em qualquer teste com dado
   fictício no futuro** (esta árvore usa `2026-10-05` em fixtures enquanto o relógio real da máquina é
   `2026-09-16`): o `now()` do Postgres nunca teria "passado" da data fictícia, e a suíte só pegou o problema
   porque eu rodei o teste de Postgres **antes** de adicionar a guarda e **depois**. Corrigido para um parâmetro
   ligado (`:as_of`, default `utcnow()` do chamador) — nunca `now()` do SQL — exatamente para isto: o cron real
   passa o instante real, o teste passa o instante fictício da fixture, e um fecho `time_stop` nos últimos 35 min
   do dia (o cron roda às 00:10 BRT) não pode ser rotulado antes do tempo real ter passado.
6. **Cron (`infra/vps/meme_close_nightly.sh`):** um passo novo, `meme_reclassify_series_ended.py --day <dia>
   --apply`, roda **antes** de `meme_close_day.py` — só assim a seção 6 do diário e as notas de
   `meme_render_bets.py` já nascem com o motivo separado, sem precisar reabrir um dia já fechado (a seção 6
   nunca se reescreve). Falha do passo de rótulo não trava o fechamento (`set +e`, `rc` só do close). Não
   apliquei/testei contra a VPS — só editei o arquivo do repositório.
7. **Fechamento diário mostra a quebra por motivo.** `meme_close_queries._INDETERMINATE` passou de `count(*)`
   para `GROUP BY outcome_quality_reason`; `CloseInputs.indeterminate_by_reason: Mapping[str,int]` novo;
   `meme_close_render._indeterminate_line` renderiza "indeterminadas (...): N (`rug_no_snapshot` X,
   `series_ended` Y)". `meme_render_bets_notes.py`: a tabela de apostas por dia passou de "(indeterminada)" fixo
   para "(indeterminada: {motivo})", mostrando o valor real (`no_snapshot_in_window` ou `series_ended`).

## Comandos e saídas (reais)

```
$ timeout 120 uv run pytest services/meme-worker/tests/test_fast_lane.py -q          → 6 passed (3.3s)
$ timeout 280 uv run pytest services/meme-worker/tests -q -m "unit and not live"     → 269 passed, 97 deselected
$ timeout 120 uv run pytest infra/scripts/tests/test_meme_ops_scripts.py -q          → 10 passed
$ timeout 120 uv run pytest infra/scripts/tests/test_meme_close_render.py infra/scripts/tests/test_meme_close_lessons.py \
      infra/scripts/tests/test_meme_close_day.py -q                                  → 15 passed
$ timeout 120 uv run pytest infra/scripts/tests/test_meme_render_bets.py -q          → 10 passed, 2 skipped (matplotlib)
$ timeout 590 uv run pytest infra/scripts/tests/test_meme_close_day_integration.py -q -k series_ended   → 1 passed (18.7s, Postgres real)
$ timeout 590 uv run pytest infra/scripts/tests/test_meme_render_bets_integration.py -q                  → 3 passed (24.5s, Postgres real)
$ timeout 280 uv run pytest infra/scripts/tests -q -m "unit and not live"            → 11 failed (pré-existentes, ver "Achados fora do escopo"), 120 passed
$ timeout 120 uv run ruff check <15 arquivos meus>                                    → All checks passed!
$ timeout 120 uv run ruff format --check <15 arquivos meus>                           → todos já formatados
$ timeout 280 uv run pyright <arquivos de produção + testes meus>                     → 0 errors, 0 warnings, 0 informations
$ timeout 120 uv run python infra/scripts/check_file_size.py                         → 904 arquivos, 1 acima do orçamento
                                                                                          (meme_rule_set.py, não é meu)
$ bash -n infra/vps/meme_close_nightly.sh                                            → OK
```

Não rodei a suíte completa `services/meme-worker/tests infra/scripts/tests -q -x -m "not live"` porque `-x`
pararia no primeiro dos 11 falhos pré-existentes (import quebrado de `meme_rule_set_history`, T4.35 em voo) e
no teste de vault-lint que corre risco de correr com escrita concorrente de outro agente no
`obsidian/09-OPERATIONS/Diario/2026-09-16.md` (visto uma vez, ausente na segunda rodada) — reportado abaixo, não
é meu.

## Achados fora do escopo (não corrigidos — não são meus)

- `infra/scripts/meme_rule_set.py` importa `meme_rule_set_history` (T4.35 no próprio docstring do arquivo), que
  não existe ainda: quebra 11 testes de `infra/scripts/tests` (`test_meme_event_rematch.py`,
  `test_meme_ops_mayhem.py`, `test_meme_ops_scripts.py::test_deprecate_*`) e deixa `meme_rule_set.py` em
  381/350 linhas no `check_file_size.py`. Confirmado que nenhum é meu (nenhum dos meus `test_series_ended_*`/
  `test_reclassify_*` está na lista de falhos).
- `test_meme_close_day_integration.py::test_apply_closes_the_day_into_a_copy_of_the_vault_that_lints_clean_and_refuses_twice`
  falhou uma vez com "faltam: updated" em `obsidian/09-OPERATIONS/Diario/2026-09-16.md` — arquivo com `git status`
  modificado (outro agente escrevendo nele nesse instante); rodado de novo isoladamente, passou. Race de árvore
  compartilhada, não uma regressão minha (o arquivo não é da Diario-**Meme**, é o diário geral de operações).

## Suposições e decisões que o pedido não fixa

- Sem migração `0045`: `outcome_quality_reason` nunca teve CHECK de valores — a condição do brief ("se houver
  CHECK") não se aplica. Se algum dia um CHECK for adicionado, `series_ended` precisa entrar nele junto com
  `no_snapshot_in_window`/o texto livre do `--reason` humano.
- `series_ended` é gravado como **string fixa**, não uma frase auditada como o `--reason` do
  `meme_reclassify_indeterminate.py` — decisão deliberada (é o "gêmeo mecânico" do `no_snapshot_in_window` do
  laço, não um julgamento humano); `meme_reclassify_series_ended.py` não aceita `--reason`.
- A janela verificada é só `meme_features_1m` (retenção 90 d), nunca `meme_features_15s` (retenção 7 d) — a
  própria KB-0113 mede "fim de série" pela série de 1 min nessa tabela, e usar a de 15 s tornaria o backfill
  impossível além de 7 dias.
- `meme_close_nightly.sh`: o passo novo roda mesmo se `meme_close_day.py` for chamado sem `--day` (usa o mesmo
  "ontem" implícito) — não sincronizei os dois cálculos de dia explicitamente porque os dois scripts calculam o
  mesmo "ontem BRT" de formas equivalentes (um em Python, outro herdando `$DAY` vazio); se algum dia divergirem,
  o `--day` explícito do cron (`meme_close_nightly.sh <dia>`) já cobre os dois com o mesmo valor.

## Arquivos

**Criados:** `infra/scripts/meme_reclassify_series_ended.py`; esta nota.

**Modificados:** `services/meme-worker/hunter_meme_worker/{fast_lane,sources,config}.py`,
`services/meme-worker/tests/test_fast_lane.py`; `infra/scripts/meme_close_{queries,inputs,render}.py`,
`infra/scripts/meme_render_bets_notes.py`; `infra/scripts/tests/{test_meme_close_render,test_meme_ops_scripts,
test_meme_close_day_integration,test_meme_render_bets}.py`; `infra/vps/meme_close_nightly.sh`;
`docs/{RISK_ENGINE_MEME,DATABASE,DEPLOYMENT}.md`.
