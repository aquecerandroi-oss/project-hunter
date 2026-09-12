# T4.2d — o que "graduou" quer dizer, o denominador do progresso e a cegueira declarada (migração `0024_meme_graduation`)

Execução de 12/09/2026, das ~07:25 às ~08:40 BRT (UTC−3). Papel: backend-specialist.
Sem commit (o orquestrador commita por pathspec). Nada real: nenhuma ordem, nenhuma chave, nenhum
servidor de desenvolvimento, nenhuma leitura ao vivo — tudo sobre fixtures capturadas na T4.1/T4.2c.

**Antes de mim, na árvore (não são meus, não tocados):** `.claude/launch.json`, `docs/DESIGN.md`. O
`apps/web/components/meme/labels.ts` já estava modificado (`trenches_ws`/`no_sells`, T4.2c) — editei
por cima; o commit por pathspec leva as duas mudanças.

## Arquivos

**Adaptador** — `packages/exchange-adapters/hunter_exchanges/pumpfun/quote.py`
(`curve_fill_threshold_lamports`: `buy_cost` dos `initial_real_token_reserves` numa curva virgem =
85 005 359 057 lamports para o registro de 18/07/2025 — bate com os 85,005 SOL medidos e com o
`115 005 359 057` de SOL virtual da WOTF), `rest.py` (`get_global_params(created_at_ms)`); testes
`tests/unit/test_pumpfun_quote.py`, `test_pumpfun_clients.py`.

**Migração** — `infra/migrations/versions/0024_meme_graduation.py`, `ddl/meme_graduation.py`
(seis colunas, quatro CHECKs, trigger `WRITE_ONCE_COLUMNS_0024` + ramo "só recua" de `completed_at`,
backfill de evidência com o trigger da 0021 desligado só nesse passo, `meme_radar_features_v1` com seis
colunas no fim, vista `meme_graduation_matrix_v1`, guarda de downgrade). Modelo
`packages/core/hunter_core/db/models/meme.py`. Testes `packages/core/tests/integration/test_migrations.py`
(HEAD → `0024`, `MEME_BOARDS_REVISION`, os dois testes da 0023 restageados, +5 `test_0024_*`);
`test_schema_privileges.py` sem união nova (nenhuma tabela; a vista fica fora do `relkind IN ('r','p')`).

**Worker** (`services/meme-worker/hunter_meme_worker/`) — novos: `graduation.py` (`CompletionSignals`,
`earliest_completion`, `curve_signals`, `fill_threshold_sol`, `denominator_for` com guarda Mayhem,
`GlobalParamsStore`), `curve_rows.py` (`snapshot_row`, `token_row_from_curve`, `tracked_from_curve` — saíram
de `collect.py` pelo orçamento de 350 linhas), `repo_rows.py` (`TokenRow`/`SnapshotRow`/`GapRow`, idem de
`repo.py`). Modificados: `repo.py` (seis colunas; `completed_at = LEAST`; `_LOAD_TRACKED` por
`rest_complete_seen_at`, leitura final para quem concluiu por board/pool), `boards.py` (board `graduated`
→ `graduated_board_seen_at` + pool sem rastrear; `ingest` devolve primeiras aparições), `discovery.py`
(`migrate` → pool), `risk.py` (`graduationDate` → pool), `sources.py` (`new_board_entries_1h`,
`new_board_non_pump_1h`, `blind_share_1h`), `wiring.py`, `collect.py`, `context.py` (`params`),
`config.py` (`global_params_refresh_s`), `main.py`, `features.py` (`meme_features_v2`). Testes novos:
`tests/test_graduation.py` (15), `test_curve_rows.py` (5), `test_graduation_persistence.py` (testcontainer,
4); ajustados: `test_boards.py` (+2), `test_discovery_rows.py` (+1), `test_sources.py` (+1),
`test_boards_trades_persistence.py` e `test_persistence.py` (a semântica nova de `completed_at`).

**API** — `apps/api/hunter_api/schemas/meme.py` (`PoolCreatedSource`, `ProgressDenominatorSource`,
`GraduationMatrixOut`, seis campos em `MemeTokenOut`, `graduation_matrix` na overview),
`schemas/meme_sources.py` (`discovery_blind_share_1h`, contagens, `DISCOVERY_BLIND_EXPLANATION`),
`services/meme.py`, `services/meme_sources.py`, `repositories/meme.py` (`graduation_matrix_for`: o dia
de Brasília é do banco), `meme_rows.py`, `meme_tables.py`; testes `tests/unit/test_meme_service.py`,
`test_meme_sources_service.py`, `tests/integration/test_meme_repository.py` (cópia da DDL atualizada).
`pnpm gen:types` rodado → `packages/shared-types/src/generated/api.d.ts`.

**Web** — novos: `components/meme/meme-graduation-signals.ts` (puro), `meme-graduation-strip.tsx`,
`meme-signal-marks.tsx`, `tests/meme-graduation-signals.test.ts`; modificados: `labels.ts` (rótulos dos
quatro sinais, das fontes da pool e do denominador; `completed` = "Concluída (sinal mais antigo)"),
`meme-curve-chart.tsx` (`markX` + marcas verticais em âmbar), `meme-overview-strip.tsx`,
`app/(app)/[orgSlug]/meme/[mint]/page.tsx`. `/meme/page.tsx` não precisou mudar (a faixa recebe a
matriz pela overview; o filtro `completed` já era `completed_at` na API).

**Docs** — `docs/DATABASE.md` §36, `docs/PUMPFUN.md` §4.2.1, `docs/plans/T4-MEME-RADAR.md` §T4.2d.

## Decisões

1. **`completed_at` = a mais antiga das quatro, exceto REST com reserva zero sozinho** — e a exceção não
   empresta nem o instante: o graduado real da fixture (`complete: true`, `real_sol 0`) fica sem
   veredito até o `migrate` do PumpPortal trazer a pool. No banco é `LEAST(existente, novo)` e o
   trigger só deixa recuar (o `gd` do indexer é retrospectivo).
2. **Mayhem nunca toma o denominador do registro.** A fixture `2sduGq…` (Mayhem pausada) tem 822,6 M
   tokens reais na curva, mais que os 793,1 M do `/global-params`; nem `Global` nem o endpoint trazem
   parâmetro de reserva Mayhem (o campo certo é a conta `mayhem_state`, não decodificada). Guarda
   dupla: `mayhem_enabled`/`mayhem_state` presentes ⇒ unknown; `real_token > inicial` ⇒ unknown.
3. **O board `graduated` escreve a linha mas não rastreia** (curva estática = zero orçamento); o
   `_LOAD_TRACKED` exclui por `rest_complete_seen_at` (foto REST completa = reservas estáticas) e traz
   de volta, para uma leitura final, quem concluiu só por board/pool — o orçamento fica igual à T4.2c.
4. **`pool_created_source` é a fonte da entrada** (`pumpportal_ws` | `trenches_ws` | `indexer_rest:/boards`
   | `indexer_rest:/in-memory-coin`), não uma palavra inventada.
5. **Backfill na migração, com o trigger desligado só nesse passo**: `rest_complete_seen_at` das
   fotografias, `graduated_board_seen_at` das linhas de board, pool do `migrated_at` senão do `gd`,
   `observed_virgin` para todo denominador existente, `completed_at` recomputado; `curve_filled_seen_at`
   começa no deploy (o limiar precisa do registro).
6. **`meme_features_v2`**: `curve_progress_pct` pode vir de `global_params`; `v1` não é reescrita; o Lab
   lê a versão da config (`lab_repo.load_gate_rows` usa `:version`).
7. **`/global-params` no orçamento da curva, uma vez por hora** (`GlobalParamsStore`); um registro por
   instante de criação anterior ao cacheado é lido uma vez e lembrado; falha conta e não vira palpite.

## Comandos e saídas reais

```
$ timeout 290 uv run pytest packages/exchange-adapters/tests/unit/test_pumpfun_quote.py packages/exchange-adapters/tests/unit/test_pumpfun_clients.py -q
ImportError: cannot import name 'curve_fill_threshold_lamports'      (antes)  →  26 passed in 1.25s  (depois)
$ timeout 290 uv run pytest packages/exchange-adapters/tests/unit/ -q -k pumpfun
118 passed, 375 deselected in 2.99s
$ timeout 290 uv run pytest services/meme-worker/tests/test_graduation.py …test_curve_rows.py …test_boards.py …test_discovery_rows.py …test_sources.py -q
ModuleNotFoundError: No module named 'hunter_meme_worker.curve_rows'  (antes)
$ timeout 290 uv run pytest services/meme-worker/tests -q --ignore=<4 testcontainer>
119 passed in 2.17s
$ timeout 290 uv run pytest apps/api/tests/unit/test_meme_service.py apps/api/tests/unit/test_meme_sources_service.py -q
ImportError: cannot import name 'DISCOVERY_BLIND_EXPLANATION'         (antes)
$ timeout 290 uv run pytest apps/api/tests/unit/test_meme_service.py …test_meme_sources_service.py …test_meme_lab_service.py -q
35 passed in 0.36s
$ timeout 290 uv run pytest packages/core/tests/unit -q
1331 passed in 74.84s

$ timeout 590 uv run pytest services/meme-worker/tests/test_graduation_persistence.py -q      # testcontainer, head = 0024, sozinho
4 passed in 17.81s
$ timeout 590 uv run pytest services/meme-worker/tests/test_boards_trades_persistence.py -q
8 passed in 21.81s
$ timeout 590 uv run pytest services/meme-worker/tests/test_persistence.py -q
10 passed in 22.35s
$ timeout 590 uv run pytest apps/api/tests/integration/test_meme_repository.py -q
18 passed in 11.74s
$ timeout 590 uv run pytest packages/core/tests/integration/test_migrations.py -q
50 failed, 97 passed in 208.95s   → HINT do guarda de downgrade embutia 'global_params' num literal (syntax error); escapado
3 failed, 3 passed (-k 0024)      → asyncpg exige datetime nos parâmetros (o teste passava string ISO); corrigido
147 passed in 448.46s (0:07:28)   ← rodada completa final
$ timeout 590 uv run pytest packages/core/tests/integration/test_schema_privileges.py -q
57 passed in 175.85s (0:02:55)

$ timeout 290 uv run ruff check <todos os .py tocados>  → All checks passed!
$ timeout 290 uv run ruff format --check <idem>         → 241 files already formatted
$ timeout 290 uv run pyright services/meme-worker apps/api/hunter_api/services/meme_sources.py apps/api/hunter_api/schemas/meme_sources.py <demais>
0 errors, 0 warnings, 0 informations   (antes: 2 erros — `_RETENTION_MARKER` sem anotação; anotado)
$ timeout 290 uv run python infra/scripts/check_file_size.py
scanned 742 files; 0 over budget, 0 grandfathered
$ timeout 290 pnpm gen:types
openapi-typescript 7.13.0 … packages/shared-types/openapi.json → packages/shared-types/src/generated/api.d.ts [452.7ms]
$ cd apps/web && timeout 290 npx vitest run tests/meme*.test.ts
Test Files 9 passed (9) · Tests 79 passed (79)      (antes: 8/69; o novo arquivo falhou primeiro por import inexistente)
$ timeout 590 npx turbo run typecheck lint --filter=@hunter/web
Tasks: 2 successful, 2 total · lint: 0 errors, 2 warnings (lab-page.test.tsx 377 linhas e ws.test.ts 557 — pré-existentes, fora do escopo)
```

## Preocupações / pendências

1. **Mayhem (64 % das criações) só ganha denominador se observada virgem** — o registro não descreve a
   curva Mayhem (decisão 2). O portão do Lab continua recusando a maioria delas por `progress_unknown`;
   a correção real é decodificar a conta `mayhem_state` (fora de escopo).
2. **`curve_filled_seen_at` não é preenchida no backfill** (precisa do registro); a matriz mostra
   `curve_filled = 0` para os dias anteriores ao deploy — declarado, não corrigido.
3. **O downgrade da 0024 recusa em qualquer base com sinal** (como a 0023 recusa com linha de board):
   reverter na VPS exige `COPY` antes.
4. **Sem checagem visual no navegador**: o brief proíbe servidor de desenvolvimento; as telas foram
   verificadas por vitest + typecheck + lint apenas.
5. **Astra não consultada** (`SendMessage` desabilitado; `astra.sh` não usado para não gastar a
   janela) — a revisão do diff foi minha.
6. `pool_created_at` no backfill prefere `migrated_at` (PumpPortal) ao `gd` quando os dois existem;
   "o que chegou primeiro" não é recuperável para linhas antigas — declarado na DDL.
