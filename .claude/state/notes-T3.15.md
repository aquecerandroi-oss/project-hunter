# Notas T3.15 — `purpose` na versão e o rótulo `paper` (D10)

Fechada pelo orquestrador em 2026-09-07 depois de duas quedas de agente por limite semanal da conta (Sonnet e Opus). O agente anterior deixou os itens 1–3 do brief prontos na árvore; o orquestrador entregou o 4 e o 5, corrigiu o que apareceu nos portões e rodou tudo.

## Entregue
1. **`0010_strategy_purpose`** (`infra/migrations/{versions/0010_strategy_purpose.py,ddl/strategy_purpose.py}`): coluna `purpose text NOT NULL DEFAULT 'research_only'` + CHECK dos três rótulos; trigger de congelamento da `0002` substituída com `purpose` na lista; `hunter_worker` perde INSERT/UPDATE de tabela e recebe os dois por coluna, todas menos `purpose` (REVOKE de coluna não estreita GRANT de tabela — medido); downgrade recusa enquanto houver linha fora de `research_only`. `docs/DATABASE.md` §22.
2. **Envelope lê da versão**: `catalogue.py` carrega `purpose`, recusa `live` na origem (`purpose_live_forbidden`); `record.py` grava `meta.purpose`, o payload do evento **e** `envelope["purpose"]` com `version.purpose` (o `SignalEnvelope` das estratégias nasce `research_only` porque o código não sabe a coorte; o carimbo é do worker — foi o ponto que o teste de ponta a ponta pegou).
3. **Portão de admissão**: `PURPOSE_PAPER` em `hunter_core.strategies.envelope`; `ProposalRequest.purpose` default `paper`; `origin()` recusa `live` por nome ("live é Fase 4; ENABLE_LIVE_TRADING=false") e `research_only` como antes; ordem manual da API nasce `paper`.
4. **Script de ativação `--paper-line`** (`infra/scripts/activate_strategy_version.py` → lógica em `hunter_strategy_worker/{activation_db,paper_line}.py` por orçamento de 350 linhas): deriva `v<n+1>` livre, `draft`, `purpose=paper`, conteúdo copiado da linha congelada, `code_ref` recalculado e conferido, uma linha paper não deprecada por estratégia, `system_events`; `activate` resolve pelo `code_ref` congelado quando o registro não nomeia a versão, e recusa `purpose=live`. `--dry-run` em todos os modos.
5. Docs: `DATABASE.md` §22, `PIPELINE.md` (linha do envelope), `plans/SHADOW-LAB.md` item 10.

## Tabela papel × `strategy_versions.purpose`
| Papel | `purpose` | Demais colunas |
|---|---|---|
| `hunter_app` | SELECT | SELECT |
| `hunter_worker` | SELECT | SELECT, INSERT, UPDATE por coluna |
| dono (migrações / script) | tudo | tudo |

## Correções feitas nos portões
- `services/strategy-worker/tests/builders.py`: `activate_version` só nomeia `purpose` quando não é o default, e então com `RESET ROLE` + `SET LOCAL ROLE` de volta (o worker não pode nomear a coluna — é a própria garantia da 0010).
- `packages/core/tests/integration/test_schema_constraints.py::test_a_system_kill_switch_row_can_never_carry_an_organization`: quebrado desde a 0006 (o CHECK "an automatic move shows its numbers" avalia antes do de escopo); o INSERT do teste passa a levar `evidence`.
- `test_activation.py`: aponta para `script.migration_applied` (nome novo depois da divisão).

## Saída real
test_migrations 49 · test_schema_privileges 23 · test_schema_paper 96 · test_schema_shadow 53 · test_schema_rls 17 · test_schema_constraints 13 · test_admission 17 · test_admission_reservation 10 · core unit 706 · api unit 382 · api test_admission_adapter 10 · strategy-worker: test_activate_paper_line 6, test_activation 12, test_version_roster 9, test_shadow_decisions 15, test_code_ref 23, unit 159. ruff check/format limpos; pyright 0; check_file_size 0 over budget (465 arquivos). `alembic check` = `test_alembic_check_reports_no_drift` dentro de test_migrations.

## Pendências
- **T3.15b**: `bridge_screen.py` importa `PURPOSE_PAPER` e admite `paper` (hoje aceita só `live`, então a ponte continua sem admitir nada — coerente com "nada ativa").
- Revisões obrigatórias (database-architect, risk-engine-guardian, security-reviewer) não rodaram: cota. Astra volta 12/09.
- Nada foi ativado. Nenhuma linha `paper` existe em banco nenhum.
