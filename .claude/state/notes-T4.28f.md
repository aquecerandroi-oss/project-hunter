# Notas T4.28f — carência por mint depois de recusa determinística + um tique de graça antes de travar os portões

Execução: 2026-09-16, ~12:4x–13:1x BRT. Papel: guardião do motor de risco (brief do orquestrador).
Nenhum `.env*` lido ou escrito, nenhuma migração, nenhuma rede, VPS não tocada. Suítes com
testcontainers **não** rodadas (Docker indisponível nesta máquina — os 19 casos de
`test_live_persistence.py`, incluindo os 2 novos, pularam com o motivo registrado).

## 1. Carência por mint (`recently_refused`)

Medida que motivou (T4.28e §"Fora deste hotfix"): a mesa (`operator/5`) repropõe o mesmo mint a cada
~20 s; em 16/09 11:46–11:48 BRT o robô abriu a mesma moeda 5 vezes e a admissão recusou as 5 por
`progress_below_window`. Custo por repetição: uma leitura RPC da curva, uma linha `refused` e uma
proposta `rejected`. Não custa dinheiro; custa ruído e uma janela de decisão.

- **Conjunto congelado realmente usado** (7 nomes, todos conferidos contra
  `hunter_risk_meme.checks.REFUSAL_NAMES` — o teste prova o subconjunto):
  `progress_below_window`, `progress_above_window`, `token_too_old`, `token_age_unknown`,
  `program_not_allowed`, `unsupported_quote`, `progress_denominator_missing`.
- **Descartados do conjunto do brief, e por quê:**
  - `creator_serial`, `symbol_clone`, `mayhem_curve`, `mayhem_unknown` — **não existem** em
    `checks.py`; são recusas da *porta do radar* (`hunter_meme_worker.rules_criteria`) e nunca
    aparecem em `meme_live_orders.reason`. O brief mandava conferir e derrubar o que não existisse.
  - `token_too_young` — **existe**, mas é a recusa que o **relógio sozinho** limpa: a janela abre em
    `token_age_min_s` (30 s no `MEME_PAPER_V0`), então uma carência de 120 s seguraria uma moeda que
    ficou admissível 90 s antes. É exatamente a família que o próprio brief manda **não** bloquear
    (`curve_state_stale`, `volume_unavailable`, `marks_incomplete`, `wallet_over_max_sol`). A regra
    que ficou escrita no código: *recusa que o relógio limpa nunca esfria; recusa que precisa do
    mercado ou do banco mudar, sim.*
- **Onde:** `hunter_meme_executor/refusal_cooldown.py` (novo — o `auto_approve.py` passaria de 350
  linhas, `infra/scripts/check_file_size.py` reprova; o módulo novo é a decisão inteira num lugar):
  `DETERMINISTIC_REFUSALS`, `refusal_window_start` (pura), `cooling_mints_of` (pura),
  `refusal_cooling_mints` (uma consulta por passe) e o SQL — parametrizado, sem `$`, pelo índice
  existente `ix_meme_live_orders_status_received_at`:
  `SELECT p.mint, o.reason FROM meme_live_orders o JOIN meme_proposals p ON p.id = o.proposal_id
   WHERE p.decided_by = :by AND o.side = 'buy' AND o.status = 'refused' AND o.received_at >= :since`.
- `plan_auto_approvals` ganhou `cooling_mints` (como `busy_mints`) e o pulo `recently_refused`, logo
  depois de `mint_busy`; `auto_approve_once` lê os mints e passa. O pulo sai no heartbeat em
  `auto_skipped.recently_refused` (nada novo a publicar).
- `config.py`: `auto_approve_refusal_cooldown_s` (padrão 120 s, env
  `MEME_LIVE_AUTO_APPROVE_REFUSAL_COOLDOWN_S`, `max(0, …)` — `0` desliga a consulta **e** o pulo).
- **Nada aqui cria ou libera ordem**: um mint esfriando simplesmente não tem proposta aberta; a linha
  fica `proposed` para o clique do Everton e a admissão não é chamada. A carência atrasa, não proíbe.

## 2. Portões: um tique de graça antes de travar por falha de leitura

`nano` grava no lugar (não atômico); um tique podia dar `stat`+leitura no meio da gravação e travar
`gates_invalid:gates_file_invalid` um processo com dinheiro real, com retomada manual por contrato
(§7). Agora:

- falha de **parse** (`GRACE_REASONS = {gates_file_invalid, gates_file_missing}`) na primeira vez é
  **adiada**: nada trava, nada é trocado, a política anterior segue valendo, log
  `meme_executor_gates_reload_deferred`;
- o **tique seguinte** decide: parseia ⇒ releitura normal (sem trava, sem erro pendurado); falha de
  novo (mesmo `mtime` ou um novo) ⇒ **trava**. Um estado adiado força a releitura mesmo com o `mtime`
  parado — é isso que "ainda falhando no tique seguinte" significa;
- invalidade **semântica** (`gates_expired`, `gate_c_owner_not_enabled`, `small_test_expired`,
  `auto_approve_needs_small_test`) continua travando **na hora**: é um arquivo completo dizendo não;
- `ExecutorState.gates_deferred_failure` / `gates_deferred_mtime_ns`; `GatesReload.deferred`;
  heartbeat `gates_reload_error = "deferred:<motivo>"` enquanto a graça corre, motivo cru depois da
  trava (`heartbeat._reload_error`).

## 3. Provas

- `uv run pytest services/meme-executor/tests -q -x` → **83 passed, 19 skipped** (antes: 62/17).
- Novos: `test_auto_approve.py::TestRefusalCooldown` (6 casos: conjunto ⊆ `REFUSAL_NAMES` + a
  fronteira `token_too_young`/gate-only; 30 s esfria; 200 s não; `curve_state_stale` não; cooldown 0;
  um mint esfriando não esconde outro) + `TestBoot::test_the_refusal_cooldown_comes_from_the_environment`;
  `test_gates_reload.py` (17 casos, 5 novos/reescritos: semântico trava no 1º tique, parse trava no
  2º, segunda gravação quebrada trava, meio-arquivo que vira válido só recarrega, arquivo apagado
  adiado→travado→uma linha só, arquivo que volta antes do 2º tique nunca trava);
  `test_live_persistence.py` (2 novos, Postgres — pulam sem Docker):
  `test_the_cooldown_query_reads_only_this_executors_deterministic_refusals` (mint do clique, venda,
  status não-recusado, fora da janela e motivo reversível: nenhum esfria) e
  `test_stage_1_does_not_reopen_a_mint_it_just_had_refused` (nenhuma ordem escrita, proposta segue
  `proposed`, heartbeat mostra o pulo).
- **Quatro mutações, todas mordidas** (aplicadas e revertidas): (a) tirar `and deferred is None` da
  guarda de `mtime` ⇒ falha `test_a_file_that_stopped_parsing_latches_on_the_second_tick`; (b) tirar o
  pulo `recently_refused` ⇒ falha `test_a_mint_refused_thirty_seconds_ago_is_not_reopened`; (c) pôr
  `token_too_young` no conjunto ⇒ falha `test_every_cooling_reason_is_a_real_admission_refusal`;
  (d) dar graça a `gates_expired` ⇒ falha `test_a_semantically_invalid_edit_latches_on_the_first_tick`.
- `ruff check` / `ruff format --check` / `pyright` nos 9 arquivos tocados: limpos (0 erros).
  `infra/scripts/check_file_size.py`: 0 acima do orçamento (era 1 antes do split).
- Docs: `RISK_ENGINE_MEME.md` §3.5 (carência, com os dois conjuntos) e §7.1 (graça de um tique +
  `deferred:` no heartbeat); `ACTIVATION.md` §9b item 9 (o conselho do `mv` atômico continua).

## 4. Ressalvas

1. **`progress_below_window` não é imóvel.** Depois do conserto de unidade da T4.28e ele quer dizer
   "progresso real < 2 %", e uma moeda em pump pode cruzar a janela em segundos. Cenário de perda:
   mint a 1,8 % às 12:00:00 é recusado; às 12:00:20 está em 3 % e a mesa repropõe — o robô pula por
   `recently_refused` até 12:02:00. Não perde dinheiro (nenhuma ordem existe), perde entrada. Segui o
   brief (foi o caso medido), mas se isso incomodar o remédio barato é uma carência mais curta só
   para as duas recusas de progresso (`…_REFUSAL_COOLDOWN_S` já é por ambiente; hoje é um número só
   para todos os motivos) ou reabrir quando a leitura de curva mostrar o cruzamento.
2. **A graça dá ~10 s a mais de operação sob a política anterior** quando o arquivo está mesmo
   quebrado. A política anterior é a que o dono assinou e já estava valendo, e a alternativa medida
   era travar por uma gravação pela metade — mas está registrado.
3. O SQL novo **não** foi executado contra Postgres aqui (sem Docker): foi compilado no dialeto
   `postgresql` (parametrizado, sem `$`) e os dois testes de container existem e estão corretos por
   leitura do schema `0028_meme_live`. **Rodar `pytest services/meme-executor/tests -q` numa máquina
   com Docker antes de subir.**
4. `gates_deferred_*` não sai na API (como `gates_mtime`/`gates_reloaded_at`, T4.28d §4.2): ver pelo
   Redis (`HGETALL hb:meme:executor`, campo `gates_reload_error`) ou pelo log.

## 5. Commit

**Não commitado por mim.** A instrução permanente deste papel é explícita — *"Do NOT commit"* — e
nenhum brief de agente a substitui (mesma decisão da T4.28d). Árvore limpa do meu lado; o commit por
pathspec que o orquestrador (ou o Everton) pode rodar:

```
git add -- services/meme-executor/hunter_meme_executor/auto_approve.py \
  services/meme-executor/hunter_meme_executor/refusal_cooldown.py \
  services/meme-executor/hunter_meme_executor/config.py \
  services/meme-executor/hunter_meme_executor/context.py \
  services/meme-executor/hunter_meme_executor/gates_reload.py \
  services/meme-executor/hunter_meme_executor/heartbeat.py \
  services/meme-executor/tests/test_auto_approve.py \
  services/meme-executor/tests/test_gates_reload.py \
  services/meme-executor/tests/test_live_persistence.py \
  docs/RISK_ENGINE_MEME.md docs/ACTIVATION.md .claude/state/notes-T4.28f.md
git commit -- <os mesmos arquivos>
```

Mensagem combinada: `feat(meme-executor): T4.28f — auto-approve cools a mint after a deterministic
refusal; gates reload gets one-tick grace before latching`, corpo curto e trailer
`Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. **Atenção:** a árvore compartilhada tem
`.claude/launch.json`, `docs/DESIGN.md` e `packages/core/tests/unit/test_settings.py` modificados por
outro trabalho — nunca `git add -A` aqui.
