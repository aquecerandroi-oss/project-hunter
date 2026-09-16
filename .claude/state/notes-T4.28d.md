# Notas T4.28d — o executor meme relê o `meme_gates.json` em voo (mtime), sem `docker restart`

Execução: 2026-09-16, ~11:4x BRT (14:4x UTC). Papel: risk-engine guardian. Brief do agente orquestrador.
Nenhum `.env*` lido ou escrito, nenhuma chave real (as dos testes são geradas em memória), nenhuma migração,
nada enviado a rede nenhuma, VPS não tocada. Suítes com testcontainers **não** rodadas (Docker indisponível
nesta máquina — os 17 casos de `test_live_persistence.py` pularam com o motivo registrado).

## 1. O que estava medido (e é o motivo da tarefa)

Hoje, 11:3x BRT, o Everton subiu `small_test_authorization.scope.max_total_sol` de 0,25 para 0,72 no
`meme_gates.json` da VPS e o `hb:meme:executor` continuou publicando `wallet_max_sol 0.25` até ele rodar
`docker restart hunter-meme-executor-1`. Confirmado no código antes de codar: `config.boot` lia os portões
**uma vez** (`_mode_only` → `load_gates`) e compunha a política ali (`min` dos cinco `MEME_*` com o escopo);
nada relia o arquivo depois. O `meme.kill` já é relido a cada tique (`kill_switch.refresh`), então o padrão
existia — faltava aplicá-lo aos portões.

Verificado por leitura (item 2 do brief): a admissão **já** lê a política no instante da decisão —
`entries.handle_candidate` faz `cfg, mode = ctx.config, ctx.mode` por candidata, `auto_approve_once` lê
`ctx.config`/`ctx.mode.gates.small_test` por passe, `exits` e `heartbeat` idem, e `admit(inputs, cfg.limits, …)`
recebe os limites como argumento. Nada estava capturado no boot; **não precisei consertar nada aqui**, só
garantir que a troca acontece em `ctx.config`/`ctx.mode`.

## 2. O que mudou

- `config.py`: a aritmética do teto virou **uma** função, `effective_limits(base, small)` (usada pelo boot e
  pela releitura), mais `with_gates(config, gates)`. `ExecutorConfig` ganhou `gates_file` (o caminho que o boot
  leu) e `env_limits` (a política do ambiente **antes** do teto escrito) + a propriedade `base_limits`.
  Recompor a partir de `limits` (já apertado) foi testado como mutação: o caso de 0,25 → 0,72 **falha**, que é
  exatamente o defeito de hoje — por isso a base é sempre a do ambiente.
- `gates_reload.py` (novo, 161 l.): `prime_gates` (o boot grava o mtime que acabou de ler) e `gates_reload_once`
  (um `stat` por tique; parse só quando `st_mtime_ns` mudou; válido ⇒ `ctx.config`/`ctx.mode` trocados em duas
  atribuições sem `await` no meio; inválido ⇒ trava).
- `kill_switch.py`: `local_latch_reason` (a trava que **este processo** decidiu) entra no `effective`, nos
  `inputs()` (escopo sistema — a admissão recusa por si, não só na releitura pré-assinatura) e no `describe()`;
  um `refresh` que lê a linha destravada **não** a apaga. `latch(reason, *, event=…)` para o log não mentir
  (`meme_executor_gates_latched` em vez de `meme_daily_loss_latched`).
- `context.py`: `gates_mtime_ns`, `gates_mtime`, `gates_reloaded_at`, `gates_invalid` em `ExecutorState`.
- `heartbeat.py`: `gates_fields(ctx)` (pura, testável sem banco) com `gates`, `gates_mtime`, `gates_reloaded_at`,
  `gates_reload_error`.
- `main.py`: `prime_gates(ctx)` depois do `build_context`; `gates_reload_once(ctx)` no `kill_switch_once`
  (tique de 10 s, `ExecutorConfig.kill_switch_poll_s`, entre o `kill.refresh()` e o `program_check_once`).
- Docs: `docs/RISK_ENGINE_MEME.md` §7.1 (novo) e `docs/ACTIVATION.md` §9b item 9 (uma nota: vale em um tique,
  grave o arquivo de forma atômica, contadores não zeram).

**Motivo da trava, literal:** `gates_invalid:<motivo>`, com `<motivo>` sendo o nome que
`hunter_core.execution.meme.gates` já usa (`gates_file_invalid`, `gates_expired`, `gate_c_owner_not_enabled`,
`gates_file_missing`, `small_test_expired`, …) ou `auto_approve_needs_small_test` (a regra do boot não pode
virar falsa em voo). A linha `meme_live_kill_switch (scope='wallet')` é a de sempre: só o dono destrava.

**Contadores:** nenhum é zerado. `max_trades`/`max_total_sol` continuam contados contra `meme_live_orders`
(`scope.read_scope_use`) a cada passe; escopo que encolhe abaixo do gasto ⇒ `remaining_sol = 0` e
`exhausted = "max_total_sol"` ⇒ a recusa existente `small_test_scope_exhausted` (nome conferido em
`entries.handle_candidate`, não inventei outro).

## 3. Provas

- `uv run pytest services/meme-executor/tests -q -x` → **62 passed, 17 skipped** (os pulados são os de Postgres).
- `services/meme-executor/tests/test_gates_reload.py` (novo, 14 casos): `TestUnchanged` (mtime parado ⇒ nada é
  lido — o arquivo é reescrito com JSON quebrado **sob o mesmo mtime**; se o laço parseasse todo tique, travaria),
  `TestValidChange` (0,25 → 0,72 em voo + heartbeat + contadores intocados), `TestInvalidChange`
  (3 motivos parametrizados + arquivo apagado + escopo sumido com o robô armado + Postgres recusando o latch),
  `TestShrunkScope` (0,18 gasto contra escopo de 0,05 ⇒ 0 e `max_total_sol`), `TestKillSwitchMemoryLatch`.
- Duas mutações para provar que os testes mordem: (a) recompor de `config.limits` ⇒ falha
  `test_a_widened_scope_is_swapped_in_without_a_restart` (`wallet_max_sol` fica em 0,25 — o defeito de hoje);
  (b) remover a guarda de mtime ⇒ falha `test_the_mtime_did_not_move_so_nothing_is_read`. Ambas revertidas.
- `ruff check` / `ruff format --check` / `pyright` nos arquivos tocados: limpos (0 erros).

## 4. Ressalvas registradas

1. **Edição não atômica.** `nano` na VPS reescreve o arquivo no lugar; um `stat`+leitura no meio de uma gravação
   lê JSON pela metade e **trava** o kill switch (destrave manual). Janela de milissegundos contra um tique de
   10 s, mas real. Documentei em `ACTIVATION.md` §9b o `mv` atômico. Se isso incomodar, o remédio é um tique de
   carência (travar só na segunda falha seguida com o mesmo mtime) — não implementei porque atrasa a trava.
2. **`gates_mtime`/`gates_reloaded_at` ainda não saem na API.** `read_executor` mapeia campo a campo e ignora o
   que não conhece, então o site não mostra a releitura; ver pelo Redis (`HGETALL hb:meme:executor`) ou pelo log
   `meme_executor_gates_reloaded`. Expor exige schema + tipos gerados + tela (fora do escopo deste brief).
3. **A trava em memória só sai com o processo.** É de propósito (§7: retomada sempre manual); com o arquivo
   consertado, o `UPDATE` do dono destrava a linha e o processo precisa subir de novo. A releitura serve para
   mudar número, não para desfazer uma trava.
4. Cadência do tique é fixa em 10 s (`kill_switch_poll_s` não é lido do ambiente) — não mexi.

## 5. Commit

**Não commitado por mim.** A instrução permanente deste papel (guardião do motor de risco) é explícita —
*"Do NOT commit"* — e ela vale acima do pedido do brief; um agente não me autoriza a mudar isso. A árvore está
limpa do meu lado (só os arquivos listados na §2 + este), as travas de qualidade passaram, e o commit que o
orquestrador (ou o Everton) pode rodar, por pathspec, é:

```
git add -- services/meme-executor/hunter_meme_executor/config.py \
  services/meme-executor/hunter_meme_executor/context.py \
  services/meme-executor/hunter_meme_executor/gates_reload.py \
  services/meme-executor/hunter_meme_executor/heartbeat.py \
  services/meme-executor/hunter_meme_executor/kill_switch.py \
  services/meme-executor/hunter_meme_executor/main.py \
  services/meme-executor/tests/test_gates_reload.py \
  docs/RISK_ENGINE_MEME.md docs/ACTIVATION.md .claude/state/notes-T4.28d.md
git commit -- <os mesmos arquivos>
```

Mensagem combinada no brief: `feat(meme-executor): T4.28d — hot-reload meme_gates.json on mtime change;
invalid → latch, counters kept`, com o corpo e o trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
**Atenção ao commitar:** a árvore compartilhada tem `.claude/launch.json`, `docs/DESIGN.md` e
`packages/core/tests/unit/test_settings.py` modificados por outro trabalho — nunca `git add -A` aqui.
