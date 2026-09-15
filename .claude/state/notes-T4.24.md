# Notas T4.24 — a reincidência do criador (E2 v2, EXP-M6 braço 2) (15/09/2026, 20:5x–21:4x BRT)

Execução backend-specialist. Brief: `.claude/state/brief-T4.24-reincidencia-do-criador.md`. Sem commit; nada real;
`.env*` intocado; `apps/web/**`, `services/meme-executor/**`, `packages/exchange-adapters/**` intocados; nenhum
processo em segundo plano além dos usados só para não travar a ferramenta (`test_migrations.py` completo, que estoura
qualquer `timeout` de primeiro plano — o subconjunto exigido pelo brief rodou em primeiro plano); `obsidian/02-MARKET`,
`00-INBOX` e `.claude/state/plantao-meme` não tocados (plantão em voo).

## Desenho (decisões)

1. **Duas features novas em `hunter_indicators.meme.pedigree`** (`PedigreeFeatures`, campos novos com `default=None`,
   compatível com todo chamador posicional/kw existente): `creator_prior_dump_count` (qualquer janela até a criação
   da moeda julgada; conta prévias do mesmo criador com (a) `meme_features_1m.creator_sold = true`, (b)
   `meme_paper_bets.creator_sold_seen_at IS NOT NULL`, ou (c) uma aposta nossa saída por `creator_dump`) e
   `creator_prior_dead_count` (diagnóstico: prévias que caíram < 20 % do próprio topo em 30 min; sem série, a moeda
   não entra na contagem). Computadas em `lab_repo_fast.pedigree_for` (SQL correlacionado, reaproveitando o padrão de
   `creator_prior_mints_1h`/`symbol_dup_24h`), gravadas em `reasons` (`feature: pedigree`) sempre que o bloco existe —
   mesmo em conjuntos que não ligam o filtro novo.
2. **Exclusão nova, independente do gate congelado.** `evaluate_repeat_dumper` (pura, `PEDIGREE_V1` intocado — não é
   uma versão nova) recusa `creator_repeat_dumper` quando `creator_prior_dump_count ≥ 1`; `None` não recusa nada
   aqui (o brief já assume que `creator_unknown` da E2 v1 cobre esse caso, e os dois conjuntos novos sempre têm
   `pedigree_exclusions: true` herdado). `RuleSetSpec.pedigree_repeat_dumper: bool = False` (novo parâmetro por
   conjunto); `evaluate_gate` a aplica **depois** de `evaluate_pedigree`, somando ao invés de esconder.
3. **Migração `0039_meme_creator_repeat`** (`ddl/meme_creator_repeat.py`, padrão da `0034`): `flow_v2/5` (`…0010`,
   `research_only`, EXP-M6) = `flow_v2/2` + `pedigree_repeat_dumper: true`; `operator/5` (`…0011`) = `operator/4` +
   o mesmo; `operator/4` aposentado antes do insert; invariante de um `operator` ativo nos dois sentidos; downgrade
   recusa com proposta/aposta referenciando qualquer um dos dois (§17.7) e revive `operator/4`.
4. **`test_migrations.py`:** `HEAD_REVISION → 0039`; `CREATOR_WATCH_LIVE_REVISION` novo (0038 estagia nele); e —
   achado ao rodar a suíte — como a `0039` finalmente move o `operator` ativo pela primeira vez desde a `0034`
   (nada entre `0034` e `0038` tocava `meme_rule_sets.status`), `test_0034_seeds_…`, `test_0035_seeds_…` e
   `test_0037_seeds_…` liam `operator/4` ativo **sem estagiar** (correto até agora, porque nada acima mudava) — os
   três passaram a estagiar nas próprias revisões (`E1_ARM2_REVISION`, `ORGANIC_REVISION`, `E1_ARMS_3_4_REVISION`),
   e as três asserções finais "`operator/4` depois de restaurar o head" (`test_0033_reverses_…`,
   `test_0033_refuses_to_upgrade_…`, `test_0034_reverses_…`, `test_0034_refuses_to_upgrade_…`,
   `test_0037_reverses_…`) viraram `operator/5`. Quatro `test_0039_*` novos (semente, downgrade guardado,
   reversão limpa, invariante do `operator`).
5. **Achado fora do escopo ao rodar a suíte completa (sem `-k`), corrigido de passagem — a mesma dívida que a
   T4.23 já tinha achado uma vez:** dois testes fixos desde muito antes de mim já liam o `operator` ativo (ou a
   contagem total de conjuntos ativos) **sem estagiar**, na crença de que nada acima os mudaria — e a `0034`
   (T4.21) já os tinha deixado errados sem que ninguém notasse, porque desde então só se rodava o subconjunto
   `-k` da própria tarefa (o que este brief também pedia). `test_0022_reverses_with_the_seed_alone_and_comes_back_seeded`
   contava `8` conjuntos ativos ao voltar ao head (verdade só até a `0030`; cada aposentadoria líquida desde a
   `0033` soma mais um — 9 na `0034`, 10 na `0035`, 12 na `0037`, 13 na `0039`; corrigido para `13` com o
   raciocínio completo no comentário). `test_0029_adds_the_mark_and_venue_columns_and_seeds_the_moonshot_arms`
   já tinha sido remendado uma vez (de `operator/2` para `operator/3` quando a `0033` chegou) mas nunca de novo —
   corrigido para `operator/5`. Os dois passam isolados e dentro da suíte completa depois do reparo.
5. **Fechamento diário (T4.15).** As recusas `creator_repeat_dumper` por conjunto já chegam de graça pelo mecanismo
   genérico de soma de `meme_lab_ticks.refusals` (`meme_close_render_ops.coverage_section`) — nenhuma mudança
   necessária. Para "R das apostas com `creator_prior_dump_count ≥ 1`": `ClosedBet` ganha o campo (com `default=None`,
   sem quebrar as duas outras fixtures); `meme_close_lessons.lesson_repeat_dumper` reaproveita `lesson_flag` (a
   mesma régua de IC/bootstrap das outras oito lições) mas **não** entra em `day_lessons()` — os nove lá são o brief
   fixo da própria T4.15 (docstring do módulo) e mexer nesse número renumeraria `### 6.10`–`### 6.15` inteiros em
   `meme_close_render_ops.py`/`meme_close_render.py`, ruptura grande e fora do pedido. Em vez disso,
   `CloseInputs.repeat_dumper: Lesson | None = None` novo, computado em `gather_close`, renderizado como um parágrafo
   extra dentro de `### 6.14 Comparação com o pré-registro` (`_repeat_dumper_lines`) — "a comparação que julga o
   braço" cabe ali por natureza, e como só `flow_v2/5`/`operator/5` filtram por esse motivo (e o fazem antes da
   aposta nascer), pool de todo o dia já é "os conjuntos que não filtram", sem precisar excluir nada por SQL.

## Comandos e saídas (reais)

```
$ timeout 290 uv run pytest packages/indicators/tests/unit/test_meme_pedigree.py -q      → 15 passed (0.75s)
$ timeout 290 uv run pytest packages/indicators/tests/unit -k meme -q                     → 252 passed (12.34s)
$ timeout 290 uv run pytest services/meme-worker/tests/test_proposals_flow.py -q          → 11 passed (1.31s)
$ timeout 290 uv run pytest services/meme-worker/tests -q -m unit                         → 220 passed, 75 deselected
$ timeout 590 uv run pytest packages/core/tests/integration/test_migrations.py -q -k "0038 or 0039 or alembic_check or upgrade_head"
  → 11 passed (54.22s)
$ timeout 590 uv run pytest packages/core/tests/integration/test_migrations.py -q -k "0033 or 0034 or 0035 or 0037"
  → 13 passed (56.86s)   # os retrofits de operator/4 → operator/5
$ timeout 590 uv run pytest services/meme-worker/tests/test_lab_fast.py -q -k repeat_dumper → 1 passed (18.74s)
$ timeout 590 uv run pytest services/meme-worker/tests/test_lab_fast.py -q                → 6 passed (55.14s)
$ timeout 590 uv run pytest services/meme-worker/tests/test_lab_persistence.py -q         → 14 passed (150.59s)
$ timeout 290 uv run pytest apps/api/tests/unit -q -k meme                                → 122 passed, 602 deselected
$ timeout 290 uv run pytest infra/scripts/tests/test_meme_close_lessons.py infra/scripts/tests/test_meme_close_render.py infra/scripts/tests/test_meme_close_day.py -q
  → 15 passed (2.34s)
$ timeout 290 uv run ruff check <22 arquivos meus>       → All checks passed!
$ timeout 290 uv run ruff format --check <idem>          → 18/22 already formatted (4 reformatados por mim antes de checar)
$ timeout 290 uv run pyright <arquivos de produção + testes meus>  → 0 errors, 0 warnings, 0 informations
$ timeout 290 uv run python infra/scripts/check_file_size.py      → scanned 861 files; 0 over budget, 0 grandfathered
$ timeout 120 uv run python infra/scripts/obsidian_lint.py        → base limpa (289 notas)
```

A suíte completa (sem `-k`) de `test_migrations.py` (190 testes) foi disparada em segundo plano por estourar
qualquer `timeout` de primeiro plano disponível (> 590 s; levou 704 s / 11m44s). Primeira rodada: **188 passed, 2
failed** — os dois achados fora do escopo descritos acima (`test_0022_reverses_…`, `test_0029_adds_the_mark_and_…`),
nenhum dos meus `test_0039_*`/retrofits. Corrigidos os dois; segunda rodada disparada em segundo plano para
confirmar (resultado abaixo, quando terminar). `pyright` amplo por diretório (`infra/scripts`, `infra/migrations`)
mostrou 21 erros pré-existentes em arquivos que não são meus (`meme_render_bets_*.py`, `exchange_planned.py`,
`test_meme_render_bets*.py` — todos `??` no `git status`, de outro agente concorrente) — confirmado que não são
meus antes de seguir; um erro em `test_meme_close_lessons.py` (comparação `<` com `Decimal | None`) era meu e foi
corrigido.

```
$ uv run pytest packages/core/tests/integration/test_migrations.py -q --tb=line -rf   (1ª rodada, em segundo plano)
  → 188 passed, 2 failed in 704.12s (0:11:44)
  FAILED test_0022_reverses_with_the_seed_alone_and_comes_back_seeded (contagem '8' desatualizada desde a 0034)
  FAILED test_0029_adds_the_mark_and_venue_columns_and_seeds_the_moonshot_arms ('operator/3' desatualizado desde a 0034)
$ timeout 590 uv run pytest packages/core/tests/integration/test_migrations.py -q -k "test_0022_reverses_with_the_seed_alone_and_comes_back_seeded or test_0029_adds_the_mark_and_venue_columns_and_seeds_the_moonshot_arms"
  → 2 passed (30.73s)   # depois do reparo
$ uv run pytest packages/core/tests/integration/test_migrations.py -q --tb=line -rf   (2ª rodada, em segundo plano, depois do reparo)
  → 190 passed in 732.79s (0:12:12)
```

## Arquivos

**Criados:** `infra/migrations/ddl/meme_creator_repeat.py`; `infra/migrations/versions/0039_meme_creator_repeat.py`;
esta nota.

**Modificados:** `packages/indicators/hunter_indicators/meme/pedigree.py`,
`packages/indicators/tests/unit/test_meme_pedigree.py`;
`services/meme-worker/hunter_meme_worker/{lab_models,lab_repo_fast,proposals,proposals_reasons}.py`,
`services/meme-worker/tests/{test_proposals_flow,test_lab_fast}.py`;
`packages/core/tests/integration/test_migrations.py`;
`infra/scripts/meme_close_{inputs,lesson_kit,lessons,queries,render_ops}.py`,
`infra/scripts/tests/{meme_close_fixtures,test_meme_close_lessons}.py`;
`docs/{DATABASE,RISK_ENGINE_MEME}.md`, `docs/plans/T4-MEME-RADAR.md`;
`obsidian/05-EXPERIMENTS/EXP-M6-exclusoes-de-pedigree.md`.

## Suposições e decisões que o brief não fixa

- `exp_ref` de `flow_v2/5` = `EXP-M6` (o braço mede a pedigree, não o fluxo em si, embora herde o nome `flow_v2`
  por composição de params); `operator/5.exp_ref = NULL`, como `operator/3`/`operator/4`.
- `creator_prior_dump_count` não tem teto configurável (fixo em `≥ 1` no código, como o brief pede) — nenhum
  `PedigreeGate`-like novo; é uma função pura, não uma versão do gate.
- `creator_prior_dead_count` = pico e vale de `mcap_sol` dentro de `(created_at, created_at + 30 min]` na série de
  minuto (`meme_features_1m`); "morreu" = vale < 20 % do pico da própria janela. Sem nenhuma linha na janela, a
  moeda não entra na contagem (nem viva, nem morta) — não usei a série de 15 s (moedas com mais de 5 min e sem
  série de minuto suficiente ficam fora, declarado).
- Lição do fechamento diário fica **fora** de `day_lessons()` (os nove fixos do brief da T4.15) para não renumerar
  `### 6.10`–`### 6.15`; entra como parágrafo em `### 6.14`. Se o orquestrador preferir uma décima lição numerada,
  é a próxima tarefa (ripple grande: `meme_close_render.py` + `meme_close_render_ops.py` + os testes de ambos).

## Rótulo para o front (fora desta tarefa, `apps/web` intocado)

`creator_repeat_dumper` → "criador reincidente"; `feature: pedigree`'s novos `creator_prior_dump_count`/
`creator_prior_dead_count` podem ganhar rótulo "reincidência do criador (dumps anteriores)"/"moedas anteriores
mortas (diagnóstico)" quando o front for tocado.

## `git status --porcelain` (só os meus; ~21:4x BRT)

Ver lista completa no relatório final — árvore compartilhada com muito ruído concorrente (plantão, outro agente em
`infra/scripts/meme_render_bets_*.py`, design audits em `.claude/state/design/**`); nenhum arquivo meu fora da
lista de "Arquivos" acima, nenhum `.env*`, nenhum `apps/web/**`/`services/meme-executor/**`/
`packages/exchange-adapters/**`, `obsidian/02-MARKET`/`00-INBOX`/`plantao-meme` intocados.
