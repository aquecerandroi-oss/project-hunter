# Notas T4.23 — dois braços irmãos da E1, contradizendo o próprio pré-registro (15/09/2026, 16:2x–17:1x BRT)

**Por quê:** o fechamento diário de 13/09 (`obsidian/09-OPERATIONS/Diario-Meme/2026-09-13.md` §6.4/§6.5, 66 apostas
medidas, IC 95 % por blocos de hora, repetido pelo lote de 14/09) mediu `snipers > 2` a R médio +0,25 (n = 17) contra
−0,28 nas demais (n = 49) — Δ +0,53 R, IC [0,23, 0,88] — e `top10_share` em 0,1767–0,257 a +0,25 (n = 14) contra
−0,25 nas demais (n = 52) — Δ +0,50 R, IC [0,14, 1,36]. Os dois contradizem o pré-registro da própria E1
(`snipers ≤ 2`, sem piso em `top10_share`); pela régua (KB-0092) isso não move os conjuntos vivos — vira dois braços
irmãos pré-registrados `descartar`, medidos ao lado.

**Entregue:**
- **Regras (`packages/indicators/hunter_indicators/meme/rules.py`/`rules_criteria.py`):** `min_snipers` (recusa
  `snipers_below_min`) e `min_top10_share` (recusa `top10_below_min`), pisos ao lado dos tetos já existentes
  (`max_snipers`, `max_top10_share`), desligados por padrão; um valor desconhecido recusa pelo próprio motivo mesmo
  sem teto (restruturei `hype_refusals` em `_snipers_refusals`/`_top10_refusals`); `as_parameters` lista as duas
  chaves só quando pedidas; validações (piso ≥ 0, piso ≤ teto quando os dois existem). **20 testes novos**
  (`test_meme_rules_e1_arms_3_4.py`, `ARM_3`/`ARM_4` = `ARM_2` + as chaves).
- **`rules_validation.py` (novo):** todas as validações de `EntryGate.__post_init__` extraídas para cá — `rules.py`
  ia para 353+ linhas com as duas chaves novas; a extração o deixa em 341.
- **Worker:** `lab_models.py` lê `min_snipers`/`min_top10_share` (`GateRow` já carregava `snipers`/`top10_share`
  desde T4.21/T4.22 — nenhuma mudança em `proposals.py`/`lab_repo*.py`).
- **Migração `0037_meme_e1_arms_3_4`** (`ddl/meme_e1_arms_3_4.py`): `flow_v2/3` (`…000e`) = `flow_v2/2`
  (`ARM2_OVERRIDES` sobre `FLOW_V2_PARAMS`) + `min_snipers 3` (`max_snipers 10` já era do braço 2); `flow_v2/4`
  (`…000f`) = `flow_v2/2` + `min_top10_share "0.1767"`, `max_top10_share "0.257"` (nenhuma das duas chaves existia
  no braço 2); nada aposentado — `flow_v2/1`, `flow_v2/2` e a mesa (`operator/4`) continuam ativos. Downgrade recusa
  com proposta ou aposta referenciando qualquer um dos dois (§17.7).
- **`test_migrations.py`:** `HEAD_REVISION` foi para `0038_meme_creator_watch_live` — a `0038` (T4.2h-b) chegou ao
  mesmo tempo em cima da `0037`; `test_0036_*` estagiado em `CREATOR_WATCH_REVISION` (padrão `_staged_at`);
  `E1_ARMS_3_4_REVISION` novo, e os `test_0037_*` (4, incluindo `test_0037_refuses_...` e
  `test_0037_reverses_on_a_clean_database_and_comes_back`) estagiam nele pela mesma razão — a mesma cortesia que
  cada revisão nova já dá à anterior desde a `0033`.
- **Achado fora do escopo, corrigido de passagem:** `alembic_check` estava quebrado desde a `0036` (T4.2h, 13/09) —
  `ck_meme_paper_bets_creator_balance_reason_is_a_known_label` existe no DDL mas nunca foi declarado no modelo ORM
  (`hunter_core/db/models/meme_lab.py`); um comentário no próprio arquivo dizia isso ser proposital ("a reason's
  label CHECK lives in ddl/meme_creator_watch.py only"), o que não é verdade — o autogenerate detecta a diferença e
  `test_alembic_check_reports_no_drift`/`test_downgrade_base_then_upgrade_head` falhavam há dois dias sem que
  ninguém rodasse `alembic_check` para notar (T4.2h não incluiu esse teste nas provas). Adicionei o `CheckConstraint`
  que faltava em `meme_lab.py` (a docstring do módulo foi comprimida em 3 linhas para caber no teto de 350 — ficou em
  350 exatas). A metade equivalente de `meme_live_positions` (`0038`) foi corrigida pela T4.2h-b antes desta tarefa
  terminar, de forma independente.
- **Docs:** `DATABASE.md` §49, plano `T4-MEME-RADAR.md` §T4.23, `RISK_ENGINE_MEME.md` §10 item 13; EXP-M5 ganha
  "Braços 3 e 4 (15/09/2026)" (append-only, previsão `descartar`, contradição com o braço 1 declarada).

**Provas (saídas reais):** indicators `-k meme` **247 passed** (227 antes + 20 novos); worker unit **218 passed**
(`-m unit`, 75 deselected); `test_migrations -k "0036 or 0037 or alembic_check or upgrade_head"` **7 passed (60 s,
Postgres)**; ruff 0, `ruff format --check` 0 (9 arquivos), pyright 0; `check_file_size.py` **0 acima** (`rules.py`
341, `meme_lab.py` 350 exatas). `obsidian_lint.py`: base limpa (286 notas).

**Concorrência (T4.2h-b, ao mesmo tempo):** essa agente estava em `creator_watch.py`, `sources.py`, o executor,
`apps/web`, `hunter_core/db/models/meme_live.py` e `services/meme-worker/hunter_meme_worker/main.py` — nenhum
tocado por mim. A migração dela (`0038_meme_creator_watch_live`) já existia com `down_revision =
"0037_meme_e1_arms_3_4"` antes de eu terminar (coordenação prévia do orquestrador nos ids); reconciliei
`test_migrations.py` bumping `HEAD_REVISION` e estagiando meus testes, sem tocar no conteúdo dela.

**Fora desta tarefa:** validação prospectiva dos braços 3/4 (o Lab mede sozinho, régua ≥ 100 apostas e 30 dias);
qualquer mudança a conjunto vivo (nenhuma régua de descarte foi atingida hoje).
