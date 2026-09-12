# T4.10 Parte A — traçado de linhas e sonda de hype (migração `0026_meme_lines`)

Execução de 12/09/2026, das ~10:58 às ~11:45 BRT (UTC−3). Papel: quant/backend. Contrato:
`.claude/state/brief-T4.10-tracado-de-linhas-e-sonda-de-hype.md` (nomes de colunas, vocabulários,
conjuntos e `parent_bet_id`/`leg` exatamente como lá). Sem commit; nada real; `.env*` intocado;
`apps/web/**` e `hunter_core/execution/**` intocados. Nenhum processo em segundo plano; todo comando com
`timeout 290` (590 nos testcontainers).

**Antes de mim, na árvore (não são meus, não tocados):** `.claude/launch.json`,
`apps/web/tests/meme-desk-labels.test.ts`, `apps/web/tests/meme-labels.test.ts`, `docs/DESIGN.md`,
`packages/exchange-adapters/hunter_exchanges/pumpfun/{rate_shared,rpc,swap_api}.py`,
`packages/exchange-adapters/tests/unit/test_pumpfun_swap_api.py`, os `??` de `.claude/state/astra-*`,
`.claude/state/design/**`, `.claude/state/tmp/**` e `.claude/state/exp-drafts/**` (`git status` às 13:58Z).
**Durante a sessão, outro agente (T4.2f) modificou em paralelo** `services/meme-worker/hunter_meme_worker/
{collect,config,context,main,sources,tracker,trades,wiring}.py`, `chain.py`, `tape_budget.py`,
`apps/api/hunter_api/{schemas,services}/meme_sources.py`, `docs/{PIPELINE,PUMPFUN,PUMPFUN-ONCHAIN,
DEPLOYMENT,EXCHANGE_INTEGRATION}.md`, `docs/plans/T4-MEME-RADAR.md` (§T4.2f), testes `test_chain*`,
`test_mayhem/test_sources/test_tracker_priority/test_trades.py`, `rpc_curves.py`, fixtures `t42f_*`,
`notes-T4.2f.md`. Conferi com `git diff -U0` que os arquivos que **eu** editei só carregam os meus hunks.

## Arquivos meus

**Criados**
- `packages/indicators/hunter_indicators/meme/{lines,hype,exits}.py`
- `packages/indicators/tests/unit/{test_meme_lines,test_meme_hype,test_meme_rules_lines}.py`
- `services/meme-worker/hunter_meme_worker/{features_lines,repo_lines,lab_values,paper_fill,lines_exit,lab_repo_lines,proposals_scale}.py`
- `services/meme-worker/tests/{test_features_lines,test_proposals_scale,test_lines_exit,test_lab_lines}.py`
- `infra/migrations/versions/0026_meme_lines.py`, `infra/migrations/ddl/meme_lines.py`
- `obsidian/05-EXPERIMENTS/EXP-M2-a-linha-manda.md`, `obsidian/05-EXPERIMENTS/EXP-M3-sonda-de-hype.md`
- `.claude/state/notes-T4.10a.md` (este)

**Modificados**
- `packages/indicators/hunter_indicators/meme/rules.py` (porta com critérios opcionais; re-exporta `exits`)
- `services/meme-worker/hunter_meme_worker/{features,fold,repo,lab,lab_bets,lab_models,lab_repo,lab_repo_bets,paper_engine,proposals}.py`
- `packages/core/hunter_core/db/models/{meme_features,meme_lab}.py`
- `packages/core/tests/integration/test_migrations.py` (HEAD → `0026_meme_lines`; `MEME_MAYHEM_REVISION`; 0025 posiciona antes de reverter; seed da 0022 lida por id; ativos = 4; +3 testes da 0026). `test_schema_privileges.py` **não muda**: a 0026 não cria tabela nem grant.
- `apps/api/hunter_api/schemas/{meme,meme_desk}.py`, `repositories/{meme,meme_rows,meme_tables,meme_desk_rows,meme_desk_tables}.py`, `services/{meme,meme_desk_out}.py`
- `docs/DATABASE.md` §38, `docs/plans/T4-MEME-RADAR.md` §T4.10
- `obsidian/05-EXPERIMENTS/Experiments Index.md` (2 tabelas, linhas EXP-M2/EXP-M3), `obsidian/03-TRADING/Meme/README.md` (tabela de conjuntos)
- `packages/shared-types/src/generated/api.d.ts` (`pnpm gen:types`, +53/−2)

## Decisões de desenho

- Módulos puros: `lines.py` (linhas, 9 `FeatureDefinition` v1), `hype.py` (`hype_score` v1 com decomposição raw/normalizado/peso/contribuição); o lado das saídas de `rules.py` foi para `exits.py` (re-exportado — `code_ref` `hunter_indicators.meme.rules:evaluate_entry+evaluate_exit` continua válido) para caber nos 350.
- Não-antecipação das linhas: pontos com `received_at <= end_time`; janela `(end_time − 15 min, end_time]`; a máxima de referência do rompimento é a da janela **anterior** `(end_time − 16 min, end_time − 1 min]` (o minuto nunca é a própria referência). Fold lê `meme_curve_snapshots` (`repo_lines.py`) e os boards do mesmo minuto (`features_lines.board_standing`).
- `line_reason` explica o NULL de `support_line_sol`; `too_few_points`/`no_snapshot` anulam tudo, `flat`/`out_of_range` só o grupo do suporte. `hype_reason = partial` convive com score (regra do brief) → CHECK `(hype_score IS NULL) = coalesce(hype_reason = 'no_tape_no_board', false)`. **CHECKs escopados a `line_points IS NOT NULL`**: linhas `v1`/`v2` não ganham motivo inventado (nenhuma das 4 palavras seria verdade para elas).
- `as_parameters()`/`suggested()` só listam critérios/chaves novos quando pedidos — a decomposição registrada e o `suggested` da EXP-M1 ficam byte a byte (o teste da T4.5 congela o dicionário).
- Escala: propriedade do conjunto `hype_probe_v0` (`scale_size_sol = 0,04`, `scale_gate = trendline_v0/1`); `lab._scale_step` só olha sondas `open`/`leg = probe` não escaladas (`lab_repo_lines.scaled_parent_ids` conta apostas com `parent_bet_id` **e** propostas pendentes com `suggested.parent_bet_id`); a porta da linha é avaliada com o tamanho **0,04**; a proposta da perna 2 nasce aprovada por `rules` com `leg`/`parent_bet_id` no `suggested` (nenhuma coluna nova em `meme_proposals`); `paper_fill` grava as colunas e recusa `scale_without_parent`/`unknown_leg`. `open_positions` do teto conta pernas ≠ `scale` (o brief fixa "máximo 5 sondas abertas").
- Saída `line_broken` (precedência: rug → creator_dump → migração → max_loss → **line_broken** → alvo → trailing → time stop): `lines_exit.support_at` projeta a linha do último minuto dobrado **em ou antes** da fotografia; a sequência é reconstruída a partir da fotografia da última marca (uma para trás — para 2 fotografias é exato; nunca dispara cedo).
- Vistas `meme_desk_v1`/`meme_lab_scoreboard_v1` intocadas (a API da mesa lê as tabelas base — Emendas T4.7).

## Suposições numéricas (o brief não fixa)

`max_loss_pct = 50` nos dois conjuntos (piso da EXP-M1); `max_age_s = 600` no `trendline_v0`; progresso **não** é critério da sonda (`require_progress = false`; um mint de 30 s raramente tem denominador); `max_exposure_per_mint_sol = 0,05` e `max_sol_per_bet = 0,04` na sonda (sonda + perna 2); posição de board ≥ 50 conta como ausente (0); `has_social`/`snipers` desconhecidos contribuem 0 no score; snipers desconhecidos **recusam** a porta da sonda (`snipers_unknown`); `dev_share` desconhecido passa só com motivo (`dev_share_unknown_allowed`).

## Comandos e saídas (reais)

```
$ uv run ruff format packages/indicators/ && uv run ruff check packages/indicators/
All checks passed!
$ uv run pytest packages/indicators/tests/unit -k "meme" -q -p no:cacheprovider
141 passed, 1044 deselected in 5.86s
$ uv run pytest services/meme-worker/tests -m unit -q -p no:cacheprovider
159 passed, 42 deselected in 2.20s
$ uv run pytest apps/api/tests/unit -k "meme" -q -p no:cacheprovider
78 passed, 602 deselected, 1 warning in 1.06s
$ timeout 590 uv run pytest packages/core/tests/integration/test_migrations.py -q -p no:cacheprovider \
    -k "0026 or 0025 or 0022_seeds or 0022_reverses or 0024_reverses"
9 passed, 144 deselected in 50.28s          # inclui command.check (paridade ORM ↔ banco)
$ timeout 590 uv run pytest services/meme-worker/tests/test_lab_lines.py -q -p no:cacheprovider
3 passed in 34.34s
$ uv run python infra/scripts/check_file_size.py --max 350 --baseline infra/scripts/file_size_baseline.txt
scanned 757 files; 0 over budget, 0 grandfathered
$ uv run ruff check .
All checks passed!
$ uv run ruff format --check <66 arquivos meus>
66 files already formatted
$ uv run ruff format --check .
11 files would be reformatted   # 10 não são meus (infra/scripts/backfill_funding.py, request_backfill.py,
                                # market-worker funding_*, core test_settings.py, 4 .md do obsidian);
                                # o 11.º (test_lab_lines.py) foi formatado em seguida
$ uv run pyright services/meme-worker/hunter_meme_worker packages/indicators/hunter_indicators/meme apps/api/hunter_api packages/core/hunter_core
0 errors, 0 warnings, 0 informations
$ uv run pyright   # repositório inteiro
37 errors — todos em arquivos que não toquei (strategy-worker/tests/test_replay_*, apps/api/tests/integration/
test_lab_signals_pagination_api.py e test_risk_limits_api.py, packages/core/tests/unit/{execution/meme/test_meme_submit,
strategies/test_mean_reversion_v1,strategies/test_no_lookahead}.py, exchange-adapters/tests/unit/test_pumpfun_verify.py,
infra/scripts/tests/test_render_operations.py); os 2 meus (reportPrivateUsage nos imports de helpers dos testes vizinhos)
corrigidos com `# pyright: ignore[reportPrivateUsage]` → 0 nos meus arquivos
$ pnpm gen:types
packages/shared-types/openapi.json → packages/shared-types/src/generated/api.d.ts [540.9ms]
```

Erros meus corrigidos no caminho (todos em teste ou guarda, nenhum em regra): série "fundos descendentes"
mal desenhada (44 em −12 deixa de ser fundo; refeita 36 → 30); `_snapshot(30)` anterior à decisão no teste
de fill (→ 120); `BoardMinuteRow` exige `patches`; a guarda de descida da 0026 tinha aspas simples no
predicado dentro do `HINT` (agora escapadas — nenhuma guarda anterior tinha aspas no predicado); o teste do
laço plantava as fotografias "futuras" antes do tick 2 e o laço, corretamente, as percorria no mesmo tick
(agora são inseridas entre o tick 2 e o 3); a recusa da segunda sonda é `already_open`, não `age_above_max`.

## O que está provado

- Linhas: dois fundos 36 → 41 ⇒ inclinação 1 SOL/min, suporte 48, distância 0,166667; série exponencial ⇒
  inclinação ln 0,02/min exata e `flat`; a fotografia do próprio minuto não é referência do rompimento;
  fotografia recebida 1 s depois do fecho não muda a linha (puro, no `build_row` e contra Postgres em
  `load_line_points`).
- Hype: 15 compras, 10 compradores, posição 3, social, 1 sniper = 0,700000; pesos somam 1; `partial` e
  `no_tape_no_board` como o brief manda.
- Porta/saídas: critérios novos só refusam quando pedidos; nomes de recusa por insumo (`line_flat`,
  `hype_no_tape_no_board`, `snipers_unknown`…); `line_broken` com 2 fechos, precedência entre `max_loss` e alvo.
- Migração: colunas, 8 + 2 CHECKs (com os casos que recusam), FK/índice, seeds com os parâmetros congelados,
  guarda de descida (perna, linha, referências), ida e volta limpa, `alembic check` ok.
- Laço contra Postgres: sonda de 0,01 aos 2 min → linha nasce aos 6 min (suporte 30,4) → perna 2 de 0,04
  com `parent_bet_id` = sonda, vigiando a linha → 2 fechos abaixo → venda `line_broken` na fotografia
  seguinte; a sonda continua aberta; uma única proposta de escala jamais escrita.

## Preocupações

- A T4.2f mexe nos mesmos módulos do worker em paralelo (`main.py`, `config.py`…); as suítes passam na
  árvore combinada agora, mas o commit por pathspec deve levar os dois conjuntos de arquivos juntos.
- `ExitReason` da API ganhou `max_loss` e `line_broken` (o laço já escrevia `max_loss` desde a T4.6); o
  tipo TS é `string` na prática (`ExitReason | str`), então o `labels.ts` da Parte B não quebra por isso.
- `meme_features_v2` para de ser lido pelo Lab no deploy (o config nomeia `v3`): a série quebra no deploy,
  como aconteceu na v2 — declarado em `features.py`.

## `git status --porcelain` dos meus arquivos (14:4xZ)

```
 M apps/api/hunter_api/repositories/meme.py
 M apps/api/hunter_api/repositories/meme_desk_rows.py
 M apps/api/hunter_api/repositories/meme_desk_tables.py
 M apps/api/hunter_api/repositories/meme_rows.py
 M apps/api/hunter_api/repositories/meme_tables.py
 M apps/api/hunter_api/schemas/meme.py
 M apps/api/hunter_api/schemas/meme_desk.py
 M apps/api/hunter_api/services/meme.py
 M apps/api/hunter_api/services/meme_desk_out.py
 M docs/DATABASE.md
 M docs/plans/T4-MEME-RADAR.md
 M obsidian/03-TRADING/Meme/README.md
 M "obsidian/05-EXPERIMENTS/Experiments Index.md"
 M packages/core/hunter_core/db/models/meme_features.py
 M packages/core/hunter_core/db/models/meme_lab.py
 M packages/core/tests/integration/test_migrations.py
 M packages/indicators/hunter_indicators/meme/rules.py
 M packages/shared-types/src/generated/api.d.ts
 M services/meme-worker/hunter_meme_worker/features.py
 M services/meme-worker/hunter_meme_worker/fold.py
 M services/meme-worker/hunter_meme_worker/lab.py
 M services/meme-worker/hunter_meme_worker/lab_bets.py
 M services/meme-worker/hunter_meme_worker/lab_models.py
 M services/meme-worker/hunter_meme_worker/lab_repo.py
 M services/meme-worker/hunter_meme_worker/lab_repo_bets.py
 M services/meme-worker/hunter_meme_worker/paper_engine.py
 M services/meme-worker/hunter_meme_worker/proposals.py
 M services/meme-worker/hunter_meme_worker/repo.py
?? .claude/state/notes-T4.10a.md
?? infra/migrations/ddl/meme_lines.py
?? infra/migrations/versions/0026_meme_lines.py
?? obsidian/05-EXPERIMENTS/EXP-M2-a-linha-manda.md
?? obsidian/05-EXPERIMENTS/EXP-M3-sonda-de-hype.md
?? packages/indicators/hunter_indicators/meme/exits.py
?? packages/indicators/hunter_indicators/meme/hype.py
?? packages/indicators/hunter_indicators/meme/lines.py
?? packages/indicators/tests/unit/test_meme_hype.py
?? packages/indicators/tests/unit/test_meme_lines.py
?? packages/indicators/tests/unit/test_meme_rules_lines.py
?? services/meme-worker/hunter_meme_worker/features_lines.py
?? services/meme-worker/hunter_meme_worker/lab_repo_lines.py
?? services/meme-worker/hunter_meme_worker/lab_values.py
?? services/meme-worker/hunter_meme_worker/lines_exit.py
?? services/meme-worker/hunter_meme_worker/paper_fill.py
?? services/meme-worker/hunter_meme_worker/proposals_scale.py
?? services/meme-worker/hunter_meme_worker/repo_lines.py
?? services/meme-worker/tests/test_features_lines.py
?? services/meme-worker/tests/test_lab_lines.py
?? services/meme-worker/tests/test_lines_exit.py
?? services/meme-worker/tests/test_proposals_scale.py
```
