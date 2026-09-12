# T4.19 — `operator/3`: a mesa propõe pela porta E1 e cada proposta traz o plano para executar à mão (migração `0033_meme_operator_3`)

Execução de 12/09/2026, ~17:5x → 18:15 BRT. Papel: backend. Brief: `.claude/state/brief-T4.19-operador-3-porta-e1-na-mesa.md`.
Sem commit; nada real; `.env*` intocado; `apps/web/**` intocado (só `pnpm gen:types` → `packages/shared-types`); nenhum
arquivo da lista "Não tocar" da T4.2g tocado (`sources/source_stats/main/collect/trades*/tape*/features*/fold/repo_tape`,
`packages/exchange-adapters/**`). Tudo em primeiro plano, `timeout 290`/`590`.

## Desvio do brief, declarado

- **A revisão é `0033_meme_operator_3`, não `0032`.** Ao começar, a T4.2g já tinha `0032_meme_activity.py` no disco (sobre a
  `0031`) e `HEAD_REVISION` já apontava para ela. A única cadeia linear é `0032 → 0033`; a docstring da revisão e a
  `DATABASE.md` §45 (a §44 é da 0032) dizem isso. `HEAD_REVISION` → `0033_meme_operator_3`; constante nova
  `MEME_ACTIVITY_REVISION`.
- **O plano manual ganhou a cláusula do trailing** ("se recuar 35 % do topo depois de 1,5×"), que a frase do brief não
  tinha. Must-fix da Astra com cenário concreto (marca 2× → 1,3×: o motor vende pelo trailing — `exits.py` —, quem seguisse
  só o texto seguraria). Lida de `trailing_pct`/`trailing_arm_x`, nunca fixa.
- **A semente afirma "exatamente um `operator` ativo"** depois de aposentar `operator/2` e plantar `operator/3` (e depois
  de reverter). Sugestão da Astra: um conjunto plantado à mão, ou um `operator/3` já existente aposentado (`ON CONFLICT DO
  NOTHING` o deixaria assim), deixaria a mesa com dois ou nenhum — recusado, nunca consertado numa migração. Testado
  (`test_0033_refuses_to_upgrade_a_desk_that_already_has_another_active_operator_set`: o upgrade recusado não comita).

## Desenho

1. **`0033` + `ddl/meme_operator_3.py`:** `operator/3` (`…000a`, `kind = operator`, `clock = 15s`) = `'{FLOW_V2_PARAMS}'::jsonb ||
   '{overrides}'::jsonb` — a base é a constante da `0030`, composta em SQL; a sobreposição traz `ttl_s = 180`,
   `max_open_positions = 2` e **reafirma** os números do brief (0,05 SOL, 3×, 35 % após 1,5×, 1800 s, `max_loss` 50 %,
   `exit_on_line_break`, `max_sol_per_bet`/`max_exposure_per_mint_sol` 0,05). Só `ttl_s` e `max_open_positions` diferem da
   base hoje (`test_0033_seeds…` prova `params − ttl_s − max_open_positions = flow_v2/1.params − max_open_positions`).
   `operator/2` aposentado **antes** do insert; downgrade recusa com proposta/aposta sob `operator/3`, apaga, revive `operator/2`.
2. **Worker:** `RuleSetSpec.ttl_s` (opcional; ausente = `lab_proposal_ttl_s` do laço — os conjuntos congelados não mudam);
   `evaluate_gate` usa o `ttl` do conjunto e, só para `kind = operator`, grava `suggested.manual_plan`
   (`proposals_plan.py`, puro: `pt_number`, `ticker_of`, `manual_plan`); `GateRow.symbol` lido de `t.symbol` nos dois
   loaders (`lab_repo._GATE_ROWS`, `lab_repo_fast._FAST_ROWS`); ticker ausente → mint abreviado (`5bmYxJ…`).
   Texto: "Comprar 0,05 SOL de PEPE até 17:33:00 (proposta expira). Vender até 18:00 (30 min) — antes disso se triplicar (3×),
   se recuar 35 % do topo depois de 1,5×, se cair pela metade (−50 %), se o dev vender, ou se a linha de suporte quebrar."
   Palavras só onde o número as tem (2 dobrar / 3 triplicar / 4 quadruplicar; 50 % "pela metade"); fora disso "chegar a N×",
   "cair N %"; `max_hold_s` não múltiplo de 60 → "N s"; horas em `America/Sao_Paulo` (`proposed_at + ttl`, `+ max_hold_s`).
   O laço não mudou: a porta de 15 s já corria todo conjunto `15s`; `operator/3` entra no mesmo passo e propõe a mesma moeda.
3. **API:** `DeskRowOut.manual_plan: str | None` (lido de `suggested.manual_plan`, `_str_or_none`; nunca composto na API) —
   chega em `GET /desk` e em `ProposalOut.row` (o brief dizia `ProposalOut.manual_plan`; `ProposalOut` é `{label, row}` e o
   plano está na linha, onde a mesa lê `suggested`). `OPERATOR_RULE_SET = ("operator", "3")` (documental — a leitura é por
   nome + `status = 'active'`, maior versão). `pnpm gen:types` regenerado (`manual_plan?: string | null`).

## Comandos e saídas (reais, em ordem; BRT)

```
$ uv run pytest services/meme-worker/tests/test_proposals_operator_3.py -q      # 17:5x — TDD: ModuleNotFoundError proposals_plan
$ uv run pytest apps/api/tests/unit/test_meme_desk_manual_plan.py -q            # 2 failed: DeskRowOut sem manual_plan
  → implementação → 7 passed / 2 passed; worker unit 209 passed; api -k meme 120 passed
$ timeout 590 uv run pytest packages/core/tests/integration/test_migrations.py -k 0033 -q   # antes do DDL: [] == ['operator/3…'], FK recusa
  → ddl/meme_operator_3.py + 0033 → 1 failed (asserção minha: f.params ainda tinha max_open_positions) → 3 passed
$ timeout 590 uv run pytest services/meme-worker/tests/test_lab_operator_3.py -q            # 1 failed (UUID vs str no meu teste) → 2 passed
$ bash infra/scripts/astra.sh ask T4.19-operator-3 "…"                           # ver "Segunda opinião" abaixo
  → trailing no plano + guarda "exatamente um operator ativo" + teste da guarda
$ uv run pytest services/meme-worker/tests/test_proposals_operator_3.py -q      → 7 passed
$ timeout 590 uv run pytest services/meme-worker/tests/test_lab_operator_3.py -q → 2 passed
$ timeout 590 uv run pytest …/test_lab_moonshot.py …/test_lab_fast.py …/test_lab_operator_3.py -q → 10 passed  (moonshot lê operator/2 aposentado)
$ timeout 590 uv run pytest services/meme-worker/tests/test_lab_persistence.py -q → 14 passed  (porta de minuto com t.symbol)
$ timeout 590 uv run pytest packages/core/tests/integration/test_migrations.py -q -k "0033"
  2 failed, 2 passed   # 18:0x — as 2 falhas nas linhas 6657/6688 = `command.check(config)`: drift dos CHECKs da 0032 (T4.2g, nomes > 63 chars)
$ timeout 590 … -k "0022 or 0029 or 0030 or every_revision_id_fits or upgrade_head_reaches or downgrade_base_then or new_revision_reverses"
  15 passed in 93.29s  # 18:1x — a T4.2g já tinha corrigido o drift
$ timeout 590 … -k "0033 or alembic_check_reports or upgrade_head_reaches" → 6 passed in 25.14s   # 18:13
$ uv run pytest services/meme-worker/tests -q -m unit → 218 passed   (a T4.2g acrescentou testes em paralelo)
$ uv run pytest apps/api/tests/unit -q -k meme → 121 passed;  packages/indicators/tests/unit → 1246 passed
$ uv run ruff check <meus 16> → All checks passed!;  ruff format --check → already formatted
$ uv run pyright <meus> → 0 errors (o único erro visto no caminho, test_migrations.py:6464, é da seção 0032 da T4.2g)
$ uv run python infra/scripts/check_file_size.py → scanned 853 files; 0 over budget  (meme_desk.py estava em 351: docstring encurtada)
$ pnpm gen:types → api.d.ts: + manual_plan?: string | null  (as mudanças `no_sol_quote` no mesmo arquivo são da T4.2g, regeneradas junto)
```

## Segunda opinião (Astra) — `.claude/state/astra-review-T4.19-operator-3.md`

- **Must-fix aceito:** trailing ausente do plano (cenário 2× → 1,3×). Incluído, lido dos params; testes e docs atualizados.
- **Nice-to-have aceito:** a migração afirmar "exatamente um `operator` ativo" em vez de concluir em silêncio com estado
  divergente. Feito nos dois sentidos + teste de recusa.
- **Rejeitados, com razão:** (a) "30 min desde a proposta" explícito no texto — a hora absoluta é a instrução e o brief fixou a
  base em `proposed_at`; (b) `%H:%M` sem segundos na hora de venda — formato fixado pelo brief ("HH:MM"), precisão de minuto
  basta para 30 min; (c) data/offset no texto (virada de dia/DST) — TTL de 3 min e hold de 30 min tornam a hora inequívoca
  para quem executa; fica anotado. (d) "a CLI não garante unicidade" — fora do escopo (a migração agora garante no seu ato).
- Concordou: composição `jsonb ||` com overrides à direita; aposentar antes de inserir; downgrade recusa proposta/aposta;
  TTL por conjunto sem regressão nos `research_only`; `manual_plan` só em `kind = operator`.
- Aviso do `astra.sh` ("a Astra alterou a árvore: docs/EXCHANGE_INTEGRATION.md, docs/PUMPFUN.md"): são edições concorrentes
  da T4.2g (escopo dela); não toquei nem revertí.

## Arquivos

**Criados:** `infra/migrations/ddl/meme_operator_3.py`, `infra/migrations/versions/0033_meme_operator_3.py`,
`services/meme-worker/hunter_meme_worker/proposals_plan.py`, `services/meme-worker/tests/{test_proposals_operator_3,test_lab_operator_3}.py`,
`apps/api/tests/unit/test_meme_desk_manual_plan.py`, estas notas, `.claude/state/astra-review-T4.19-operator-3.md`.
**Modificados:** `services/meme-worker/hunter_meme_worker/{proposals,lab_models,lab_repo,lab_repo_fast}.py`,
`services/meme-worker/tests/test_lab_moonshot.py` (lê `operator/2` como aposentado), `apps/api/hunter_api/{schemas/meme_desk,services/meme_desk_out,repositories/meme_desk}.py`,
`apps/api/tests/unit/test_meme_desk_moonshot.py`, `packages/core/tests/integration/test_migrations.py` (HEAD, constante, seção 0033,
0029 ajustada para `operator/2` retired), `packages/shared-types/src/generated/api.d.ts`, `docs/{DATABASE,RISK_ENGINE_MEME}.md`,
`docs/plans/T4-MEME-RADAR.md`.

## Pendências para o orquestrador

1. `apps/web` (T4.17): mostrar `row.manual_plan` no cartão da proposta (`proposal-card.tsx`) — o campo já vem em `GET /desk`.
2. Na VPS, após o deploy: `alembic upgrade head` (0032 + 0033); conferir `meme_rule_set.py --list` → um só `operator` ativo (`operator/3`).
3. Obsidian (sugestão da Astra): registrar `operator/3`/aposentadoria de `operator/2`/TTL 180 s nas páginas "Meme — o que uma
   estratégia é aqui" e "A Mesa do operador em papel".
4. O trailing e as recusas pelo pedigree continuam no `suggested`/`reasons`; a mesa ainda é papel — a compra real é à mão e
   a carteira observada (T4.12) grava o que foi feito.
