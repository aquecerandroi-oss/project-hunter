# T4.27 — o mcap teórico das moedas Mayhem não é preço (notas de execução)

Relógio da máquina ao escrever: 15/09/2026 22:4x BRT (16/09 01:4x UTC). O brief e a KB-0098 falam em
"16/09 02:2x BRT"; os nomes de arquivo seguem o brief (`2026-09-16-t427-*`), os horários abaixo são os
da máquina. Nada real; nenhum `.env*` lido; nenhum `git add/commit/stash`.

## 1. O que foi entregue (mapa)

| Entrega do brief | Onde |
|---|---|
| 1. Preço executável | `packages/indicators/hunter_indicators/meme/curve.py` (`quote_sell(..., real_sol_reserves=)`, `sell_all_value_sol`, `SellQuote.real_sol_cap_applied`); `hunter_indicators/meme/executable.py` (novo: `executable_market_cap_sol`, `sell_cap_sol`, `is_mayhem_curve`, `EXECUTABLE_DEFINITIONS` v1); marca: `services/meme-worker/hunter_meme_worker/paper_engine.py` (`mark_bet`/`close_bet`, `exit.real_sol_cap_applied`, `exit.mark_basis`), `lab_values.Snapshot.mayhem_enabled` + `sell_cap_sol()`, `lab_rows.snapshot_from_row`, `lab_repo_bets` (`mayhem_enabled` na foto e `t.mayhem_enabled` na aposta), `lab_models.BetState.is_mayhem`; séries: `features.py` (1m), `fast.py`/`features_fast.py`/`repo_fast.py` (15 s), `collect.py`, `fold.py`, `fast_lane.py`; migração `infra/migrations/versions/0042_meme_executable_mcap.py` + `ddl/meme_executable_mcap.py`; modelos `meme_features.py`/`meme_features_15s.py`; docs `RISK_ENGINE_MEME.md` §6, `T4-MEME-RADAR.md` §4 |
| 2. Portão | `rules.py` (`EntryGate.exclude_mayhem=True`, `EntryFeatures.is_mayhem`), `rules_criteria.mayhem_refusals` (`mayhem_curve` / `mayhem_unknown`), `lab_models._gate_from_params`, `proposals.py`/`proposals_row.py` (`GateRow.mayhem_enabled/mayhem_state`, `entry_features_of`), `lab_repo_fast._FAST_ROWS` (15 s), `lab_repo_mayhem.py` (novo: o flag do relógio de minuto), `lab.py` (chama `load_gate_rows_with_mayhem`), `wallets_lab.py`; script `infra/scripts/meme_rule_set.py --set-param KEY=VALUE --all-active|--rule-set … --apply --reason` (novo subcomando); páginas `obsidian/05-EXPERIMENTS/EXP-M1…M7` (avaliação datada "Mayhem excluído desde 16/09 (T4.27)") |
| 3. Placar retroativo | `infra/scripts/meme_reclassify_mayhem.py` (novo; dry-run por padrão; motivo `mayhem_virtual_sol`) |
| 4. Estudo "bum real" | `infra/scripts/sql/research/2026-09-16-t427-bum-real.sql`; `obsidian/11-KNOWLEDGE/KB-0098-…md` §5 (a KB-0098 já existia com o nome do orquestrador — apêndice em vez de segunda KB-0098) + `Index.md` |
| 5. Testes / qualidade | `packages/indicators/tests/unit/test_meme_executable.py` (11), `services/meme-worker/tests/test_mayhem_mark.py` (8), `services/meme-worker/tests/test_lab_mayhem.py` (3, testcontainer), `infra/scripts/tests/test_meme_ops_mayhem.py` (8), `packages/core/tests/integration/test_migrations.py` (4 testes `0042`; `HEAD_REVISION = 0042`; os 3 testes `0041` que usavam `"-1"` passaram a `_staged_at(0041)`) |

## 2. Definições numéricas (as suposições, declaradas)

- **Marca (posição):** `bruto = min(S·q/(T+q), real_sol_reserves)`, `taxa = bruto × fee%`, `líquido = bruto − taxa`.
  O teto vale quando a moeda não é **sabidamente** padrão (bit da foto → `mayhem_enabled` do token → desconhecido
  mantém o teto, que numa curva padrão não prende) **e** a curva não está `complete` (o SOL foi para a pool). O
  teto nunca se aplica à primeira marca do fill (o bruto da venda imediata é ≤ cofre + custo por construção).
- **`mcap_executable_sol`:** `min(mcap_sol, real_sol_reserves)` em Mayhem; `= mcap_sol` em padrão e em flag
  desconhecido sem `mayhem_state` (`active`/`paused`/`completed` são testemunhas; `unknown` não). NULL com
  `mcap_sol` NULL e em Mayhem sem `real_sol_reserves` na foto. **Não é preço; é teto.** Alternativa descartada:
  `min(S, S0 + real)/T × supply` (precisaria de `initial_virtual_sol_reserves`, nem sempre gravado).
- **Precisão:** teste Hypothesis (200 caminhos compra→venda da curva 30×300): numa curva padrão o teto muda o
  líquido em < 1e-20 SOL (arredondamento de 28 dígitos quando um só holder vende a compra inteira) e nunca prende
  para quem detém menos que a compra inteira.
- **Portão:** `mayhem_unknown` recusa (falha fechado). Consequência: as fixtures de teste passaram a dizer
  `is_mayhem=False`/`mayhem_enabled=False` (`test_meme_rules*.py`, `test_meme_replay.py`, `test_proposals.py`,
  `test_lab_persistence._token`); no replay, uma captura sem o bit é recusada `mayhem_unknown` (teste atualizado).
- **Patamares do "bum real":** a curva enche a 85,005 SOL reais (registro 2025-07-18); 100/300/1 000 SOL reais
  não existem numa curva — as três colunas do SQL devem ler 0. Patamares reais: 10/30/60 SOL e "encheu"
  (≈ 50/112/252/411 SOL de mcap teórico numa curva padrão).

## 3. Consulta por tique (regra T4.24b) — `lab_repo_mayhem.mayhem_flags_for`

```sql
SELECT mint, mayhem_enabled, mayhem_state FROM meme_tokens WHERE mint = ANY(:mints)
```
Limites: `mints` = os mints das linhas do minuto (o conjunto acompanhado, ~130); savepoint próprio
(`begin_nested`) com `SET LOCAL statement_timeout = 2000`; falha → `{}` (as linhas ficam `mayhem_enabled = None` e
todo portão recusa `mayhem_unknown` — falha fechado) + `meme_mayhem_flags_read_failed` no log. Plano esperado na VPS
(105 k linhas, PK em `mint`): `Index Scan using pk_meme_tokens on meme_tokens … Index Cond: (mint = ANY (…))`. No
container de teste (tabela vazia) o planejador escolhe `Seq Scan`; o teste `test_the_minute_gate_refuses_a_mayhem_coin…`
executa o `EXPLAIN` e só afirma a forma. **Orquestrador:** rodar na VPS
`EXPLAIN (ANALYZE, BUFFERS) SELECT mint, mayhem_enabled, mayhem_state FROM meme_tokens WHERE mint = ANY(ARRAY['<mint1>','<mint2>'])`
e colar aqui. É temporário: quando `lab_repo.py` (T4.26) liberar, `t.mayhem_enabled, t.mayhem_state` entram em
`_GATE_ROWS` e `lab_repo_mayhem.py` sai. O relógio de 15 s já lê as duas colunas em `_FAST_ROWS` (sem consulta extra).

## 4. Pendências para o orquestrador (fora do que a T4.27 podia tocar)

1. `services/meme-worker/hunter_meme_worker/repo.py::_FEATURE_COLUMNS` (T4.26 em voo): acrescentar
   `"mcap_executable_sol"` — uma linha. Sem ela a série de **minuto** calcula o valor mas o `INSERT` deixa a coluna
   NULL (o teste `test_the_minute_gate_refuses_a_mayhem_coin_by_name_and_reads_its_flag_bounded` afirma o NULL de
   propósito e diz por quê). A série de 15 s já grava (`repo_fast._ROW_COLUMNS` deriva do dataclass).
2. `lab_repo.py::_GATE_ROWS`: `t.mayhem_enabled, t.mayhem_state` (e então apagar `lab_repo_mayhem.py`).
3. `proposals_reasons.py` (T4.26): listar `exclude_mayhem`/`is_mayhem` no bloco de razões da proposta.
4. Rótulo web (fora da tarefa): `mayhem_curve` → "curva Mayhem (SOL virtual do agente)"; `mayhem_unknown` →
   "Mayhem não lido"; `outcome_quality_reason = mayhem_virtual_sol` → "marca era SOL virtual do agente Mayhem";
   `exit.mark_basis = real_sol_reserves` → "vendida pelo SOL real do cofre". Gráficos da T4.25: trocar `mcap_sol`
   por `mcap_executable_sol` (ou desenhar os dois).
5. Rodar na VPS, nesta ordem: `alembic upgrade head` (0042); `uv run python infra/scripts/meme_rule_set.py --set-param
   exclude_mayhem=true --all-active --reason "T4.27: os picos de mcap sao SOL virtual do agente Mayhem, nao demanda"`
   (dry-run) e depois `--apply`; `uv run python infra/scripts/meme_reclassify_mayhem.py` (dry-run) e depois
   `--apply --reason "T4.27: a marca era SOL virtual do agente Mayhem, nao o que a curva pagaria"`; `psql -f
   infra/scripts/sql/research/2026-09-16-t427-bum-real.sql` e colar as 4 tabelas na KB-0098 §5.
6. Falhas pré-existentes / da T4.26 vistas ao rodar a suíte (não tocadas): `test_proposals_flow.py::test_exp_m1_reasons…`
   (razão `identity` extra — T4.26), `test_events_persistence.py` (CHECK `a_twitter_link_names_its_kind` — T4.26),
   `test_migrations.py::test_0041_*` (downgrade "cannot drop columns from view"; `_CLEAN_0041` sem `app.meme_retention`
   — T4.26) e `test_downgrade_base_then_upgrade_head` (cai no downgrade da 0041), `test_lab_operator_3.py` (`operator/4`
   aposentado pela 0039), `test_lab_lines.py::test_a_probe_scales_once…` (`creator_unknown`/`symbol_unknown` do pedigree
   — token de teste sem criador/símbolo).
