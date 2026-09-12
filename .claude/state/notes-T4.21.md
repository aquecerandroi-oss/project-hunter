# Notas T4.21 — `operator/4` + `flow_v2/2`, o segundo braço da porta E1 (12/09/2026, 19:1x–19:5x BRT)

A agente (backend-specialist, fable) entregou `rules.py`/`rules_criteria.py` + `test_meme_rules_e1_arm2.py` (11 testes)
e foi cortada pelo limite semanal; o orquestrador fechou o resto:

- **Regras (parte 1, commit 5ea43ac):** `min_holders`, `holders_rising_or_flat`, `creator_unknown_allowed_if_dev_measured`,
  `progress_or_mcap_rising` — desligadas por padrão; `creator_refusals` extraído; indicators `-k meme` 223.
- **Worker:** `GateRow.holders/holders_prev` (`proposals.py`), lidos em `lab_repo.py` (minuto: `prev.holders`) e
  `lab_repo_fast.py` (15 s: `f.holders, f.holders_prev`), passados a `EntryFeatures`; `lab_models.py` lê as quatro chaves.
- **API:** `OPERATOR_RULE_SET = ("operator", "4")` (`repositories/meme_desk.py`) e o teste que o afirma.
- **Migração `0034_meme_gate_e1_arm2`** (`ddl/meme_gate_e1_arm2.py`): `flow_v2/2` (`…000b`, EXP-M5) e `operator/4`
  (`…000c`) = `FLOW_V2_PARAMS || overrides`; `operator/3` aposentado antes do insert; invariante "um operator ativo";
  downgrade recusa com referências e revive `operator/3`. `HEAD_REVISION → 0034`; `OPERATOR_3_REVISION` novo; os quatro
  `test_0033_*` estagiados em `_staged_at(upgraded, OPERATOR_3_REVISION)` (classe com `__enter__/__exit__`, porque o
  pyright do projeto marca `contextmanager` como deprecado); quatro `test_0034_*` espelham os da 0033.
- **`test_lab_operator_3.py`** passa a provar `operator/4` × `flow_v2/2` (fixture com `holders=24, holders_prev=21`,
  porque o braço 2 exige ≥ 20; `rule = fluxo_e_holders/2`).
- **Provas (saídas reais):** worker unit **221**; API `-k meme` **121**; indicators `-k meme` **223**; `test_migrations -k
  "0033 or 0034 or alembic_check or upgrade_head"` **11 passed (55 s)**; `test_lab_operator_3` + `test_lab_moonshot` +
  `test_lab_persistence` **19 passed (227 s)**; ruff/`ruff format --check`/pyright 0; `check_file_size` 0 acima (853).
- **Docs:** `DATABASE.md` §46, plano §T4.21, `RISK_ENGINE_MEME.md` §10.10, EXP-M5 "Braço 2" (previsão `descartar`).
- **Prova na VPS após o deploy:** `operator/4` e `flow_v2/2` ativos, `operator/3` retired, `flow_v2/1` ativo; primeira
  proposta `operator/4` com `manual_plan` (esperado 1–4 por hora pelo funil); 0 reinícios.
- **Fora desta tarefa:** o lote não traz vendas do criador (`creator_net_seller_unknown` fica alto; o braço 2 só o
  contorna quando `dev_share` foi medido) — T4.2h.
