# Notas T4.35 — histórico de parâmetros + trilha de recusa por moeda, amostrada (16/09/2026)

Execução backend-specialist. Sem commit; nada real; `.env*` intocado. Não tocados (concorrência
declarada no brief): `services/meme-worker/hunter_meme_worker/{lab_models,proposals,proposals_reasons,
lab_repo_e2b,fast_lane}.py`, `packages/indicators/hunter_indicators/meme/pedigree_e2b.py`, migrações
0044/0045, `packages/core/tests/integration/test_migrations.py`, `infra/scripts/meme_close_day*.py`.

## O que ficou pronto

1. **Histórico de parâmetros** (`meme_rule_set_param_history`, migração `0046`). `meme_rule_set.py
   --set-param --apply` grava uma linha por conjunto mudado **na mesma transação** do `UPDATE`
   (`meme_rule_set_params.insert_history_row`). `--history NAME/VERSION` imprime a linha do tempo.
   `--backfill` (dry-run por padrão, `--apply` grava) recupera o que dá dos `system_events` de
   `param_set` **anteriores** a esta revisão, fazendo *parsing* da `message` livre — achado ao
   verificar: `meme_ops_db.record_event` nunca gravou `data` estruturado antes de hoje, só texto.
   Agora grava os dois (`data` jsonb + a `message` de sempre, byte a byte igual, para não quebrar
   quem já lia `message`).
2. **Trilha de recusa por moeda, amostrada** (`meme_gate_refusals_by_mint`, mesma migração `0046`).
   Seletor puro (`hunter_meme_worker.gate_refusal_trail.is_trail_candidate`/`select_trail_row`) e o
   corte por tique (`cap_trail_rows`, padrão 200 linhas) totalmente testados (unit). Repositório
   (`lab_repo_fast.insert_refusal_trail`/`prune_refusal_trail`) testado contra Postgres real —
   idempotente por `(rule_set_id, mint, as_of)`, poda em lote de 7 dias no estilo de
   `repo.prune_tokens`.
3. **Migração `0046`**: `down_revision = "0044_meme_gate_e2b_arm"`, não `0043` (o head commitado).
   Decisão deliberada, desviando da letra do brief: `0044` já existe em disco (não commitado) e a
   suíte compartilhada `services/meme-worker/tests/conftest.py` resolve `"head"` uma vez por sessão —
   ramificar a partir da `0043` teria tornado `"head"` ambíguo para **qualquer** agente concorrente
   rodando essa suíte agora, não só para mim. Confirmado com `ScriptDirectory.get_heads()` → um único
   head (`0046_meme_rule_set_history`) na árvore atual. **Quando `0044`/`0045` forem commitadas, quem
   integrar precisa conferir a cadeia** — pode precisar mover `down_revision` para o que vier depois.
4. Documentação: `docs/DATABASE.md` §54 (as duas tabelas — §53 já pertencia à E2-b, escrita em
   paralelo), `docs/RISK_ENGINE_MEME.md` item 16 da lista de §10 ("por que a moeda X não virou
   proposta").

## O que ficou faltando — a ligação ao tique de 15 s

**Não liguei o seletor ao laço real (`lab_fast.fast_gate_step`).** Duas travas genuínas, não preguiça:

- `proposals.evaluate_gate` hoje devolve `GateOutcome.refusals` **agregado** do lote inteiro (um
  `Counter` por conjunto, não por moeda) — para saber quantos critérios **uma** linha falhou eu
  precisaria ou (a) que `evaluate_gate` exponha esse dado por linha, o que é editar `proposals.py`
  (arquivo de outro agente nesta sessão), ou (b) chamar `evaluate_gate` uma vez por linha em vez de
  uma vez por lote dentro de `fast_gate_step` — comportamento idêntico (o corpo do laço não depende
  de linhas irmãs: `already_open`/`pedigree`/`e2b` já chegam prontos), mas é uma mudança de controle
  de fluxo num laço quente que eu preferi não fazer sem revisão, dado o resto abaixo.
- Os dois lugares óbvios para carregar os dois contadores novos do heartbeat
  (`lab_refusal_trail_rows`/`_capped`) — `LabState` em `lab.py` e `MemeConfig` em `config.py` — já
  estão **exatamente** no teto de 350 linhas (medido antes de eu tocar em qualquer um dos dois:
  `wc -l` deu 350/350). Qualquer campo novo empurra um dos dois para cima do orçamento e exige um
  split primeiro — um refactor de arquivo compartilhado e quente, fora do escopo desta tarefa e
  arriscado numa árvore com outro agente editando módulos vizinhos (`lab_repo_e2b.py`) que `lab.py`
  importa.

**O que falta, concretamente, para quem pegar isto a seguir:** dentro de `fast_gate_step`, para cada
`spec` em `fast`, chamar `evaluate_gate(spec, [row], ...)` por linha (em vez de `evaluate_gate(spec,
rows, ...)` uma vez), somar os `outcome.refusals` como hoje, e para cada linha computar
`gate_refusal_trail.select_trail_row(as_of=row.end_time, rule_set_id=spec.id, mint=row.mint,
refusals=tuple(outcome.refusals.elements()))` (o outcome de uma lista de um elemento é a lista de
recusas *daquela* linha) — depois `cap_trail_rows` e `lab_repo_fast.insert_refusal_trail`. Os dois
campos do heartbeat pedem um split de `lab.py`/`config.py` primeiro (não tentei desenhar o split
aqui — é a próxima tarefa, não um detalhe desta).

## Arquivos

**Criados:** `infra/migrations/ddl/{meme_rule_set_history,meme_gate_refusals}.py`,
`infra/migrations/versions/0046_meme_rule_set_history.py`,
`packages/core/tests/integration/test_migration_0046.py`,
`infra/scripts/{meme_rule_set_types,meme_rule_set_params}.py`,
`services/meme-worker/hunter_meme_worker/gate_refusal_trail.py`,
`services/meme-worker/tests/{test_gate_refusal_trail,test_lab_repo_fast_trail}.py`, esta nota.

**Modificados:** `infra/scripts/{meme_ops_db,meme_rule_set}.py`,
`infra/scripts/tests/test_meme_ops_mayhem.py` (um import movido),
`services/meme-worker/hunter_meme_worker/lab_repo_fast.py`,
`docs/{DATABASE,RISK_ENGINE_MEME}.md`.

## Comandos e saídas (reais)

```
$ uv run pytest packages/core/tests/integration/test_migration_0046.py -q          → 8 passed (18.01s)
$ uv run pytest services/meme-worker/tests/test_gate_refusal_trail.py -q -m unit   → 13 passed (0.59s)
$ uv run pytest services/meme-worker/tests/test_lab_repo_fast_trail.py -q          → 5 passed (20.23s)
$ uv run pytest infra/scripts/tests/test_meme_ops_scripts.py infra/scripts/tests/test_meme_ops_mayhem.py -q
  → 19 passed (0.68s)
$ uv run pytest services/meme-worker/tests infra/scripts/tests -q -m unit         → 413 passed, 264 deselected (19.76s)
$ uv run pytest services/meme-worker/tests -q -m "integration and not live"       → 1 failed, 88 passed (638.15s)
  FAILED test_persistence.py::test_retention_prunes_only_what_aged_out_and_needs_the_marker
  — não é meu: mesmo arquivo isolado → 11 passed (26.02s). Colisão de dado entre suítes na sessão
  cheia (mint `T426B_RETRO` de outro teste, FK de `meme_event_matches`), nada em meme_tokens/retenção
  tocado por esta tarefa.
$ uv run ruff check <22 arquivos meus>                → All checks passed!
$ uv run ruff format --check <idem>                    → 2 reformatados por mim antes de checar
$ uv run pyright <arquivos de produção + testes meus>  → 0 errors, 0 warnings, 0 informations
```

`check_file_size.py` e o gate completo do brief ficam no relatório final (rodados antes de reportar).
