# Notas T4.70 — assinar no instante do `create` (EXP-M19, P0)

Data: 2026-09-19. Escopo: `services/meme-worker/hunter_meme_worker/{event_gate_subscriptions,
event_state,event_gate_eval,event_gate_stats,context,discovery,main}.py`, testes novos/estendidos
em `services/meme-worker/tests/{test_event_gate_notify,test_event_state,test_event_gate_stats,
test_discovery_event_gate_create,test_event_gate_crowd_integration,test_event_gate_integration}.py`,
`docs/RISK_ENGINE_MEME.md` §9, `obsidian/05-EXPERIMENTS/EXP-M19-subida-com-gente-atras.md`.
`services/meme-worker/hunter_meme_worker/executor` (o pacote de execução) não tocado.

## 1. O problema (notes-T4.66.md §7, P0 da EXP-M19)

`event_gate_subscriptions.sync_subscriptions` só assinava a cada `subscription_sync_s` (5 s) sobre
`fast_lane.young_mints`; um sniper compra em 1–2 s. A maioria dos mints entrava rastreado **depois**
do próprio `create`, então `MintEventState.covered_since` (= `subscribed_at`) ficava fora da graça
de 5 s de `covered_from_birth`, e `crowd.py` recusava `not_covered_from_birth` ⇒
`early_retention_unknown` — a porta media a própria cegueira, não a multidão.

## 2. A fiação entregue

- `event_gate_subscriptions.subscribe_at_create(rt, event, *, now=None)` (novo): mesma PDA
  (`bonding_curve_address`), mesmo `_subscribe_mint` (que ganhou um parâmetro `now` opcional para
  não depender de `utcnow()` interno — sem isso o teste não conseguiria travar `subscribed_at` perto
  de `event.received_at`), mesmo teto `max_mints`, mesma guarda `mint in rt.subs` que
  `sync_subscriptions` já usa — as duas pistas nunca assinam duas vezes o mesmo mint, em qualquer
  ordem. Marca `state.expects_create_slot = True` e `creation_block_buyers = {event.creator}`;
  mede `create_to_subscribe_ms` = `(now − event.received_at)` e conta em
  `EventGateStats.subscribed_at_create_total`.
- `discovery._handle` chama `subscribe_at_create(ctx.event_gate, event, now=utcnow())` para todo
  `NormalizedMemeTokenCreated`, **no mesmo lugar e independente** de `launch_lane_on_create`
  (T4.67a) — nunca aguardado por nada a jusante, nunca levanta para dentro do laço. `off` (
  `ctx.event_gate is None`, o padrão quando `MEME_EVENT_GATE=off`) não chama nada, como já valia
  para a pista de lançamento.
- `RadarContext.event_gate: EventGateRuntime | None = None` (novo campo) — mas `RadarContext` é
  `frozen=True`/`slots=True` e é construído **antes** de o portão de evento existir (`main.py`: o
  portão precisa de `ctx.tracker`/`ctx.chain` via `LabContext`, que por sua vez precisa de `ctx` já
  pronto). Resolvido com `context.attach_event_gate(ctx, event_gate)` — `object.__setattr__` num
  ponto único, documentado, chamado uma vez em `main.py` logo depois de `build_event_gate`, antes do
  `TaskGroup` abrir (nenhuma tarefa lê `ctx.event_gate` antes disso). Alternativa descartada: passar
  `event_gate` como parâmetro extra de `run_discovery`/`_handle` em vez de um campo do contexto —
  rejeitada porque quebraria a doutrina do próprio módulo ("Everything a loop is allowed to reach ...
  built once, in `main`") sem necessidade.
- `MintEventState.expects_create_slot`/`creation_block_buyers` (novos campos). `apply_trade`: se
  `expects_create_slot` e `crowd.create_slot` ainda `None`, a **primeira** notificação de trade dá o
  slot (a suposição só é segura quando a cobertura começou no próprio `create` — um mint que a
  sincronização periódica pegou depois nunca marca `expects_create_slot`, então nunca infere um slot
  errado a partir de um trade arbitrário). Toda compra no mesmo slot do `create_slot` entra em
  `creation_block_buyers` (o criador já está lá desde `subscribe_at_create`). O `create_slot`
  aprendido é escrito em `crowd.create_slot` **antes** do `crowd.push` daquele mesmo trade, para a
  regra dos 3 slots (T4.66, já implementada, nunca antes exercitada) valer já na primeira admissão.
- `event_gate_eval.evaluate_mint`: conta `record_early_retention_unknown` quando a `GateRow` julgada
  tem `early_retention_pct is None` — o denominador é o mesmo `evaluations_window` de 60 s de sempre.
- `event_gate_stats.py`: três campos/heartbeat novos — `subscribed_at_create_total`,
  `create_to_subscribe_ms` (deque, `_p50`/`_p95` via `percentile`, mesmo padrão de
  `event_to_proposal_s`), `early_retention_unknown_window` → `early_retention_unknown_share_60s`
  (string vazia sem nada julgado, nunca um `0` que leia como medição).

## 3. Por que `creation_block_buyers` não alimenta `crowd.py` diretamente

`crowd.CrowdLedger._admits_early` já lê `self.create_slot` sozinho — bastava preencher esse campo.
`creation_block_buyers` é só auditoria em `MintEventState` (quem comprou no bloco da criação,
criador incluído), não um segundo caminho de decisão; nenhum set hoje o lê. Documentado como tal no
docstring do campo para a próxima tarefa não duplicar a lógica.

## 4. Testes

- `test_event_gate_notify.py` (+3): `subscribe_at_create` assina na mesma execução (
  `subscribed_at ≤ received_at + poucos ms`, `covered_from_birth`, `expects_create_slot`,
  `creation_block_buyers == {creator}`); dedupe com `sync_subscriptions` nas duas ordens; teto
  `max_mints` respeitado (o segundo `create` não assina, `subscribed_at_create_total` não conta).
- `test_event_state.py` (+2, puro): a primeira notificação de trade define `crowd.create_slot`
  (nunca uma posterior); o criador nunca entra em `early_wallets`; um mint sem `expects_create_slot`
  (a sincronização periódica) nunca infere slot algum.
- `test_event_gate_stats.py` (novo, 4 casos): os três campos de heartbeat, incluindo os dois casos
  "nada medido ainda" (`""`, nunca `0`).
- `test_discovery_event_gate_create.py` (novo, 2 casos): `_handle` chama o gancho quando
  `ctx.event_gate` existe (com o mint certo) e não chama nada quando é `None` (`MEME_EVENT_GATE=off`).
- `test_event_gate_crowd_integration.py` (+1, Postgres real): `subscribe_at_create` (com um pubkey
  real, `b58encode(os.urandom(32))` — a PDA de verdade é derivada) seguido de um `create`-buy do
  criador (slot 100, aprende `create_slot`) e nove compradores nos slots 100–102, cada um vendendo
  10 % 10 s antes de `as_of` ⇒ `row.early_retention_pct == Decimal("0.9")`, nunca
  `early_retention_unknown`. `test_event_gate_integration._rt` ganhou um parâmetro `ws` opcional
  (default `None`, como antes) só para este teste poder passar um `_FakeWs` local.

## 5. Comandos

- `uv run pytest services/meme-worker/tests/test_event_gate_stats.py test_event_state.py
  test_event_gate_notify.py test_discovery_event_gate_create.py -q` → 27 passed (3,7 s).
- `uv run pytest services/meme-worker/tests -q -m "not live and not integration"` → 457 passed,
  110 deselected (era 446 antes desta tarefa + os novos).
- `uv run pytest services/meme-worker/tests/test_event_gate_integration.py
  test_event_gate_crowd_integration.py -q` → 10 passed (~39 s).
- `uv run pytest services/meme-worker/tests -q -m "integration and not live"
  --ignore=.../test_event_gate_integration.py --ignore=.../test_event_gate_crowd_integration.py`
  (a suíte de integração pré-existente): `exit code 0`, sem falhas (saída em pontos, contagem exata
  não capturada, mas confirma zero regressões — inclusive na mudança de assinatura de `_rt` em
  `test_event_gate_integration.py`, que ganhou um parâmetro `ws` opcional default `None`).
- `uv run ruff check`/`format --check` em `services/meme-worker/`: limpos (0 erros, 195 arquivos
  formatados). `uv run pyright` nos arquivos tocados: 0 erros (dois achados corrigidos no caminho —
  `reportUnnecessaryComparison` em `event_state.py`, já que `NormalizedCurveTrade.slot` é `int` não
  opcional; `reportPrivateUsage` em `test_discovery_event_gate_create.py`, resolvido com o mesmo
  `# pyright: reportPrivateUsage=false` que `test_discovery_bonding_curve_metric.py` já usa).
- `uv run python infra/scripts/check_file_size.py` → `1004 files; 0 over budget` (nenhum arquivo
  tocado passou de 350 linhas; o maior é `event_state.py`, 334).

## 6. Concerns

- A fração `early_retention_unknown_share_60s` só existe enquanto o processo está de pé (não é uma
  série persistida) — a leitura de 24 h que o P0 da EXP-M19 pede continua vindo de
  `meme_lab_ticks.refusals` por nome (como já registrado em notes-T4.66.md §7); o heartbeat é o
  número ao vivo, não o substituto do agregado histórico.
- Não medi ao vivo (mainnet) o `create_to_subscribe_ms` real — só a mecânica determinística dos
  testes (`now` passado explicitamente). O número de produção só aparece depois do deploy com
  `MEME_EVENT_GATE=shadow`.
- `object.__setattr__` em `context.attach_event_gate` é o escape documentado para o ciclo de
  construção (`RadarContext` frozen, o portão de evento precisa de `ctx` antes de existir) — vale
  revisão de quem aceitar o braço, é o único ponto do módulo que faz isso.
