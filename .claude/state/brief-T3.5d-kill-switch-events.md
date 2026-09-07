# Brief T3.5d — `kill_switch.changed`: um formato, uma publicação, e a retomada pela API chega ao stream

**Owner:** backend-specialist. **Revisor depois:** risk-engine-guardian (leitura). **Não commitar.** **Regra operacional: nunca Bash em background; comandos em primeiro plano com timeout ≤ 5 min; suítes com testcontainers por arquivo; Astra indisponível até 2026-09-12.** Despachar **depois** da T3.5c commitada (mesmos arquivos).

Origem: plantão da Sexta-feira 2026-09-07 (manhã) + confirmação do orquestrador no código.

## Dois achados
1. **Publicação dupla com dois formatos.** `services/execution-worker/hunter_execution_worker/mtm.py` chama `evaluate_and_persist(..., publish=True)` — o core enfileira em `packages/core/hunter_core/risk/transitions.py` (`record_transition`) um evento `{scope, scope_id, organization_id, from_state, to_state, reason, actor_type, evidence}` com `event_id = transition_id` — e, se `evaluation.changed`, chama ainda `events.publish_kill_switch` (segundo evento, `{event, organization_id, portfolio_id, scope, previous, state, effective, reason, ts}`). Um consumidor recebe dois eventos por transição, em formatos diferentes.
   **Decisão:** fica **só o do core** (mesma transação da latch, idempotente por `transition_id`). Remover a chamada em `mtm.py` (manter o `logger.warning("kill_switch_moved")`); `events.publish_kill_switch` some ou vira delegação. Verificar consumidores (`apps/api` realtime/SSE, `apps/web`): se algum lê o formato do worker, adaptar o **consumidor** ao formato do core. `docs/PIPELINE.md`: formato único documentado.
2. **Retomada pela API nunca chega ao stream.** `apps/api/hunter_api/routers/risk.py` chama `resume()` com `publish=False` porque a 0007 nega `INSERT` em `outbox_events` ao `hunter_app` (correto). O adendo do brief T3.5 (item 4) mandava o worker publicar "ao processar uma retomada" — não foi entregue.
   **Entregar:** no ciclo do kill switch (10 s), o worker lê as `kill_switch_transitions` de escopo portfolio com `actor_type='user'` ainda não publicadas e enfileira `kill_switch.changed` no formato do core com `event_id = transition_id` (o `enqueue` com id existente é no-op → sem cursor em memória; se o outbox for podado, usar um marcador durável — decidir e documentar). Sem tocar em `packages/core/hunter_core/risk/**` nem `apps/api/**`.

## Provar (testcontainers, `services/execution-worker/tests/**`)
- Transição automática → **exatamente um** evento no outbox, formato do core.
- Resume gravado como `hunter_app` (transição `user`, outbox vazio) → primeiro ciclo enfileira um evento; segundo ciclo, nenhum; processo morto entre a leitura e o `enqueue` → ainda um só.
- Consumidor da API (se existir) processa o formato do core.
Relatório em português no formato estendido com saída real; `.claude/state/notes-T3.5.md` seção nova.
