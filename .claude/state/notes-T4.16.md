# T4.16 — a porta v2 (fluxo e holders), o relógio de 15 s e o placar honesto (migração `0030_meme_gate_v2`)

Execução de 12/09/2026, início 14:56 BRT (17:56 UTC). Papel: quant/backend. Brief:
`.claude/state/brief-T4.16-porta-v2-e-relogio-de-15s.md`; estudo de origem:
`obsidian/03-TRADING/Meme/Estudo-2026-09-12-21-apostas.md` (E1 = `flow_v2/1`, E2 = exclusões de pedigree).
Sem commit; nada real; `.env*` intocado; `apps/web/**` intocado; arquivos da T4.8b e da T4.15 intocados
(`pumpfun/{tx,verify,trade_event,quote}.py`, `services/meme-executor/**`, `meme_close_day*.py`,
`meme_diary*.py`). Nenhum processo em segundo plano; todo comando com `timeout 290` (590 nos testcontainers).

**Árvore ao começar (17:56Z):** HEAD `8122dc7` (o brief dizia `2e14972`; os commits por cima são de
plantão/briefs — nenhuma migração acima da `0029_meme_moonshot`, logo a minha é **`0030_meme_gate_v2`**).
Já modificados por outros, não meus: `.claude/launch.json`, `docs/DESIGN.md`; `??` em `.claude/state/**`.

## Desenho (decisões, antes de codar)

1. **Placar honesto.** `meme_paper_bets.outcome_quality text NOT NULL DEFAULT 'measured'` ∈ {`measured`,
   `indeterminate`} + `outcome_quality_reason text` + `outcome_quality_at timestamptz`; CHECKs: rótulo
   conhecido; `indeterminate` ⇒ `status = 'closed'`; `(outcome_quality = 'indeterminate') = (reason IS NOT
   NULL)` = `(… = (outcome_quality_at IS NOT NULL))`. O laço fecha `rug_no_snapshot` já como
   `indeterminate` (`reason = no_snapshot_in_window`); as linhas do dia 12/09 são reclassificadas pelo
   script auditado `infra/scripts/meme_reclassify_indeterminate.py --apply --reason "…"` (dry-run por
   padrão; grava `system_events`). `pnl_sol`/`r_multiple` da linha **não mudam** (o CHECK
   `an_exit_carries_its_numbers` exige os números; o simulador recebeu 0) — quem muda são as **somas**:
   `meme_lab_scoreboard_v1` (reescrita: `wins`/`pnl_sol`/`pnl_usd`/`r_sum`/drawdown só sobre `measured`,
   coluna nova `indeterminate`), `/meme/tests` (totais: `indeterminate` à parte; `wins`/`losses`/`pnl`/`r`
   só medidas), a carteira derivada do laço (`wallet_state`: saldo e `realized_today` só medidas — em
   12/09 os 5 artefatos somavam −0,25 SOL, acima do teto diário de 0,20: o artefato travava o Lab) e o
   fechamento diário (T4.15 lê `outcome_quality`; declarado nas notas para o orquestrador).
2. **Relógio de 15 s.** Laço novo `meme-fast` (`fast_lane.py`, 15 s): mints rastreados com `created_at`
   conhecido e idade < 300 s, não concluídos, cotação em SOL → `get_curve_states` (≤ 2 chamadas de 100 +
   ≤ 2 `getBlockTime`) → `persist_reading(count_request=False)` (o mesmo caminho da T4.2f) → linhas
   `meme_features_15s` (`meme_features_15s_v1`, PK `(as_of, mint, features_version)`, RANGE mensal por
   `as_of`, retenção **7 d** em `partition_retention.py` — em partições mensais isso significa "o mês
   cai quando o seu fim tem mais de 7 dias", declarado). Não-antecipação **no SQL e no puro**: pontos com
   `received_at <= as_of` (fotografias), trades com `received_at <= as_of` (fita, `tape_for` reaproveitado
   com `end_time = as_of`), leituras de holders com `received_at <= as_of`. Features instantâneas
   (`hunter_indicators.meme.fast`, `FeatureDefinition` v1): `mcap_delta_60s`, `mcap_slope_60s` (OLS de
   ln mcap, fração/min — `log_slope` das linhas), `progress_delta_60s`, `holders_rising` (duas leituras
   seguidas), fita dos últimos 60 s. O Lab passa a bater a **15 s** (`lab_cycle_s = 15`): a porta de minuto
   fechado só roda quando um minuto fechou (já era assim: `closed_minutes`), a porta de 15 s roda sobre as
   linhas novas de `meme_features_15s` (`as_of <= now`, atraso máximo 45 s), e **fills e vendas passam a
   ser avaliados a cada 15 s** — a fotografia seguinte de uma moeda jovem chega em 15 s.
   `decision_to_fill_s_p50/p95` medidos sobre os fills do processo (`entry.decision_to_fill_s`).
3. **Porta v2.** `EntryGate` ganha critérios opcionais (todos desligados por padrão — a EXP-M1/M2/M3/M4
   continuam byte a byte): `require_positive_flow` (`net_sol_flow_1m > 0`, ou `mcap_delta_60s > 0` quando
   a fita falta), `min_unique_buyers`, `max_sells_to_buys`, `require_holders_rising`,
   `require_progress_rising`. Conjuntos semeados na `0030` (`research_only`, `clock = 15s`): `flow_v2/1`
   (EXP-M5) e `hype_probe_v0/2` (a sonda + fluxo; registrada como braço 2 da EXP-M5 — a EXP-M3 recebe a
   avaliação `descartar` e aponta a sucessora). **E2** (EXP-M6): `hunter_indicators.meme.pedigree`
   (`exclusoes_de_pedigree v1`: `creator_prior_mints_1h ≥ 2` → `creator_serial`, `symbol_dup_24h ≥ 3` →
   `symbol_clone`, desconhecido recusa por nome), aplicado a **todo** conjunto pela porta (1 min e 15 s),
   contado a partir de `meme_tokens` na hora da proposta (`lab_repo.pedigree_for`). Aposentadoria de
   `meme_paper_v0/1` e `hype_probe_v0/1`: **não** pela migração — pelo script auditado
   `infra/scripts/meme_rule_set.py --deprecate name/version --reason "…" --apply` (o orquestrador roda na
   VPS; `system_events` registra).
4. Heartbeat: `fast_lane_mints`, `fast_lane_reads_60s`, `fast_lane_cycle_s`, `fast_lane_calls_60s`;
   `lab_decision_to_fill_s_p50/p95`, `lab_bets_indeterminate_total`; `/meme/sources` os expõe; a mesa
   (`BetOut`) ganha `decision_to_fill_s` e `outcome_quality`; `/meme/tests` ganha `outcome_quality` +
   rótulo "indeterminado (sem fotografia)" por linha e `indeterminate` nos totais.

## Comandos e saídas (reais, em ordem)

**Cadeia de migrações (achado às 18:05Z):** a T4.15 já tinha no disco `0031_meme_lab_ticks.py` com
`down_revision = "0029_meme_moonshot"` e o docstring dela diz "the merge that lands both must point
`down_revision` at `0030` (one line)". Não toco no arquivo dela. Para provar a minha `0030` com a cadeia
linear (0029 → 0030 → 0031) sem duas cabeças, os conftests do core (integração) e do meme-worker ganharam
um override **só de teste** `HUNTER_MIGRATIONS_DIR` (padrão = a árvore; a CI nunca o define), e rodei
contra uma cópia de `infra/migrations` em `%TEMP%\claude\t416-migrations` onde a única diferença é essa
linha da `0031` (`refresh_migrations.sh` na scratchpad; a scratchpad em si tem 261 caracteres de caminho —
acima do `MAX_PATH` do Windows para o `os.access` do Python, por isso o destino curto).
**Para o orquestrador:** ao juntar, mudar `down_revision` da `0031` para `"0030_meme_gate_v2"`;
`HEAD_REVISION` em `test_migrations.py` já aponta para `0031_meme_lab_ticks`.

```
$ timeout 290 uv run pytest packages/indicators/tests/unit/test_meme_fast.py test_meme_pedigree.py test_meme_rules_flow.py test_meme_rules.py test_meme_rules_lines.py -q
84 passed in 1.33s                                   # 18:12Z — puro: série de 15 s, pedigree, fluxo, porta antiga byte a byte
$ timeout 290 uv run ruff check <novos + editados>   → All checks passed!
$ timeout 290 uv run ruff format <idem>              → 4 files reformatted, 21 files left unchanged
$ HUNTER_MIGRATIONS_DIR=…/t416-migrations timeout 590 uv run pytest packages/core/tests/integration/test_migrations.py -q \
    -k "0030 or 0029 or upgrade_head_reaches or partitioned_parent or 0022_seeds or alembic_check"
10 passed, 155 deselected in 53.85s                  # 18:31Z — 0030 sobe/recusa/reverte; 0029 reestagiada; head = 0031; partições; 8 ativos; alembic check
$ timeout 290 uv run pytest services/meme-worker/tests -q -m unit          # 18:40Z, 1.ª rodada após o pedigree
14 failed, 163 passed   # pedigree=None recusava tudo como pedigree_unknown → semântica: o chamador OPTA passando o mapa
177 passed, 47 deselected in 2.72s                   # 18:44Z (após o ajuste; meme_lab.py/meme_gate_v2.py/sources.py divididos p/ caber em 350)
$ timeout 290 uv run pytest services/meme-worker/tests/test_features_fast.py test_fast_lane.py test_proposals_flow.py test_outcome_quality.py -q
1 failed, 19 passed    # percentile: round(p·n + 0,5) ≠ nearest-rank → ceil(p·n); o teste estava certo
$ timeout 290 uv run pyright apps/api/hunter_api services/meme-worker/hunter_meme_worker → 0 errors
$ timeout 290 uv run pytest services/meme-worker/tests -q -m unit → 197 passed, 52 deselected in 3.27s   # 18:52Z
$ timeout 290 uv run pytest apps/api/tests/unit -q -k meme → 118 passed (com test_meme_outcome_quality.py: 5)
$ timeout 290 uv run pytest infra/scripts/tests/test_meme_ops_scripts.py -q → 6 passed in 0.55s
$ HUNTER_MIGRATIONS_DIR=… timeout 590 uv run pytest services/meme-worker/tests/test_lab_fast.py -q   # sozinho
3 failed, 2 passed     # (1) _CLOSE_BET: `CASE WHEN … THEN :exit_at END` fazia o asyncpg deduzir text para $1 → bind próprio outcome_quality_at
1 failed, 4 passed     # (2) referência de 60 s é a foto de −60 s (30,5): delta 3,5 — asserção errada, comentário certo
1 failed, 4 passed     # (3) contagens dependentes de linhas de outros testes na sessão → asserções por mint/conjunto
5 passed in 52.99s                                   # 18:53Z
$ HUNTER_MIGRATIONS_DIR=… timeout 590 uv run pytest services/meme-worker/tests/test_lab_persistence.py -q
7 failed, 5 passed     # o mesmo (1) do _CLOSE_BET
1 failed, 11 passed    # a porta congelada via `creator_unknown` antes de `creator_net_seller_unknown` → recusas do pedigree SOMADAS às da porta
12 passed in 119.49s                                 # 18:4xZ (estourou os 120 s da ferramenta e foi a segundo plano — saída lida do arquivo; daí em diante timeout explícito)
$ HUNTER_MIGRATIONS_DIR=… timeout 590 uv run pytest packages/core/tests/integration/test_migrations.py -q -k "0028 or 0027 or 0026"
9 passed, 156 deselected in 65.77s                   # o estágio delas passa pela 0030/0031 (guardas limpas)
$ timeout 290 uv run ruff check <116 arquivos meus> → All checks passed!
$ timeout 290 uv run ruff format --check <idem> → 116 files already formatted
$ timeout 290 uv run pyright <idem> → 0 errors, 0 warnings, 0 informations
$ timeout 290 uv run python infra/scripts/check_file_size.py --max 350 --baseline infra/scripts/file_size_baseline.txt
error 353 > 350 apps/api/hunter_api/services/meme_desk_out.py; error 351 > 350 sources.py   → docstrings enxugadas
scanned 841 files; 0 over budget, 0 grandfathered   # 18:58Z
$ timeout 290 uv run python infra/scripts/obsidian_lint.py
Valores fora do vocabulário (2): result = 'descartada'   → 'reprovada' (vocabulário: inconclusivo|validada|reprovada|nao-iniciado)
RESULTADO: base limpa                                # 18:58Z
$ timeout 290 pnpm gen:types
packages/shared-types/openapi.json → packages/shared-types/src/generated/api.d.ts [559ms]   # +40 linhas: outcome_quality, decision_to_fill_s, fast_lane_*, lab_decision_to_fill_s_*, indeterminate
```

## Arquivos (meus)

**Criados:** `packages/indicators/hunter_indicators/meme/{fast,pedigree,rules_criteria}.py`;
`packages/indicators/tests/unit/{test_meme_fast,test_meme_pedigree,test_meme_rules_flow}.py`;
`packages/core/hunter_core/db/models/{meme_features_15s,meme_lab_commands}.py` (o segundo é `MemeOperatorCommand`
movido de `meme_lab.py` pelo teto de 350, reexportado);
`infra/migrations/versions/0030_meme_gate_v2.py`, `infra/migrations/ddl/{meme_gate_v2,meme_gate_v2_seed,meme_gate_v2_view}.py`;
`infra/scripts/{meme_ops_db,meme_reclassify_indeterminate,meme_rule_set}.py`, `infra/scripts/tests/test_meme_ops_scripts.py`;
`services/meme-worker/hunter_meme_worker/{fast_lane,features_fast,repo_fast,lab_fast,lab_repo_fast,lab_heartbeat,proposals_reasons}.py`;
`services/meme-worker/tests/{test_fast_lane,test_features_fast,test_proposals_flow,test_outcome_quality,test_lab_fast}.py`;
`apps/api/hunter_api/repositories/meme_desk_quality.py`, `apps/api/tests/unit/test_meme_outcome_quality.py`;
`obsidian/05-EXPERIMENTS/{EXP-M5-fluxo-e-holders,EXP-M6-exclusoes-de-pedigree}.md`; estas notas.

**Modificados:** `packages/indicators/hunter_indicators/meme/rules.py`; `packages/core/hunter_core/db/models/{__init__,meme_lab}.py`;
`packages/core/tests/integration/{conftest,test_migrations,test_schema_privileges}.py`; `infra/migrations/ddl/meme_wallets.py`
(`recreate_scoreboard_0027`); `infra/scripts/partition_retention.py`; `services/meme-worker/hunter_meme_worker/{config,lab,lab_bets,lab_models,lab_repo,lab_repo_bets,lab_values,main,paper_engine,proposals,sources}.py`;
`services/meme-worker/tests/{conftest,test_lab_persistence}.py`; `apps/api/hunter_api/{repositories/{meme_desk,meme_desk_rows,meme_lab,meme_tests},schemas/{meme_desk,meme_lab,meme_sources,meme_tests},services/{meme_desk_out,meme_lab,meme_sources,meme_tests},routers/meme_tests}.py`;
`docs/{DATABASE,PIPELINE,RISK_ENGINE_MEME}.md`, `docs/plans/T4-MEME-RADAR.md`; `obsidian/05-EXPERIMENTS/{EXP-M1-…,EXP-M3-…,Experiments Index}.md`,
`obsidian/03-TRADING/Meme/README.md`; `packages/shared-types/src/generated/api.d.ts`.

**Não meus, vistos na árvore:** T4.15 (`0031_meme_lab_ticks.py`, `ddl/meme_lab_ticks.py`, `models/meme_lab_ticks.py`,
`lab_ticks.py`, hunk `record_tick` em `lab.py` — preservado —, `meme_close_stats.py`, `test_meme_close_*.py`, §42 do
`DATABASE.md`, hunk em `test_schema_privileges.py`), T4.8b (`pumpfun/{tx,verify,trade_event,program_identity}.py`,
`meme-executor/**`, fixtures `t48b_*`, KB-0094), plantão (`Hipoteses-do-plantao.md`, `Diario/2026-09-12.md`).

## Suposições numéricas e decisões que o brief não fixa

- `flow_v2/1`: `max_open_positions = 5` (horizonte de 30 min num relógio de 15 s), `wallet 2,0`, `dia 0,20`,
  `line_break_snapshots = 2`, `dev_share_unknown_allowed = false` ("dev_share ≤ 0,10" sem exceção no brief).
- `hype_probe_v0/2` fica no **relógio de 1 min**: o `hype_score` é feature do minuto (fita + board do minuto) e a
  série de 15 s não tem board; registado como braço 2 da EXP-M5 (`exp_ref = EXP-M5`), com a EXP-M3 apontando a sucessora.
- Série de 15 s: janela 120 s, referência = foto mais nova com `observed_at ≤ newest − 60 s` (sem ela: `too_few_points`);
  `holders_rising` = leitura mais recente > anterior (instantes distintos, `received_at ≤ as_of`).
- Pedigree: `creator_prior_mints_1h > 1` e `symbol_dup_24h > 2` (outras moedas; a própria conta), só moedas
  criadas **até** a julgada; desconhecido recusa por nome; recusas **somadas** às da porta (não curto-circuito);
  `pedigree=None` = o chamador não pediu (o scale step e os testes da porta sozinha); mint fora do mapa = `pedigree_unknown`.
- Carteira do laço e teto diário: só desfechos `measured` — declarado (os 5 artefatos travariam o Lab a −0,25 SOL).
- `lab_cycle_s = 15`: fills/vendas/heartbeat 4×/min; a porta de minuto continua 1×/minuto fechado; `meme_lab_ticks`
  (T4.15) passa a receber 4 linhas/min (~5 760/dia).
- Retenção de `meme_features_15s` = 7 d em partições **mensais** (o mês cai quando o fim dele tem > 7 dias).
- `decision_to_fill_s_p50/p95` = nearest-rank sobre os últimos 200 fills do processo (deque); vazio = "" no heartbeat.
- A migração **não** aposenta nada: `meme_rule_set.py --deprecate` (auditado) é o caminho; a `0030` semeia 2 conjuntos.

## Pendências para o orquestrador / próximas tarefas

1. **Cadeia:** ao juntar, `0031_meme_lab_ticks.py` → `down_revision = "0030_meme_gate_v2"` (a linha que a própria
   T4.15 pediu); depois `test_migrations.py -k "0030 or 0031"` na árvore real (sem `HUNTER_MIGRATIONS_DIR`).
2. **Na VPS, após o deploy:** `uv run python infra/scripts/meme_reclassify_indeterminate.py --day 2026-09-12`
   (dry-run) e depois `--apply --reason "artefato do simulador antes de 12:14 BRT: sem fotografia por 3 min; mcap 30 min depois = entrada"`;
   `uv run python infra/scripts/meme_rule_set.py --deprecate meme_paper_v0/1 --reason "EXP-M1: descartar (9/9 negativas, 5 artefato)" --apply`
   e `--deprecate hype_probe_v0/1 --reason "EXP-M3: descartar (8/8 sondas em giro); sucessora hype_probe_v0/2" --apply`.
3. T4.15: o fechamento diário e `meme_diary*.py` devem ler `outcome_quality` (hoje contam `rug_no_snapshot` como perda).
4. CSV de `/meme/tests` sem a coluna `outcome_quality` (o teste de bytes do T4.13 congela as colunas) — a API já a traz.
5. Rótulos do `apps/web` (`components/meme-desk/labels.ts` e `/meme/sources`), fora desta tarefa:
   `outcome_quality`: `indeterminate` → "indeterminado (sem fotografia)", `measured` → "medido"; `totals.indeterminate` → "indeterminadas";
   `bet.decision_to_fill_s` → "decisão → fill {N}s"; `reasons[0].series = meme_features_15s_v1` → "porta de 15 s";
   `fast_lane_mints` → "moedas < 5 min no relógio de 15 s", `fast_lane_reads_60s`/`fast_lane_calls_60s` → "leituras/chamadas por minuto",
   `lab_decision_to_fill_s_p50`/`_p95` → "decisão → fill p50/p95 (medido)", `lab_bets_indeterminate_total` → "indeterminadas (total)";
   recusas: `creator_serial` → "criador em série", `symbol_clone` → "clone de ticker", `pedigree_unknown` → "pedigree não lido",
   `creator_unknown`/`symbol_unknown` → "criador/ticker desconhecido", `flow_not_positive` → "sem demanda líquida",
   `flow_<motivo>` → "fluxo: sem fita (<motivo>)", `buyers_below_min` → "poucos compradores", `buyers_unknown` → "compradores desconhecidos",
   `sells_ratio_above_max` → "giro (vendas/compras)", `no_buys` → "sem compras", `holders_not_rising` → "holders não sobem",
   `holders_<motivo>` → "holders: <motivo>", `progress_not_rising` → "progresso não sobe", `progress_trend_unknown` → "tendência do progresso desconhecida";
   `/meme/lab` `indeterminate` → "indeterminadas".

## `git status --porcelain` (só os meus; 19:0xZ)

Ver a lista de 45 ` M` + 30 `??` na saída do comando de 18:56Z acima no histórico da sessão — reproduzida no
relatório final. Nenhum `.env*`, nenhum `apps/web/**`, nenhum arquivo da T4.8b/T4.15 tocado; `lab.py` carrega o
hunk `record_tick` da T4.15 intacto.
