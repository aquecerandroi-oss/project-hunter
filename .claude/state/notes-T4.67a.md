# Notas T4.67a — a pista de lançamento (radar, EXP-M18)

Data: 2026-09-19. Escopo: `services/meme-worker/hunter_meme_worker/launch_lane*.py` (novo),
`packages/indicators/hunter_indicators/meme/launch_lane.py` (novo, gate puro),
`packages/indicators/hunter_indicators/meme/curve.py` (+`INITIAL_REAL_TOKEN_RESERVES`),
`context.py`/`discovery.py`/`main.py` (fiação), `paper_engine.py`/`meme_bets.py` (dois motivos de
saída + CHECK de `mark_source` alargado), migração `0053`, `.env.example`,
`infra/vps/docker-compose.prod.yml`, `docs/RISK_ENGINE_MEME.md` §9, `docs/DATABASE.md` §43.2/§60.
Não tocado: `services/meme-executor/` (agente T4.67b, rodando em paralelo na mesma árvore — ver §6).

## 1. Decisão de gatilho (o brief pedia medir e escolher)

**Escolhido: o stream `create` do PumpPortal**, já em produção via `discovery.py` — não um novo
`logsSubscribe` program-wide no programa pump. Razão: o próprio `plan-T4.52b.md` §1 já mediu e
descartou o caminho program-wide para qualquer uso além de uma PDA já conhecida (item 8, só
per-mint); construir e decodificar um `CreateEvent` nunca antes visto, sobre uma assinatura de
altíssimo volume, sem fixture e sem medição própria, gastaria o orçamento inteiro desta tarefa
num transporte que a tabela do próprio `plan-T4.52b.md` já classifica como ~100 ms — a mesma ordem
de grandeza do que já está rodando. Não fiz uma nova medição ao vivo (o brief permite reusar
medição existente); isso é uma simplificação declarada, não uma medição nova.

## 2. Arquitetura entregue

- `hunter_indicators.meme.launch_lane` (puro): `LaunchGate`/`LaunchFeatures`/`evaluate_launch` — os
  quatro critérios do brief, cada um com o refuso "unknown" próprio; `reconstruct_initial_real_token_reserves`
  (inverte a identidade de T4.45: `initial_virtual_token_reserves + creator_initial_tokens −` o gap
  fixo do programa `= initial_real_token_reserves`) e `initial_real_token_reserves_is_sane` (1 % de
  tolerância contra a constante `INITIAL_REAL_TOKEN_RESERVES = 793 100 000`, nova em `curve.py`).
- `hunter_meme_worker.launch_lane_symbols.RecentSymbols`: o clone de símbolo em 60 s, em memória —
  deliberadamente **não** o `symbol_dup_24h` de `pedigree.py` (esse é de 24 h, lido do banco; caro
  demais para o orçamento de 200 ms).
- `hunter_meme_worker.launch_lane_repo.LaunchRuleSpec`: parse próprio de `meme_rule_sets`, **não**
  `RuleSetSpec.from_params` (que exige `gate_key`/`min_age_s`/... que `launch_v0/1` não tem) nem
  `CLOCKS` (que nunca lista `"event"` — por isso as pistas de 15 s/1 min pulam esta linha sem
  precisar de nenhuma mudança nelas).
- `hunter_meme_worker.launch_lane_entry`: um `create` → `ProposalDraft` (reaproveitando a classe de
  `proposals.py`) ou os refusos nomeados; `quote.reason = "no_snapshot_at_create"` (não existe
  snapshot ainda) e `reasons[0].series = "meme_launch_lane_v1"`.
- `hunter_meme_worker.launch_lane_pricing` (puro): `entry_point`/`born_full`/`exit_trigger` sobre o
  **mesmo** `MintEventState` do portão de evento (T4.52b-2) — nenhuma série nova. `standard_reserves`
  reconstrói as reservas virtuais de uma foto só com o token real (invariantes de uma curva padrão:
  `virtual − real` constante e `S·T = k` constante — as duas provadas por teste).
- `hunter_meme_worker.launch_lane_bets`: abre/fecha a aposta de papel reaproveitando **de verdade**
  `BetEntry`/`BetExit`/`BetState`/`EffectiveParams`/`mark_filled`/`close_bet_row` (`lab_repo_bets.py`)
  e `paper_engine.close_bet` — não um segundo caminho de escrita. `EffectiveParams.target_x` recebe
  um sentinela (1000) para que uma aposta órfã (o processo caiu entre abrir e fechar) que o tique do
  Lab venha a pegar feche pelo `time_stop_s` honesto, nunca pelo alvo.
- `hunter_meme_worker.launch_lane_eval`/`launch_lane.py`: o fold de notificação + as duas escritas
  (`on_create`, `progress_mint`) e os quatro laços (`_read_loop`/`_sweep_loop`/`_spec_refresh_loop`/
  `_heartbeat_loop`) — split em dois arquivos pelo orçamento de 350 linhas, a mesma divisão de
  `event_gate.py`/`event_gate_eval.py`.
- `launch_lane_wiring.py`: `build_launch_lane` (usa o mesmo `SOLANA_RPC_WS_URL`/`MEME_EVENT_COMMITMENT`
  resolvidos do portão de evento) + `register_launch_lane_health` (`/ready` nunca vermelho).

## 3. "Nasce cheia" — leitura declarada do brief

O brief diz "`born_full_60s` (progresso ≥ 90 % em 2 s ⇒ não proposto, contado)". Isso é
cronologicamente impossível ao pé da letra: a proposta sai em < 200 ms, bem antes de 2 s existirem.
Minha leitura: a proposta em si permanece (é a decisão da pista no instante do `create`, o registro
de auditoria), mas a **entrada em papel pendente é abandonada** se o progresso atingir 90 % dentro
de 2 s antes que o preço de +1 s exista — contado em `born_full_60s`. Documentado aqui e em
`docs/RISK_ENGINE_MEME.md` §9; é uma interpretação, não uma certeza, e está sinalizada para revisão.

## 4. Mudança de schema (`0053`, além do seed)

`meme_paper_bets.mark_source` precisava de um terceiro rótulo (`solana_ws` — a pista nunca lê
`meme_curve_snapshots`); o CHECK `ck_meme_paper_bets_mark_source_is_a_known_label` foi alargado de
`{curve, pool_tape}` para `{curve, pool_tape, solana_ws}` na própria `0053` (dois `ALTER TABLE`
separados — asyncpg recusa dois comandos numa só prepared statement) e **nunca** estreitado no
downgrade (uma aposta já fechada sob o valor novo não pode ficar sem CHECK que a explique).
`packages/core/hunter_core/db/models/meme_bets.py` (`MARK_SOURCES`, o CHECK do ORM) atualizado
junto para que `alembic check` continue limpo. Também adicionei `first_third_party_sell` e
`max_drawdown_from_peak` a `BET_EXIT_REASONS`/`paper_engine.EXIT_REASONS` (vocabulário de
documentação, nenhum dos dois imposto por CHECK real).

## 5. Simplificações declaradas

1. **Testes de integração "replay" o formato decodificado, não os bytes da wire.** O decode de
   `TradeEvent` a partir de `logsSubscribe` já está provado (T4.52b-1); construir bytes Borsh válidos
   à mão só para este teste testaria o decoder outra vez, não a lógica da pista. Os testes chamam
   `MintEventState.apply_trade`/`progress_mint` diretamente com `NormalizedCurveTrade` construídos.
2. **`creation_buyers = {creator}`** — só o criador pode comprar dentro da própria transação de
   `create` no pump.fun padrão; não há uma lista de "compradores do bloco de criação" no frame.
3. **A pista carrega seu próprio `SolanaWsClient`**, separado do portão de evento — não depende de
   `MEME_EVENT_GATE` estar ligado, e nunca compete pelo mesmo teto de assinaturas.
4. **Um pequeno buraco de partida**: `_spec_refresh_loop` e `_discovery` (que chama `on_create`)
   correm no mesmo `TaskGroup`; um `create` que chegue antes da primeira leitura de `launch_v0/1`
   simplesmente não vê spec nenhuma (nenhuma proposta, nenhum crash) — um punhado de segundos na
   subida do processo, nunca depois.

## 6. Para o orquestrador — achado no §18 do T4.67b (não fiz nada aqui)

`docs/RISK_ENGINE_MEME.md` §18 (escrito pelo agente T4.67b, em paralelo) registra: *"Hoje a T4.67a
não escreve `creation_slot`/`known_buyers`, então toda [...]"* — o executor parece querer esses dois
campos na proposta/decomposição para o seu próprio "terceiro comprador". Não escrevi nenhum dos
dois (não estavam no meu brief); registrando aqui para quem decidir se uma T4.67a-2 os adiciona.

## 7. Comandos

- `uv run pytest packages/indicators/tests/unit/test_meme_launch_lane.py -q` → 15 passed.
- `uv run pytest services/meme-worker/tests/test_launch_lane_symbols.py test_launch_lane_entry.py
  test_launch_lane_pricing.py test_launch_lane_wiring.py -q` → 32 passed.
- `uv run pytest services/meme-worker/tests/test_launch_lane_integration.py -q` (testcontainers) →
  2 passed (~17 s).
- `uv run pytest services/meme-worker/tests -q -m "not live and not integration"` → 435 passed (era
  373 antes desta tarefa + as 62 novas puras).
- `uv run pytest packages/core/tests/integration/test_migration_0053.py -q` → 8 passed (~34 s).
- `uv run pytest packages/core/tests/integration/test_migration_0052.py -q` → 8 passed (ainda
  intacto depois do CHECK alargado).
- `uv run pytest packages/core/tests/integration/test_migrations.py -q -k "0022 or head or
  autogenerate or reverses"` → 45 passed (~5 min 15 s).
- `uv run ruff check`/`format` limpos nos arquivos tocados. `uv run pyright` 0 erros nos arquivos
  tocados. `uv run python infra/scripts/check_file_size.py` → 0 acima do orçamento (`launch_lane.py`
  387→ dividido em `launch_lane.py`+`launch_lane_eval.py`, ambos < 350).

## Concerns

- A leitura de "nasce cheia" (§3) e a escolha de gatilho (§1) são interpretações declaradas, não
  certezas — ambas sinalizadas para revisão de quem aceitar o braço.
- Árvore compartilhada com o agente T4.67b (executor) durante toda a tarefa: `docs/DATABASE.md`,
  `docs/RISK_ENGINE_MEME.md`, `.env.example`, `infra/vps/docker-compose.prod.yml` e
  `packages/core/hunter_core/db/models/meme_bets.py` foram editados por ambos, sem sobreposição (`git
  diff --stat` conferido arquivo a arquivo) — mas o orquestrador deve revisar o merge final com
  atenção antes de commitar.
