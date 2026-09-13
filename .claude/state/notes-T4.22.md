# Notas T4.22 — `organic_v0/1`, a orgânica lenta (E3) (13/09/2026, 01:1x–02:0x BRT, orquestrador; agentes no limite semanal)

**Por quê:** 12/09 fechou 35 apostas medidas a −9,4 R; `high_water_x ≤ 1,0` em 31 de 35 (compramos no topo); `creator_dump`
em 22. Todos os conjuntos vivos compram 30–300 s depois da criação. Pedido do Everton (13/09 01:0x): "então aprimore essa parte".

**Entregue:**
- `rules.py`: `max_top10_share` (fração, validado em [0, 1], listado em `as_parameters` só quando pedido) +
  `EntryFeatures.top10_share/top10_reason`; `rules_criteria.hype_refusals`: `top10_above_max` / `top10_<motivo>`.
- Worker: `GateRow.top10_share/top10_reason` (`proposals.py`), lidos da série de minuto (`lab_repo.py`:
  `f.top10_share, f.top10_share_reason`); a série de 15 s não os tem → `top10_unknown` (E3 é de minuto);
  `lab_models.py` lê `max_top10_share`.
- Migração `0035_meme_organic_e3` (`ddl/meme_organic_e3.py`): `organic_v0/1` (`…000d`, `research_only`, EXP-M7, `clock 1m`)
  = `FLOW_V2_PARAMS || E3`; nada aposentado; downgrade recusa com referências. `HEAD_REVISION → 0035`; `E1_ARM2_REVISION`;
  `test_0034_refuses_a_downgrade…` estagiado (`_staged_at`); `test_0035_*` (2).
- Obsidian: EXP-M7 pré-registrada (previsão `descartar`, P1–P5), Experiments Index (2 tabelas), Meme/README; docs
  `DATABASE.md` §47, plano §T4.22, `RISK_ENGINE_MEME.md` §10.11.

**Provas (saídas reais):** indicators `-k meme` 227 (4 novos em `test_meme_rules_organic.py`); worker unit 221;
`test_migrations -k "0034 or 0035 or alembic_check or upgrade_head"` 9 passed (45 s, Postgres); ruff/format/pyright 0;
`check_file_size` 0 acima (`rules.py` 350 — no teto); `obsidian_lint` base limpa.

**Prova na VPS após o deploy:** `organic_v0/1` ativo (8 conjuntos), recusas `organic_v0` no heartbeat com `progress_below_min`/
`holders_below_min`/`top10_*` dominando (P1), 0 reinícios; primeira proposta quando houver.

**Fora desta tarefa:** T4.2h (vendas do criador em tempo real pela cadeia — vigiar a conta de tokens do criador dos mints
com aposta aberta a cada 15 s e sair no primeiro decréscimo).
