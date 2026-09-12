# T4.11 — o braço "moonshot" (10×/25×) e segurar através da migração (migração `0028_meme_moonshot`)

Execução de 12/09/2026, a partir das ~12:30 BRT (UTC−3). Papel: quant/backend. Brief:
`.claude/state/brief-T4.11-moonshot-e-pos-migracao.md`. Sem commit; nada real; `.env*` intocado;
`apps/web/**` e `wallets.py` intocados; `main.py` intocado (nenhum hunk foi necessário — ver §Decisões).
Nenhum processo em segundo plano; todo comando com `timeout 290` (590 no testcontainer).

**Árvore ao começar (14:30Z–15:35Z):** HEAD `e32956a` (plantão) sobre `ef5f4df` (T4.10a + T4.2f). Já
modificados por outros agentes, não meus: `.claude/launch.json`, `apps/api/hunter_api/app.py` (T4.13),
`docs/DESIGN.md`, `packages/shared-types/src/generated/api.d.ts`, `infra/migrations/ddl/meme_lab_views.py`,
`packages/core/hunter_core/db/models/__init__.py`, `services/meme-worker/hunter_meme_worker/{config,context}.py`
(T4.12); untracked da T4.12: `infra/migrations/versions/0027_meme_wallets.py`, `ddl/meme_wallets.py`,
`packages/core/hunter_core/db/models/meme_wallets.py`, `services/meme-worker/hunter_meme_worker/{wallet_positions,wallets_repo}.py`;
da T4.13: `apps/api/hunter_api/{repositories,routers,schemas,services}/meme_tests*.py`.

**Número da migração:** a T4.12 já ocupou `0027_meme_wallets` no disco quando criei a minha → a minha é
**`0028_meme_moonshot`** (`down_revision = "0027_meme_wallets"`), como o brief manda ("NEXT free number").

## Verificação pedida pelo brief: a fita do `swap-api` inclui negociações pós-migração?

**Sim.** Duas provas:
1. Fixture real da T4.2c (`packages/exchange-adapters/tests/fixtures/pumpfun/swap_api_trades_graduated_pump_raw.json`,
   capturada 12/09 06:01 BRT): 100 negociações, todas `program = "pump_amm"`, chaves
   `slotIndexId/tx/timestamp/userAddress/type/program/priceSol/amountSol/baseAmount/quoteAmount/fillPriceSol/…`.
2. **Uma** chamada ao vivo (≤ 5 permitidas), 15:35:04Z (12:35 BRT), mint graduado da mesma captura
   `5RFwNs16ShCeSNQY9Kf5iR5esbEMsnYm7PbWGQAwpump`:
   ```
   $ timeout 290 uv run python -c "... SwapApiClient(capacity=1).get_trades('5RFwNs16ShCeSNQY9Kf5iR5esbEMsnYm7PbWGQAwpump') ..."
   received_at 2026-09-12T15:35:04.609651+00:00 trades 100 has_more True malformed 0
   programs {'pump_amm': 100} native_sol 100
   newest 2026-09-12T10:51:08+00:00 sell price 1.878003203571540852057373216403443533337E-8 sol 0.001181796
   oldest 2026-09-12T08:58:17+00:00
   lag_newest_s 17036
   ```
   A pool continua na fita horas depois da migração; a última negociação foi há 4,7 h — exatamente o
   caso que o brief chama de **morta** (`dead`).

**Mas o worker descartava essas linhas:** `repo_tape.trade_rows` só aceitava `is_bonding_curve`
(`program == "pump"`) e contava o resto como `not_bonding_curve` (`test_trades.py` afirmava
`{"not_bonding_curve": 100}` para a página do graduado). Logo o item 1 exige persistir a fita da pool —
coluna `meme_trades.program` (`pump` | `pump_amm`) na `0028`. O mint migrado com aposta aberta continua
na fita por `wiring.tape_tiers` (`ctx.state.open_bets` → `TIER_OPEN_BET`, independente do tracker), então
nenhum hunk em `main.py` foi necessário.

## Comandos e saídas (reais, em ordem)

(preenchido incrementalmente abaixo)

### Retomada em 12/09, ~13:3x BRT (16:3x UTC) — a partir do disco, sem apagar nada

**Renumeração:** enquanto esta tarefa estava cortada, a T4.14 ocupou `0028_meme_live`; a minha passou a
ser **`0029_meme_moonshot`** (`down_revision = "0028_meme_live"`; DDL `ddl/meme_moonshot.py`;
`docs/DATABASE.md` §41). O cabeçalho desta nota dizia 0028 — vale 0029. Ordem no disco: 0027 → 0028 → 0029.

**O que estava pronto no disco** (conferido por `git diff`): puro (`pool.py`, `exits.py`, `rules.py`), laço
(`lab_bets_pool.py`, `lab_params.py`, `lab_repo_pool.py`, `pool_mark.py` + hunks em `lab_bets/lab_models/
lab_repo_bets/lab_rows/lab_values/paper_engine/repo_tape`), migração + DDL + modelo + `test_migrations.py`,
testes unit (4 arquivos) e o testcontainer `test_lab_moonshot.py`, API (`schemas/meme_desk.py`,
`services/meme_desk_out.py`, `repositories/meme_desk{,_rows,_tables}.py`), docs §T4.11/§41/§6, EXP-M4 +
Index + README, `test_meme_desk_moonshot.py`.

**O que faltava e foi feito nesta retomada:**
1. **Crítico — a mesa num banco ainda na `0028`.** `repositories/meme_desk_tables.py` declarava
   `mark_source`/`mark_stale_s` na `Table` compartilhada; `select(meme_paper_bets)` (a mesa e o
   `/meme/tests` da T4.13) quebraria com `UndefinedColumn` antes da migração. Colunas **removidas** da
   `Table`; módulo novo `repositories/meme_desk_marks.py`: sonda `information_schema.columns` (não levanta
   nada, sem savepoint) e, só com as duas colunas presentes, uma segunda leitura por id numa `Table`
   privada (`MetaData()` própria), dobrada nos `BetRow` com `dataclasses.replace`. Sem cache por processo
   (os testes de integração alternam bancos no mesmo processo; a sonda custa microssegundos).
   `_assemble` e `get_bet` usam `with_marks_0029`.
2. **`get_operator_rule_set`** lia `("operator", "2")` fixo → num banco na `0028` a compra manual
   recusaria `operator_rule_set_missing`. Agora: `name = 'operator' AND status = 'active'`, `ORDER BY
   length(version) DESC, version DESC LIMIT 1` — `operator/2` na `0029`, `operator/1` abaixo.
3. `EXIT_REASON_PT["dead"] = "morta"` em `schemas/meme_tests.py` (T4.13; o unit
   `test_every_exit_reason_has_a_portuguese_label` falhava com `dead` no `ExitReason`).
4. `test_meme_tests_api.py::_insert_bet` (T4.13, integração) inseria `mark_sol` sem `mark_source` — o CHECK
   `a_mark_names_its_source` da `0029` recusaria; coluna `mark_source = 'curve'` acrescentada ao INSERT.
   A fixture da T4.13 semeia por `version = '1'`, então os rótulos `operator/1` dela continuam válidos.
   `test_meme_desk_repository.py` cria um schema próprio pré-`0029` — é exatamente o caminho "abaixo da
   `0029`" do leitor tolerante.
5. Testes unit novos em `test_meme_desk_moonshot.py`: a `Table` compartilhada não declara as colunas;
   abaixo da `0029` só a sonda é consultada e os `BetRow` dizem `None`; na `0029` as marcas entram por id
   e uma linha não pedida não vira aposta; mapa vazio não consulta nada.
6. isort nos meus 4 testes do worker (a T4.14 acrescentou `hunter_meme_worker` a `known-first-party`).
7. Docs: §T4.11 (leitura tolerante + operator por nome + rótulos pendentes do front), §41.3/§41.5.

**Não tocado, mas visto (T4.14, em andamento por outro agente).** Às ~13:4x BRT a coleta da API quebrava
(`routers/meme_live.py` importava `hunter_core.errors`, inexistente) e `services/meme_desk.py` chamava
`enforce_live_mode` sem defini-lo (7 falhas unit); às ~14:0x BRT (17:0x UTC) a T4.14 já tinha consertado
os dois em paralelo (`uv run pytest apps/api/tests/unit -q -k meme` → **113 passed**). **Continua no disco:**
`repositories/meme_desk_rows.py:266` `mode=str(row.get("mode") or "paper")` — a variável é `r` →
`NameError: name 'row' is not defined` em **toda** `proposal_from_mapping` (confirmado em runtime: 500 em
`GET /meme/tests` e na mesa; pyright/ruff F821 apontam). Um caractere (`row` → `r`), hunk da T4.14, não
toquei. `check_file_size.py`: 2 acima de 350 (`infra/scripts/meme_vm.py` 361,
`packages/core/hunter_core/settings.py` 352) — não meus.

**Integração da API no tree combinado (um container por arquivo, `timeout 590`):**
- `apps/api/tests/integration/test_meme_desk_repository.py` → 11 failed, 4 passed, 1 xfailed —
  `column meme_tokens.rest_complete_seen_at does not exist`: o schema **local** que o próprio teste cria
  ficou atrás de `repositories/meme_tables.py` (coluna da `0024`, T4.2c). **Pré-existente no HEAD**
  (`git show HEAD:` do teste não cria a coluna; do `meme_tables.py` tem) — não é da T4.11. Esse arquivo é,
  por acaso, o caminho "banco abaixo da `0029`" do leitor tolerante (sonda → 0 → só `None`).
- `apps/api/tests/integration/test_meme_tests_api.py` → 10 failed, 3 passed: (a) o `NameError` `row`
  acima (500 em toda listagem); (b) `test_every_exit_reason_is_seeded_once` exigia `REASONS ==
  ExitReason` → `dead` acrescentado à semente (fecha a **zero**, sem venda, como `rug_no_snapshot`:
  `fill = none`, `sol_usd_at_exit = NULL`; totais: `losses` 2 → 3, `pnl_sol` − 0,2, `unpriced_usd` 1 → 2).
  Com o `row` → `r` da T4.14 aplicado, o arquivo deve ficar verde — **não pude provar** sem tocar no hunk.

```
$ timeout 290 uv run pytest apps/api/tests/unit/test_meme_desk_moonshot.py apps/api/tests/unit/test_meme_tests_service.py -q --noconftest
26 passed in 2.99s
$ timeout 290 uv run pytest apps/api/tests/unit -q -k meme            # com conftest, depois do conserto da T4.14
113 passed, 602 deselected, 1 warning in 1.36s
$ timeout 290 uv run pytest services/meme-worker/tests -q -m unit      # após o isort
177 passed, 47 deselected in 3.04s
$ timeout 290 uv run ruff check <todos os arquivos T4.11 + testes> && ruff format --check <idem>
All checks passed! / 38 files already formatted
$ timeout 290 uv run pyright apps/api/tests/unit/test_meme_desk_moonshot.py apps/api/hunter_api/repositories/meme_desk_marks.py apps/api/hunter_api/repositories/meme_desk.py apps/api/hunter_api/repositories/meme_desk_tables.py apps/api/hunter_api/schemas/meme_tests.py apps/api/tests/integration/test_meme_tests_api.py
0 errors, 0 warnings, 0 informations
$ timeout 590 uv run pytest apps/api/tests/integration/test_meme_tests_api.py -q          # ver acima (NameError da T4.14)
10 failed, 3 passed in 91.11s
$ timeout 590 uv run pytest apps/api/tests/integration/test_meme_desk_repository.py -q   # pré-existente no HEAD
11 failed, 4 passed, 1 xfailed in 33.14s
$ timeout 290 uv run pytest "apps/api/tests/integration/test_meme_tests_api.py::test_every_exit_reason_is_seeded_once" -q
1 passed in 0.32s
```

**Rótulos que o front precisa (`apps/web/components/meme-desk/labels.ts`, fora desta tarefa):**
`mark_source`: `curve` → "marcada pela curva", `pool_tape` → "marcada pela pool (fita)"; `mark_stale_s`
(inteiro, segundos; mostrar quando ≥ 900, i.e. `dead_stale_s`) → "marca envelhecida há {N}s";
`exit.reason` `dead` → "morta"; `params/suggested/decision.exit_on_migration === false` → "segura na
migração"; `trailing_arm_x` → "trailing só depois de {x}×". `pnpm gen:types` regenerado (`api.d.ts`).

**Estado final:** DONE_WITH_CONCERNS — os meus arquivos estão verdes (unit, testcontainer, migrações,
ruff/format, pyright, tamanho); a árvore combinada depende do `row` → `r` da T4.14 para a mesa e o
`/meme/tests` responderem, e o `test_meme_desk_repository.py` já quebrava no HEAD.

```
$ timeout 290 uv run pytest packages/indicators/tests/unit/test_meme_exits_moonshot.py packages/indicators/tests/unit/test_meme_pool.py services/meme-worker/tests/test_lab_params_moonshot.py services/meme-worker/tests/test_pool_mark.py services/meme-worker/tests/test_trades.py -q
54 passed in 2.04s
$ timeout 590 uv run pytest services/meme-worker/tests/test_lab_moonshot.py -q        # testcontainer, sozinho
3 passed in 40.89s
$ timeout 590 uv run pytest packages/core/tests/integration/test_migrations.py -q -k "0029 or 0027 or 0028"
6 passed, 153 deselected in 41.03s
$ timeout 290 uv run pytest services/meme-worker/tests -q -m unit
177 passed, 47 deselected in 2.69s
$ timeout 290 uv run pytest packages/indicators/tests/unit -q
1215 passed in 17.24s
$ timeout 290 uv run pytest packages/core/tests/unit -q -k meme
56 passed, 1275 deselected in 4.46s
$ timeout 290 uv run pyright packages/indicators/hunter_indicators/meme services/meme-worker/hunter_meme_worker packages/core/hunter_core/db/models/meme_lab.py infra/migrations/ddl/meme_moonshot.py <testes T4.11>
0 errors, 0 warnings, 0 informations
$ timeout 290 uv run pytest apps/api/tests/unit -q -k meme
ImportError while loading conftest ... routers/meme_live.py:34: from hunter_core.errors import NotFoundError
E   ModuleNotFoundError: No module named 'hunter_core.errors'          # T4.14 — não é meu
$ timeout 290 pnpm gen:types
🚀 packages/shared-types/openapi.json → packages/shared-types/src/generated/api.d.ts [407.5ms]
$ timeout 290 uv run python infra/scripts/check_file_size.py --max 350 --baseline infra/scripts/file_size_baseline.txt
error   361 > 350  infra/scripts/meme_vm.py            # T4.12/T4.14 — não meu
error   352 > 350  packages/core/hunter_core/settings.py  # idem
scanned 812 files; 2 over budget, 0 grandfathered
```
